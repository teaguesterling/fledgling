-- Fledgling: Source Retrieval Macros (read_lines)
--
-- Thin wrappers around read_lines that provide convenient interfaces
-- for the common file-reading patterns agents use most.
--
-- NOTE: sitting_duck#22 (read_lines shadowing) is fixed in DuckDB 1.4.4+.
-- The DROP MACRO TABLE workaround is no longer needed.

-- read_source: Read lines from a file with optional line selection and filtering.
-- This is the primary replacement for cat/head/tail bash commands.
-- Use match to filter lines by case-insensitive substring match.
-- Raises IO Error if the file does not exist (read_lines fix in DuckDB 1.5.1).
--
-- Examples:
--   SELECT * FROM read_source('src/main.py');
--   SELECT * FROM read_source('src/main.py', '10-20');
--   SELECT * FROM read_source('src/main.py', '42 +/-5');
--   SELECT * FROM read_source('src/main.py', match := 'import');
CREATE OR REPLACE MACRO read_source(file_path, lines := NULL, ctx := 0, match := NULL) AS TABLE
    SELECT line_number, content
    FROM (
        SELECT
            line_number,
            content,
            max(CASE WHEN content ILIKE '%' || match || '%' THEN 1 ELSE 0 END)
                OVER (
                    ORDER BY line_number
                    ROWS BETWEEN ctx PRECEDING AND ctx FOLLOWING
                ) AS near_match
        FROM read_lines(file_path, lines, context := ctx)
    )
    WHERE match IS NULL OR near_match > 0;

-- read_source_text: Formatted text output for read_source with line numbers.
-- Handles git revision dispatch: if commit is provided, reads from git via
-- git_uri(); otherwise reads from the working tree.
-- Requires duck_tails (for git_uri) — always available via fledgling.connect().
--
-- Examples:
--   SELECT * FROM read_source_text('src/main.py');
--   SELECT * FROM read_source_text('README.md', lines := '1-20');
--   SELECT * FROM read_source_text('README.md', commit := 'HEAD~1');
CREATE OR REPLACE MACRO read_source_text(
    file_path,
    lines := NULL,
    ctx := 0,
    match := NULL,
    commit := NULL
) AS TABLE
    SELECT printf('%4d  %s', line_number, content) AS line
    FROM read_source(
        CASE WHEN commit IS NULL
             THEN file_path
             -- git_uri() prepends the repo root, so it needs a repo-relative
             -- path. file_path may already be absolutized by _resolve() in the
             -- tool wrapper; strip the root prefix to avoid doubling it.
             ELSE git_uri(
                 _session_root(),
                 CASE WHEN starts_with(file_path, _session_root() || '/')
                      THEN substr(file_path, length(_session_root()) + 2)
                      ELSE file_path END,
                 commit
             )
        END,
        lines, ctx, match
    );

-- read_source_batch: Like read_source but includes file_path column
-- for multi-file batch reads via glob patterns.
--
-- Examples:
--   SELECT * FROM read_source_batch('src/**/*.py', '1-10');
CREATE OR REPLACE MACRO read_source_batch(file_pattern, lines := NULL, ctx := 0) AS TABLE
    SELECT
        file_path,
        line_number,
        content
    FROM read_lines(file_pattern, lines, context := ctx);

-- read_context: Read lines centered around a specific line number.
-- Optimized for error investigation — show context around a location.
--
-- Examples:
--   SELECT * FROM read_context('src/main.py', 42);
--   SELECT * FROM read_context('src/main.py', 42, 10);
CREATE OR REPLACE MACRO read_context(file_path, center_line, ctx := 5) AS TABLE
    SELECT
        line_number,
        content,
        line_number = center_line AS is_center
    FROM read_lines(file_path, center_line, context := ctx);

-- file_line_count: Get line counts for files matching a pattern.
--
-- Examples:
--   SELECT * FROM file_line_count('src/**/*.py');
CREATE OR REPLACE MACRO file_line_count(file_pattern) AS TABLE
    SELECT
        file_path,
        max(line_number) AS line_count
    FROM read_lines(file_pattern)
    GROUP BY file_path
    ORDER BY line_count DESC;

-- list_files: List files matching a pattern.
-- Filesystem mode uses glob syntax; git mode uses SQL LIKE syntax.
-- Uses query() for dynamic dispatch so git functions (duck_tails) are only
-- resolved at runtime when commit is provided.
--
-- Examples:
--   SELECT * FROM list_files('src/**/*.py');
--   SELECT * FROM list_files('sql/%', 'HEAD');
CREATE OR REPLACE MACRO list_files(pattern, commit := NULL) AS TABLE
    SELECT * FROM query(
        CASE WHEN commit IS NULL
             THEN 'SELECT file AS file_path FROM glob(''' || replace(pattern, '''', '''''') || ''') ORDER BY file_path'
             ELSE 'SELECT file_path FROM git_tree(''.'', ''' || replace(commit, '''', '''''') || ''') WHERE file_path LIKE ''' || replace(pattern, '''', '''''') || ''' ORDER BY file_path'
        END
    );

