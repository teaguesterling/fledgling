-- Fledgling: Git Repository Tool Publications
--
-- MCP tool publications for git repository state.
-- Wraps macros from sql/repo.sql.
--
-- Uses _resolve() and _session_root() from sandbox.sql for path resolution
-- in tool templates (getvariable is not available in MCP execution context).

SELECT mcp_publish_tool(
    'GitChanges',
    'Recent commit history. Replaces `git log --oneline`.',
    'SELECT hash, author, date, split_part(message, chr(10), 1) AS message
     FROM recent_changes(
        COALESCE(TRY_CAST(NULLIF($count, ''null'') AS INT), 10),
        COALESCE(_resolve(NULLIF($path, ''null'')), _session_root())
    )',
    '{"count": {"type": "string", "description": "Number of commits to return (default 10)"}, "path": {"type": "string", "description": "Repository path (default: project root)"}}',
    '[]',
    'markdown'
);

SELECT mcp_publish_tool(
    'GitBranches',
    'List all branches with current branch marked.',
    'SELECT * FROM branch_list(_session_root())',
    '{}',
    '[]',
    'markdown'
);

SELECT mcp_publish_tool(
    'GitDiffSummary',
    'File-level summary of changes between two git revisions. Shows added, deleted, and modified files with sizes.',
    'SELECT * FROM file_changes(
        $from_rev,
        $to_rev,
        COALESCE(_resolve(NULLIF($path, ''null'')), _session_root())
    )',
    '{"from_rev": {"type": "string", "description": "Base revision (e.g. HEAD~1, main, commit hash)"}, "to_rev": {"type": "string", "description": "Target revision (e.g. HEAD, feature-branch)"}, "path": {"type": "string", "description": "Repository path (default: project root)"}}',
    '["from_rev", "to_rev"]',
    'markdown'
);

SELECT mcp_publish_tool(
    'GitTags',
    'List all tags with metadata. Shows tag name, commit hash, tagger, date, and whether annotated.',
    'SELECT * FROM tag_list(_session_root())',
    '{}',
    '[]',
    'markdown'
);

SELECT mcp_publish_tool(
    'GitDiffFile',
    'Line-level unified diff for a specific file between two git revisions. Shows additions, removals, and context lines.',
    'SELECT * FROM file_diff(
        $file_path,
        $from_rev,
        $to_rev,
        COALESCE(_resolve(NULLIF($path, ''null'')), _session_root())
    )',
    '{"file_path": {"type": "string", "description": "Repository-relative file path (e.g. sql/repo.sql)"}, "from_rev": {"type": "string", "description": "Base revision (e.g. HEAD~1, main, commit hash)"}, "to_rev": {"type": "string", "description": "Target revision (e.g. HEAD, feature-branch)"}, "path": {"type": "string", "description": "Repository path (default: project root)"}}',
    '["file_path", "from_rev", "to_rev"]',
    'json'
);

SELECT mcp_publish_tool(
    'GitShow',
    'Show file content at a specific git revision with metadata (path, ref, size). Replaces `git show rev:path`.',
    'SELECT * FROM file_at_version(
        $file,
        $rev,
        COALESCE(_resolve(NULLIF($path, ''null'')), _session_root())
    )',
    '{"file": {"type": "string", "description": "Repository-relative file path (e.g. README.md, sql/repo.sql)"}, "rev": {"type": "string", "description": "Git revision (e.g. HEAD, HEAD~1, main, v1.0, commit hash)"}, "path": {"type": "string", "description": "Repository path (default: project root)"}}',
    '["file", "rev"]',
    'json'
);

SELECT mcp_publish_tool(
    'GitStatus',
    'Working tree status: untracked and deleted files compared to HEAD. Does not detect content modifications — use GitDiffSummary for revision diffs. Gitignored files may appear as untracked.',
    'SELECT * FROM working_tree_status(_session_root())',
    '{}',
    '[]',
    'markdown'
);
