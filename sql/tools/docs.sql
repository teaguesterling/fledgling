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
--   doc_outline, find_code_examples, doc_stats

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

SELECT mcp_publish_tool(
    'MDOverview',
    'Browse documentation: shows markdown section outlines. Call with no arguments to see all docs. Use search to filter by keyword. Returns section IDs for use with MDSection.',
    'SELECT * FROM doc_outline(
        COALESCE(_resolve(NULLIF($pattern, ''null'')), _session_root() || ''/'' || ''**/*.md''),
        COALESCE(TRY_CAST(NULLIF($max_level, ''null'') AS INT), 3),
        search := NULLIF($search, ''null'')
    )',
    '{"pattern": {"type": "string", "description": "Glob pattern for markdown files (default: **/*.md)"}, "search": {"type": "string", "description": "Filter sections by keyword in title or content (case-insensitive)"}, "max_level": {"type": "string", "description": "Maximum heading depth to include (default: 3)"}}',
    '[]',
    'markdown'
);
