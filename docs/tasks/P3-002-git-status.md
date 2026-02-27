# P3-002: GitStatus Tool

**Status:** Not started
**Depends on:** P2-004 (git tools), P2-005 (sandbox/resolve)
**Estimated scope:** New macro + tool publication. Requires investigation — duck_tails has no `git_status` function.

## Motivation

`git status` accounts for 775 bash calls — the single most frequent git read
operation in the conversation analysis. It's the first thing an LLM checks
before commits, merges, and conflict resolution.

During the P2-004 session, `git status` was used to:
- Check for uncommitted changes before merging
- Verify merge conflict state
- Confirm clean working tree after conflict resolution
- Check branch tracking state

## Design Considerations

### duck_tails gap

Unlike `git_diff`, there is **no `git_status` function** in duck_tails.
The extension provides tree/log/branch/tag queries against the git object
database, but working tree status requires comparing the index against both
HEAD and the working directory — a fundamentally different operation.

### Possible approaches

1. **Shell out via DuckDB** — Use a DuckDB macro that calls `git status
   --porcelain` via a system command. DuckDB doesn't have a built-in
   shell-out mechanism, so this would need an extension or workaround.

2. **Synthesize from git_tree** — Compare `git_tree('.', 'HEAD')` against
   the filesystem (via `glob` or `read_lines`) to detect modifications.
   This gives tracked-file changes but misses staged vs unstaged distinction
   and untracked files.

3. **Upstream contribution** — Add `git_status()` to duck_tails. This is
   probably the right long-term answer since libgit2 (which duck_tails
   likely uses) has `git_status_list_new()`.

4. **Defer** — Accept that `git status` stays as a bash call. It's fast,
   well-understood, and the output is small. The MCP benefit is primarily
   about structured output, not permission reduction.

### Recommendation

Start with approach 3 (upstream) if feasible. If not, approach 4 (defer) is
acceptable — `git status` is a single quick bash call, not a multi-step
pipeline. The 775 calls are high-frequency but low-cost individually.

File an issue on duck_tails requesting `git_status(repo)` that returns:
```
| file_path | index_status | worktree_status |
```

Where status values are: new, modified, deleted, renamed, untracked, ignored.

## Tools

| Tool | Required Params | Optional Params | Maps To |
|------|----------------|-----------------|---------|
| GitStatus | — | path | `working_tree_status(repo)` (pending upstream) |

## Files

| File | Action | Description |
|------|--------|-------------|
| `sql/repo.sql` | Update | Add `working_tree_status()` macro (once upstream exists) |
| `sql/tools/git.sql` | Update | Add `mcp_publish_tool()` call |
| `tests/test_repo.py` | Update | Macro-level tests |
| `tests/test_mcp_server.py` | Update | MCP tool tests |

## Acceptance Criteria

- `TestGitStatus` tests pass:
  - Shows modified files in working tree
  - Shows untracked files
  - Returns empty result on clean working tree
- Existing tests unaffected

## Blockers

- Requires `git_status()` in duck_tails, or a decision to use a workaround approach.
