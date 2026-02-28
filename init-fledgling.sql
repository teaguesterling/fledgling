-- Fledgling: Init Script
--
-- Entry point for: duckdb -init init-fledgling.sql
--
-- Loads extensions, configures sandbox, loads macros and tool
-- publications, then starts the MCP server on stdio transport.
--
-- Usage:
--   duckdb -init /path/to/fledgling/init-fledgling.sql
--
-- The MCP client must set cwd to the fledgling directory so
-- .read paths resolve correctly (they are relative to CWD, not to
-- this init script). The target project root is passed separately
-- via the FLEDGLING_ROOT environment variable, or by
-- pre-setting the session_root DuckDB variable.

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
-- Priority: pre-set variable > FLEDGLING_ROOT env var > CWD.
SET VARIABLE session_root = COALESCE(
    getvariable('session_root'),
    NULLIF(getenv('FLEDGLING_ROOT'), ''),
    getenv('PWD')
);

-- Additional allowed directories (set before this point if needed).
-- Example: SET VARIABLE extra_dirs = ['/data/shared', '/opt/models'];

-- Path resolution macro (resolve relative paths against session_root)
.read sql/sandbox.sql

-- Load macro definitions
.read sql/source.sql
.read sql/code.sql
.read sql/docs.sql
.read sql/repo.sql

-- Materialize skill guide (fledgling dir not in allowed_directories after lockdown)
CREATE TABLE _help_sections AS
SELECT section_id, section_path, level, title, content, start_line, end_line
FROM read_markdown_sections('SKILL.md', content_mode := 'full',
    include_content := true, include_filepath := false);
.read sql/help.sql

-- Publish MCP tools (comment out a line to disable that category)
.read sql/tools/files.sql
.read sql/tools/code.sql
.read sql/tools/docs.sql
.read sql/tools/git.sql
.read sql/tools/help.sql

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
SELECT mcp_server_start('stdio', '{
    "enable_query_tool": true,
    "enable_describe_tool": true,
    "enable_list_tables_tool": true,
    "enable_database_info_tool": false,
    "enable_export_tool": false,
    "enable_execute_tool": false,
    "default_result_format": "markdown"
}');
