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
