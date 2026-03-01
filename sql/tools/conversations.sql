-- Fledgling: Conversation Intelligence Tool Publications
--
-- MCP tool publications for Claude Code conversation analysis.
-- Wraps macros from sql/conversations.sql.

SELECT mcp_publish_tool(
    'ChatSessions',
    'Browse Claude Code conversation sessions. Shows session metadata, duration, tool usage, and token consumption. Filter by project name or date range.',
    'SELECT session_id, project_dir, slug, git_branch,
            started_at, duration, user_messages,
            total_tool_calls, distinct_tools_used, top_tool,
            total_tokens, avg_cache_hit_rate
     FROM session_summary()
     WHERE (NULLIF($project, ''null'') IS NULL
            OR project_dir ILIKE ''%'' || NULLIF($project, ''null'') || ''%'')
       AND (NULLIF($days, ''null'') IS NULL
            OR started_at >= CURRENT_TIMESTAMP::TIMESTAMP - (NULLIF($days, ''null'') || '' days'')::INTERVAL)
     ORDER BY started_at DESC
     LIMIT COALESCE(TRY_CAST(NULLIF($limit, ''null'') AS INT), 20)',
    '{"project": {"type": "string", "description": "Substring match on project directory name (case-insensitive)"}, "days": {"type": "string", "description": "Only sessions from last N days"}, "limit": {"type": "string", "description": "Max rows returned (default 20)"}}',
    '[]',
    'markdown'
);

SELECT mcp_publish_tool(
    'ChatSearch',
    'Full-text search across Claude Code conversation messages. Finds matching text in both user and assistant messages. Filter by role, project, or date range.',
    'SELECT sm.session_id, sm.slug, sm.role,
            left(sm.content, 500) AS content_preview, sm.created_at
     FROM search_messages($query) sm
     LEFT JOIN sessions() s ON s.session_id = sm.session_id
     WHERE (NULLIF($role, ''null'') IS NULL
            OR sm.role = NULLIF($role, ''null''))
       AND (NULLIF($project, ''null'') IS NULL
            OR s.project_dir ILIKE ''%'' || NULLIF($project, ''null'') || ''%'')
       AND (NULLIF($days, ''null'') IS NULL
            OR sm.created_at >= CURRENT_TIMESTAMP::TIMESTAMP - (NULLIF($days, ''null'') || '' days'')::INTERVAL)
     ORDER BY sm.created_at DESC
     LIMIT COALESCE(TRY_CAST(NULLIF($limit, ''null'') AS INT), 20)',
    '{"query": {"type": "string", "description": "Search term (case-insensitive substring match)"}, "role": {"type": "string", "description": "Filter to user or assistant messages"}, "project": {"type": "string", "description": "Substring match on project directory name"}, "days": {"type": "string", "description": "Only messages from last N days"}, "limit": {"type": "string", "description": "Max rows returned (default 20)"}}',
    '["query"]',
    'markdown'
);

SELECT mcp_publish_tool(
    'ChatToolUsage',
    'Tool usage patterns across Claude Code sessions. Shows which tools are used most frequently, with session counts and date ranges. Filter by project, session, or date range.',
    'SELECT tf.tool_name,
            sum(tf.call_count) AS total_calls,
            count(DISTINCT tf.session_id) AS sessions,
            min(tf.first_used) AS first_used,
            max(tf.last_used) AS last_used
     FROM tool_frequency() tf
     LEFT JOIN sessions() s ON s.session_id = tf.session_id
     WHERE (NULLIF($project, ''null'') IS NULL
            OR s.project_dir ILIKE ''%'' || NULLIF($project, ''null'') || ''%'')
       AND (NULLIF($session_id, ''null'') IS NULL
            OR tf.session_id = NULLIF($session_id, ''null''))
       AND (NULLIF($days, ''null'') IS NULL
            OR tf.first_used >= CURRENT_TIMESTAMP::TIMESTAMP - (NULLIF($days, ''null'') || '' days'')::INTERVAL)
     GROUP BY tf.tool_name
     ORDER BY total_calls DESC
     LIMIT COALESCE(TRY_CAST(NULLIF($limit, ''null'') AS INT), 50)',
    '{"project": {"type": "string", "description": "Substring match on project directory name"}, "session_id": {"type": "string", "description": "Filter to a single session UUID"}, "days": {"type": "string", "description": "Only usage from last N days"}, "limit": {"type": "string", "description": "Max rows returned (default 50)"}}',
    '[]',
    'markdown'
);

SELECT mcp_publish_tool(
    'ChatDetail',
    'Deep view of a single Claude Code session: metadata, token costs, and per-tool breakdown. Returns one row per tool used in the session with session metadata on every row.',
    'SELECT s.slug, s.project_dir, s.git_branch,
            s.started_at, s.duration,
            s.user_messages, s.assistant_messages,
            s.total_tokens, s.avg_cache_hit_rate,
            s.bash_calls, s.bash_replaceable_calls,
            tf.tool_name, tf.calls
     FROM (SELECT * FROM session_summary() WHERE session_id = $session_id) s
     LEFT JOIN (
         SELECT session_id, tool_name, sum(call_count) AS calls
         FROM tool_frequency() WHERE session_id = $session_id
         GROUP BY session_id, tool_name
     ) tf ON tf.session_id = s.session_id
     ORDER BY tf.calls DESC NULLS LAST',
    '{"session_id": {"type": "string", "description": "Session UUID to inspect"}}',
    '["session_id"]',
    'markdown'
);
