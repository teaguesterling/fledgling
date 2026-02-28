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

-- Conversation data root (Claude Code session logs).
-- Priority: pre-set variable > CONVERSATIONS_ROOT env var > ~/.claude/projects.
SET VARIABLE conversations_root = COALESCE(
    getvariable('conversations_root'),
    NULLIF(getenv('CONVERSATIONS_ROOT'), ''),
    getenv('HOME') || '/.claude/projects'
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

-- Bootstrap raw_conversations table (must exist before conversations.sql loads;
-- DuckDB validates table refs at macro definition time).
-- Uses query() for conditional dispatch: loads JSONL if files exist, otherwise
-- creates an empty table with the expected schema.
CREATE TABLE raw_conversations AS
SELECT * FROM query(
    CASE WHEN (SELECT count(*) FROM glob(
        getvariable('conversations_root') || '/*/*.jsonl'
    )) > 0
    THEN 'SELECT *, filename AS _source_file FROM read_json_auto(
        ''' || getvariable('conversations_root') || '/*/*.jsonl'',
        union_by_name=true, maximum_object_size=33554432, filename=true
    )'
    ELSE 'SELECT NULL::VARCHAR AS uuid, NULL::VARCHAR AS sessionId,
          NULL::VARCHAR AS type, NULL::JSON AS message,
          NULL::TIMESTAMP AS timestamp, NULL::VARCHAR AS requestId,
          NULL::VARCHAR AS slug, NULL::VARCHAR AS version,
          NULL::VARCHAR AS gitBranch, NULL::VARCHAR AS cwd,
          NULL::BOOLEAN AS isSidechain, NULL::BOOLEAN AS isMeta,
          NULL::VARCHAR AS parentUuid, NULL::VARCHAR AS _source_file
          WHERE false'
    END
);
.read sql/conversations.sql

-- Publish MCP tools (comment out a line to disable that category)
.read sql/tools/files.sql
.read sql/tools/code.sql
.read sql/tools/docs.sql
.read sql/tools/git.sql
.read sql/tools/conversations.sql

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
