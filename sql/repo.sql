-- Fledgling: Repository Intelligence Macros (duck_tails)
--
-- Structured access to git repository state. Replaces git CLI
-- commands with composable, queryable results.

-- recent_changes: What changed recently in the repository.
-- The most common git query — replaces `git log --oneline`.
--
-- Examples:
--   SELECT * FROM recent_changes();
--   SELECT * FROM recent_changes(10);
--   SELECT * FROM recent_changes(5, '/path/to/repo');
CREATE OR REPLACE MACRO recent_changes(n := 10, repo := '.') AS TABLE
    SELECT
        commit_hash[:8] AS hash,
        author_name AS author,
        author_date AS date,
        message
    FROM git_log(repo)
    LIMIT n;

-- branch_list: List all branches with current branch marked.
-- Replaces `git branch -a`.
--
-- Examples:
--   SELECT * FROM branch_list();
--   SELECT * FROM branch_list('/path/to/repo');
CREATE OR REPLACE MACRO branch_list(repo := '.') AS TABLE
    SELECT
        branch_name,
        commit_hash[:8] AS hash,
        is_current,
        is_remote
    FROM git_branches(repo)
    ORDER BY is_current DESC, is_remote, branch_name;

-- tag_list: List all tags with metadata.
-- Replaces `git tag -l`.
--
-- Examples:
--   SELECT * FROM tag_list();
CREATE OR REPLACE MACRO tag_list(repo := '.') AS TABLE
    SELECT
        tag_name,
        commit_hash[:8] AS hash,
        tagger_name,
        tagger_date,
        message,
        is_annotated
    FROM git_tags(repo)
    ORDER BY tagger_date DESC NULLS LAST;

-- repo_files: List all tracked files at a given revision.
-- Replaces `git ls-tree`.
--
-- Examples:
--   SELECT * FROM repo_files('HEAD');
--   SELECT * FROM repo_files('HEAD', '/path/to/repo');
CREATE OR REPLACE MACRO repo_files(rev := 'HEAD', repo := '.') AS TABLE
    SELECT
        file_path,
        file_ext,
        size_bytes,
        kind,
        is_text
    FROM git_tree(repo, rev)
    ORDER BY file_path;

-- file_at_version: Read a file as it existed at a specific revision.
-- Replaces `git show revision:path`.
--
-- Examples:
--   SELECT * FROM file_at_version('README.md', 'HEAD~1');
--   SELECT * FROM file_at_version('src/main.py', 'v1.0', '/path/to/repo');
CREATE OR REPLACE MACRO file_at_version(file, rev, repo := '.') AS TABLE
    SELECT
        file_path,
        ref,
        size_bytes,
        text AS content
    FROM git_read(git_uri(repo, file, rev));

-- file_changes: File-level summary of changes between two revisions.
-- Compares git trees using blob_hash to detect modifications even when
-- file sizes are unchanged. Like `git diff --stat`.
--
-- Examples:
--   SELECT * FROM file_changes('HEAD~1', 'HEAD');
--   SELECT * FROM file_changes('main', 'feature-branch', '/path/to/repo');
CREATE OR REPLACE MACRO file_changes(from_rev, to_rev, repo := '.') AS TABLE
    SELECT
        COALESCE(a.file_path, b.file_path) AS file_path,
        CASE
            WHEN a.file_path IS NULL THEN 'added'
            WHEN b.file_path IS NULL THEN 'deleted'
            ELSE 'modified'
        END AS status,
        a.size_bytes AS old_size,
        b.size_bytes AS new_size
    FROM git_tree(repo, from_rev) a
    FULL OUTER JOIN git_tree(repo, to_rev) b
        ON a.file_path = b.file_path
    WHERE a.file_path IS NULL
       OR b.file_path IS NULL
       OR a.blob_hash != b.blob_hash
    ORDER BY file_path;

-- file_diff: Line-level diff for a specific file between two revisions.
-- Parses diff content lines from read_git_diff into typed rows.
--
-- Examples:
--   SELECT * FROM file_diff('README.md', 'HEAD~1', 'HEAD');
--   SELECT * FROM file_diff('src/main.py', 'main', 'feature', '/path/to/repo');
CREATE OR REPLACE MACRO file_diff(file, from_rev, to_rev, repo := '.') AS TABLE
    WITH raw_diff AS (
        SELECT diff_text
        FROM read_git_diff(
            git_uri(repo, file, from_rev),
            git_uri(repo, file, to_rev)
        )
    ),
    lines AS (
        SELECT unnest(string_split(diff_text, chr(10))) AS line
        FROM raw_diff
    )
    SELECT
        row_number() OVER () AS seq,
        CASE
            WHEN starts_with(line, '+') THEN 'ADDED'
            WHEN starts_with(line, '-') THEN 'REMOVED'
            ELSE 'CONTEXT'
        END AS line_type,
        line[2:] AS content
    FROM lines
    WHERE length(line) > 0;
