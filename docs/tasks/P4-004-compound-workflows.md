# P4-004: Compound Workflow Tools

## Status: Done

## Problem

Common agent tasks require 3-5 sequential tool calls that follow a predictable pattern. Each round trip adds latency and token overhead. The agent does the same dance every time it needs to explore a codebase, investigate a function, or review changes.

## Solution

Add compound tools that orchestrate multiple fledgling macros in a single call, returning a formatted briefing. These supplement individual tools — shortcuts for common patterns.

## Prerequisites

- P4-002 (Smart Defaults) — compound tools use `ProjectDefaults` for language-aware patterns
- P4-003 (Token Awareness) — compound tools apply truncation to each section

## Compound Tools to Add

### `explore`

**Purpose:** First-contact codebase briefing.
**Orchestrates:** `project_overview()` → `code_structure()` (top 20 by complexity) → `doc_outline()` (top 15) → `recent_changes(5)`

Parameters:
- `path` (optional, default from ProjectDefaults or ".")

Output format:
```
## Project: /path/to/project

### Languages
Python: 42 files, TypeScript: 18 files, SQL: 12 files

### Key Definitions (top 20 by complexity)
src/parser.py: parse_config (cyclomatic: 8), validate_input (5)
src/server.py: handle_request (12), ...

### Documentation
README.md: Getting Started, Installation, API Reference
docs/architecture.md: Overview, Components

### Recent Activity
a1b2c3d feat: add user authentication
d4e5f6g fix: connection timeout handling
```

Each section gets a token budget. If code_structure returns 200 rows, truncate to top 20 by complexity. If doc_outline returns 100, take top 15.

### `investigate`

**Purpose:** Deep dive on a specific function or symbol.
**Orchestrates:** `find_definitions()` → `read_source()` (the definition with context) → `function_callers()` → `find_in_ast('calls')` (what the function calls)

Parameters:
- `name` (required — function/class name or pattern)
- `file_pattern` (optional, default from ProjectDefaults)

Output format:
```
## Investigating: parse_config

### Definition
Found in src/parser.py:42-80 (DEFINITION_FUNCTION)

### Source
  42  def parse_config(path):
  43      with open(path) as f:
  ...
  80      return config

### Called by (3 sites)
src/main.py:15  (in main)
src/server.py:42  (in handle_request)
tests/test_parser.py:8  (in test_parse_config)

### Calls
  validate_schema, open, json.loads
```

If no definition found, return: `"No definition found for 'name'. Try a broader pattern or check spelling."`

### `review`

**Purpose:** Code review prep for a revision range.
**Orchestrates:** `file_changes()` → `changed_function_summary()` → `file_diff()` (for top 3 most-changed files)

Parameters:
- `from_rev` (default from ProjectDefaults or "HEAD~1")
- `to_rev` (default "HEAD")
- `file_pattern` (optional, scopes the review)

Output format:
```
## Review: HEAD~1..HEAD

### Changed Files (4)
modified  src/parser.py (+30 -12)
modified  src/server.py (+5 -2)
added     src/validator.py (+45)
deleted   src/old_parser.py (-120)

### Changed Functions (by complexity)
src/parser.py: parse_config (cyclomatic: 8, modified)
src/validator.py: validate_schema (cyclomatic: 5, added)

### Diff: src/parser.py
+ def parse_config(path, strict=False):
-     with open(path) as f:
+     with open(path, encoding='utf-8') as f:
  ...

### Diff: src/validator.py
(new file — 45 lines)
```

Diffs limited to top 3 files by change size. Each diff section truncated per P4-003 limits.

### `search`

**Purpose:** Multi-source search across code, docs, and git.
**Orchestrates:** `find_definitions()` → `find_in_ast('calls')` → `doc_outline(search=)` → `search_messages()` (if conversations loaded)

Parameters:
- `query` (required — search term)
- `file_pattern` (optional, default from ProjectDefaults)

Output format:
```
## Search: "validate"

### Definitions (3)
src/validator.py:10  validate_schema (DEFINITION_FUNCTION)
src/parser.py:85  validate_config (DEFINITION_FUNCTION)
tests/test_validator.py:5  TestValidate (DEFINITION_CLASS)

### Call Sites (8)
src/parser.py:42  validate_schema(data)
src/server.py:15  validate_config(path)
...

### Documentation (2 sections)
docs/api.md#validation: Validation
docs/architecture.md#data-flow: Data Flow
```

Each section limited to 10 results.

## Implementation

```python
# fledgling/pro/workflows.py

async def explore(con, defaults, path=None):
    path = path or defaults.project_root or "."
    sections = []
    # Each section catches errors independently
    try:
        overview = con.project_overview(path).fetchall()
        sections.append(("Languages", _format_overview(overview)))
    except Exception:
        sections.append(("Languages", "(could not read project overview)"))
    # ... repeat for each section
    return _format_briefing(sections)
```

Register in server.py:
```python
from fledgling.pro.workflows import register_workflows
register_workflows(mcp, con, defaults)
```

## Design Principles

1. **Graceful degradation** — if one sub-query fails (no git, no docs), skip that section with a note. Never fail the whole tool.
2. **Token-aware** — each section gets a budget from P4-003 limits.
3. **Default-aware** — uses P4-002 ProjectDefaults for patterns.
4. **Supplements, not replaces** — individual tools remain available.

## Testing

- Each compound tool returns non-empty output on the fledgling repo
- Missing data handled gracefully (test with modules=["sandbox", "source"] only)
- Output sections are present and labeled
- Truncation applied per section
- investigate with unknown name returns helpful message
- search with no results returns helpful message
- explore works on projects with no git/no docs

## Files

- Add: `fledgling/pro/workflows.py`
- Modify: `fledgling/pro/server.py` (register workflows)
- Add: `tests/test_pro_workflows.py`
