# P4-006: Session State — Track What the Agent Has Explored

## Status: Ready

## Problem

Agents revisit the same code repeatedly. They call `find_definitions('src/parser.py')` three times, read the same function twice, check `project_overview()` at the start of every task. Each redundant call wastes tokens and time.

## Solution

Track what the agent has accessed during the session and surface it:
1. **Access log** — which files, functions, and sections were read
2. **Dedup hints** — "You already read parser.py:42-80 — showing cached result"
3. **Session context resource** — MCP resource showing what's been explored
4. **Bookmarks** — agent can mark locations for quick return

## What to Track

### File access
```python
@dataclass
class FileAccess:
    file_path: str
    lines: Optional[str]  # "42-80" or None for whole file
    timestamp: datetime
    tool: str  # "read_source", "find_definitions", etc.
```

### Definition lookups
```python
@dataclass
class DefinitionAccess:
    name: str
    file_path: str
    start_line: int
    timestamp: datetime
```

### Search queries
```python
@dataclass
class SearchAccess:
    query: str
    tool: str
    result_count: int
    timestamp: datetime
```

## Behaviors

### Dedup detection
When the same file+lines combination is requested within a session:
```
(showing cached result from 3 minutes ago)
  42  def parse_config(path):
  43      ...
```
No re-query — return cached output. The agent saves a DuckDB round trip.

### Session context resource
```python
@mcp.resource("fledgling://session")
async def session_context() -> str:
    """What has been explored in this session."""
    return f"""## Session Activity

### Files Read
{_format_file_log(session.files)}

### Definitions Found
{_format_def_log(session.definitions)}

### Searches
{_format_search_log(session.searches)}
"""
```

### Bookmarks
```python
@mcp.tool()
async def bookmark(file_path: str, line: int, note: str = "") -> str:
    """Bookmark a location for quick return."""
    session.bookmarks.append(Bookmark(file_path, line, note))
    return f"Bookmarked {file_path}:{line}"

@mcp.tool()
async def bookmarks() -> str:
    """List all bookmarks."""
    ...
```

## Implementation

```python
class SessionState:
    files: list[FileAccess] = []
    definitions: list[DefinitionAccess] = []
    searches: list[SearchAccess] = []
    bookmarks: list[Bookmark] = []
    cache: dict[str, tuple[str, datetime]] = {}  # key → (output, time)

    def log_access(self, tool, **kwargs): ...
    def check_cache(self, tool, **kwargs) -> Optional[str]: ...
```

Middleware wraps every tool call to log access and check cache:
```python
@mcp.add_middleware
async def session_middleware(context, call_next):
    cached = session.check_cache(context.tool, **context.arguments)
    if cached:
        return cached
    result = await call_next(context)
    session.log_access(context.tool, result=result, **context.arguments)
    return result
```

## Caching Policy

- **read_source, read_context:** Cache by (file_path, lines). Invalidate on git changes.
- **find_definitions, code_structure:** Cache by (file_pattern). Long TTL (files don't change mid-session).
- **recent_changes, working_tree_status:** Short TTL (5 seconds) — git state changes.
- **project_overview:** Cache for entire session.

## Testing

- Repeated calls return cached results
- Cache key includes all relevant parameters
- Bookmark CRUD works
- Session resource shows access log
- Cache respects TTL
- Different parameters → different cache entries

## Files

- Add: `fledgling/pro/session.py`
- Modify: `fledgling/pro/server.py` (middleware, bookmark tools)
- Add tests: `tests/test_pro_session.py`
