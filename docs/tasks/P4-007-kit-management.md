# P4-007: Kit Management — The Quartermaster Pattern

## Status: Ready (depends on P4-001, P4-002)

## Problem

The agent sees 26 tools. For a simple "read this file" task, 26 tools is noise. For a complex investigation, the agent needs to know which tools compose well together. The Quartermaster pattern from the Ma experimental program solves this: present curated tool subsets per task type.

## Solution

Define named kits — curated tool subsets with strategy instructions. The agent (or the harness) activates a kit, and only those tools are visible.

## Kit Definitions

### `navigate` (5 tools)
**Strategy:** "Understand structure before reading content."
**Tools:** ReadLines, CodeStructure, FindDefinitions, ListFiles, MDOverview

### `diagnose` (7 tools)
**Strategy:** "Trace from symptom to root cause. Check what changed recently."
**Tools:** ReadLines, FindDefinitions, FindInAST, GitDiffSummary, GitDiffFile, GitShow, search_messages

### `review` (6 tools)
**Strategy:** "Structure before opinion. Check complexity impact."
**Tools:** ReadLines, FindDefinitions, GitDiffSummary, GitDiffFile, CodeStructure, changed_function_summary

### `analyze` (5 tools)
**Strategy:** "Measure before concluding."
**Tools:** CodeStructure, complexity_hotspots, project_overview, doc_outline, find_in_ast

### `explore` (4 tools)
**Strategy:** "Map the territory. Don't read everything — find what matters."
**Tools:** project_overview, CodeStructure, MDOverview, recent_changes

### `full` (all tools)
**Strategy:** "Use the right tool for the job."
**Tools:** All 26.

## Kit Format

```yaml
# fledgling/pro/kits/navigate.yaml
name: navigate
description: "Explore unfamiliar code. Map before reading."
strategy: "Understand structure before reading content."
tools:
  - read_source
  - code_structure
  - find_definitions
  - list_files
  - doc_outline
  - help
model_config:
  # Weaker models get fewer tools
  haiku:
    max_tools: 4
    exclude: [doc_outline, help]
```

Or as Python dicts if YAML feels heavy.

## API

### `activate_kit` tool
```python
@mcp.tool()
async def activate_kit(kit: str) -> str:
    """Activate a tool kit: navigate, diagnose, review, analyze, explore, full."""
    if kit not in _KITS:
        return f"Unknown kit. Available: {', '.join(_KITS)}"
    session.active_kit = kit
    _apply_kit(mcp, kit)
    return f"Activated '{kit}' kit: {', '.join(_KITS[kit].tools)}\nStrategy: {_KITS[kit].strategy}"
```

### `current_kit` resource
```python
@mcp.resource("fledgling://kit")
async def current_kit() -> str:
    kit = session.active_kit or "full"
    return f"Active kit: {kit}\nTools: {', '.join(_KITS[kit].tools)}\nStrategy: {_KITS[kit].strategy}"
```

## Implementation

FastMCP supports tool visibility control:
```python
def _apply_kit(mcp, kit_name):
    kit = _KITS[kit_name]
    for tool in mcp.list_tools():
        if tool.name in kit.tools or tool.name in _ALWAYS_VISIBLE:
            mcp.enable(tool.name)
        else:
            mcp.disable(tool.name)
```

`_ALWAYS_VISIBLE` = {`activate_kit`, `help`, `dr_fledgling`} — meta tools always available.

## Model-Aware Configuration

From the experimental findings: "Haiku with 9 tools: 40% pass. With 5 tools: could reach 100% with the right 5."

```python
def _kit_for_model(kit_name, model_hint=None):
    kit = _KITS[kit_name]
    if model_hint and model_hint in kit.model_config:
        config = kit.model_config[model_hint]
        tools = kit.tools[:config.max_tools]
        tools = [t for t in tools if t not in config.get("exclude", [])]
        return tools
    return kit.tools
```

The model hint comes from the client (Claude Code knows which model is running).

## Testing

- All kit names are valid
- Activating a kit changes visible tools
- Kit tools are subset of all tools
- Strategy text is non-empty
- Default kit is "full"
- activate_kit returns tool list and strategy
- Unknown kit returns error with available options
- Model config reduces tool count

## Files

- Add: `fledgling/pro/kits.py`
- Modify: `fledgling/pro/server.py` (register activate_kit, kit resource)
- Add: `fledgling/pro/kits/` directory with kit definitions
- Add tests: `tests/test_pro_kits.py`
