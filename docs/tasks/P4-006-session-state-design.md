# P4-006: Session State — Cache & Access Log

## Scope

Session cache and access log for fledgling-pro. The kibitzer (agent-level and
user-level) is deferred to a separate project (`~/Projects/kibitzer/docs/plans/`).

This ticket delivers:
1. **Session cache** — memoize macro results, TTL + mtime invalidation
2. **Access log** — SQL table recording every tool call
3. **`fledgling://session` resource** — exposes access log summary

No changes to fledgling core (`sql/`, `fledgling/connection.py`, `fledgling/tools.py`).
Everything lives in `fledgling/pro/`.

## Architecture

```
Tool call in server.py
  → check SessionCache
    → HIT:  log(cached=True) → return cached text with "(cached)" note
    → MISS: call macro → truncate → format → store in cache → log(cached=False) → return
  → write AccessLog entry
```

### Storage layers

- **Session cache**: Python dict. Key = `(tool_name, frozen_args)` where
  `frozen_args` is the kwargs dict **after** defaults are applied, frozen as
  a tuple of sorted items. Two calls with different explicit args but the same
  effective args share a cache entry. Value = `CachedResult(...)`. Transient,
  session-scoped.
- **Access log**: SQL table in pro's DuckDB connection. Queryable, persists
  for session lifetime. Designed so the kibitzer can query it later.

## Data Model

### Access log table

```sql
CREATE TABLE session_access_log (
    call_id       INTEGER PRIMARY KEY,
    timestamp     DOUBLE,
    tool_name     VARCHAR,
    arguments     JSON,
    result_rows   INTEGER,
    cached        BOOLEAN,
    elapsed_ms    DOUBLE
);
```

Written by Python after each tool call.

### Cache entry

```python
@dataclass
class CachedResult:
    text: str              # Formatted output (post-truncation)
    row_count: int         # Rows before truncation
    timestamp: float       # time.time() when cached
    ttl: float             # Seconds until expiry
    file_mtimes: dict[str, float]  # {path: mtime} for invalidation
```

## Cache Policy

| Tool | Cache key | TTL | Invalidation |
|------|-----------|-----|-------------|
| `project_overview` | `(root,)` | Session lifetime | None (stable) |
| `find_definitions` | `(file_pattern, name_pattern)` | 5 min | TTL only (glob too expensive to stat) |
| `code_structure` | `(file_pattern,)` | 5 min | TTL only |
| `read_source` | `(file_path, lines, match)` | 5 min | File mtime check |
| `doc_outline` | `(file_pattern, search)` | Session lifetime | None (stable) |
| `recent_changes` | `(n,)` | 30 sec | TTL only |
| `working_tree_status` | `()` | 10 sec | TTL only |

### Invalidation strategy

- **Single-file tools** (`read_source`, `code_structure` on one file): check
  mtime of the file on cache hit. If changed, invalidate. Fast — single stat.
- **Glob-pattern tools** (`find_definitions`, `list_files`): TTL only. Stat-ing
  every matching file defeats the purpose of caching.
- **Cache key includes all output-affecting arguments**, including `max_lines`
  if overridden. Prevents serving truncated-to-50 when user asked for 200.

### Cache hit presentation

Prepend to output:
```
(cached — same as 23s ago)
```

## Session Resource

`fledgling://session` returns:

```
Session: 47 tool calls, 12 cached (25%)
Cache: 8 entries, 3 expired

Recent calls:
| # | tool | args | rows | cached | ms |
|---|------|------|------|--------|----|
| 45 | ReadLines | {file: "server.py"} | 50 | no | 23 |
| 46 | FindDefinitions | {file_pattern: "**/*.py"} | 34 | yes | 0 |
| 47 | CodeStructure | {file_pattern: "**/*.py"} | 12 | no | 145 |
```

## Integration into server.py

The tool registration pipeline currently does:
```
apply defaults → call macro → truncate → format
```

We wrap the existing `tool_fn` closure in `_register_tool`:
```
apply defaults → check cache
  → HIT:  log access → return cached text
  → MISS: call macro → truncate → format → store in cache → log access → return
```

This is a wrapper, not middleware. Keeps the change localized to
`_register_tool` and the new `session.py` module.

## Files

| Action | File | Contents |
|--------|------|----------|
| Add | `fledgling/pro/session.py` | `SessionCache`, `AccessLog` classes |
| Modify | `fledgling/pro/server.py` | Wrap tool calls, register resource |
| Add | `tests/test_pro_session.py` | Cache, access log, resource tests |

## Testing

### Cache tests
- Repeated calls return cached results
- Different parameters produce different cache entries
- TTL expiry works (mock time)
- File mtime invalidation works (touch file between calls)
- Cache note appears in output on hit
- `max_lines` override produces separate cache entry

### Access log tests
- Every tool call is logged
- Cached and uncached calls both logged
- Arguments and result counts recorded correctly
- Log is queryable via SQL

### Resource tests
- `fledgling://session` returns formatted summary
- Summary reflects actual call history
- Cache stats are accurate

## Design Notes for Future Kibitzer

The access log table is designed so the kibitzer can query it:
- `tool_name` + `arguments` enables pattern detection (repeated calls,
  same file different match, etc.)
- `result_rows` enables "too many results" detection
- `cached` flag shows whether the agent is hitting cache or re-querying
- `elapsed_ms` enables performance coaching

Kibitzer plans are in `~/Projects/kibitzer/docs/plans/`.
