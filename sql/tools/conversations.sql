-- Fledgling: Conversation Intelligence Tool Publications
--
-- MCP tool publications for Claude Code conversation analysis.
-- Wraps view macros from sql/conversations.sql.

PRAGMA mcp_publish_tool(
    'ChatSessions',
    'Browse Claude Code conversation sessions. Shows session metadata, duration, tool usage, and token consumption. Filter by project name or date range.',
    'SELECT * FROM browse_sessions(
        NULLIF($project, ''null''),
        NULLIF($days, ''null''),
        COALESCE(TRY_CAST(NULLIF($limit, ''null'') AS INT), 20)
    )',
    '{"project": {"type": "string", "description": "Substring match on project directory name (case-insensitive)"}, "days": {"type": "string", "description": "Only sessions from last N days"}, "limit": {"type": "string", "description": "Max rows returned (default 20)"}}',
    '[]',
    'markdown'
);

PRAGMA mcp_publish_tool(
    'ChatSearch',
    'Full-text search across Claude Code conversation messages. Finds matching text in both user and assistant messages. Filter by role, project, or date range.',
    'SELECT * FROM search_chat(
        $query,
        NULLIF($role, ''null''),
        NULLIF($project, ''null''),
        NULLIF($days, ''null''),
        COALESCE(TRY_CAST(NULLIF($limit, ''null'') AS INT), 20)
    )',
    '{"query": {"type": "string", "description": "Search term (case-insensitive substring match)"}, "role": {"type": "string", "description": "Filter to user or assistant messages"}, "project": {"type": "string", "description": "Substring match on project directory name"}, "days": {"type": "string", "description": "Only messages from last N days"}, "limit": {"type": "string", "description": "Max rows returned (default 20)"}}',
    '["query"]',
    'markdown'
);

PRAGMA mcp_publish_tool(
    'ChatToolUsage',
    'Tool usage patterns across Claude Code sessions. Shows which tools are used most frequently, with session counts and date ranges. Filter by project, session, or date range.',
    'SELECT * FROM browse_tool_usage(
        NULLIF($project, ''null''),
        NULLIF($session_id, ''null''),
        NULLIF($days, ''null''),
        COALESCE(TRY_CAST(NULLIF($limit, ''null'') AS INT), 50)
    )',
    '{"project": {"type": "string", "description": "Substring match on project directory name"}, "session_id": {"type": "string", "description": "Filter to a single session UUID"}, "days": {"type": "string", "description": "Only usage from last N days"}, "limit": {"type": "string", "description": "Max rows returned (default 50)"}}',
    '[]',
    'markdown'
);

PRAGMA mcp_publish_tool(
    'ChatDetail',
    'Deep view of a single Claude Code session: metadata, token costs, and per-tool breakdown. Returns one row per tool used in the session with session metadata on every row.',
    'SELECT * FROM session_detail($session_id)',
    '{"session_id": {"type": "string", "description": "Session UUID to inspect"}}',
    '["session_id"]',
    'markdown'
);
