-- Fledgling: File Access Tool Publications
--
-- MCP tool publications for file reading.
-- Wraps macros from sql/source.sql.
--
-- Embeds session_root at publish time (getvariable is not available
-- in MCP tool execution context). Must be loaded after sandbox.sql
-- and source.sql, with session_root already set.
--
-- Git mode dispatch (commit param) is handled in tool templates because
-- git functions (git_tree, git_uri) require duck_tails, while the backing
-- macros in source.sql depend only on read_lines.
--
-- Macros without tool publications (use via query tool):
--   list_files, project_overview, read_as_table

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
    'json'
);
