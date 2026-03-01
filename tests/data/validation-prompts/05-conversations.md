# Conversations Tier Validation

Requires Claude Code conversation data in ~/.claude/projects/. If no
conversation data exists, these tools return empty results (not errors).

## ChatSessions

### 5.1 Recent sessions

```
Use Fledgling ChatSessions with limit=5.

Expected: Returns up to 5 most recent sessions with session_id,
project_dir, slug, git_branch, started_at, duration, user_messages,
total_tool_calls, distinct_tools_used, top_tool, total_tokens, and
avg_cache_hit_rate columns. Ordered by started_at descending.
```

### 5.2 Project filter

```
Use Fledgling ChatSessions with project=sextant and limit=5.

Expected: Returns only sessions from projects with "sextant" in the
project directory name. Should include sessions from this repository.
```

### 5.3 Date range filter

```
Use Fledgling ChatSessions with days=3 and limit=5.

Expected: Returns only sessions from the last 3 days.
```

## ChatSearch

### 5.4 Basic search

```
Use Fledgling ChatSearch with query=resolve and limit=5.

Expected: Returns messages containing "resolve" with session_id, slug,
role, content_preview (truncated to 500 chars), and created_at.
```

### 5.5 Role-filtered search

```
Use Fledgling ChatSearch with query=test and role=user and limit=5.

Expected: Returns only user messages containing "test". No assistant
messages should appear.
```

## ChatToolUsage

### 5.6 Overall tool usage

```
Use Fledgling ChatToolUsage with limit=10.

Expected: Returns the 10 most-used tools across all sessions with
tool_name, total_calls, sessions, first_used, and last_used columns.
Common tools like Bash, Read, Edit should appear near the top.
```

### 5.7 Project-scoped usage

```
Use Fledgling ChatToolUsage with project=sextant and limit=10.

Expected: Returns tool usage patterns only from sextant-related sessions.
```

## ChatDetail

### 5.8 Session detail

```
First use Fledgling ChatSessions with limit=1 to get a session_id,
then use ChatDetail with that session_id.

Expected: Returns one row per tool used in that session, with session
metadata (slug, project_dir, git_branch, started_at, duration, message
counts, token counts) repeated on each row. The tool_name and calls
columns show per-tool breakdown.
```
