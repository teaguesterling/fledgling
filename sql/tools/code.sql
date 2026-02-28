-- Fledgling: Code Intelligence Tool Publications
--
-- Publishes 4 MCP tools for AST-based code analysis.
-- Macros are defined in sql/code.sql; this file only creates MCP bindings.
--
-- mcp_publish_tool(name, description, sql_template, properties_json, required_json, format)
-- format = 'markdown' renders results as markdown tables.

SELECT mcp_publish_tool(
    'FindDefinitions',
    'AST-based definition search — not grep. Finds functions, classes, and variable definitions. Use name_pattern with SQL LIKE wildcards (%) to filter by name.',
    'SELECT * FROM find_definitions(
        resolve($file_pattern),
        COALESCE(NULLIF($name_pattern, ''null''), ''%'')
    )',
    '{"file_pattern": {"type": "string", "description": "Glob pattern for files to search (e.g. src/**/*.py)"}, "name_pattern": {"type": "string", "description": "SQL LIKE pattern to filter by name (e.g. parse%). Default: % (all)"}}',
    '["file_pattern"]',
    'markdown'
);

SELECT mcp_publish_tool(
    'FindCalls',
    'Find where functions or methods are called. Uses AST parsing to identify call sites, not text matching. Use name_pattern with SQL LIKE wildcards (%) to filter.',
    'SELECT * FROM find_calls(
        resolve($file_pattern),
        COALESCE(NULLIF($name_pattern, ''null''), ''%'')
    )',
    '{"file_pattern": {"type": "string", "description": "Glob pattern for files to search (e.g. src/**/*.py)"}, "name_pattern": {"type": "string", "description": "SQL LIKE pattern to filter by call name (e.g. connect%). Default: % (all)"}}',
    '["file_pattern"]',
    'markdown'
);

SELECT mcp_publish_tool(
    'FindImports',
    'Find import/include/require statements in source files. Uses AST parsing to identify language-specific import constructs.',
    'SELECT * FROM find_imports(
        resolve($file_pattern)
    )',
    '{"file_pattern": {"type": "string", "description": "Glob pattern for files to search (e.g. src/**/*.py)"}}',
    '["file_pattern"]',
    'markdown'
);

SELECT mcp_publish_tool(
    'CodeStructure',
    'Top-level structural overview of source files: definitions with line counts. Shows what is defined in each file without implementation details.',
    'SELECT * FROM code_structure(
        resolve($file_pattern)
    )',
    '{"file_pattern": {"type": "string", "description": "Glob pattern for files to analyze (e.g. src/**/*.py)"}}',
    '["file_pattern"]',
    'markdown'
);
