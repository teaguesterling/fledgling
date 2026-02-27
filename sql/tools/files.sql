-- Source Sextant: File Tools (ListFiles, ReadLines, ReadAsTable)
--
-- MCP tool publications for file access. These wrap macros from
-- source.sql with parameter handling for the MCP transport layer.
--
-- Path resolution: getvariable('sextant_root') is NOT available in the
-- MCP tool execution context, so we bake the root path into the SQL
-- template at registration time via string concatenation.
--
-- Patterns used:
--   sextant_root baked via || getvariable('sextant_root') ||
--   NULLIF($param, 'null')             optional string (duckdb_mcp#19)
--   COALESCE(TRY_CAST(...AS INT), d)   optional integer with default
--   CASE WHEN $p[1] = '/'              absolute vs relative path
--   UNION ALL with WHERE               git vs filesystem dispatch

-- ListFiles: List files matching a pattern.
-- Filesystem mode uses glob syntax (*.sql), git mode uses SQL LIKE (%.sql).
SELECT mcp_publish_tool(
    'ListFiles',
    'List files matching a pattern. Uses glob syntax (e.g. src/*.py, **/*.sql) for filesystem. With commit param, uses SQL LIKE syntax (e.g. src/%.py) against git tree.',
    'SELECT * FROM ('
    || '    SELECT file AS file_path FROM glob('
    || '        CASE WHEN $pattern[1] = ''/'''
    || '             THEN $pattern'
    || '             ELSE ''' || getvariable('sextant_root') || '/'' || $pattern'
    || '        END'
    || '    )'
    || '    WHERE NULLIF($commit, ''null'') IS NULL'
    || '    UNION ALL'
    || '    SELECT file_path FROM git_tree(''.'', NULLIF($commit, ''null''))'
    || '    WHERE NULLIF($commit, ''null'') IS NOT NULL'
    || '      AND file_path LIKE $pattern'
    || ') ORDER BY file_path',
    '{"pattern": {"type": "string", "description": "File pattern: glob syntax for filesystem (*.sql), SQL LIKE for git mode (%.sql)"}, "commit": {"type": "string", "description": "Git revision (e.g. HEAD, abc123). Omit for filesystem mode."}}',
    '["pattern"]',
    'markdown'
);

-- ReadLines: Read lines from a file with optional filtering.
-- Replaces cat/head/tail. Supports line ranges, context, grep, and git revisions.
SELECT mcp_publish_tool(
    'ReadLines',
    'Read lines from a file with optional filtering. Replaces cat/head/tail. Supports line ranges (e.g. "10-20", "42"), context lines around selection, pattern matching (case-insensitive grep), and reading from git revisions.',
    'SELECT * FROM read_source('
    || '    CASE WHEN NULLIF($commit, ''null'') IS NOT NULL'
    || '         THEN git_uri(''.'', $file_path, NULLIF($commit, ''null''))'
    || '         WHEN $file_path[1] = ''/'''
    || '         THEN $file_path'
    || '         ELSE ''' || getvariable('sextant_root') || '/'' || $file_path'
    || '    END,'
    || '    NULLIF($lines, ''null''),'
    || '    COALESCE(TRY_CAST(NULLIF($ctx, ''null'') AS INT), 0),'
    || '    NULLIF($match, ''null'')'
    || ')',
    '{"file_path": {"type": "string", "description": "Path to the file to read"}, "lines": {"type": "string", "description": "Line selection: single line (42), range (10-20), or with context (42 +/-5)"}, "ctx": {"type": "string", "description": "Number of context lines around selection (default: 0)"}, "match": {"type": "string", "description": "Filter to lines containing this text (case-insensitive)"}, "commit": {"type": "string", "description": "Git revision to read from (e.g. HEAD, abc123). Omit for current filesystem."}}',
    '["file_path"]',
    'markdown'
);

-- ReadAsTable: Read a data file as a structured table.
-- Uses DuckDB auto-detection for CSV, JSON, Parquet, etc.
--
-- NOTE: Uses FROM $file_path directly (DuckDB string replacement scan)
-- instead of query_table() to avoid Python namespace collisions
-- (e.g. `import json` shadows .json file detection).
--
-- Path resolution limitation: DuckDB's FROM replacement scan requires
-- a string literal, so we cannot wrap $file_path in a CASE expression
-- for sextant_root resolution like the other tools do. In production,
-- the init script sets file_search_path to the project root, and
-- allowed_directories enforces sandboxing. MCP clients should pass
-- absolute paths for reliable behavior.
SELECT mcp_publish_tool(
    'ReadAsTable',
    'Read a data file (CSV, JSON, Parquet, etc.) as a structured table using DuckDB auto-detection. Returns up to limit rows. Use absolute paths.',
    'SELECT * FROM $file_path'
    || ' LIMIT COALESCE(TRY_CAST(NULLIF($limit, ''null'') AS INT), 100)',
    '{"file_path": {"type": "string", "description": "Absolute path to the data file (CSV, JSON, Parquet, etc.)"}, "limit": {"type": "string", "description": "Maximum number of rows to return (default: 100)"}}',
    '["file_path"]',
    'markdown'
);
