# Conversation Intelligence

**Extension**: DuckDB built-in JSON support

Queryable access to Claude Code conversation history. Turns raw JSONL session logs into structured views for tool usage analysis, token tracking, and cross-session search.

!!! warning
    This tier is drafted but not yet fully tested. See [Next Steps](../planning/NEXT_STEPS.md).

## Loading

### `load_conversations`

Load conversation JSONL files into a table.

```sql
load_conversations(path)
```

```sql
-- Load all conversations
CREATE TABLE raw_conversations AS
SELECT * FROM load_conversations('~/.claude/projects/*/*.jsonl');
```

## Views

Once `raw_conversations` is loaded, these views become available:

### `sessions`
One row per session with aggregated metadata: slug, version, git branch, duration, message counts.

### `messages`
Flattened user + assistant messages with token usage.

### `content_blocks`
Unnested assistant message content — each text, thinking, or tool_use block becomes a row.

### `tool_calls`
Extracted `tool_use` blocks with convenience columns: `bash_command`, `file_path`, `grep_pattern`.

### `tool_results`
Matched `tool_result` blocks from user messages, joinable to `tool_calls` via `tool_use_id`.

### `token_usage`
Per-message token consumption with cache hit rate metrics.

!!! note
    Token usage records must be deduplicated on `request_id` for accurate totals, as streaming chunks share usage data. The analysis views handle this automatically.

### `tool_frequency`
Aggregated tool usage counts by project, session, and tool.

### `bash_commands`
Parsed bash command analysis with categories (`git_read`, `git_write`, `build_tools`, etc.) and `replaceable_by` annotations.

### `session_summary`
Dashboard view joining sessions with tool counts, token totals, and bash replacement stats.

### `model_usage`
Token consumption broken down by model.

## Search Macros

### `search_messages`

Full-text search across conversation content.

```sql
search_messages(search_term)
```

**Returns**: `message_id`, `session_id`, `slug`, `role`, `content`, `created_at`

```sql
SELECT * FROM search_messages('schema migration');
```

### `search_tool_inputs`

Search within tool call parameters.

```sql
search_tool_inputs(search_term)
```

**Returns**: `tool_use_id`, `session_id`, `slug`, `tool_name`, `bash_command`, `file_path`, `grep_pattern`, `input_text`, `created_at`

```sql
-- Find when a specific file was accessed
SELECT * FROM search_tool_inputs('conftest.py');
```
