# P3-003: GitShow Tool (File at Version)

**Status:** Done
**Depends on:** P2-004 (git tools), P2-005 (sandbox/resolve)
**Estimated scope:** Tool publication only — macro already exists

## Motivation

`git show` accounts for 91 bash calls in the conversation analysis. The
macro `file_at_version(file, rev, repo)` already exists in `repo.sql` and
wraps `git_read(git_uri(...))`. It just needs an MCP tool publication.

During the P2-004 session, reading files at specific revisions was needed to
compare the prior state of `test_mcp_server.py` on main vs the feature branch
before resolving conflicts. The `ReadLines` tool already supports a `commit`
parameter for this, but `GitShow` would be the explicit git-native equivalent
with different output shape (includes metadata like file_path, ref, size).

## Design Considerations

### Overlap with ReadLines

`ReadLines` with `commit` parameter already does `git show rev:path`
semantically. The difference:

- **ReadLines(file_path, commit)**: Returns line-numbered content in a markdown
  table. Designed for code reading with context/match filtering.
- **GitShow(file, rev)**: Returns raw content with metadata (path, ref, size).
  Designed for git inspection — "what did this file look like at v1.0?"

The question is whether both are needed or whether ReadLines subsumes this.

### Recommendation

Publish as a tool anyway — it's a single `mcp_publish_tool()` call with zero
new macro work. Let usage data determine whether it earns its keep. If it's
redundant with ReadLines+commit, it can be removed later.

## Tools

| Tool | Required Params | Optional Params | Maps To |
|------|----------------|-----------------|---------|
| GitShow | file, rev | path | `file_at_version(file, rev, repo)` |

## Files

| File | Action | Description |
|------|--------|-------------|
| `sql/repo.sql` | No change | `file_at_version` macro already exists |
| `sql/tools/git.sql` | Update | Add `mcp_publish_tool()` call |
| `tests/test_mcp_server.py` | Update | MCP tool test |

## Acceptance Criteria

- `TestGitShow` test passes:
  - Returns file content at HEAD
  - Returns file content at a prior revision
  - Returns metadata (file_path, ref, size_bytes)
- Existing tests unaffected
