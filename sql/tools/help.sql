-- Fledgling: Help Tool Publication
--
-- MCP tool publication for the skill guide.
-- Wraps the help() macro from sql/help.sql.

SELECT mcp_publish_tool(
    'Help',
    'Fledgling skill guide. Call with no arguments for the table of contents. Call with a section ID to read that section.',
    'SELECT * FROM help(NULLIF($section, ''null''))',
    '{"section": {"type": "string", "description": "Section ID from the outline. Omit to see the table of contents."}}',
    '[]',
    'markdown'
);
