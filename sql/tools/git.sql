-- MCP tool publications for git repository state.
--
-- Embeds sextant_root at publish time (getvariable is not available
-- in MCP tool execution context). Must be loaded after sandbox.sql
-- and repo.sql, with sextant_root already set.

SELECT mcp_publish_tool(
    'GitChanges',
    'Recent commit history. Replaces `git log --oneline`.',
    'SELECT hash, author, date, split_part(message, chr(10), 1) AS message
     FROM recent_changes(
        COALESCE(TRY_CAST(NULLIF($count, ''null'') AS INT), 10),
        COALESCE(resolve(NULLIF($path, ''null'')), ''' || getvariable('sextant_root') || ''')
    )',
    '{"count": {"type": "string", "description": "Number of commits to return (default 10)"}, "path": {"type": "string", "description": "Repository path (default: project root)"}}',
    '[]',
    'markdown'
);

SELECT mcp_publish_tool(
    'GitBranches',
    'List all branches with current branch marked.',
    'SELECT * FROM branch_list(''' || getvariable('sextant_root') || ''')',
    '{}',
    '[]',
    'markdown'
);
