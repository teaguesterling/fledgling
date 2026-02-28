# Fledgling: Product Specification

**Version**: 0.1 (Draft)
**Status**: Alpha — Phase 2 (MCP tool publications) in progress

## What Is Fledgling?

Fledgling is a DuckDB-powered MCP server that unifies development intelligence tools
into a single queryable surface. It brings together existing DuckDB extensions —
`sitting_duck` (code semantics), `duck_tails` (git state), `read_lines` (file retrieval),
`duckdb_markdown` (document structure) — and adds conversation analysis capabilities,
all exposed as purpose-built MCP tools via `duckdb_mcp`.

The name: a fledgling learning to navigate — this tool helps AI agents get their bearings in source code.

## Problem Statement

AI coding assistants like Claude Code spend significant tokens and user patience on
low-level bash commands for tasks that are fundamentally *data retrieval*:

- **File reading**: `cat`, `head`, `tail`, `sed -n '10,20p'` — when what you want is
  "give me lines 42-60 of these three files"
- **Code search**: `grep -rn`, `find -name` — when what you want is
  "find all function definitions matching X"
- **Git queries**: `git log --oneline`, `git diff HEAD~3` — when what you want is
  "what changed in src/ this week?"
- **Documentation**: Reading entire markdown files when you only need one section —
  when what you want is "give me the Installation section from README.md"
- **Conversation history**: No tooling at all — when what you want is
  "what approaches did we try last session?"

Each of these requires bash whitelisting, produces unstructured text output, and
can't compose with each other. Meanwhile, DuckDB extensions already exist that solve
each problem with structured, queryable results.

## Architecture

Fledgling is **not a new codebase** in the traditional sense. It is:

1. A **DuckDB init script** (`init-fledgling.sql`) that loads extensions, defines
   macros, publishes MCP tools, and starts the server
2. A set of **SQL macro files** organized by concern
3. **Configuration** for Claude Code (`settings.json` / `.mcp.json` integration)

```
fledgling/
  init-fledgling.sql          # Entry point: load, configure, publish, serve
  sql/
    source.sql                # read_lines macros + tools
    code.sql                  # sitting_duck macros + tools
    docs.sql                  # duckdb_markdown macros + tools
    repo.sql                  # duck_tails macros + tools
    conversations.sql         # Conversation log analysis macros + tools
  docs/
    vision/PRODUCT_SPEC.md    # This file
  config/
    claude-code.example.json  # Example MCP server config for settings.json
```

### Extension Dependencies

| Extension | Purpose | Status |
|-----------|---------|--------|
| `duckdb_mcp` | MCP server infrastructure, tool publishing | Required |
| `read_lines` | Line-level file access with ranges/context | Required |
| `sitting_duck` | AST parsing, semantic code analysis (27 langs) | Required |
| `duckdb_markdown` | Markdown section/block parsing and extraction | Required |
| `duck_tails` | Git repository state as queryable tables | Required |
| `json` | JSONL conversation log parsing | Built-in |

### How It Works

```sql
-- init-fledgling.sql (conceptual)
LOAD duckdb_mcp;
LOAD read_lines;
LOAD sitting_duck;
LOAD markdown;
LOAD duck_tails;

-- Load macro definitions
.read sql/source.sql
.read sql/code.sql
.read sql/docs.sql
.read sql/repo.sql
.read sql/conversations.sql

-- Start MCP server (blocks on stdio)
SELECT mcp_server_start('stdio', '{
    "enable_query_tool": true,
    "enable_execute_tool": false,
    "default_result_format": "markdown"
}');
```

Claude Code configuration:
```json
{
  "mcpServers": {
    "fledgling": {
      "command": "duckdb",
      "args": ["-init", "/path/to/fledgling/init-fledgling.sql"]
    }
  }
}
```

## Tool Design

### Tier 1: Source Retrieval (`read_lines`)

These replace bash file-reading commands with structured, batch-capable retrieval.

#### `read_source`
Read specific lines from one or more files with optional context.

