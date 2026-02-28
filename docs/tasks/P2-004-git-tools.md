# P2-004: Git Tools (GitChanges, GitBranches)

**Status:** Complete
**Depends on:** None (can be implemented independently)
**Estimated scope:** Tool publications only — existing macros match signatures

## Goal

Publish 2 MCP tools for git repository state. Both macros exist in `repo.sql`.
Param names differ slightly between tool and macro (by design — tool names
are user-facing, macro names follow SQL convention).

## Tools

| Tool | Required Params | Optional Params | Maps To |
|------|----------------|-----------------|---------|
| GitChanges | — | count, path | `recent_changes(n, repo)` |
| GitBranches | — | — | `branch_list(repo)` |

## Files

| File | Action | Description |
|------|--------|-------------|
| `sql/repo.sql` | No change | Macros already match tool signatures |
| `sql/tools/git.sql` | Create | 2 `mcp_publish_tool()` calls |

## Path Resolution

Git tools use `session_root` as the default repo path (instead of `'.'`)
so they work correctly under the sandbox. The `resolve()` macro is used
for the optional `path` param on GitChanges.

```sql
-- GitBranches: no params, uses session_root directly
SELECT * FROM branch_list(getvariable('session_root'))

-- GitChanges: optional path defaults to session_root
SELECT * FROM recent_changes(
    COALESCE(TRY_CAST(NULLIF($count, 'null') AS INT), 10),
    COALESCE(resolve(NULLIF($path, 'null')), getvariable('session_root'))
)
```

## Tool Publications (sql/tools/git.sql)

GitChanges has all-optional params. GitBranches has no params at all.

For GitBranches, the SQL template has no `$param` references so the
duckdb_mcp#19 bug doesn't apply.

Tool descriptions:
- **GitChanges**: "Recent commit history. Replaces `git log --oneline`."
- **GitBranches**: "List all branches with current branch marked."

## Acceptance Criteria

These tests in `test_mcp_server.py` must pass:
- `TestGitChanges` (2 tests): returns commits, count limit
- `TestGitBranches` (1 test): lists branches

Existing `test_repo.py` (18 tests) unaffected.
