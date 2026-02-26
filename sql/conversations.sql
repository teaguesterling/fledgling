-- conversations.sql: DuckDB schema for analyzing Claude Code conversation logs
--
-- Prerequisites: A `raw_conversations` table loaded from JSONL files.
-- All objects are CREATE OR REPLACE for idempotency.
-- See docs/vision/CONVERSATION_SCHEMA_DESIGN.md for design details.

-- 1. LOADING MACRO
CREATE OR REPLACE MACRO load_conversations(path) AS TABLE
    SELECT *, filename AS _source_file
    FROM read_json_auto(
        path, union_by_name=true, maximum_object_size=33554432, filename=true
    );

-- 2a. SESSIONS - One row per session with metadata
CREATE OR REPLACE VIEW sessions AS
    SELECT
        sessionId AS session_id,
        regexp_extract(_source_file, '.claude/projects/([^/]+)/', 1) AS project_dir,
        last(slug ORDER BY timestamp) FILTER (WHERE slug IS NOT NULL) AS slug,
        last(version ORDER BY timestamp) FILTER (WHERE version IS NOT NULL) AS version,
        last(gitBranch ORDER BY timestamp) FILTER (WHERE gitBranch IS NOT NULL) AS git_branch,
        last(cwd ORDER BY timestamp) FILTER (WHERE cwd IS NOT NULL) AS working_dir,
        min(timestamp) AS started_at,
        max(timestamp) AS ended_at,
        age(max(timestamp), min(timestamp)) AS duration,
        count(*) FILTER (WHERE type = 'user') AS user_messages,
        count(*) FILTER (WHERE type = 'assistant') AS assistant_messages,
        count(*) FILTER (WHERE type = 'progress') AS progress_events,
        count(*) FILTER (WHERE type = 'system') AS system_events,
        count(*) AS total_records,
        any_value(_source_file) AS source_file
    FROM raw_conversations
    WHERE sessionId IS NOT NULL
    GROUP BY sessionId,
             regexp_extract(_source_file, '.claude/projects/([^/]+)/', 1);

-- 2b. MESSAGES - Flattened user + assistant messages
CREATE OR REPLACE VIEW messages AS
    SELECT
        r.uuid AS message_id,
        r.sessionId AS session_id,
        r.parentUuid AS parent_id,
        r.type AS record_type,
        r.message.role AS role,
        r.message.content AS content,
        r.message.model AS model,
        r.message.id AS api_message_id,
        r.message.stop_reason AS stop_reason,
        r.requestId AS request_id,
        r.slug, r.version,
        r.gitBranch AS git_branch,
        r.cwd AS working_dir,
        r.isSidechain AS is_sidechain,
        r.isMeta AS is_meta,
        r.message.usage.input_tokens AS input_tokens,
        r.message.usage.output_tokens AS output_tokens,
        r.message.usage.cache_creation_input_tokens AS cache_creation_tokens,
        r.message.usage.cache_read_input_tokens AS cache_read_tokens,
        r.timestamp AS created_at,
        r._source_file AS source_file
    FROM raw_conversations r
    WHERE r.type IN ('user', 'assistant');

-- 2c. CONTENT BLOCKS - Unnested assistant message content
-- Key pattern: LATERAL UNNEST(CAST(content AS JSON[])) turns JSON array into rows
-- Guard: json_type() = 'ARRAY' prevents CAST errors on string user content
CREATE OR REPLACE VIEW content_blocks AS
    SELECT
        r.uuid AS message_id,
        r.sessionId AS session_id,
        r.slug, r.timestamp AS created_at,
        r.requestId AS request_id,
        r.message.model AS model,
        b.block,
        b.block ->> 'type' AS block_type,
        b.block ->> 'text' AS text_content,
        b.block ->> 'thinking' AS thinking_content,
        b.block ->> 'name' AS tool_name,
        b.block ->> 'id' AS tool_use_id,
        b.block -> 'input' AS tool_input,
        r._source_file AS source_file
    FROM raw_conversations r,
         LATERAL UNNEST(CAST(r.message.content AS JSON[])) AS b(block)
    WHERE r.type = 'assistant'
      AND r.message.content IS NOT NULL
      AND json_type(r.message.content) = 'ARRAY';

-- 2d. TOOL CALLS - Extracted tool_use blocks with convenience columns
CREATE OR REPLACE VIEW tool_calls AS
    SELECT
        cb.tool_use_id, cb.message_id, cb.session_id,
        cb.slug, cb.model, cb.created_at, cb.tool_name,
        cb.tool_input AS input,
        cb.tool_input ->> 'command' AS bash_command,
        COALESCE(cb.tool_input ->> 'file_path', cb.tool_input ->> 'path') AS file_path,
        cb.tool_input ->> 'pattern' AS grep_pattern,
        cb.source_file
    FROM content_blocks cb
    WHERE cb.block_type = 'tool_use';

