-- Fledgling: File Access Tool Publications
--
-- MCP tool publications for file listing, reading, and data preview.
-- Wraps macros from sql/source.sql.
--
-- Embeds session_root at publish time (getvariable is not available
-- in MCP tool execution context). Must be loaded after sandbox.sql
-- and source.sql, with session_root already set.
--
-- Git mode dispatch (commit param) is handled in tool templates because
-- git functions (git_tree, git_uri) require duck_tails, while the backing
-- macros in source.sql depend only on read_lines.

SELECT mcp_publish_tool(
    'ListFiles',
    'List files matching a pattern. Filesystem mode uses glob syntax (e.g. src/**/*.py). Git mode (with commit) uses SQL LIKE syntax (e.g. src/%.py).',
    'SELECT * FROM list_files(
        CASE WHEN NULLIF($commit, ''null'') IS NULL
             THEN CASE WHEN $pattern[1] = ''/'' THEN $pattern
                       ELSE ''' || getvariable('session_root') || '/'' || $pattern END
             ELSE $pattern
        END,
        NULLIF($commit, ''null'')
    )',
    '{"pattern": {"type": "string", "description": "File pattern: glob syntax for filesystem (src/**/*.py), SQL LIKE for git mode (src/%.py)"}, "commit": {"type": "string", "description": "Git revision (e.g. HEAD, main). Omit for filesystem mode."}}',
    '["pattern"]',
    'markdown'
);

SELECT mcp_publish_tool(
    'ReadLines',
    'Read lines from a file with optional line range, context, and match filtering. Replaces cat/head/tail.',
    'SELECT * FROM read_source(
        CASE WHEN NULLIF($commit, ''null'') IS NULL
             THEN CASE WHEN $file_path[1] = ''/'' THEN $file_path
                       ELSE ''' || getvariable('session_root') || '/'' || $file_path END
             ELSE git_uri(''' || getvariable('session_root') || ''', $file_path, NULLIF($commit, ''null''))
        END,
        NULLIF($lines, ''null''),
        COALESCE(TRY_CAST(NULLIF($ctx, ''null'') AS INT), 0),
        NULLIF($match, ''null'')
    )',
    '{"file_path": {"type": "string", "description": "Path to the file (absolute or relative to project root)"}, "lines": {"type": "string", "description": "Line selection: single (42), range (10-20), or context (42 +/-5)"}, "ctx": {"type": "string", "description": "Context lines around selection (default 0)"}, "match": {"type": "string", "description": "Case-insensitive substring filter on line content"}, "commit": {"type": "string", "description": "Git revision (e.g. HEAD, main~2). Uses repo-relative path."}}',
    '["file_path"]',
    'markdown'
);

SELECT mcp_publish_tool(
    'ReadAsTable',
    'Preview structured data files (CSV, JSON) as tables. Uses DuckDB auto-detection for schema inference.',
    'SELECT * FROM read_as_table(
        CASE WHEN $file_path[1] = ''/'' THEN $file_path
             ELSE ''' || getvariable('session_root') || '/'' || $file_path END,
        COALESCE(TRY_CAST(NULLIF($limit, ''null'') AS INT), 100)
    )',
    '{"file_path": {"type": "string", "description": "Path to a CSV, JSON, or other structured data file"}, "limit": {"type": "string", "description": "Maximum rows to return (default 100)"}}',
    '["file_path"]',
    'markdown'
);
