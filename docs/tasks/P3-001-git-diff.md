# P3-001: GitDiff Tool

**Status:** Not started
**Depends on:** P2-004 (git tools), P2-005 (sandbox/resolve)
**Estimated scope:** New macro + tool publication

## Motivation

`git diff` accounts for 708 bash calls (4.2% of all bash) in the conversation
analysis. During the P2-004 review/merge session, diff was the single most
frequent operation — checking PR diffs, comparing branches, viewing staged
changes. It's the highest-value missing git read tool.

duck_tails provides `read_git_diff(uri1, uri2)` which returns unified diff text
between two git URIs, and `diff_text(a, b)` / `text_diff_lines(diff)` for
structured line-level output. The building blocks exist but need a usable
macro and MCP tool wrapper.

## Design Considerations

### What callers actually need

From the session, these were the real queries:

1. **`git diff rev1..rev2` (branch comparison)** — "What changed between main
   and this branch?" Used before PRs, during reviews.
2. **`git diff --stat`** — "Which files changed and how much?" The summary view.
3. **`git diff -- file`** — "Show me the diff for this specific file."

Working tree diffs (`git diff` with no args, `git diff --staged`) are less
useful in MCP context because the LLM rarely has uncommitted changes of its
own to inspect — it usually wants to compare commits or branches.

### Proposed approach

Two-level output: a **file-level summary** (like `--stat`) by default, with
an optional `file_path` parameter to drill into a specific file's line-level
diff. This avoids dumping massive unified diffs for multi-file changes.

**File-level summary** uses `git_tree` comparison (no new extension functions
needed):

```sql
-- Compare trees at two revisions to find changed files
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
   OR a.size_bytes != b.size_bytes
```

**File-level diff** uses `read_git_diff` + `text_diff_lines`:

```sql
-- Line-level diff for a specific file between two revisions
SELECT * FROM text_diff_lines(
    (SELECT diff_text FROM read_git_diff(
        git_uri(repo, file, from_rev),
        git_uri(repo, file, to_rev)
    ))
)
```

### Open questions

- Should the file summary compare by content hash rather than size? Two files
  can have the same size but different content. `git_tree` doesn't expose the
  blob hash, so this may require `read_git_diff` per file (expensive for large
  repos). Alternatively, accept the false-negative rate as a tradeoff.
- Should there be a `context` parameter (like `git diff -U3`) for the
  line-level view? `text_diff_lines` may not support this.
- The `read_git_diff` function returns an error when given directory paths
  rather than file paths. Need to verify behavior with binary files.

## Tools

| Tool | Required Params | Optional Params | Maps To |
|------|----------------|-----------------|---------|
| GitDiff | from_rev, to_rev | file_path, path | `file_changes(from, to, repo)` or `file_diff(file, from, to, repo)` |

Alternatively, this could be two tools:
- `GitDiffSummary` (file-level, `--stat` equivalent)
- `GitDiffFile` (line-level, single file)

## Files

| File | Action | Description |
|------|--------|-------------|
| `sql/repo.sql` | Update | Add `file_changes()` and/or `file_diff()` macros |
| `sql/tools/git.sql` | Update | Add `mcp_publish_tool()` call(s) |
| `tests/test_repo.py` | Update | Macro-level tests for new macros |
| `tests/test_mcp_server.py` | Update | MCP tool tests |

## Acceptance Criteria

- `TestGitDiff` tests pass in `test_mcp_server.py`:
  - Returns changed files between two revisions
  - Shows add/delete/modify status correctly
  - Line-level diff for a specific file shows additions and removals
- Existing tests unaffected
