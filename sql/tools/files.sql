-- Fledgling: File Access Tool Publications
--
-- MCP tool publications for file reading.
-- Wraps macros from sql/source.sql.
--
-- Uses _resolve() and _session_root() from sandbox.sql for path resolution
-- in tool templates (getvariable is not available in MCP execution context).
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
    'SELECT printf(''%4d  %s'', line_number, content) AS line FROM read_source(
        CASE WHEN NULLIF($commit, ''null'') IS NULL
             THEN _resolve($file_path)
             ELSE git_uri(_session_root(), $file_path, NULLIF($commit, ''null''))
        END,
        NULLIF($lines, ''null''),
        COALESCE(TRY_CAST(NULLIF($ctx, ''null'') AS INT), 0),
        NULLIF($match, ''null'')
    )',
    '{"file_path": {"type": "string", "description": "Path to the file (absolute or relative to project root)"}, "lines": {"type": "string", "description": "Line selection: single (42), range (10-20), or context (42 +/-5)"}, "ctx": {"type": "string", "description": "Context lines around selection (default 0)"}, "match": {"type": "string", "description": "Case-insensitive substring filter on line content"}, "commit": {"type": "string", "description": "Git revision (e.g. HEAD, main~2). Uses repo-relative path."}}',
    '["file_path"]',
    'text'
);
