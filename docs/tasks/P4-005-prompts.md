# P4-005: MCP Prompt Templates

## Status: Done

## Problem

The skill guides (`explore-codebase.md`, `investigate-issue.md`, `review-changes.md`) are static files. MCP's prompt protocol was designed for exactly this: context-aware, parameterized instructions the client can request.

## Solution

Convert skill guides into FastMCP prompt templates that incorporate live project context. Each prompt returns workflow instructions pre-filled with relevant data from the project.

## Prompts to Add

### `explore`
**Arguments:** `path` (optional)
**Returns:** Exploration workflow with project overview, doc outline, and suggested starting points pre-filled from P4-004's explore logic.

### `investigate`
**Arguments:** `symptom` (required — error message, function name, or file)
**Returns:** Investigation workflow with relevant definitions pre-found and suggested next steps.

### `review`
**Arguments:** `from_rev`, `to_rev` (both optional)
**Returns:** Review checklist with change summary and complexity deltas pre-loaded.

## Key difference from P4-004

P4-004 compound tools return **data** (the briefing). P4-005 prompts return **instructions + data** (workflow steps with context). The agent uses prompts to learn *how* to approach a task; it uses compound tools to get the *information* for the task.

## Implementation

```python
# fledgling/pro/prompts.py

def register_prompts(mcp, con, defaults):
    @mcp.prompt()
    async def explore(path: str = None) -> str:
        # Gather context using P4-004 logic
        context = await _explore_context(con, defaults, path)
        return EXPLORE_TEMPLATE.format(**context)

EXPLORE_TEMPLATE = """## Explore Codebase

### Your Project
{overview}

### Suggested Workflow
1. Start with CodeStructure on {dominant_language} files
2. Read: {suggested_entry_points}
3. Check docs: {doc_sections}
4. Recent activity: {recent_commits}

### Available Tools
- CodeStructure, FindDefinitions for code navigation
- MDSection, MDOverview for documentation
- recent_changes, GitDiffSummary for history
"""
```

## Testing

- Each prompt returns non-empty content with instructions
- Prompts include live data from the project
- Missing data handled gracefully
- Prompt metadata (name, description, arguments) correct in MCP protocol
- Prompts appear in `mcp.list_prompts()`

## Files

- Add: `fledgling/pro/prompts.py`
- Modify: `fledgling/pro/server.py`
- Add: `tests/test_pro_prompts.py`
