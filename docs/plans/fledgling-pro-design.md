# Fledgling-Pro: FastMCP Coordination Layer

## Architecture

```
┌─────────────────────────────────┐
│  fledgling-pro (FastMCP)        │  pip install fledgling-pro
│  Level 1-2: coordination        │
│                                 │
│  Kit management (Quartermaster) │
│  Coach queries + injection      │
│  Mode switching                 │
│  Strategy instructions          │
│  Streaming, validation          │
│                                 │
│  ┌───────────────────────────┐  │
│  │  fledgling (DuckDB)       │  │  pip install fledgling (CLI only)
│  │  Level 0: reads           │  │  curl | duckdb (MCP server)
│  │                           │  │
│  │  SQL macros               │  │
│  │  14 MCP tools             │  │
│  │  read_ast, read_lines,    │  │
│  │  duck_tails, markdown     │  │
│  └───────────────────────────┘  │
└─────────────────────────────────┘
```

## Package Strategy

### `fledgling` (pip)
- Installs `fledgling` CLI to PATH
- Provides `fledgling install` (wraps the curl|duckdb installer)
- Provides `fledgling update`, `fledgling help`, etc.
- No Python runtime dependency for the MCP server (pure DuckDB SQL)
- The SQL macros and installer SQL ship as package data

### `fledgling-pro` (pip)
- Depends on `fledgling`, `duckdb`, `fastmcp`
- FastMCP server that loads the same SQL macros via Python DuckDB
- Adds coordination tools (level 1-2 mutations)
- Kit manifests, coach hooks, mode controller
- Richer parameter validation, streaming, error messages

## What fledgling-pro adds

### 1. Kit Management (Quartermaster Pattern)
```python
@mcp.tool()
def switch_kit(kit_name: str) -> str:
    """Activate a tool kit for the current task type."""
    # Loads kit manifest, configures available tools
    # Kits: navigate, diagnose, review, analyze, refactor, history
```

### 2. Coach Integration
```python
@mcp.tool()
def coaching_suggestions(session_id: str) -> list[str]:
    """Query fledgling analytics for tool usage suggestions."""
    # Runs coaching SQL queries against conversation data
    # Returns suggestions like "Try FindDefinitions instead of grep"
```

### 3. Mode Controller
```python
@mcp.tool()
def switch_mode(mode: str) -> str:
    """Switch operating mode based on task context."""
    # Reconfigures tool visibility and strategy instruction
```

### 4. Strategy Instructions
```python
@mcp.tool()
def get_strategy(kit_name: str) -> str:
    """Get the strategy instruction for a kit."""
    # Returns the one-line principle: "Understand before editing"
```

### 5. Enhanced Tool Wrappers
The same fledgling macros, but with:
- Pydantic parameter validation
- Streaming for large results (ReadLines on big files)
- Structured error messages instead of SQL errors
- Token counting / budget awareness

## Kit Manifests

```yaml
# kits/navigate.yaml
name: navigate
description: "Explore unfamiliar code. Map before reading."
strategy: "Understand structure before reading content."
tools:
  - ReadLines
  - CodeStructure
  - FindDefinitions
  - FindInAST
model_config:
  haiku: {max_tools: 5}
  sonnet: {max_tools: 10}
  opus: {max_tools: all}
```

## Open Questions

1. **Repo structure**: monorepo (fledgling + fledgling-pro) or separate repos?
2. **Kit storage**: YAML files? SQL tables? DuckDB-native config?
3. **Hook integration**: Claude Code hooks for Coach? Or standalone?
4. **Streaming**: FastMCP supports streaming — which tools benefit?
5. **Session state**: Does fledgling-pro maintain state across calls?

## Next Steps

1. Create `pyproject.toml` for pip-installable `fledgling` (CLI + installer as package data)
2. Prototype `fledgling-pro` with FastMCP wrapping 2-3 fledgling tools
3. Design kit manifest format and implement Quartermaster
4. Wire coaching queries from the patterns doc