```
Parameters:
  files: string[]    — File paths (required)
  lines: string      — Line selection: "42", "10-20", "42 +/-5" (optional)
  context: integer   — Context lines around selection (optional, default 0)

Returns: file_path, line_number, content
```

**Replaces**: `cat`, `head -n`, `tail -n`, `sed -n 'X,Yp'`

#### `read_context`
Read lines around a specific location (optimized for error context).

```
Parameters:
  file: string       — File path (required)
  line: integer      — Center line (required)
  context: integer   — Lines before/after (optional, default 5)

Returns: line_number, content, is_center
```

**Replaces**: `sed -n 'X,Yp' file` patterns in error investigation

### Tier 2: Code Intelligence (`sitting_duck`)

These replace text-based grep with semantic code understanding.

#### `find_definitions`
Find function, class, or variable definitions by name pattern.

```
Parameters:
  pattern: string    — Name pattern, supports wildcards (required)
  path: string       — File or directory to search (optional, default ".")
  language: string   — Filter by language (optional, auto-detected)
  kind: string       — "function", "class", "variable", "type" (optional)

Returns: file_path, name, kind, start_line, end_line, signature
```

**Replaces**: `grep -rn "def pattern\|class pattern\|function pattern"`

#### `find_references`
Find where a symbol is used (calls, imports, assignments).

```
Parameters:
  name: string       — Symbol name (required)
  path: string       — Search scope (optional, default ".")
  kind: string       — "call", "import", "assignment", "all" (optional)

Returns: file_path, line, usage_kind, context_line
```

**Replaces**: `grep -rn "symbol_name"` followed by manual filtering

#### `code_structure`
Get a structural overview of a file or directory.

```
Parameters:
  path: string       — File or directory (required)
  depth: string      — "shallow" (names only) or "deep" (with signatures) (optional)

Returns: file_path, kind, name, start_line, end_line, children_count
```

**Replaces**: Manual file reading to understand code organization

### Tier 3: Documentation Intelligence (`duckdb_markdown`)

These provide structured access to markdown documentation — selective section
retrieval, code block extraction, and document structure overview. This is the
documentation counterpart to `sitting_duck`'s source code analysis.

#### `read_doc_section`
Read a specific section from a markdown file by section ID or heading.

```
Parameters:
  file: string       — Markdown file path (required)
  section: string    — Section ID slug, e.g., "installation" (required)
  include_children: boolean — Include subsections (optional, default true)

Returns: section_id, title, level, content, parent_id
```

**Replaces**: Reading an entire file just to find one section. Uses
`read_markdown_sections` fragment syntax (`'file.md#section'`) underneath.

#### `doc_outline`
Get the structural outline (table of contents) of a markdown file or directory.

```
Parameters:
  path: string       — File or glob pattern (required)
  max_level: integer — Max heading depth (optional, default 3)

Returns: file_path, section_id, section_path, level, title, start_line, end_line
```

**Use case**: Agent decides which section to read before committing tokens
to reading full content. Especially valuable for large docs.

#### `find_code_examples`
Extract code blocks from documentation, filtered by language.

```
Parameters:
  path: string       — File or glob pattern (required)
  language: string   — Code block language filter (optional)

Returns: file_path, language, code, line_number, section_title
```

**Replaces**: Manually reading docs to find example code. Uses
`md_extract_code_blocks()` underneath.

#### `doc_search`
Search across documentation content with structural context.

```
Parameters:
  query: string      — Text to search for (required)
  path: string       — File or glob pattern (optional, default "**/*.md")

Returns: file_path, section_id, section_title, line_number, match_context
```

**Replaces**: `grep -rn "query" docs/` — but returns section context instead
of raw line matches.

### Tier 4: Repository Intelligence (`duck_tails`)

These replace git CLI commands with structured, composable results.

#### `recent_changes`
What changed recently in the repository or a specific path.

```
Parameters:
  path: string       — File or directory filter (optional)
  count: integer     — Number of commits (optional, default 10)
  since: string      — Date filter, e.g., "7 days ago" (optional)

Returns: commit_hash, author, date, message, files_changed
```

