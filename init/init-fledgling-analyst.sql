-- Fledgling: Analyst Profile Entry Point
--
-- All structured tools plus raw SQL query access.
-- Default profile for unrestricted use.
--
-- Usage:
--   duckdb -init init/init-fledgling-analyst.sql

-- Shared setup: extensions, sandbox, macros, tool publications
.read init/init-fledgling-base.sql

-- Analyst profile: higher resource limits, built-in query tools enabled
.read sql/profiles/analyst.sql

-- Lock down filesystem access (after all .read commands).
-- session_root is always allowed; extras are appended if set.
-- git:// prefix allows ReadLines git mode (duck_tails resolves to repo-relative
-- paths, so only the bare scheme works as an allowed prefix).
-- NOTE: This block is duplicated in each entry point because profile SQL
-- must run before lock_configuration. Extract to sql/lockdown.sql if a
-- third profile is added.
SET allowed_directories = list_concat(
    [getvariable('session_root'), 'git://'],
    COALESCE(getvariable('extra_dirs'), [])
);
SET enable_external_access = false;
SET lock_configuration = true;

-- Restore output and start server
.output stdout
SELECT mcp_server_start(COALESCE(getvariable('transport'), 'stdio'), getvariable('mcp_server_options'));
