# Conversation Schema Design

**File**: `sql/conversations.sql`
**Status**: Draft / Ready for testing
**Date**: 2026-02-26

## Overview

The conversation schema turns Claude Code's raw JSONL logs into a structured,
queryable analytics surface using DuckDB. It consists of 10 views, 1 loading
macro, and 2 search macros -- all building on a single base table called
`raw_conversations`.

The design goal is to make it possible to answer questions like:

- What tools am I using most? Which bash commands could be replaced?
- How long are my sessions? How many tokens am I burning?
- What did we discuss in the last session on project X?
- When was a specific file last touched by Claude?

## The Data: What Claude Code Logs

Claude Code stores one JSONL file per session under
`~/.claude/projects/<project-dir>/<session-uuid>.jsonl`. Each line is a JSON
object with a `type` field. There are eight record types:

| Type | Frequency | Purpose |
|------|-----------|---------|
| `progress` | ~39% | Subagent/hook progress events |
| `assistant` | ~35% | Model responses (contain tool_use blocks) |
| `user` | ~19% | User messages and tool results |
| `file-history-snapshot` | ~3% | File backup snapshots |
| `queue-operation` | ~2% | Subagent queue events |
| `system` | ~2% | System/hook events |
| `summary` | <1% | Conversation summaries |
| `pr-link` | <1% | PR associations |

The schema focuses on `user` and `assistant` records since they contain the
actual conversation and tool interactions.

### Key Structural Insights

**Assistant messages are streamed as chunks.** A single API response
(`requestId`) produces multiple JSONL records, each containing one content
block. The first record might have a `thinking` block, the second a `text`
block, the third a `tool_use` block. They share the same `requestId` and
`message.id` but have different `uuid` values.

**User messages have polymorphic content.** When the user types text,
`message.content` is a plain string. When returning tool results,
`message.content` is a JSON array of `tool_result` blocks. This means
JSON unnesting must guard against trying to CAST a string as JSON[].

**Token usage is duplicated across chunks.** Every chunk in a streamed
response carries the same `message.usage` object. To count tokens accurately,
you must deduplicate on `requestId`.

**Project identity is encoded in the path.** The project directory name under
`~/.claude/projects/` is the absolute path with `/` replaced by `-`. For
example, `/mnt/aux-data/teague/Projects/aidr` becomes
`-mnt-aux-data-teague-Projects-aidr`.

## Schema Architecture

The schema is organized in layers, each building on the one below:

```
Layer 3: Analysis Views
  session_summary, tool_frequency, bash_commands, model_usage
      |
Layer 2: Core Views
  messages, content_blocks, tool_calls, tool_results, token_usage
      |
Layer 1: Session Aggregation
  sessions
      |
Layer 0: Base Table
  raw_conversations (loaded from JSONL)
```

### Layer 0: Base Table

```sql
CREATE TABLE raw_conversations AS
SELECT *, filename AS _source_file
FROM read_json_auto(
    '~/.claude/projects/*/*.jsonl',
    union_by_name = true,
    maximum_object_size = 33554432,
    filename = true
);
```

The `union_by_name=true` parameter is critical: different record types have
different columns, and JSONL files across sessions may have slight schema
variations. DuckDB unifies them by column name, filling missing columns
with NULL.

The `maximum_object_size` is raised to 32MB because some tool results
(especially file reads of large files) produce very large JSON objects.

The `filename=true` parameter adds the source file path to each row,
which we alias to `_source_file` for downstream use.

### Layer 1: sessions

One row per session. Aggregates metadata using conditional aggregates:

```sql
SELECT * FROM sessions ORDER BY started_at DESC LIMIT 5;
```

| session_id | project_dir | slug | version | git_branch | duration | user_messages |
|------------|------------|------|---------|------------|----------|---------------|
| b38b442b-... | -mnt-...-aidr | curious-churning-treehouse | 2.1.56 | main | 03:50:49 | 15 |

Key design decisions:
- `slug` and `gitBranch` use `LAST(...) FILTER (WHERE ... IS NOT NULL)` because
  they can change mid-session (slug is assigned after the first response)
- Grouped by both `sessionId` and `project_dir` to handle edge cases where
  the same session UUID appears in different directories (shouldn't happen,
  but defensive)

### Layer 2: Core Views

**`messages`** -- Flattened user + assistant records with session context.
Filters to only type IN ('user', 'assistant'), extracting the `message`
struct fields into top-level columns. Token usage fields are pulled from
the nested `message.usage` struct.

