# P4-003: Token-Aware Output — Truncation, Pagination, Budgets

## Status: Done

## Problem

The agent calls `read_source` on a 3000-line file and gets 3000 lines back, consuming most of its context window. Or `find_definitions('**/*.py')` returns 500 results across a large codebase. The tools have no awareness of output cost.

## Solution

Add token-aware output handling:
1. **Auto-truncation** with informative messages
2. **Pagination hints** in truncated output
3. **Optional `max_lines` parameter** for content tools
4. **Result count warnings** for discovery tools

## Behaviors

### Content tools (read_source, read_context, file_diff, file_at_version)

**Default max:** 200 lines. If output exceeds:
```
   1  def parse_config(path):
   2      ...
 ...
 200
 --- truncated (1847 more lines) ---
 Use lines='200-400' to see the next section, or match='keyword' to filter.
```

**With explicit `lines` parameter:** No truncation (user asked for a range).

### Discovery tools (find_definitions, find_in_ast, doc_outline, list_files)

**Default max:** 50 results. If output exceeds:
```
| file_path | name | kind | start_line |
|-----------|------|------|------------|
| ...50 rows shown... |
--- 340 total results. Use name_pattern to narrow, or file_pattern to scope. ---
```

### Git tools (file_changes, recent_changes)

**Default max:** 25 for file_changes, 20 for recent_changes. Same truncation pattern.

## Implementation

```python
_MAX_LINES = {
    "read_source": 200,
    "read_context": 50,
    "file_diff": 300,
    "file_at_version": 200,
}

_MAX_ROWS = {
    "find_definitions": 50,
    "find_in_ast": 50,
    "list_files": 100,
    "doc_outline": 50,
    "file_changes": 25,
    "recent_changes": 20,
}

def _truncate_output(rows, cols, max_rows, macro_name):
    total = len(rows)
    if total <= max_rows:
        return rows, None  # no truncation
    truncated = rows[:max_rows]
    hint = _truncation_hint(macro_name, total, max_rows)
    return truncated, hint
```

Truncation hints are macro-specific:
```python
_HINTS = {
    "read_source": "Use lines='N-M' to see a range, or match='keyword' to filter.",
    "find_definitions": "Use name_pattern='%keyword%' to narrow results.",
    "list_files": "Use a more specific glob pattern.",
    "file_changes": "Use a narrower revision range.",
}
```

## API

Tools gain an optional `max_lines` / `max_results` parameter:
```python
async def read_source(file_path, lines=None, max_lines=200, ...):
```

The agent can override: `read_source(path, max_lines=500)` for when it needs more.

## Testing

- Small file: no truncation
- Large file: truncated with hint message
- Explicit max_lines: respected
- Explicit lines parameter: no truncation
- Discovery tool: row count shown
- Hint text includes actionable suggestion

## Files

- Modify: `fledgling/pro/server.py` (output formatting)
- Add tests: `tests/test_pro_truncation.py`
