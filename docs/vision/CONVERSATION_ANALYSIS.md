# Fledgling: Conversation Log Analysis

**Date**: 2026-02-26
**Method**: DuckDB `read_json_auto()` across all `~/.claude/projects/*/*.jsonl`

## Dataset

| Metric | Value |
|--------|-------|
| JSONL files | 270 |
| Project directories | 75 |
| Total records | 267,473 |
| Total size | 849 MB |
| Sessions | 192 |
| Date range | 2025-11-28 to 2026-02-26 |
| User messages | 49,611 |
| Assistant messages | 94,251 |

## Tool Usage (43,320 total calls)

| Tool | Calls | % | Notes |
|------|------:|--:|-------|
| **Bash** | 17,003 | 39.2% | Dominant. The problem. |
| Edit | 8,282 | 19.1% | Working as intended |
| Read | 7,440 | 17.2% | Working as intended |
| Grep | 2,910 | 6.7% | Working as intended |
| Write | 1,166 | 2.7% | Working as intended |
| blq (all tools) | 1,332 | 3.1% | MCP working well |
| Task/subagents | 1,173 | 2.7% | — |
| Glob | 675 | 1.6% | Working as intended |
| aidr (all tools) | 116 | 0.3% | Lower usage (newer) |

**Key finding**: Nearly 40% of all tool calls go through Bash. This is the
bottleneck — every Bash call requires permission whitelisting, produces
unstructured text, and can't compose with other tools.

## Bash Command Breakdown (17,003 calls)

### By Category

| Category | Calls | % of Bash | % of All Tools |
|----------|------:|----------:|---------------:|
| Git write ops | 2,810 | 16.5% | 6.5% |
| Git read ops | 2,022 | 11.9% | 4.7% |
| GitHub CLI | 1,801 | 10.6% | 4.2% |
| Build tools (cargo/make/npm) | 1,395 | 8.2% | 3.2% |
| Runtime exec (python/node/duckdb) | 1,149 | 6.8% | 2.7% |
| Filesystem ops (ls/mkdir/rm) | 982 | 5.8% | 2.3% |
| File search (grep/find) | 756 | 4.4% | 1.7% |
| File reading (cat/head/tail) | 459 | 2.7% | 1.1% |
| Text processing (wc/sort/awk) | 98 | 0.6% | 0.2% |
| Other | 5,531 | 32.5% | 12.8% |

### Git Subcommands (5,733 calls)

| Subcommand | Calls | Replaceable by |
|------------|------:|----------------|
| git add | 1,794 | safe-git MCP |
| git status | 775 | duck_tails |
| git diff | 708 | duck_tails |
| git log | 642 | duck_tails |
| git push | 598 | safe-git MCP |
| git commit | 273 | safe-git MCP |
| git tag | 175 | duck_tails / safe-git |
| git checkout | 161 | safe-git MCP |
| git show | 91 | duck_tails |
| git fetch | 85 | safe-git MCP |
| git rev-parse | 79 | duck_tails |
| git branch | 40 | duck_tails |

### GitHub CLI (1,967 calls)

| Subcommand | Calls | Notes |
|------------|------:|-------|
| gh api repos | 473 | Generic API calls |
| gh run view | 263 | CI status |
| gh run list | 154 | CI history |
| gh pr view | 143 | PR inspection |
| gh issue view | 106 | Issue inspection |
| gh issue create | 72 | Issue creation |
| gh release create | 66 | Release management |

GitHub CLI is probably best left as bash — it's well-structured with
`--json` flags and doesn't benefit much from a DuckDB layer.

## Fledgling Replacement Potential

| Replacement | Bash Calls Replaced | % of Bash | % of All Tools |
|-------------|--------------------:|----------:|---------------:|
| duck_tails (git read) | 2,022 | 11.9% | 4.7% |
| read_lines (file read) | 459 | 2.7% | 1.1% |
| sitting_duck (code search) | 756 | 4.4% | 1.7% |
| DuckDB SQL (text processing) | 98 | 0.6% | 0.2% |
| **Total fledgling** | **3,335** | **19.6%** | **7.7%** |
| safe-git (future, git write) | 2,810 | 16.5% | 6.5% |
| **Total if both built** | **6,145** | **36.1%** | **14.2%** |
| Not replaceable | 10,864 | 63.9% | 25.1% |

