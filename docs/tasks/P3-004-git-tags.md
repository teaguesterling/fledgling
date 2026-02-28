# P3-004: GitTags Tool

**Status:** Not started
**Depends on:** P2-004 (git tools), P2-005 (sandbox/resolve)
**Estimated scope:** Tool publication only — macro already exists

## Motivation

`git tag` accounts for 175 bash calls in the conversation analysis. The
macro `tag_list(repo)` already exists in `repo.sql` and wraps `git_tags()`.
It just needs an MCP tool publication.

Tags are used for release management, version checking, and understanding
project history. The `tag_list` macro returns structured tag data including
tagger, date, message, and whether the tag is annotated.

## Tools

| Tool | Required Params | Optional Params | Maps To |
|------|----------------|-----------------|---------|
| GitTags | — | — | `tag_list(repo)` |

## Files

| File | Action | Description |
|------|--------|-------------|
| `sql/repo.sql` | No change | `tag_list` macro already exists |
| `sql/tools/git.sql` | Update | Add `mcp_publish_tool()` call |
| `tests/test_mcp_server.py` | Update | MCP tool test |

## Implementation

Same pattern as `GitBranches` — no parameters, hardcode `session_root`
at publish time:

```sql
SELECT mcp_publish_tool(
    'GitTags',
    'List all tags with metadata. Shows tag name, commit hash, tagger, date, and whether annotated.',
    'SELECT * FROM tag_list(''' || getvariable('session_root') || ''')',
    '{}',
    '[]',
    'markdown'
);
```

## Acceptance Criteria

- `TestGitTags` test passes:
  - Returns tags (if repo has any) or empty result
- Existing tests unaffected
- Note: this repo may not have tags yet, so the test may need to
  create one in a fixture or just verify the tool executes without error