-- _is_vendored_path: TRUE when a path lives in a dependency, build, cache, VCS,
-- or checked-in third-party tree that should be excluded from project
-- discovery. Used by source_files / project_overview (and reused by squackit's
-- AST tools) so the "what to ignore" policy has a single home in fledgling.
-- Pattern-based, so it catches checked-in vendored trees (googletest,
-- third_party, vendor) that git-awareness alone misses. Submodules are handled
-- separately by _submodule_prefixes since their directory names are arbitrary.
CREATE OR REPLACE MACRO _is_vendored_path(file_path) AS (
       file_path LIKE '%/.git/%'
    OR file_path LIKE '%/.svn/%'
    OR file_path LIKE '%/.hg/%'
    OR file_path LIKE '%/.venv/%'
    OR file_path LIKE '%/venv/%'
    OR file_path LIKE '%/node_modules/%'
    OR file_path LIKE '%/bower_components/%'
    OR file_path LIKE '%/__pycache__/%'
    OR file_path LIKE '%/.mypy_cache/%'
    OR file_path LIKE '%/.pytest_cache/%'
    OR file_path LIKE '%/.ruff_cache/%'
    OR file_path LIKE '%/.tox/%'
    OR file_path LIKE '%/.idea/%'
    OR file_path LIKE '%/.vscode/%'
    OR file_path LIKE '%/dist/%'
    OR file_path LIKE '%/build/%'
    OR file_path LIKE '%/_build/%'
    OR file_path LIKE '%/cmake-build-%/%'
    OR file_path LIKE '%/CMakeFiles/%'
    OR file_path LIKE '%-prefix/%'
    OR file_path LIKE '%/.eggs/%'
    OR file_path LIKE '%.egg-info/%'
    -- checked-in third-party / vendored trees (not git-distinguishable)
    OR file_path LIKE '%/vendor/%'
    OR file_path LIKE '%/third_party/%'
    OR file_path LIKE '%/third-party/%'
    OR file_path LIKE '%/External/%'
    OR file_path LIKE '%/googletest%'
);

-- _submodule_prefixes: directory prefixes (root-absolute, trailing slash) of any
-- git submodules declared in root/.gitmodules. Empty when there are no submodules
-- or the directory is not a git repo — read_lines(..., ignore_errors := true)
-- yields no rows instead of an IO error on a missing .gitmodules. This is the
-- git-aware half of the ignore policy: submodule contents are not gitignored and
-- carry arbitrary names (e.g. duckdb/, rdkit/), so only .gitmodules identifies them.
--
-- Examples:
--   SELECT * FROM _submodule_prefixes('/path/to/repo');
CREATE OR REPLACE MACRO _submodule_prefixes(root := '.') AS TABLE
    SELECT DISTINCT rtrim(root, '/') || '/' ||
           trim(regexp_extract(content, 'path[ \t]*=[ \t]*(\S.*)', 1)) || '/' AS prefix
    FROM read_lines(rtrim(root, '/') || '/.gitmodules', ignore_errors := true)
    WHERE regexp_matches(content, 'path[ \t]*=[ \t]*\S');

-- source_files: List a project's own source files, excluding vendored, build,
-- cache, and submodule trees. This is the filtered discovery surface — prefer it
-- over raw list_files/glob when you want "the project's code" rather than
-- "every file on disk". Combines a pattern denylist (_is_vendored_path) with
-- git-submodule exclusion (_submodule_prefixes). Pass include_ignored := true to
-- get the unfiltered glob (the same set as list_files).
--
-- Examples:
--   SELECT * FROM source_files('.');
--   SELECT * FROM source_files('/path/to/repo', '**/*.py');
--   SELECT * FROM source_files('.', '**/*', include_ignored := true);
CREATE OR REPLACE MACRO source_files(root := '.', pattern := '**/*', include_ignored := false) AS TABLE
    SELECT file AS file_path
    FROM glob(rtrim(root, '/') || '/' || pattern)
    WHERE include_ignored
       OR (NOT _is_vendored_path(file)
           AND NOT EXISTS (
               SELECT 1 FROM _submodule_prefixes(root) s
               WHERE file LIKE s.prefix || '%'
           ))
    ORDER BY file_path;

