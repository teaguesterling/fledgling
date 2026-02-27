-- Source Sextant: Source Retrieval Macros (read_lines)
--
-- Thin wrappers around read_lines that provide convenient interfaces
-- for the common file-reading patterns agents use most.
--
-- NOTE: sitting_duck defines a read_lines() table macro that shadows the
-- read_lines extension. When both are loaded, the caller must drop
-- sitting_duck's macro first: DROP MACRO TABLE IF EXISTS read_lines;
-- See: https://github.com/teaguesterling/sitting_duck/issues/22

-- list_files: List files matching a glob pattern.
-- Uses shell glob syntax (*.sql, src/**/*.py).
--
-- Git mode (listing files at a revision) is handled by the tool
-- layer using git_tree() from duck_tails, not this macro.
--
-- Examples:
--   SELECT * FROM list_files('src/*.py');
--   SELECT * FROM list_files('sql/**/*.sql');
CREATE OR REPLACE MACRO list_files(pattern) AS TABLE
    SELECT file AS file_path
    FROM glob(pattern)
    ORDER BY file_path;

-- read_source: Read lines from a file with optional line selection
-- and pattern matching. This is the primary replacement for
-- cat/head/tail bash commands.
--
-- The file_path can be a local path or a git_uri() for reading
-- files at specific revisions (requires duck_tails extension).
-- Git dispatch is handled by the tool layer, not this macro.
--
-- Examples:
--   SELECT * FROM read_source('src/main.py');
--   SELECT * FROM read_source('src/main.py', '10-20');
--   SELECT * FROM read_source('src/main.py', '42 +/-5');
--   SELECT * FROM read_source('src/main.py', match := 'import');
--   SELECT * FROM read_source('src/main.py', '1-20', match := 'def');
CREATE OR REPLACE MACRO read_source(file_path, lines := NULL, ctx := 0,
                                     match := NULL) AS TABLE
    SELECT
        line_number,
        content
    FROM read_lines(file_path, lines, context := ctx)
    WHERE match IS NULL OR content ILIKE '%' || match || '%';

-- read_source_numbered: Like read_source but includes file_path column
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

-- read_as_table: Read a data file (CSV, JSON, Parquet, etc.) as a table
-- using DuckDB's auto-detection via replacement scan.
--
-- Examples:
--   SELECT * FROM read_as_table('data.csv');
--   SELECT * FROM read_as_table('results.json', 10);
CREATE OR REPLACE MACRO read_as_table(file_path, lim := 100) AS TABLE
    SELECT * FROM query_table(file_path) LIMIT lim;
