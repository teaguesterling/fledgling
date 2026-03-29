# P4-006: Session State — Caching, Access Log, and Kibitzer

## Status: Ready

## Problem

Three problems, one solution:

1. **Redundancy** — agents call `project_overview()` and `find_definitions()` repeatedly. Same query, same result, wasted tokens.
2. **No memory** — the server doesn't know what the agent has already explored. It can't say "you already read this file."
3. **No coaching** — neither the agent nor the human gets feedback on how they're using the tools. Are they using grep when FindDefinitions would be better? Are they reading whole files when line ranges would suffice?

## Solution

### Session cache
Cache macro results by (macro_name, arguments). Return cached results with a note:
```
(cached — same as 2 minutes ago)
   42  def parse_config(path):
```

### Access log
Track every tool call: what was called, when, what arguments, how many results. Exposed as a resource:
```python
@mcp.resource("fledgling://session")
```

### Kibitzer (two levels)

**Agent-level kibitzer** — observes the agent's tool usage and suggests better approaches:
- Agent called ReadLines 3 times searching for a function → suggest FindDefinitions
- Agent read a whole file → suggest using `lines` parameter
- Agent used bash grep → suggest FindInAST

**User-level kibitzer** — observes the human's workflow patterns across sessions and suggests improvements:
- User always starts sessions by reading README → suggest adding it as a resource
- User frequently searches for the same patterns → suggest a custom macro or alias
- User's CLAUDE.md is missing common patterns → suggest additions
- User could benefit from a slash command they haven't used → suggest it
- User's blq/jetsam setup is incomplete → suggest init-dev

The agent kibitzer runs per-tool-call (middleware). The user kibitzer runs per-session (analyzes conversation history via fledgling's chat macros).

## Agent Kibitzer Suggestions

Triggered by middleware after each tool call:

| Pattern | Suggestion |
|---------|-----------|
| 3+ ReadLines on same file with different `match` | "Try FindInAST with kind='calls' or FindDefinitions for structural search" |
| ReadLines without `lines` on file > 200 lines | "This file has {n} lines. Use lines='N-M' to read a section" |
| find_definitions returning 50+ results | "Use name_pattern to narrow: find_definitions(pattern, name_pattern='%keyword%')" |
| Repeated identical calls | "You already queried this — showing cached result" |
| No code tools used after explore | "Try CodeStructure or FindDefinitions to understand the code" |

Implementation:
```python
class AgentKibitzer:
    def __init__(self):
        self.call_log: list[ToolCall] = []

    def observe(self, tool_name, args, result_count):
        self.call_log.append(ToolCall(tool_name, args, result_count, time.time()))
        return self._check_patterns()

    def _check_patterns(self) -> Optional[str]:
        # Check each heuristic
        if suggestion := self._check_repeated_search():
            return suggestion
        if suggestion := self._check_large_file_no_range():
            return suggestion
        ...
```

Suggestions are appended to tool output:
```
   42  def parse_config(path):
   43      ...
 200

💡 This file has 1847 lines. Use lines='N-M' to read a specific section.
```

## User Kibitzer

Analyzes conversation history (via fledgling's chat macros) to suggest workflow improvements. Runs as an MCP tool the agent can call, or as a resource.

```python
@mcp.tool()
async def suggest_improvements() -> str:
    """Analyze recent sessions and suggest workflow improvements."""
    # Query conversation history
    sessions = con.sessions().limit(10).fetchall()
    tool_usage = con.sql("""
        SELECT tool_name, count(*) as calls
        FROM tool_frequency()
        GROUP BY tool_name
        ORDER BY calls DESC
    """).fetchall()

    suggestions = []

    # Check for bash-heavy sessions
    bash_pct = _bash_percentage(tool_usage)
    if bash_pct > 50:
        suggestions.append(
            "You're using bash for {bash_pct}% of operations. "
            "Fledgling tools like FindDefinitions and ReadLines are more "
            "token-efficient for code navigation."
        )

    # Check for missing tools
    if not _uses_tool(tool_usage, "CodeStructure"):
        suggestions.append(
            "Try CodeStructure before reading files — it shows what's "
            "defined and how complex each function is."
        )

    # Check for CLAUDE.md gaps
    claude_md = _read_claude_md()
    if claude_md and "fledgling" not in claude_md.lower():
        suggestions.append(
            "Your CLAUDE.md doesn't mention fledgling tools. Adding "
            "guidance like 'use FindDefinitions instead of grep' helps "
            "the agent choose structured tools."
        )

    # Check for init-dev setup
    if not _has_blq():
        suggestions.append("Consider running init-dev to set up blq for build/test tracking.")
    if not _has_jetsam():
        suggestions.append("Consider running init-dev to set up jetsam for git workflow.")

    return _format_suggestions(suggestions)
```

### User kibitzer resource

```python
@mcp.resource("fledgling://suggestions")
async def suggestions_resource() -> str:
    """Workflow improvement suggestions based on recent usage."""
    ...
```

## Caching Policy

| Macro | Cache key | TTL |
|-------|-----------|-----|
| project_overview | (root,) | Session lifetime |
| find_definitions | (file_pattern, name_pattern) | 5 minutes |
| code_structure | (file_pattern,) | 5 minutes |
| read_source | (file_path, lines, match) | 5 minutes |
| doc_outline | (file_pattern, search) | Session lifetime |
| recent_changes | (n,) | 30 seconds |
| working_tree_status | () | 10 seconds |

```python
class SessionCache:
    def get(self, key) -> Optional[CachedResult]: ...
    def put(self, key, result, ttl): ...
    def invalidate(self, pattern): ...
```

## Testing

### Cache tests
- Repeated calls return cached results
- Different parameters → different cache entries
- TTL expiry works
- Cache note appears in output

### Kibitzer tests
- Repeated search pattern triggers suggestion
- Large file without range triggers suggestion
- Suggestion text is actionable
- No false positives on normal usage

### User kibitzer tests
- Bash-heavy usage triggers suggestion
- Missing CLAUDE.md guidance triggers suggestion
- Empty history returns no suggestions
- suggest_improvements tool returns formatted output

## Files

- Add: `fledgling/pro/session.py` (SessionCache, AgentKibitzer)
- Add: `fledgling/pro/kibitzer.py` (UserKibitzer, suggest_improvements)
- Modify: `fledgling/pro/server.py` (middleware, resource, tool)
- Add: `tests/test_pro_session.py`
- Add: `tests/test_pro_kibitzer.py`