-- project_overview: Summarize project contents by file type.
-- Groups files by extension and maps to language names, giving a quick
-- overview of what a project contains. By default excludes vendored, build,
-- cache, and git-submodule trees (via source_files) so the summary reflects
-- the project's own code rather than its dependencies. Pass
-- include_ignored := true to count everything on disk.
--
-- Examples:
--   SELECT * FROM project_overview('/path/to/project');
--   SELECT * FROM project_overview('.');
--   SELECT * FROM project_overview('.', include_ignored := true);
CREATE OR REPLACE MACRO project_overview(root := '.', include_ignored := false) AS TABLE
    SELECT
        CASE extension
            WHEN 'py' THEN 'Python'
            WHEN 'pyi' THEN 'Python'
            WHEN 'js' THEN 'JavaScript'
            WHEN 'jsx' THEN 'JavaScript'
            WHEN 'mjs' THEN 'JavaScript'
            WHEN 'ts' THEN 'TypeScript'
            WHEN 'tsx' THEN 'TypeScript'
            WHEN 'sql' THEN 'SQL'
            WHEN 'rs' THEN 'Rust'
            WHEN 'go' THEN 'Go'
            WHEN 'java' THEN 'Java'
            WHEN 'rb' THEN 'Ruby'
            WHEN 'sh' THEN 'Shell'
            WHEN 'bash' THEN 'Shell'
            WHEN 'zsh' THEN 'Shell'
            WHEN 'md' THEN 'Markdown'
            WHEN 'json' THEN 'JSON'
            WHEN 'yaml' THEN 'YAML'
            WHEN 'yml' THEN 'YAML'
            WHEN 'toml' THEN 'TOML'
            WHEN 'html' THEN 'HTML'
            WHEN 'css' THEN 'CSS'
            WHEN 'c' THEN 'C'
            WHEN 'cpp' THEN 'C++'
            WHEN 'cc' THEN 'C++'
            WHEN 'h' THEN 'C/C++'
            WHEN 'hpp' THEN 'C/C++'
            WHEN 'txt' THEN 'Text'
            WHEN 'xml' THEN 'XML'
            WHEN '' THEN '(other)'
            ELSE extension
        END AS language,
        extension,
        count(*) AS file_count
    FROM (
        SELECT
            lower(regexp_extract(file_path, '\.([^./]+)$', 1)) AS extension
        FROM source_files(root, '**/*', include_ignored := include_ignored)
    )
    GROUP BY ALL
    ORDER BY file_count DESC;

-- read_as_table: Preview structured data files as tables.
-- Auto-detects format from extension: CSV, TSV, JSON, JSONL, Parquet.
-- Rejects source code files (detected via sitting_duck's supported languages
-- mapped to common file extensions). Use ReadLines or read_source instead.
-- Uses query() for dynamic dispatch. Avoids query_table() which conflicts
-- with Python's json module in DuckDB's replacement scan.
--
-- Supported formats (built-in):
--   .csv, .tsv      — read_csv_auto
--   .json, .jsonl   — read_json_auto
--   .parquet, .pq   — read_parquet
--
-- Unknown extensions fall back to read_csv_auto.
--
-- Examples:
--   SELECT * FROM read_as_table('data.csv');
--   SELECT * FROM read_as_table('results.json', 10);
--   SELECT * FROM read_as_table('output.parquet');
CREATE OR REPLACE MACRO _is_code_file(file_path) AS
    regexp_extract(file_path, '\.([^.]+)$', 1) IN (
        'py', 'js', 'ts', 'tsx', 'jsx', 'mjs', 'cjs',
        'rs', 'go', 'java', 'c', 'cpp', 'cc', 'h', 'hpp', 'hh',
        'rb', 'php', 'swift', 'kt', 'kts',
        'sh', 'bash', 'zsh', 'fish',
        'sql', 'r', 'cs', 'dart', 'zig', 'lua',
        'toml', 'yaml', 'yml',
        'html', 'css', 'scss', 'less',
        'md', 'graphql', 'hcl', 'tf',
        'makefile', 'cmake', 'dockerfile'
    );

CREATE OR REPLACE MACRO read_as_table(file_path, lim := 100) AS TABLE
    SELECT * FROM query(
        CASE WHEN _is_code_file(file_path)
             THEN 'SELECT ''' || replace(file_path, '''', '''''') || ' is a source code file. Use ReadLines or read_source() instead.'' AS error'
             WHEN file_path LIKE '%.json' OR file_path LIKE '%.jsonl'
             THEN 'SELECT * FROM read_json_auto(''' || replace(file_path, '''', '''''') || ''') LIMIT ' || CAST(lim AS VARCHAR)
             WHEN file_path LIKE '%.parquet' OR file_path LIKE '%.pq'
             THEN 'SELECT * FROM read_parquet(''' || replace(file_path, '''', '''''') || ''') LIMIT ' || CAST(lim AS VARCHAR)
             ELSE 'SELECT * FROM read_csv_auto(''' || replace(file_path, '''', '''''') || ''') LIMIT ' || CAST(lim AS VARCHAR)
        END
    );
