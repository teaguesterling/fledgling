# P4-004: Compound Workflow Tools

## Status: Ready

## Problem

Common agent tasks require 3-5 sequential tool calls that follow a predictable pattern. "Explore this codebase" is always: overview → structure → docs → recent history. "Investigate this function" is always: find definition → read source → find callers. Each round trip adds latency and token overhead.

## Solution

Add compound tools that orchestrate multiple macros in a single call, returning a formatted briefing. The agent gets the same information in one tool call instead of five.

## Compound Tools

### `explore`
**Purpose:** First-contact codebase briefing.
**Orchestrates:** `project_overview()` → `code_structure()` → `doc_outline()` → `recent_changes(5)`

```python
@mcp.tool()
async def explore(path: str = ".") -> str:
    """Get a complete codebase briefing: languages, structure, docs, and recent activity."""
    overview = con.project_overview(path).fetchall()
    # Pick top language, get structure for those files
    top_lang_pattern = _infer_pattern(overview)
    structure = con.code_structure(top_lang_pattern).limit(20).fetchall()
    docs = con.doc_outline(f"{path}/**/*.md").limit(15).fetchall()
    history = con.recent_changes(5).fetchall()

    return _format_briefing(overview, structure, docs, history)
```

**Output format:**
```
## Project: /path/to/project

### Languages
Python: 42 files, TypeScript: 18 files, SQL: 12 files

### Key Definitions (top 20 by complexity)
src/parser.py: parse_config (complexity: 8), validate_input (complexity: 5)
src/server.py: handle_request (complexity: 12), ...

### Documentation
README.md: Getting Started, Installation, API Reference
docs/architecture.md: Overview, Components, Data Flow

### Recent Activity (last 5 commits)
a1b2c3d feat: add user authentication
d4e5f6g fix: connection timeout handling
...
```

### `investigate`
**Purpose:** Deep dive on a specific function or symbol.
**Orchestrates:** `find_definitions()` → `read_source()` (with context) → `function_callers()` → `find_in_ast()` (calls from the function)

```python
@mcp.tool()
async def investigate(name: str, file_pattern: str = None) -> str:
    """Deep investigation of a function: definition, source, callers, and callees."""
    # Find where it's defined
    defs = con.find_definitions(pattern, name_pattern=name).fetchall()
    if not defs:
        return f"No definition found for '{name}'"

    # Read the source with context
    file_path, start, end = defs[0][0], defs[0][3], defs[0][4]
    source = con.read_source(file_path, lines=f"{start}-{end}").fetchall()

    # Who calls it?
    callers = con.function_callers(pattern, name).fetchall()

    return _format_investigation(defs, source, callers)
```

### `review`
**Purpose:** Code review briefing for a revision range.
**Orchestrates:** `file_changes()` → `changed_function_summary()` → `file_diff()` (for top changed files)

```python
@mcp.tool()
async def review(from_rev: str = "HEAD~1", to_rev: str = "HEAD") -> str:
    """Review briefing: what changed, which functions, complexity impact."""
    changes = con.file_changes(from_rev, to_rev).fetchall()
    functions = con.changed_function_summary(from_rev, to_rev, '**/*').fetchall()

    # Get diffs for top 3 most-changed files
    top_files = sorted(changes, key=lambda r: r[2], reverse=True)[:3]
    diffs = {}
    for f in top_files:
        diff = con.file_diff(f[0], from_rev, to_rev).fetchall()
        diffs[f[0]] = diff

    return _format_review(changes, functions, diffs)
```

### `search`
**Purpose:** Multi-source search across code, docs, and git.
**Orchestrates:** `find_definitions()` → `find_in_ast()` → `doc_outline(search=)` → `search_messages()`

```python
@mcp.tool()
async def search(query: str) -> str:
    """Search everywhere: definitions, AST patterns, docs, and conversations."""
    defs = con.find_definitions('**/*', name_pattern=f"%{query}%").limit(10).fetchall()
    ast = con.find_in_ast('**/*', 'calls', name_pattern=f"%{query}%").limit(10).fetchall()
    docs = con.doc_outline('**/*.md', search=query).limit(10).fetchall()

    return _format_search_results(query, defs, ast, docs)
```

## Design Principles

1. **Compound tools supplement, not replace.** The individual macros remain available. Compound tools are shortcuts for common patterns.
2. **Output is a briefing, not raw data.** Formatted for reading, not parsing. The agent can always drill deeper with individual tools.
3. **Token-aware.** Compound tools respect the truncation limits from P4-003. Each section gets a budget.
4. **Graceful degradation.** If one sub-query fails (e.g., no git repo), skip that section with a note.

## Testing

- Each compound tool returns non-empty output for the fledgling repo
- Graceful handling of missing data (no git, no docs, etc.)
- Output stays under reasonable token limits
- Individual sections are present and labeled
- Name search with no results returns helpful message

## Files

- Add: `fledgling/pro/workflows.py`
- Modify: `fledgling/pro/server.py` (register compound tools)
- Add tests: `tests/test_pro_workflows.py`
