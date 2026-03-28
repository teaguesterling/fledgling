-- Fledgling: Documentation Tools
--
-- MCP tool publications for structured markdown access.
-- Wraps macros from sql/docs.sql.
--
-- Embeds session_root at publish time (getvariable is not available
-- in MCP tool execution context). Must be loaded after sandbox.sql
-- and docs.sql, with session_root already set.
--
-- Macros without tool publications (use via query tool):
--   doc_outline

SELECT mcp_publish_tool(
    'MDSection',
    'Read a specific section from a markdown file by ID. Returns the raw markdown content. Use the query tool with doc_outline() to discover section IDs.',
    'SELECT content AS line FROM read_doc_section(
        _resolve($file_path),
        $section_id
    )',
    '{"file_path": {"type": "string", "description": "Path to the markdown file"}, "section_id": {"type": "string", "description": "Section ID (e.g. installation, getting-started). Use doc_outline() via query tool to discover IDs."}}',
    '["file_path", "section_id"]',
    'text'
);