-- 2e. TOOL RESULTS - Matched tool_result blocks from user messages
-- Join: tool_calls.tool_use_id = tool_results.tool_use_id
CREATE OR REPLACE VIEW tool_results AS
    SELECT
        r.uuid AS message_id,
        r.sessionId AS session_id,
        r.timestamp AS created_at,
        b.block ->> 'tool_use_id' AS tool_use_id,
        b.block ->> 'content' AS result_content,
        CAST(b.block ->> 'is_error' AS BOOLEAN) AS is_error,
        r._source_file AS source_file
    FROM raw_conversations r,
         LATERAL UNNEST(CAST(r.message.content AS JSON[])) AS b(block)
    WHERE r.type = 'user'
      AND r.message.content IS NOT NULL
      AND json_type(r.message.content) = 'ARRAY'
      AND b.block ->> 'type' = 'tool_result';

-- 2f. TOKEN USAGE - Per-message token consumption with cache metrics
-- WARNING: Deduplicate on request_id for accurate totals (chunks share usage)
CREATE OR REPLACE VIEW token_usage AS
    SELECT
        m.message_id, m.session_id, m.request_id,
        m.model, m.created_at, m.slug,
        m.input_tokens, m.output_tokens,
        m.cache_creation_tokens, m.cache_read_tokens,
        COALESCE(m.input_tokens,0) + COALESCE(m.cache_creation_tokens,0)
            + COALESCE(m.cache_read_tokens,0) AS total_input_tokens,
        COALESCE(m.input_tokens,0) + COALESCE(m.output_tokens,0)
            + COALESCE(m.cache_creation_tokens,0)
            + COALESCE(m.cache_read_tokens,0) AS total_tokens,
        CASE WHEN COALESCE(m.input_tokens,0) + COALESCE(m.cache_creation_tokens,0)
                  + COALESCE(m.cache_read_tokens,0) > 0
             THEN COALESCE(m.cache_read_tokens,0)::FLOAT
                  / (COALESCE(m.input_tokens,0) + COALESCE(m.cache_creation_tokens,0)
                     + COALESCE(m.cache_read_tokens,0))
             ELSE NULL END AS cache_hit_rate,
        m.source_file
    FROM messages m
    WHERE m.role = 'assistant' AND m.input_tokens IS NOT NULL;

-- 3a. TOOL FREQUENCY - Tool usage counts by project/session/tool
CREATE OR REPLACE VIEW tool_frequency AS
    SELECT
        regexp_extract(tc.source_file, '.claude/projects/([^/]+)/', 1) AS project_dir,
        tc.session_id, tc.slug, tc.tool_name,
        count(*) AS call_count,
        min(tc.created_at) AS first_used,
        max(tc.created_at) AS last_used
    FROM tool_calls tc GROUP BY ALL;

