-- Fledgling: Git Repository Tool Publications
--
-- MCP tool publications for git repository state.
-- Wraps macros from sql/repo.sql and sql/structural.sql.
--
-- Embeds session_root at publish time (getvariable is not available
-- in MCP tool execution context). Must be loaded after sandbox.sql
-- and repo.sql, with session_root already set.
--
-- Macros without tool publications (use via query tool):
--   recent_changes, branch_list, tag_list, working_tree_status,
--   structural_diff, changed_function_summary

PRAGMA mcp_publish_tool(
    'GitDiffSummary',
    'File-level summary of changes between two git revisions. Shows added, deleted, and modified files with sizes. For function-level analysis, use structural_diff() or changed_function_summary() via the query tool.',
    'SELECT * FROM file_changes(
        $from_rev,
        $to_rev,
        COALESCE(_resolve(NULLIF($path, ''null'')), ''.'')
    )',
    '{"from_rev": {"type": "string", "description": "Base revision (e.g. HEAD~1, main, commit hash)"}, "to_rev": {"type": "string", "description": "Target revision (e.g. HEAD, feature-branch)"}, "path": {"type": "string", "description": "Repository path (default: project root)"}}',
    '["from_rev", "to_rev"]',
    'markdown'
);

PRAGMA mcp_publish_tool(
    'GitShow',
    'Show file content at a specific git revision with metadata (path, ref, size). Replaces `git show rev:path`.',
    'SELECT * FROM file_at_version(
        $file,
        $rev,
        COALESCE(_resolve(NULLIF($path, ''null'')), ''.'')
    )',
    '{"file": {"type": "string", "description": "Repository-relative file path (e.g. README.md, sql/repo.sql)"}, "rev": {"type": "string", "description": "Git revision (e.g. HEAD, HEAD~1, main, v1.0, commit hash)"}, "path": {"type": "string", "description": "Repository path (default: project root)"}}',
    '["file", "rev"]',
    'json'
);

PRAGMA mcp_publish_tool(
    'GitDiffFile',
    'Line-level unified diff of a single file between two revisions. Shows added (+), removed (-), and context lines. Use GitDiffSummary first to find changed files.',
    'SELECT printf(''%s %s'',
        CASE line_type WHEN ''ADDED'' THEN ''+'' WHEN ''REMOVED'' THEN ''-'' ELSE '' '' END,
        content) AS line
     FROM file_diff(
        $file,
        $from_rev,
        $to_rev,
        COALESCE(_resolve(NULLIF($path, ''null'')), ''.'')
    )',
    '{"file": {"type": "string", "description": "File path (repo-relative)"}, "from_rev": {"type": "string", "description": "Base revision (e.g. HEAD~1, main)"}, "to_rev": {"type": "string", "description": "Target revision (e.g. HEAD)"}, "path": {"type": "string", "description": "Repository path (default: project root)"}}',
    '["file", "from_rev", "to_rev"]',
    'text'
);
