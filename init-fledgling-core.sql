-- Fledgling: Core Profile Entry Point
--
-- Structured tools only. No raw SQL query access.
--
-- Usage:
--   duckdb -init /path/to/fledgling/init-fledgling-core.sql

-- Shared setup: extensions, sandbox, macros, tool publications
.read init-fledgling-base.sql

-- Core profile: restricted resource limits, no built-in query tools
.read sql/profiles/core.sql

-- Lock down filesystem access (after all .read commands).
-- session_root is always allowed; extras are appended if set.
-- conversations_root is intentionally excluded: conversation data is
-- materialized into raw_conversations at startup (a point-in-time snapshot).
-- NOTE: This block is duplicated in each entry point because profile SQL
-- must run before lock_configuration. Extract to sql/lockdown.sql if a
-- third profile is added.
SET allowed_directories = list_concat(
    [getvariable('session_root')],
    COALESCE(getvariable('extra_dirs'), [])
);
SET enable_external_access = false;
SET lock_configuration = true;

-- Restore output and start server
.output stdout
SELECT mcp_server_start('stdio', getvariable('mcp_server_options'));
