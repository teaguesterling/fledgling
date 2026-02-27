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
-- The MCP client must set cwd to the target project directory.
-- CWD is captured as sextant_root before filesystem lockdown.
--
-- .read paths are relative to CWD where duckdb is invoked,
-- not relative to this init script. The Claude Code config must
-- set the correct working directory or use absolute paths.

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
-- Override sextant_root before this point to use a custom root.
SET VARIABLE sextant_root = COALESCE(
    getvariable('sextant_root'),
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
