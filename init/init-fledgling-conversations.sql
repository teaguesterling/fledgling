-- Fledgling: Conversation Intelligence (standalone MCP server)
--
-- Claude Code conversation analytics as an independent MCP server.
-- Can be used standalone or composed with other Fledgling profiles.
--
-- Standalone usage:
--   duckdb -init init/init-fledgling-conversations.sql
--
-- Composed usage (add to a profile entry point):
--   .read init/init-fledgling-conversations.sql

-- Suppress output during initialization
.headers off
.mode csv
.output /dev/null

-- Load extensions (idempotent if already loaded by base)
LOAD duckdb_mcp;

-- Conversation data root (Claude Code session logs).
-- Priority: pre-set variable > CONVERSATIONS_ROOT env var > ~/.claude/projects.
SET VARIABLE conversations_root = COALESCE(
    getvariable('conversations_root'),
    NULLIF(getenv('CONVERSATIONS_ROOT'), ''),
    getenv('HOME') || '/.claude/projects'
);

-- Bootstrap raw_conversations table.
-- Uses query() for conditional dispatch: loads JSONL if files exist, otherwise
-- creates an empty table with the expected schema.
SET VARIABLE _has_conversations = (SELECT count(*) > 0 FROM glob(
    getvariable('conversations_root') || '/*/*.jsonl'
));
CREATE TABLE IF NOT EXISTS raw_conversations AS
SELECT * REPLACE (CAST(timestamp AS TIMESTAMP) AS timestamp) FROM query(
    CASE WHEN getvariable('_has_conversations')
    THEN 'SELECT *, filename AS _source_file FROM read_json_auto(
        ''' || getvariable('conversations_root') || '/*/*.jsonl'',
        union_by_name=true, maximum_object_size=33554432, filename=true,
        ignore_errors=true
    )'
    ELSE 'SELECT NULL::VARCHAR AS uuid, NULL::VARCHAR AS sessionId,
          NULL::VARCHAR AS type,
          NULL::STRUCT(role VARCHAR, content JSON, model VARCHAR, id VARCHAR, stop_reason VARCHAR, usage STRUCT(input_tokens BIGINT, output_tokens BIGINT, cache_creation_input_tokens BIGINT, cache_read_input_tokens BIGINT)) AS message,
          NULL::TIMESTAMP AS timestamp, NULL::VARCHAR AS requestId,
          NULL::VARCHAR AS slug, NULL::VARCHAR AS version,
          NULL::VARCHAR AS gitBranch, NULL::VARCHAR AS cwd,
          NULL::BOOLEAN AS isSidechain, NULL::BOOLEAN AS isMeta,
          NULL::VARCHAR AS parentUuid, NULL::VARCHAR AS _source_file
          WHERE false'
    END
);
.read sql/conversations.sql

-- Publish conversation tools
.read sql/tools/conversations.sql

-- Standalone mode: start MCP server if not composed with another profile.
-- When composed, the parent profile handles server start.
-- Detect standalone by checking if mcp_server_options is already set.