-- 3b. BASH COMMANDS - Parsed bash command analysis with categories
-- Categories: git_read, git_write, github_cli, build_tools, runtime_exec,
--   file_search, file_read, filesystem, text_processing, network, other
-- replaceable_by: duck_tails, sitting_duck, read_lines, duckdb_sql
CREATE OR REPLACE VIEW bash_commands AS
    SELECT
        tc.tool_use_id, tc.message_id, tc.session_id,
        tc.slug, tc.created_at,
        tc.bash_command AS command,
        regexp_extract(trim(tc.bash_command), '^(\S+)', 1) AS leading_command,
        CASE WHEN trim(tc.bash_command) LIKE 'git %'
             THEN regexp_extract(trim(tc.bash_command), '^git\s+(\S+)', 1)
             ELSE NULL END AS git_subcommand,
        CASE WHEN trim(tc.bash_command) LIKE 'gh %'
             THEN regexp_extract(trim(tc.bash_command), '^gh\s+(\S+\s*\S*)', 1)
             ELSE NULL END AS gh_subcommand,
        CASE
            WHEN trim(tc.bash_command) LIKE 'git diff%'
              OR trim(tc.bash_command) LIKE 'git log%'
              OR trim(tc.bash_command) LIKE 'git status%'
              OR trim(tc.bash_command) LIKE 'git show%'
              OR trim(tc.bash_command) LIKE 'git rev-parse%'
              OR trim(tc.bash_command) LIKE 'git branch%'
              OR trim(tc.bash_command) LIKE 'git remote%'
              OR trim(tc.bash_command) LIKE 'git config%' THEN 'git_read'
            WHEN trim(tc.bash_command) LIKE 'git %' THEN 'git_write'
            WHEN trim(tc.bash_command) LIKE 'gh %' THEN 'github_cli'
            WHEN trim(tc.bash_command) LIKE 'cargo %'
              OR trim(tc.bash_command) LIKE 'make%'
              OR trim(tc.bash_command) LIKE 'npm %'
              OR trim(tc.bash_command) LIKE 'yarn %'
              OR trim(tc.bash_command) LIKE 'pip %'
              OR trim(tc.bash_command) LIKE 'pip3 %'
              OR trim(tc.bash_command) LIKE 'uv %'
              OR trim(tc.bash_command) LIKE 'cmake%' THEN 'build_tools'
            WHEN trim(tc.bash_command) LIKE 'python%'
              OR trim(tc.bash_command) LIKE 'node %'
              OR trim(tc.bash_command) LIKE 'duckdb%'
              OR trim(tc.bash_command) LIKE 'ruby %'
              OR trim(tc.bash_command) LIKE 'java %'
              OR trim(tc.bash_command) LIKE 'go %' THEN 'runtime_exec'
            WHEN trim(tc.bash_command) LIKE 'grep %'
              OR trim(tc.bash_command) LIKE 'rg %'
              OR trim(tc.bash_command) LIKE 'find %'
              OR trim(tc.bash_command) LIKE 'fd %'
              OR trim(tc.bash_command) LIKE 'ag %' THEN 'file_search'
            WHEN trim(tc.bash_command) LIKE 'cat %'
              OR trim(tc.bash_command) LIKE 'head %'
              OR trim(tc.bash_command) LIKE 'tail %'
              OR trim(tc.bash_command) LIKE 'less %'
              OR trim(tc.bash_command) LIKE 'bat %'
              OR trim(tc.bash_command) LIKE 'sed -n%' THEN 'file_read'
            WHEN trim(tc.bash_command) LIKE 'ls%'
              OR trim(tc.bash_command) LIKE 'mkdir%'
              OR trim(tc.bash_command) LIKE 'rm %'
              OR trim(tc.bash_command) LIKE 'cp %'
              OR trim(tc.bash_command) LIKE 'mv %'
              OR trim(tc.bash_command) LIKE 'chmod%'
              OR trim(tc.bash_command) LIKE 'touch %' THEN 'filesystem'
            WHEN trim(tc.bash_command) LIKE 'wc %'
              OR trim(tc.bash_command) LIKE 'sort %'
              OR trim(tc.bash_command) LIKE 'uniq %'
              OR trim(tc.bash_command) LIKE 'awk %'
              OR trim(tc.bash_command) LIKE 'cut %'
              OR trim(tc.bash_command) LIKE 'jq %' THEN 'text_processing'
            WHEN trim(tc.bash_command) LIKE 'curl %'
              OR trim(tc.bash_command) LIKE 'wget %'
              OR trim(tc.bash_command) LIKE 'ssh %'
              OR trim(tc.bash_command) LIKE 'scp %' THEN 'network'
            ELSE 'other'
        END AS category,
        CASE
            WHEN trim(tc.bash_command) LIKE 'git diff%'
              OR trim(tc.bash_command) LIKE 'git log%'
              OR trim(tc.bash_command) LIKE 'git status%'
              OR trim(tc.bash_command) LIKE 'git show%'
              OR trim(tc.bash_command) LIKE 'git rev-parse%'
              OR trim(tc.bash_command) LIKE 'git branch%' THEN 'duck_tails'
            WHEN trim(tc.bash_command) LIKE 'grep %'
              OR trim(tc.bash_command) LIKE 'rg %'
              OR trim(tc.bash_command) LIKE 'find %'
              OR trim(tc.bash_command) LIKE 'fd %' THEN 'sitting_duck'
            WHEN trim(tc.bash_command) LIKE 'cat %'
              OR trim(tc.bash_command) LIKE 'head %'
              OR trim(tc.bash_command) LIKE 'tail %' THEN 'read_lines'
            WHEN trim(tc.bash_command) LIKE 'wc %'
              OR trim(tc.bash_command) LIKE 'sort %'
              OR trim(tc.bash_command) LIKE 'awk %' THEN 'duckdb_sql'
            ELSE NULL
        END AS replaceable_by,
        tc.source_file
    FROM tool_calls tc
    WHERE tc.tool_name = 'Bash' AND tc.bash_command IS NOT NULL;

