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
--
-- Examples:
--   SELECT * FROM read_source('src/main.py');
--   SELECT * FROM read_source('src/main.py', '10-20');
--   SELECT * FROM read_source('src/main.py', '42 +/-5');
--   SELECT * FROM read_source('src/main.py', match := 'import');
CREATE OR REPLACE MACRO read_source(file_path, lines := NULL, ctx := 0, match := NULL) AS TABLE
    SELECT
        line_number,
        content
    FROM read_lines(file_path, lines, context := ctx)
    WHERE match IS NULL OR content ILIKE '%' || match || '%';

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

-- read_as_table: Preview structured data files (CSV, JSON) as tables.
-- Uses query() for dynamic dispatch between read_csv_auto and read_json_auto
-- based on file extension. Avoids query_table() which conflicts with Python's
-- json module in DuckDB's replacement scan.
--
-- Examples:
--   SELECT * FROM read_as_table('data.csv');
--   SELECT * FROM read_as_table('data.json', 10);
CREATE OR REPLACE MACRO read_as_table(file_path, lim := 100) AS TABLE
    SELECT * FROM query(
        CASE WHEN file_path LIKE '%.json' OR file_path LIKE '%.jsonl'
             THEN 'SELECT * FROM read_json_auto(''' || replace(file_path, '''', '''''') || ''') LIMIT ' || CAST(lim AS VARCHAR)
             ELSE 'SELECT * FROM read_csv_auto(''' || replace(file_path, '''', '''''') || ''') LIMIT ' || CAST(lim AS VARCHAR)
        END
    );