**Replaces**: `git log --oneline -n 10 -- path`

#### `file_history`
History of changes to a specific file.

```
Parameters:
  file: string       — File path (required)
  count: integer     — Max commits (optional, default 20)

Returns: commit_hash, author, date, message, lines_added, lines_removed
```

**Replaces**: `git log --follow -- file`

#### `branch_compare`
Compare current branch to another (what's different).

```
Parameters:
  base: string       — Base branch (optional, default "main")
  head: string       — Head branch (optional, default "HEAD")

Returns: file_path, status (added/modified/deleted), insertions, deletions
```

**Replaces**: `git diff --stat main...HEAD`

#### `file_at_version`
Read a file as it existed at a specific commit/branch/tag.

```
Parameters:
  file: string       — File path (required)
  version: string    — Commit hash, branch, or tag (required)
  lines: string      — Line selection (optional)

Returns: line_number, content
```

**Replaces**: `git show revision:path`

### Tier 5: Conversation Intelligence (DuckDB JSON)

These provide queryable access to Claude Code conversation history.

#### `conversation_search`
Search past conversations by content or tool usage.

```
Parameters:
  query: string      — Text to search for in messages (optional)
  tool: string       — Filter by tool name used (optional)
  role: string       — "user", "assistant", "tool" (optional)
  project: string    — Project path filter (optional)
  days: integer      — How far back to look (optional, default 30)

Returns: conversation_id, timestamp, role, content_preview, tool_name
```

**Replaces**: Nothing — this capability doesn't exist today

#### `conversation_tools`
Analyze tool usage patterns across conversations.

```
Parameters:
  project: string    — Project path filter (optional)
  days: integer      — How far back to look (optional, default 30)

Returns: tool_name, call_count, approval_rate, avg_tokens, common_patterns
```

**Use case**: Identify which bash commands to whitelist based on actual usage

#### `conversation_summary`
Get a structured summary of a past conversation.

```
Parameters:
  conversation_id: string  — Conversation ID (required)

Returns: start_time, duration, message_count, tools_used, files_touched, summary
```

**Use case**: Resume context from a previous session

## Design Principles

### 1. SQL macros first, tools second

Every tool is backed by a DuckDB macro. The macro is the real implementation;
the tool is just a published interface. This means:
- Tools are testable as plain SQL
- Power users can query the macros directly via `duckdb_mcp`'s `query` tool
- New tools are cheap to add (one `mcp_publish_tool()` call)

### 2. Composable through SQL

Because everything is DuckDB, tools compose naturally:

```sql
-- "Find all functions that changed in the last 3 commits"
-- (sitting_duck + duck_tails)
SELECT d.name, d.file_path, d.start_line, c.message
FROM find_defs('*', 'src/') d
JOIN recent_commits(3) c ON d.file_path = ANY(c.files_changed);

-- "Find documented functions that lack code examples in docs"
-- (sitting_duck + duckdb_markdown)
SELECT d.name, d.file_path
FROM find_defs('*', 'src/', kind := 'function') d
LEFT JOIN (
    SELECT DISTINCT cb.code
    FROM read_markdown_sections('docs/**/*.md') s,
    LATERAL md_extract_code_blocks(s.content) cb
) doc ON doc.code LIKE '%' || d.name || '%'
WHERE doc.code IS NULL;
```

This kind of cross-cutting query is impossible with separate bash commands.

### 3. Token-efficient output

Default output format is markdown tables (via `duckdb_mcp`), which are
compact and readable. No raw text dumps. Tools return structured results
that the agent can process without parsing.

### 4. Read-only by default

Fledgling is a *retrieval* server. It reads files, parses code, queries git
history, and analyzes conversations. It does not modify anything.
`enable_execute_tool` is `false`. Git write operations (commit, push) are
explicitly out of scope — they belong in a separate "safe-git" server with
purpose-built safety guardrails.

### 5. Symmetric structure: code and docs are peers

`sitting_duck` and `duckdb_markdown` form a natural pair. Both provide
structured, selective retrieval from files that would otherwise require
flat text reading:

| Concern | Extension | Unit of structure | Selection |
|---------|-----------|-------------------|-----------|
| Source code | `sitting_duck` | AST nodes (functions, classes) | Semantic type predicates |
| Documentation | `duckdb_markdown` | Sections, blocks, code blocks | Section ID / heading hierarchy |
| Git history | `duck_tails` | Commits, trees, file versions | Revision / path |
| File content | `read_lines` | Lines | Line number / range |
| Conversations | DuckDB JSON | Messages, tool calls | Session / timestamp / content |

An agent exploring a codebase can use `code_structure` to understand the code,
`doc_outline` to understand the docs, `recent_changes` to understand what's
active, and `read_source`/`read_doc_section` to drill into specifics — all
without a single bash command.

### 6. Zero configuration for common cases

The server should work with sensible defaults when launched from a project
directory. Extensions auto-detect languages, git discovers the repo,
conversation logs are found from `~/.claude/`.

## What Fledgling Is NOT

- **Not a replacement for aidr**: aidr is a persistent analytical workspace with
  cognitive tracking. Fledgling is a read-only retrieval layer.
- **Not a replacement for blq**: blq captures and analyzes build/test output with
  duck_hunt parsing. Fledgling doesn't run commands.
- **Not a git write tool**: No commits, no pushes, no branch operations. That's
  a separate concern with different security requirements.
- **Not a new extension**: Fledgling composes existing extensions. It adds SQL
  macros and MCP tool definitions, not C++ code.

## Impact on settings.json

With Fledgling operational, these bash whitelist entries become unnecessary:

```
REMOVE (replaced by read_source / read_context):
  Bash(cat *), Bash(head *), Bash(tail *)

REMOVE (replaced by find_definitions / find_references / code_structure):
  Bash(grep *), Bash(find *)

REMOVE (replaced by recent_changes / file_history / branch_compare):
  Bash(git log *), Bash(git diff *), Bash(git show *), Bash(git branch *)

REMOVE (replaced by DuckDB SQL via query tool):
  Bash(wc *), Bash(sort *), Bash(uniq *), Bash(cut *), Bash(tr *),
  Bash(awk *), Bash(sed *)

KEEP (no Fledgling equivalent):
  Bash(ls *), Bash(mkdir *), Bash(tree *), Bash(stat *), Bash(file *)
  Bash(realpath *), Bash(basename *), Bash(dirname *)
  Bash(diff *), Bash(echo *), Bash(printf *), Bash(pwd), Bash(which *)
  Bash(gh api *), Bash(gh pr *), Bash(gh issue *), Bash(gh run *)
  Bash(git status *)
```

Net reduction: ~20 bash whitelist entries replaced by structured MCP tools.

## Open Questions

1. **Extension availability**: Are `sitting_duck`, `duck_tails`, and `read_lines`
   installable via `INSTALL ... FROM community` on the user's current DuckDB
   version, or do they need to be loaded from local builds?

2. **Conversation log format**: What's the exact schema of the `.jsonl` files in
   `~/.claude/projects/`? Need to explore before finalizing conversation tools.

3. **Per-project vs global**: Should Fledgling run as a global MCP server (one
   instance serving all projects) or per-project? Git and code analysis are
   inherently project-scoped, but conversations span projects.

4. **Performance**: How fast is `sitting_duck` for large repos? Should there be
   a caching layer, or is DuckDB's native performance sufficient?

5. **Tool count**: MCP tool discovery becomes noisy with too many tools. Should
   some be grouped (e.g., a single `code` tool with a `kind` parameter) or
   kept separate for discoverability?

## Success Criteria

Fledgling is successful when:

- An agent can find "all Python function definitions containing 'parse'" without
  a single bash command
- An agent can answer "what files changed since yesterday?" with structured data,
  not git log text parsing
- An agent can read specific line ranges from 5 files in a single tool call
- An agent can get just the "Configuration" section from a README without reading
  the whole file
- A user can analyze their past conversations to identify tool usage patterns
- The `settings.json` bash whitelist shrinks by 50%+ without loss of capability
