-- Fledgling: Code Intelligence Tool Publications
--
-- Publishes 5 MCP tools for AST-based code analysis.
-- Macros are defined in sql/code.sql; this file only creates MCP bindings.
--
-- Embeds session_root at publish time (getvariable is not available
-- in MCP tool execution context). Must be loaded after sandbox.sql
-- and code.sql, with session_root already set.
--
-- Published tools:
--   FindDefinitions, CodeStructure, FindInAST, FindCode, ViewCode
--
-- Macros without tool publications (use via query tool):
--   find_calls, find_imports, complexity_hotspots, function_callers,
--   module_dependencies

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

PRAGMA mcp_publish_tool(
    'FindInAST',
    'Search code by semantic category: calls, imports, definitions, loops, conditionals, strings, comments. More targeted than grep — finds structural patterns, not text matches. Output is grep-style: file:line  context.',
    'SELECT printf(''%s:%d  %s'', file_path, start_line, context) AS line
     FROM find_in_ast(
        _resolve($file_pattern),
        $kind,
        COALESCE(NULLIF($name_pattern, ''null''), ''%'')
    )',
    '{"file_pattern": {"type": "string", "description": "Glob pattern for files (e.g. src/**/*.py)"}, "kind": {"type": "string", "description": "What to find: calls, imports, definitions, loops, conditionals, strings, comments"}, "name_pattern": {"type": "string", "description": "SQL LIKE filter on name (e.g. connect%). Default: all"}}',
    '["file_pattern", "kind"]',
    'text'
);

PRAGMA mcp_publish_tool(
    'FindCode',
    'Search code with CSS selectors. More expressive than FindDefinitions or FindInAST — compose :has, :not, ::callers, combinators. Examples: .func#validate, .func:has(.call#execute):not(:has(try)), .class > .func.',
    'SELECT printf(''%s:%d-%d | %s | %s | %s'', file_path, start_line, end_line, COALESCE(name, ''''), kind, peek) AS line
     FROM find_code(
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
    'SELECT printf(''%s'',
        CASE WHEN line_number = match_start AND match_start > 1
             THEN chr(10) || ''# '' || file_path || '':'' || match_start || ''-'' || match_end
                  || COALESCE('' ('' || name || '')'', '''') || chr(10)
                  || printf(''%4d| %s'', line_number, content)
             WHEN line_number = match_start
             THEN ''# '' || file_path || '':'' || match_start || ''-'' || match_end
                  || COALESCE('' ('' || name || '')'', '''') || chr(10)
                  || printf(''%4d| %s'', line_number, content)
             ELSE printf(''%4d| %s'', line_number, content)
        END) AS line
     FROM view_code(
        _resolve($file_pattern),
        $selector,
        NULLIF($language, ''null''),
        COALESCE(TRY_CAST(NULLIF($context, ''null'') AS INT), 0)
    )',
    '{"file_pattern": {"type": "string", "description": "Glob pattern for files"}, "selector": {"type": "string", "description": "CSS selector to match"}, "language": {"type": "string", "description": "Language override (default: auto-detect)"}, "context": {"type": "string", "description": "Lines of context around each match (default: 0)"}}',
    '["file_pattern", "selector"]',
    'text'
);
