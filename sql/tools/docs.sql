-- Source Sextant: Documentation Tools
--
-- MCP tool publications for structured markdown access.
-- Wraps macros from sql/docs.sql.

SELECT mcp_publish_tool(
    'MDOutline',
    'Table of contents for markdown files. Use before reading sections to decide what''s relevant. Returns headings with section IDs, levels, and line ranges.',
    'SELECT * FROM doc_outline(
        resolve($file_pattern),
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
        resolve($file_path),
        $section_id
    )',
    '{"file_path": {"type": "string", "description": "Path to the markdown file"}, "section_id": {"type": "string", "description": "Section ID from MDOutline (e.g. installation, getting-started)"}}',
    '["file_path", "section_id"]'
);
