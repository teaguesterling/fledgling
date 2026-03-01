-- Fledgling: Documentation Tools
--
-- MCP tool publications for structured markdown access.
-- Wraps macros from sql/docs.sql.
--
-- Embeds session_root at publish time (getvariable is not available
-- in MCP tool execution context). Must be loaded after sandbox.sql
-- and docs.sql, with session_root already set.

SELECT mcp_publish_tool(
    'MDOutline',
    'Table of contents for markdown files. Use before reading sections to decide what''s relevant. Returns headings with section IDs, levels, and line ranges.',
    'SELECT * FROM doc_outline(
        CASE WHEN $file_pattern[1] = ''/'' THEN $file_pattern
             ELSE ''' || getvariable('session_root') || '/'' || $file_pattern END,
        COALESCE(TRY_CAST(NULLIF($max_level, ''null'') AS INT), 3)
    )',
    '{"file_pattern": {"type": "string", "description": "Glob pattern for markdown files (e.g. docs/**/*.md or README.md)"}, "max_level": {"type": "string", "description": "Maximum heading level to include (1-6, default 3)"}}',
    '["file_pattern"]',
    'markdown'
);

SELECT mcp_publish_tool(
    'MDSection',
    'Read a specific section from a markdown file by ID. Use MDOutline first to discover section IDs.',
    'SELECT * FROM read_doc_section(
        CASE WHEN $file_path[1] = ''/'' THEN $file_path
             ELSE ''' || getvariable('session_root') || '/'' || $file_path END,
        $section_id
    )',
    '{"file_path": {"type": "string", "description": "Path to the markdown file"}, "section_id": {"type": "string", "description": "Section ID from MDOutline (e.g. installation, getting-started)"}}',
    '["file_path", "section_id"]',
    'markdown'
);
