# P4-005: MCP Prompt Templates

## Status: Ready

## Problem

The skill guides (`explore-codebase.md`, `investigate-issue.md`, `review-changes.md`) are static markdown files. The agent can read them via Help but can't request them as structured prompts. MCP's prompt protocol is designed for exactly this: the client requests a prompt template, the server fills in context-aware content.

## Solution

Convert the skill guides into FastMCP prompt templates that incorporate live project context. The prompt includes both the workflow instructions and relevant project data.

## Prompts to Add

### `explore`
**Arguments:** `path` (optional, defaults to project root)
**Returns:** Exploration instructions + project overview data pre-filled.

```python
@mcp.prompt()
async def explore(path: str = ".") -> str:
    """Systematic codebase exploration workflow with project context."""
    overview = con.project_overview(path).fetchall()
    docs = con.doc_outline(f"{path}/**/*.md").limit(10).fetchall()

    return f"""## Explore Codebase

### Project Context
{_format_overview(overview)}

### Documentation Available
{_format_doc_list(docs)}

### Workflow
1. Start with CodeStructure on the dominant language files
2. Read key entry points identified above
3. Check doc sections for architecture guidance
4. Use recent_changes to understand current focus

### Tools to Use
- CodeStructure, FindDefinitions for code
- MDSection, MDOverview for docs
- recent_changes, GitDiffSummary for history
"""
```

### `investigate`
**Arguments:** `symptom` (required — error message, function name, or file)
**Returns:** Investigation instructions with relevant definitions pre-found.

```python
@mcp.prompt()
async def investigate(symptom: str) -> str:
    """Debugging workflow with pre-located relevant code."""
    # Try to find the symptom in definitions
    defs = con.find_definitions("**/*", name_pattern=f"%{symptom}%").limit(5).fetchall()

    return f"""## Investigate: {symptom}

### Possibly Relevant Definitions
{_format_defs(defs) if defs else "No definitions found matching the symptom."}

### Workflow
1. Locate the code: FindDefinitions or ReadLines with match
2. Read with context: ReadLines with lines and ctx parameters
3. Check history: GitDiffSummary for recent changes
4. Trace dependencies: find_in_ast for calls and imports
5. Check callers: function_callers for impact analysis

### Principles
- Understand before fixing
- Check what changed recently (often the cause)
- Trace from symptom to root cause, not the reverse
"""
```

### `review`
**Arguments:** `from_rev` (default HEAD~1), `to_rev` (default HEAD)
**Returns:** Review instructions with change summary pre-loaded.

```python
@mcp.prompt()
async def review(from_rev: str = "HEAD~1", to_rev: str = "HEAD") -> str:
    """Code review workflow with change summary pre-loaded."""
    changes = con.file_changes(from_rev, to_rev).limit(20).fetchall()
    functions = con.changed_function_summary(from_rev, to_rev, "**/*").limit(10).fetchall()

    return f"""## Review: {from_rev}..{to_rev}

### Changed Files
{_format_changes(changes)}

### Changed Functions (by complexity)
{_format_functions(functions)}

### Workflow
1. Read diffs for high-complexity changes first
2. Check structural_diff for added/removed definitions
3. Verify test coverage for new functions
4. Check callers of modified functions for impact

### Checklist
- [ ] No obvious bugs in changed logic
- [ ] Error handling present for new code paths
- [ ] Tests exist for new functions
- [ ] No unintended scope (changes match PR description)
"""
```

## Implementation Notes

- Prompts use `@mcp.prompt()` decorator
- Each prompt calls fledgling macros to gather context
- Context is formatted inline (not as tool results)
- Prompts are listed via MCP `prompts/list` protocol
- The agent requests them via `prompts/get` with arguments

## Testing

- Each prompt returns non-empty content
- Prompts include both instructions and live data
- Missing data (no git, no docs) handled gracefully
- Arguments are optional with sensible defaults
- Prompt metadata (name, description, arguments) is correct

## Files

- Add: `fledgling/pro/prompts.py`
- Modify: `fledgling/pro/server.py` (register prompts)
- Add tests: `tests/test_pro_prompts.py`