**`content_blocks`** -- The critical unnesting step. Uses:
```sql
LATERAL UNNEST(CAST(r.message.content AS JSON[])) AS b(block)
```
to turn the JSON array of content blocks into rows. Each row has:
- `block_type`: text, thinking, tool_use, or tool_result
- Extracted fields: `text_content`, `thinking_content`, `tool_name`,
  `tool_use_id`, `tool_input`

The `json_type(r.message.content) = 'ARRAY'` guard is essential -- without
it, user messages with string content would cause CAST errors.

**`tool_calls`** -- Filters content_blocks to `block_type = 'tool_use'`.
Adds convenience columns for the most commonly queried tool inputs:
- `bash_command` (for Bash tool)
- `file_path` (for Read/Write/Edit)
- `grep_pattern` (for Grep)

**`tool_results`** -- Extracts tool_result blocks from user messages.
Joined to tool_calls via `tool_use_id`. Note: tool results live in user
messages (the next message after the assistant's tool call).

**`token_usage`** -- Extracts token counts from assistant messages with
derived columns for total tokens and cache hit rate. The cache_hit_rate
formula: `cache_read_tokens / (input_tokens + cache_creation_tokens + cache_read_tokens)`.

### Layer 3: Analysis Views

**`tool_frequency`** -- GROUP BY ALL aggregation of tool_calls. Shows
call counts per tool per session per project.

**`bash_commands`** -- The "what is bash doing?" view. For each Bash
tool call, extracts:
- `leading_command`: First token (git, ls, python, ...)
- `git_subcommand`: For git commands, the subcommand (add, diff, push, ...)
- `category`: High-level classification (git_read, git_write, build_tools, ...)
- `replaceable_by`: Which fledgling tool could handle this (duck_tails,
  sitting_duck, read_lines, duckdb_sql, or NULL)

**`session_summary`** -- The dashboard view. Joins sessions with aggregated
tool counts, token totals, and bash replacement stats. Token deduplication
is handled via `DISTINCT ON (request_id)` in the subquery.

**`model_usage`** -- Token consumption broken down by model (opus, sonnet,
haiku). Uses the same deduplication pattern.

### Search Macros

**`search_messages(term)`** -- ILIKE search across user text and assistant
text blocks. Returns message_id, session_id, slug, role, content, and
timestamp. Uses UNION ALL across two query paths (user strings and
assistant text blocks).

**`search_tool_inputs(term)`** -- ILIKE search across serialized tool input
JSON. Finds when specific files were accessed, commands run, or patterns
searched.

## Example Queries

### What tools am I using most?

```sql
SELECT tool_name, sum(call_count) as total
FROM tool_frequency
GROUP BY tool_name
ORDER BY total DESC;
```

### What bash commands could fledgling replace?

```sql
SELECT
    replaceable_by,
    count(*) as calls,
    round(100.0 * count(*) / sum(count(*)) OVER (), 1) as pct
FROM bash_commands
WHERE replaceable_by IS NOT NULL
GROUP BY replaceable_by
ORDER BY calls DESC;
```

### How much did each session cost in tokens?

```sql
SELECT
    slug,
    project_dir,
    total_tokens,
    total_tool_calls,
    duration
FROM session_summary
ORDER BY total_tokens DESC
LIMIT 10;
```

### What files did Claude touch most?

```sql
SELECT file_path, count(*) as touches
FROM tool_calls
WHERE file_path IS NOT NULL
GROUP BY file_path
ORDER BY touches DESC
LIMIT 20;
```

### Find all discussions about a topic

```sql
SELECT slug, role, left(content, 200) as preview, created_at
FROM search_messages('schema migration')
ORDER BY created_at;
```

### Join tool calls with their results

```sql
SELECT
    tc.tool_name,
    tc.bash_command,
    tr.is_error,
    left(tr.result_content, 100) as result_preview
FROM tool_calls tc
JOIN tool_results tr ON tc.tool_use_id = tr.tool_use_id
WHERE tc.tool_name = 'Bash'
  AND tr.is_error = true
LIMIT 20;
```

### Git subcommand frequency

```sql
SELECT git_subcommand, count(*) as calls
FROM bash_commands
WHERE git_subcommand IS NOT NULL
GROUP BY git_subcommand
ORDER BY calls DESC;
```

### Cache efficiency over time

```sql
SELECT
    date_trunc('day', created_at) as day,
    avg(cache_hit_rate) as avg_cache_rate,
    sum(total_tokens) as daily_tokens
FROM (
    SELECT DISTINCT ON (request_id) *
    FROM token_usage
    ORDER BY request_id, output_tokens DESC NULLS LAST
)
GROUP BY 1
ORDER BY 1;
```

## Gotchas and Known Issues

### 1. JSON Array vs String Content

User messages have `message.content` as either a string (typed text) or a
JSON array (tool results). Any view that unnests content must check
`json_type(message.content) = 'ARRAY'` first. Forgetting this check will
cause CAST errors on string content.

### 2. Token Deduplication

Assistant responses are streamed as multiple JSONL records sharing the same
`requestId`. Each record carries the full `message.usage` object. If you
sum tokens from `token_usage` directly without deduplication, you will
dramatically overcount. Always use `DISTINCT ON (request_id)` or `GROUP BY request_id`.

The `session_summary` and `model_usage` views handle this internally, but
if you write custom token queries against `token_usage`, remember to
deduplicate.

### 3. Progress Events Contain Full Subagent Conversations

The `progress` records contain complete subagent conversations nested inside
`data.message`. These are full user/assistant exchanges happening in parallel
Task/subagent contexts. The current schema ignores them (they are filtered
out in the `messages` view). A future extension could extract subagent
tool calls from progress events.

### 4. File-History-Snapshot Records Have No sessionId

The `file-history-snapshot` records often lack a `sessionId` field. They
have a `messageId` instead. The `sessions` view handles this by filtering
`WHERE sessionId IS NOT NULL`.

### 5. Schema Variation Across JSONL Files

Different Claude Code versions produce slightly different JSONL schemas.
Fields like `slug`, `permissionMode`, `todos`, and `context_management`
appear in newer versions but not older ones. DuckDB's `union_by_name=true`
handles this gracefully by filling missing columns with NULL.

### 6. Large Objects May Require Increased Limits

Some tool results (especially Read tool outputs of large files, or Bash
outputs from test suites) can produce JSON objects exceeding 16MB. The
schema uses `maximum_object_size=33554432` (32MB) but extremely large
results may still fail. If you hit this, increase the limit further.

### 7. Piped Bash Commands

Commands like `git log --oneline | head -20` are categorized by their
first token ("git") rather than the full pipeline. This is intentional --
the leading command represents the operation's purpose -- but means that
a `cat file.txt | grep pattern` will be categorized as "file_read" rather
than "file_search".

## Potential Blog Post Structure

### Title: "Querying Your AI Conversations: A DuckDB Schema for Claude Code Logs"

### Outline:

1. **The Hook** -- "Claude Code leaves breadcrumbs. Here's how to read them."
   Show the raw JSONL format. Mention the scale: 849MB, 267K records,
   192 sessions.

2. **The Data Model** -- Walk through the record types. Show a user message,
   an assistant message with tool_use blocks, and explain the streaming
   chunk pattern. The key insight: assistant messages are JSON arrays of
   typed blocks that need unnesting.

3. **The Core Trick: LATERAL UNNEST** -- The single most important DuckDB
   pattern in this schema. Show the content_blocks view. Explain why
   json_type() guarding is necessary.

4. **Building Up: Views on Views** -- Show how tool_calls, tool_results,
   and token_usage build on content_blocks. Emphasize composability.

5. **The Payoff: What Did We Learn?** -- Run the actual analysis queries.
   Show the tool frequency table. Show the bash command breakdown. The
   finding: 40% of all tool calls go through bash. Show which ones are
   replaceable.

6. **Token Economics** -- Cache hit rates, model distribution, session
   costs. Show how the prompt cache saves money over time.

7. **Search Across Sessions** -- Demonstrate search_messages() for finding
   past discussions. "What approaches did we try for connection pooling?"

8. **Gotchas Section** -- Token deduplication, JSON polymorphism, schema
   drift. These are genuinely useful warnings for anyone working with
   similar data.

9. **What's Next** -- Tease fledgling: structured tools replacing bash,
   conversation analysis as a live MCP capability.

### Key Visuals:

- Diagram of the view layer architecture
- Bar chart of tool frequency
- Pie chart of bash command categories
- Time series of cache hit rates
- Table showing "replaceable bash calls"

## Future Extensions

1. **Subagent extraction**: Parse `progress` events to extract subagent
   tool calls and build a parallel conversation tree.

2. **Cost estimation**: Add pricing per model per token to compute actual
   dollar costs per session.

3. **Conversation threading**: Use `parentUuid` to reconstruct the actual
   conversation tree (branching, sidechains).

4. **Error analysis**: Join tool_calls with tool_results where
   `is_error = true` to find failure patterns.

5. **Materialized aggregates**: For large datasets, materialize the
   session_summary as a table for faster dashboard queries.

6. **Summary records**: Extract and surface `summary` type records, which
   contain Claude's own summaries of conversation segments.

7. **PR link tracking**: Surface `pr-link` records to connect sessions
   to their resulting pull requests.