### What This Means

If fledgling existed today, it would replace **~3,300 bash calls** (20% of
all bash usage). Combined with a future safe-git server, that rises to
**~6,100 calls** (36% of bash). The remaining 64% is build tools, runtime
execution, GitHub CLI, and misc filesystem operations — things that genuinely
need a shell.

The bash whitelist in `settings.json` could shrink from ~40 entries to ~15.

## Conversation Intelligence Findings

### Record Types in JSONL

| Type | Count | Purpose |
|------|------:|---------|
| progress | 104,868 | Hook/tool progress events |
| assistant | 94,215 | Model responses (contain tool_use blocks) |
| user | 49,590 | User messages |
| file-history-snapshot | 8,666 | File backup snapshots |
| queue-operation | 5,104 | Subagent queue events |
| system | 4,690 | System/hook events |
| summary | 302 | Conversation summaries |
| pr-link | 30 | PR associations |

### Schema Highlights

The JSONL records have a rich, queryable schema including:

- **Session metadata**: `sessionId`, `slug`, `version`, `gitBranch`, `cwd`
- **Message content**: `message.role`, `message.content` (JSON array of
  text/thinking/tool_use/tool_result blocks)
- **Token usage**: `message.usage.{input_tokens, output_tokens,
  cache_read_input_tokens}`
- **Tool details**: Embedded in content blocks as `{type: "tool_use",
  name: "...", input: {...}}`
- **Context**: `parentUuid` for threading, `isSidechain` for branching

### Project Activity

| Project | Tool Calls | Sessions |
|---------|----------:|--------:|
| lq (blq) | 10,388 | 13 |
| duck_hunt | 6,704 | 10 |
| magic | 5,525 | 5 |
| duckdb_markdown | 2,864 | 3 |
| duckdb_yaml | 2,423 | 12 |
| aidr | 1,706 | 9 |
| duckdb_mcp | 1,589 | 9 |

### Conversation Length

| Metric | Value |
|--------|------:|
| Avg user msgs/session | 258 |
| Median user msgs/session | 69 |
| P90 user msgs/session | 772 |
| Max user msgs/session | 5,063 |

## Implications for Fledgling Design

### 1. Conversation Analysis is Viable and Valuable

DuckDB handles 849 MB of JSONL across 270 files in seconds.
`read_json_auto()` with `union_by_name=true` handles schema variations
gracefully. The data is rich enough to answer questions like:
- "What tools do I use most in project X?"
- "What bash commands keep getting denied?"
- "How long are my typical sessions?"
- "What approaches did we try in the last session on this project?"

### 2. Tool Use Extraction Requires JSON Unnesting

The core query pattern for tool analysis:
```sql
WITH blocks AS (
    SELECT sessionId, unnest(CAST(message.content AS JSON[])) as block
    FROM conversations WHERE type = 'assistant'
)
SELECT block->>'name' as tool, block->'input' as params
FROM blocks WHERE block->>'type' = 'tool_use'
```

This should be pre-materialized as a macro or view in fledgling.

### 3. Priority Order for Fledgling Tools

Based on actual usage data:

1. **duck_tails** (git read ops) — 2,022 bash calls replaced. Highest impact.
2. **sitting_duck** (code search) — 756 bash calls replaced, but also
   qualitatively different from grep (semantic vs text search).
3. **read_lines** (file read) — 459 bash calls replaced. Low volume but
   high per-call value (context around errors, batch retrieval).
4. **conversation analysis** — New capability, zero replacement but
   unique value (cross-session context, tool usage insights).
5. **DuckDB SQL** (text processing) — 98 calls. Nice to have, low priority.
