# P4-001: MCP Resources — Always-Available Context

## Status: Ready

## Problem

The agent must spend tool calls to learn basic project context: `project_overview()` for languages, `dr_fledgling()` for diagnostics, `doc_outline('**/*.md')` for documentation structure. This information rarely changes within a session but costs a tool call each time.

## Solution

Expose static/slow-changing data as MCP **resources** instead of tools. Resources appear in the agent's context automatically — no tool call needed. FastMCP supports both static and dynamic resources natively.

## Resources to Add

### `fledgling://project`
**Content:** Project overview — languages, file counts, directory structure.
**Refresh:** Once at startup (or on first access).
**Source:** `project_overview()` + `list_files('*')` top-level listing.

### `fledgling://diagnostics`
**Content:** Fledgling version, profile, loaded modules, extensions.
**Source:** `dr_fledgling()`.

### `fledgling://docs`
**Content:** Documentation outline — all markdown files with section IDs.
**Refresh:** Once at startup.
**Source:** `doc_outline('**/*.md')`.

### `fledgling://git`
**Content:** Current branch, recent commits (last 5), working tree status.
**Refresh:** On each access (cheap queries).
**Source:** `branch_list()`, `recent_changes(5)`, `working_tree_status()`.

## Implementation

```python
@mcp.resource("fledgling://project")
async def project_resource() -> str:
    overview = con.project_overview().fetchall()
    # Format as readable text
    ...

@mcp.resource("fledgling://diagnostics")
async def diagnostics_resource() -> str:
    return _format_markdown_table(
        *_fetch(con.dr_fledgling())
    )
```

## Testing

- Resource appears in `mcp.list_resources()`
- Resource content is non-empty
- Resource content matches direct macro output
- Multiple accesses return consistent data
- Resources work without prior tool calls

## Files

- Modify: `fledgling/pro/server.py`
- Add tests: `tests/test_pro_server.py`
