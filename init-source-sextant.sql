-- Source Sextant: Init Script
--
-- Entry point for: duckdb -init init-source-sextant.sql
--
-- Loads extensions, configures sandbox, loads macros and tool
-- publications, then starts the MCP server on stdio transport.
--
-- Usage:
--   duckdb -init /path/to/source-sextant/init-source-sextant.sql
--
-- The MCP client must set cwd to the source-sextant directory so
-- .read paths resolve correctly (they are relative to CWD, not to
-- this init script). The target project root is passed separately
-- via the SEXTANT_PROJECT_ROOT environment variable, or by
-- pre-setting the sextant_root DuckDB variable.

-- Suppress output during initialization
.headers off
.mode csv
.output /dev/null

-- Load extensions (must happen before sandbox lockdown; see duckdb#17136)
LOAD duckdb_mcp;
LOAD read_lines;
LOAD sitting_duck;
LOAD markdown;
LOAD duck_tails;

-- Capture project root before lockdown.
-- Priority: pre-set variable > SEXTANT_PROJECT_ROOT env var > CWD.
SET VARIABLE sextant_root = COALESCE(
    getvariable('sextant_root'),
    NULLIF(getenv('SEXTANT_PROJECT_ROOT'), ''),
    getenv('PWD')
);

-- Additional allowed directories (set before this point if needed).
-- Example: SET VARIABLE sextant_extra_dirs = ['/data/shared', '/opt/models'];

-- Path resolution macro (resolve relative paths against sextant_root)
.read sql/sandbox.sql

-- Load macro definitions
.read sql/source.sql
.read sql/code.sql
.read sql/docs.sql
.read sql/repo.sql

-- Publish MCP tools (comment out a line to disable that category)
.read sql/tools/files.sql
.read sql/tools/code.sql
.read sql/tools/docs.sql
.read sql/tools/git.sql

-- Lock down filesystem access (after all .read commands).
-- sextant_root is always allowed; extras are appended if set.
SET allowed_directories = list_concat(
    [getvariable('sextant_root')],
    COALESCE(getvariable('sextant_extra_dirs'), [])
);
SET enable_external_access = false;
SET lock_configuration = true;

-- Restore output and start server
.output stdout
SELECT mcp_server_start('stdio', '{
    "enable_query_tool": true,
    "enable_describe_tool": true,
    "enable_list_tables_tool": true,
    "enable_database_info_tool": false,
    "enable_export_tool": false,
    "enable_execute_tool": false,
    "default_result_format": "markdown"
}');
