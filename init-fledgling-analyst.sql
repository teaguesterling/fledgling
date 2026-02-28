-- Fledgling: Analyst Profile Entry Point
--
-- All structured tools plus raw SQL query access.
-- Default profile for unrestricted use.
--
-- Usage:
--   duckdb -init /path/to/fledgling/init-fledgling-analyst.sql

-- Shared setup: extensions, sandbox, macros, tool publications
.read init-fledgling-base.sql

-- Analyst profile: higher resource limits, built-in query tools enabled
.read sql/profiles/analyst.sql

-- Lock down filesystem access (after all .read commands).
-- session_root is always allowed; extras are appended if set.
SET allowed_directories = list_concat(
    [getvariable('session_root')],
    COALESCE(getvariable('extra_dirs'), [])
);
SET enable_external_access = false;
SET lock_configuration = true;

-- Restore output and start server
.output stdout
SELECT mcp_server_start('stdio', getvariable('mcp_server_options'));
