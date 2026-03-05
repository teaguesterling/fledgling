-- Fledgling: Structural Analysis Macros (sitting_duck + duck_tails)
--
-- Cross-tier macros combining AST analysis with git repository state.
-- Must load AFTER both sitting_duck and duck_tails extensions.

-- structural_diff: Compare definitions between two revisions of a file.
-- Shows which functions/classes were added, removed, or modified, with
-- complexity change signals (descendant_count, children_count).
--
-- Uses read_ast with git:// URIs to parse both revisions. Identity is
-- (name, semantic_type) — line number shifts from unrelated edits do not
-- count as modifications. Change detection uses descendant_count and
-- children_count from the AST, which reflect structural complexity
-- independent of formatting.
--
-- Requires: sitting_duck with git:// URI support (sitting_duck#48).
--
-- Examples:
--   SELECT * FROM structural_diff('src/main.py', 'HEAD~1', 'HEAD');
--   SELECT * FROM structural_diff('lib/parser.py', 'main', 'feature-branch');
CREATE OR REPLACE MACRO structural_diff(file, from_rev, to_rev, repo := '.') AS TABLE
    WITH from_defs AS (
        SELECT
            name,
            semantic_type,
            semantic_type_to_string(semantic_type) AS kind,
            end_line - start_line + 1 AS line_count,
            descendant_count,
            children_count
        FROM read_ast(git_uri(repo, file, from_rev))
        WHERE is_definition(semantic_type)
          AND depth <= 2
          AND name != ''
    ),
    to_defs AS (
        SELECT
            name,
            semantic_type,
            semantic_type_to_string(semantic_type) AS kind,
            end_line - start_line + 1 AS line_count,
            descendant_count,
            children_count
        FROM read_ast(git_uri(repo, file, to_rev))
        WHERE is_definition(semantic_type)
          AND depth <= 2
          AND name != ''
    )
    SELECT
        COALESCE(t.name, f.name) AS name,
        COALESCE(t.kind, f.kind) AS kind,
        CASE
            WHEN f.name IS NULL THEN 'added'
            WHEN t.name IS NULL THEN 'removed'
            WHEN t.descendant_count != f.descendant_count
              OR t.children_count != f.children_count THEN 'modified'
            ELSE 'unchanged'
        END AS change,
        f.line_count AS old_lines,
        t.line_count AS new_lines,
        f.descendant_count AS old_complexity,
        t.descendant_count AS new_complexity,
        COALESCE(t.descendant_count::INT, 0)
            - COALESCE(f.descendant_count::INT, 0) AS complexity_delta
    FROM to_defs t
    FULL OUTER JOIN from_defs f
        ON t.name = f.name AND t.semantic_type = f.semantic_type
    WHERE change != 'unchanged'
    ORDER BY change, name;

-- changed_function_summary: Functions in files that changed between two revisions,
-- with complexity metrics. Answers "what functions should I review for this change?"
--
-- Uses file_changes (duck_tails) to identify modified/added files, then
-- read_ast to parse their current content and extract function metrics.
-- Sorted by cyclomatic complexity so the riskiest functions surface first.
--
-- Unlike structural_diff (which shows what changed within a function),
-- this shows all functions in changed files — a broader review surface.
--
-- The file_pattern parameter scopes which files to AST-parse (e.g. '**/*.py').
-- Only files matching BOTH the pattern AND the changed file list are included.
--
-- Examples:
--   SELECT * FROM changed_function_summary('HEAD~1', 'HEAD', '**/*.py');
--   SELECT * FROM changed_function_summary('main', 'feature', 'src/**/*.py');
CREATE OR REPLACE MACRO changed_function_summary(from_rev, to_rev, file_pattern, repo := '.') AS TABLE
    WITH changed AS (
        SELECT file_path, status
        FROM file_changes(from_rev, to_rev, repo)
        WHERE status IN ('added', 'modified')
    ),
    ast AS (
        SELECT * FROM read_ast(file_pattern)
    ),
    metrics AS (
        SELECT * FROM ast_function_metrics(ast)
    ),
    defs AS (
        SELECT
            file_path,
            name,
            semantic_type_to_string(semantic_type) AS kind,
            start_line,
            end_line - start_line + 1 AS lines
        FROM ast
        WHERE is_definition(semantic_type)
          AND depth <= 2
          AND name != ''
    )
    SELECT
        d.file_path,
        d.name,
        d.kind,
        d.lines,
        COALESCE(m.cyclomatic, 0) AS cyclomatic,
        c.status AS change_status
    FROM defs d
    JOIN changed c ON suffix(d.file_path, '/' || c.file_path)
                   OR d.file_path = c.file_path
    LEFT JOIN metrics m ON d.file_path = m.file_path AND d.name = m.name
    ORDER BY COALESCE(m.cyclomatic, 0) DESC, d.file_path, d.start_line;
