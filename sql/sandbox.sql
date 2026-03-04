-- Fledgling: Path Resolution & Sandbox Setup
--
-- Sets up path resolution macros for converting relative paths to absolute.
-- Used by all tool SQL templates to work with DuckDB's allowed_directories.
--
-- Two resolution strategies:
--   resolve(p)      — uses getvariable('session_root'). Works in direct SQL
--                      and macro bodies, but NOT in MCP tool templates
--                      (getvariable returns NULL in duckdb_mcp execution context).
--   _resolve(p)     — hardcoded literal root. Works everywhere including
--                      MCP tool templates. Use in mcp_publish_tool() SQL.
--   _session_root() — returns the bare session root literal. Use in tool
--                      templates that need the root path directly.
--
-- resolve() is defined here. _resolve() and _session_root() must be created
-- BEFORE this file loads, with the session root baked into the macro body:
--   - bin/fledgling creates them via duckdb -cmd (bash variable expansion)
--   - conftest.py creates them via con.execute() (Python string interpolation)
--
-- DuckDB macros are text-substituted at call time, so getvariable() in a
-- macro body runs in the caller's context. In MCP tool templates, that
-- context has no access to session variables → getvariable returns NULL.
-- The _resolve/_session_root macros avoid this by containing only literals.
-- They can't be defined in pure SQL because there's no dynamic DDL in DuckDB.
--
-- REQUIRES: session_root variable AND _resolve/_session_root macros must
-- be set before loading this file.
--
-- From CLI (bin/fledgling launcher):
--   duckdb -cmd "SET VARIABLE session_root = '$ROOT'" \
--          -cmd "CREATE ... MACRO _resolve(p) ..." \
--          -cmd "CREATE ... MACRO _session_root() ..." \
--          -init init-fledgling-analyst.sql
--
-- From Python (tests):
--   con.execute("SET VARIABLE session_root = '/path'")
--   con.execute("CREATE ... MACRO _resolve(p) ...")
--   con.execute("CREATE ... MACRO _session_root() ...")
--   load_sql(con, "sandbox.sql")
--
-- Filesystem lockdown (allowed_directories, enable_external_access)
-- is handled by the init script, not here, so tests can load
-- sandbox.sql without restricting tmp_path access.
--
-- See: https://github.com/duckdb/duckdb/issues/21102
--   (allowed_directories check runs before file_search_path resolution)

-- resolve: Variable-backed path resolution.
-- Works in direct SQL and macro bodies, but NOT in MCP tool templates.
-- Absolute paths (starting with /) pass through unchanged.
-- NULL input returns NULL (safe for optional params).
CREATE OR REPLACE MACRO resolve(p) AS
    CASE WHEN p IS NULL THEN NULL
         WHEN p[1] = '/' THEN p
         ELSE getvariable('session_root') || '/' || p
    END;