-- 3c. SESSION SUMMARY - Dashboard view with all stats per session
CREATE OR REPLACE VIEW session_summary AS
    SELECT
        s.session_id, s.project_dir, s.slug, s.version,
        s.git_branch, s.started_at, s.ended_at, s.duration,
        s.user_messages, s.assistant_messages, s.total_records,
        COALESCE(tc.total_tool_calls, 0) AS total_tool_calls,
        COALESCE(tc.distinct_tools, 0) AS distinct_tools_used,
        tc.top_tool,
        COALESCE(tk.total_input, 0) AS total_input_tokens,
        COALESCE(tk.total_output, 0) AS total_output_tokens,
        COALESCE(tk.total_tokens, 0) AS total_tokens,
        tk.avg_cache_hit_rate,
        COALESCE(bc.bash_calls, 0) AS bash_calls,
        COALESCE(bc.replaceable_calls, 0) AS bash_replaceable_calls
    FROM sessions s
    LEFT JOIN (
        SELECT session_id, count(*) AS total_tool_calls,
               count(DISTINCT tool_name) AS distinct_tools,
               mode(tool_name) AS top_tool
        FROM tool_calls GROUP BY session_id
    ) tc ON tc.session_id = s.session_id
    LEFT JOIN (
        SELECT session_id, sum(input_tokens) AS total_input,
               sum(output_tokens) AS total_output,
               sum(total_tokens) AS total_tokens,
               avg(cache_hit_rate) AS avg_cache_hit_rate
        FROM (
            SELECT DISTINCT ON (request_id) session_id, request_id,
                input_tokens, output_tokens, total_tokens, cache_hit_rate
            FROM token_usage
            ORDER BY request_id, output_tokens DESC NULLS LAST
        ) GROUP BY session_id
    ) tk ON tk.session_id = s.session_id
    LEFT JOIN (
        SELECT session_id, count(*) AS bash_calls,
               count(*) FILTER (WHERE replaceable_by IS NOT NULL) AS replaceable_calls
        FROM bash_commands GROUP BY session_id
    ) bc ON bc.session_id = s.session_id;

-- 3d. MODEL USAGE - Token consumption by model
CREATE OR REPLACE VIEW model_usage AS
    SELECT model,
        count(DISTINCT session_id) AS sessions,
        count(DISTINCT request_id) AS api_calls,
        sum(input_tokens) AS total_input_tokens,
        sum(output_tokens) AS total_output_tokens,
        sum(total_tokens) AS total_tokens,
        avg(cache_hit_rate) AS avg_cache_hit_rate
    FROM (
        SELECT DISTINCT ON (request_id) session_id, request_id, model,
            input_tokens, output_tokens, total_tokens, cache_hit_rate
        FROM token_usage WHERE model IS NOT NULL
        ORDER BY request_id, output_tokens DESC NULLS LAST
    ) GROUP BY model ORDER BY total_tokens DESC;

-- 4a. SEARCH MESSAGES - Full-text search across conversation content
CREATE OR REPLACE MACRO search_messages(search_term) AS TABLE
    SELECT uuid AS message_id, sessionId AS session_id, slug,
           'user' AS role, CAST(message.content AS VARCHAR) AS content,
           timestamp AS created_at
    FROM raw_conversations
    WHERE type = 'user'
      AND CAST(message.content AS VARCHAR) ILIKE '%' || search_term || '%'
      AND json_type(message.content) != 'ARRAY'
    UNION ALL
    SELECT r.uuid, r.sessionId, r.slug,
           'assistant', b.block ->> 'text', r.timestamp
    FROM raw_conversations r,
         LATERAL UNNEST(CAST(r.message.content AS JSON[])) AS b(block)
    WHERE r.type = 'assistant'
      AND r.message.content IS NOT NULL
      AND json_type(r.message.content) = 'ARRAY'
      AND b.block ->> 'type' = 'text'
      AND b.block ->> 'text' ILIKE '%' || search_term || '%';

-- 4b. SEARCH TOOL INPUTS - Search within tool call parameters
CREATE OR REPLACE MACRO search_tool_inputs(search_term) AS TABLE
    SELECT tc.tool_use_id, tc.session_id, tc.slug, tc.tool_name,
           tc.bash_command, tc.file_path, tc.grep_pattern,
           CAST(tc.input AS VARCHAR) AS input_text, tc.created_at
    FROM tool_calls tc
    WHERE CAST(tc.input AS VARCHAR) ILIKE '%' || search_term || '%';
