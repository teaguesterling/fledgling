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
    defs AS (
        SELECT
            file_path,
            name,
            node_id,
            semantic_type,
            semantic_type_to_string(semantic_type) AS kind,
            start_line,
            descendant_count,
            end_line - start_line + 1 AS lines
        FROM ast
        WHERE is_definition(semantic_type)
          AND depth <= 2
          AND name != ''
    ),
    -- Inline cyclomatic calculation (mirrors code_structure and
    -- complexity_hotspots). The previous version passed the `ast` CTE
    -- to ast_function_metrics(), which worked in older sitting_duck but
    -- fails in 908927e where ast_function_metrics(source, language)
    -- treats its first argument as a file-pattern string and tries to
    -- open "ast" as a directory.
    func_complexity AS (
        SELECT
            d.node_id,
            count(CASE WHEN is_conditional(n.semantic_type)
                AND (n.type LIKE '%_statement' OR n.type LIKE '%_clause'
                     OR n.type LIKE '%_expression' OR n.type LIKE '%_arm'
                     OR n.type LIKE '%_case' OR n.type LIKE '%_branch')
                THEN 1 END) AS conditionals,
            count(CASE WHEN is_loop(n.semantic_type)
                AND (n.type LIKE '%_statement' OR n.type LIKE '%_expression'
                     OR n.type LIKE '%_loop')
                THEN 1 END) AS loops
        FROM defs d
        JOIN ast n ON n.node_id > d.node_id
                  AND n.node_id <= d.node_id + d.descendant_count
        WHERE is_function_definition(d.semantic_type)
        GROUP BY d.node_id
    )
    SELECT
        d.file_path,
        d.name,
        d.kind,
        d.lines,
        CASE WHEN is_function_definition(d.semantic_type)
             THEN COALESCE(fc.conditionals + fc.loops + 1, 1)
             ELSE 0 END AS cyclomatic,
        c.status AS change_status
    FROM defs d
    JOIN changed c ON suffix(d.file_path, '/' || c.file_path)
                   OR d.file_path = c.file_path
    LEFT JOIN func_complexity fc ON d.node_id = fc.node_id
    ORDER BY cyclomatic DESC, d.file_path, d.start_line;
