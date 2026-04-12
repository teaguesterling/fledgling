-- Fledgling: Code Intelligence Tool Publications
--
-- Publishes 4 MCP tools for AST-based code analysis.
-- Macros are defined in sql/code.sql; this file only creates MCP bindings.
--
-- Embeds session_root at publish time (getvariable is not available
-- in MCP tool execution context). Must be loaded after sandbox.sql
-- and code.sql, with session_root already set.
--
-- Published tools:
--   FindDefinitions, CodeStructure, FindCode, ViewCode
--
-- Macros without tool publications (use via query tool):
--   find_in_ast, find_calls, find_imports, complexity_hotspots,
--   function_callers, module_dependencies

PRAGMA mcp_publish_tool(
    'FindDefinitions',
    'AST-based definition search — not grep. Finds functions, classes, and variable definitions. Use name_pattern with SQL LIKE wildcards (%) to filter by name.',
    'SELECT * FROM find_definitions(
        _resolve($file_pattern),
        COALESCE(NULLIF($name_pattern, ''null''), ''%'')
    )',
    '{"file_pattern": {"type": "string", "description": "Glob pattern for files to search (e.g. src/**/*.py)"}, "name_pattern": {"type": "string", "description": "SQL LIKE pattern to filter by name (e.g. parse%). Default: % (all)"}}',
    '["file_pattern"]',
    'markdown'
);

PRAGMA mcp_publish_tool(
    'CodeStructure',
    'Top-level structural overview of source files: definitions with line counts. Good first step for unfamiliar code. For deeper analysis, use complexity_hotspots() and module_dependencies() via the query tool.',
    'SELECT * FROM code_structure(
        _resolve($file_pattern)
    )',
    '{"file_pattern": {"type": "string", "description": "Glob pattern for files to analyze (e.g. src/**/*.py)"}}',
    '["file_pattern"]',
    'markdown'
);

-- FindInAST removed — FindCode and SelectCode (in tools/workflows.sql)
-- provide the same capability with CSS selectors. The find_in_ast macro
-- remains available via the query tool for backwards compatibility.

PRAGMA mcp_publish_tool(
    'FindCode',
    'Search code with CSS selectors. More expressive than FindDefinitions — compose :has, :not, ::callers, combinators. Examples: .func#validate, .func:has(.call#execute):not(:has(try)), .class > .func.',
    'SELECT * FROM find_code_grep(
        _resolve($file_pattern),
        $selector,
        NULLIF($language, ''null'')
    )',
    '{"file_pattern": {"type": "string", "description": "Glob pattern for files (e.g. src/**/*.py, **/*.rs)"}, "selector": {"type": "string", "description": "CSS selector: .func, #name, :has(child), :not(:has(child)), ::callers, A > B, A ~ B"}, "language": {"type": "string", "description": "Language override (default: auto-detect from extension)"}}',
    '["file_pattern", "selector"]',
    'text'
);

PRAGMA mcp_publish_tool(
    'ViewCode',
    'View source code matched by CSS selector with optional context lines. Each match shows a header (# file:start-end) followed by numbered source lines.',
    'SELECT * FROM view_code_text(
        _resolve($file_pattern),
        $selector,
        NULLIF($language, ''null''),
        COALESCE(TRY_CAST(NULLIF($context, ''null'') AS INT), 0)
    )',
    '{"file_pattern": {"type": "string", "description": "Glob pattern for files"}, "selector": {"type": "string", "description": "CSS selector to match"}, "language": {"type": "string", "description": "Language override (default: auto-detect)"}, "context": {"type": "string", "description": "Lines of context around each match (default: 0)"}}',
    '["file_pattern", "selector"]',
    'text'
);
