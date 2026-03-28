-- Fledgling: Help Tool Publication
--
-- MCP tool publication for the skill guide.
-- Wraps the help() macro from sql/help.sql.

PRAGMA mcp_publish_tool(
    'Help',
    'Fledgling skill guide — tools, query-only macros, workflows, and examples. Call with no arguments for the outline. Call with a section ID for details. Use help(''macro-reference'') for the full macro catalog (available via the query tool).',
    'SELECT * FROM help(NULLIF($section, ''null''))',
    '{"section": {"type": "string", "description": "Section ID from the outline. Omit to see the table of contents."}}',
    '[]',
    'markdown'
);
