-- Fledgling: Source Retrieval Macros (read_lines)
--
-- Thin wrappers around read_lines that provide convenient interfaces
-- for the common file-reading patterns agents use most.
--
-- NOTE: sitting_duck defines a read_lines() table macro that shadows the
-- read_lines extension. When both are loaded, the caller must drop
-- sitting_duck's macro first: DROP MACRO TABLE IF EXISTS read_lines;
-- See: https://github.com/teaguesterling/sitting_duck/issues/22

-- read_source: Read lines from a file with optional line selection.
-- This is the primary replacement for cat/head/tail bash commands.
--
-- Examples:
--   SELECT * FROM read_source('src/main.py');
--   SELECT * FROM read_source('src/main.py', '10-20');
--   SELECT * FROM read_source('src/main.py', '42 +/-5');
CREATE OR REPLACE MACRO read_source(file_path, lines := NULL, ctx := 0) AS TABLE
    SELECT
        line_number,
        content
    FROM read_lines(file_path, lines, context := ctx);

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
