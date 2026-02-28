-- Fledgling: Path Resolution & Sandbox Setup
--
-- Sets up the resolve() macro for converting relative paths to absolute.
-- Used by all tool SQL templates to work with DuckDB's allowed_directories.
--
-- REQUIRES: session_root variable must be set before loading this file.
--
-- From CLI (init script):
--   SET VARIABLE session_root = getenv('PWD');
--   .read sql/sandbox.sql
--
-- From Python (tests):
--   con.execute("SET VARIABLE session_root = '/path/to/project'")
--   load_sql(con, "sandbox.sql")
--
-- Filesystem lockdown (allowed_directories, enable_external_access)
-- is handled by the init script, not here, so tests can load
-- sandbox.sql without restricting tmp_path access.
--
-- See: https://github.com/duckdb/duckdb/issues/21102
--   (allowed_directories check runs before file_search_path resolution)

-- Resolve relative paths against project root.
-- Absolute paths (starting with /) pass through unchanged.
-- NULL input returns NULL (safe for optional params).
CREATE OR REPLACE MACRO resolve(p) AS
    CASE WHEN p IS NULL THEN NULL
         WHEN p[1] = '/' THEN p
         ELSE getvariable('session_root') || '/' || p
    END;
