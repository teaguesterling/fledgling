# Fledgling Skill Guide

Fledgling gives you structured, token-efficient access to the codebase you're working in. Instead of reading raw files and guessing at structure, you get targeted tools backed by SQL macros and real parsers (AST for code, markdown parser for docs, git for history).

## Quick Reference

| Tool | Purpose | Returns | Macro |
|------|---------|---------|-------|
| | **Help** | | |
| **Help** | This guide. Call with no args for outline, or a section ID for details. | `section_id, title, level, content` | `help` |
| | **Files** | | |
| **ListFiles** | Find files by glob pattern or git tree. | `file_path` | `list_files` |
| **ReadLines** | Read file lines with optional range, context, and match filtering. | `line_number, content` | `read_source` |
| **ProjectOverview** | File counts grouped by language/extension. | `language, extension, file_count` | `project_overview` |
| **ReadAsTable** | Preview structured data (CSV, JSON) as tables. | `(varies by data)` | `read_as_table` |
| | **Code** | | |
| **FindDefinitions** | AST-based search for functions, classes, variables. | `file_path, name, kind, start_line, end_line, signature` | `find_definitions` |
| **FindCalls** | Find where functions/methods are called (AST, not grep). | `file_path, name, start_line, call_expression` | `find_calls` |
| **FindImports** | Find import/include/require statements. | `file_path, name, import_statement, start_line` | `find_imports` |
| **CodeStructure** | Top-level overview: what's defined in each file. | `file_path, name, kind, start_line, end_line, line_count` | `code_structure` |
| | **Docs** | | |
| **MDOutline** | Table of contents for markdown files. | `file_path, section_id, section_path, level, title, start_line, end_line` | `doc_outline` |
| **MDSection** | Read a specific section from a markdown file. | `section_id, title, level, content, start_line, end_line` | `read_doc_section` |
| | **Git** | | |
| **GitChanges** | Recent commit history. | `hash, author, date, message` | `recent_changes` |
| **GitBranches** | List branches with current branch marked. | `branch_name, hash, is_current, is_remote` | `branch_list` |
| **GitTags** | List tags with metadata. | `tag_name, hash, tagger_name, tagger_date, message, is_annotated` | `tag_list` |
| **GitDiffSummary** | File-level change summary between revisions. | `file_path, status, old_size, new_size` | `file_changes` |
| **GitDiffFile** | Line-level unified diff for a single file. | `seq, line_type, content` | `file_diff` |
| **GitShow** | File content at a specific revision. | `file_path, ref, size_bytes, content` | `file_at_version` |
| **GitStatus** | Working tree status (untracked/deleted files). | `file_path, status` | `working_tree_status` |
| | **Conversations** | | |
| **ChatSessions** | Browse Claude Code conversation sessions. | `session_id, project_dir, slug, git_branch, started_at, duration, ...` | `session_summary` |
| **ChatSearch** | Full-text search across conversation messages. | `session_id, slug, role, content_preview, created_at` | `search_messages` |
| **ChatToolUsage** | Tool usage frequency across sessions. | `tool_name, total_calls, sessions, first_used, last_used` | `tool_frequency` |
| **ChatDetail** | Deep view of a single session with per-tool breakdown. | `slug, project_dir, duration, total_tokens, tool_name, calls, ...` | `session_summary` |
| | **Query** | | |
| **query** | Run arbitrary SQL against any of the above macros. | `(varies)` | — |

## File Navigation

### ListFiles

Find files matching a glob pattern. Good for discovering project structure.

**Returns:** `file_path`
**Macro:** `list_files(pattern, commit := NULL)`

```
ListFiles(pattern="src/**/*.py")           # all Python files under src/
ListFiles(pattern="*.md")                  # markdown in current dir
ListFiles(pattern="sql/%", commit="HEAD")  # git mode: SQL LIKE syntax
```

Git mode (with `commit`) uses SQL LIKE wildcards (`%`, `_`) instead of globs.

### ReadLines

Read file content with precision. Replaces cat/head/tail with structured output.

**Returns:** `line_number, content`
**Macro:** `read_source(file_path, lines := NULL, ctx := 0, match := NULL)`

```
ReadLines(file_path="src/main.py")                    # whole file
ReadLines(file_path="src/main.py", lines="10-25")     # line range
ReadLines(file_path="src/main.py", lines="42", ctx="5")  # line 42 ± 5 lines
ReadLines(file_path="src/main.py", match="import")    # only matching lines
ReadLines(file_path="src/main.py", lines="1-50", match="def")  # combined
ReadLines(file_path="src/main.py", commit="HEAD~1")   # previous version
```

### ProjectOverview

Quick overview of project contents: file counts grouped by language/extension. Answers "what is this project?" without multiple exploratory calls.

**Returns:** `language, extension, file_count`
**Macro:** `project_overview(root := '.')`

```
ProjectOverview()                    # whole project
ProjectOverview(path="src")          # just src/
```

### ReadAsTable

Preview structured data files as formatted tables.

**Returns:** varies by data file schema
**Macro:** `read_as_table(file_path, lim := 100)`

```
ReadAsTable(file_path="data/results.csv")
ReadAsTable(file_path="config.json", limit="20")
```

Supports CSV, JSON, and other formats DuckDB can auto-detect.

## Code Intelligence

All code tools use AST parsing (via sitting_duck), not text matching. They work across 30 languages:

Bash, C, C++, C#, CSS, Dart, F#, Go, GraphQL, Haskell, HCL, HTML, Java, JavaScript, JSON, Julia, Kotlin, Lua, Markdown, PHP, Python, R, Ruby, Rust, Scala, Swift, TOML, TypeScript, YAML, Zig

Use `ast_supported_languages()` via the `query` tool for the live list.

### FindDefinitions

Find where things are defined: functions, classes, methods, variables.

**Returns:** `file_path, name, kind, start_line, end_line, signature`
**Macro:** `find_definitions(file_pattern, name_pattern := '%')`

```
FindDefinitions(file_pattern="src/**/*.py")                # all definitions
FindDefinitions(file_pattern="src/**/*.py", name_pattern="parse%")  # names starting with "parse"
FindDefinitions(file_pattern="lib/*.ts", name_pattern="%Handler")   # names ending with "Handler"
```

The `name_pattern` uses SQL LIKE wildcards: `%` matches any sequence, `_` matches one character.

### FindCalls

Find call sites — where functions and methods are invoked.

**Returns:** `file_path, name, start_line, call_expression`
**Macro:** `find_calls(file_pattern, name_pattern := '%')`

```
FindCalls(file_pattern="src/**/*.py")
FindCalls(file_pattern="src/**/*.py", name_pattern="connect%")
```

### FindImports

Find import/require/include statements across languages.

**Returns:** `file_path, name, import_statement, start_line`
**Macro:** `find_imports(file_pattern)`

```
FindImports(file_pattern="src/**/*.py")
FindImports(file_pattern="src/**/*.ts")
```

### CodeStructure

High-level overview of what's defined in files, with line counts. Good first step to understand unfamiliar code.

**Returns:** `file_path, name, kind, start_line, end_line, line_count`
**Macro:** `code_structure(file_pattern)`

```
CodeStructure(file_pattern="src/**/*.py")
CodeStructure(file_pattern="lib/auth.ts")
```

## Documentation

### MDOutline

Get the table of contents of markdown files. Returns section IDs you can pass to MDSection.

**Returns:** `file_path, section_id, section_path, level, title, start_line, end_line`
**Macro:** `doc_outline(file_pattern, max_lvl := 3)`

```
MDOutline(file_pattern="docs/**/*.md")
MDOutline(file_pattern="README.md", max_level="2")  # only h1 and h2
```

### MDSection

Read a specific section by ID. Use MDOutline first to discover IDs.

**Returns:** `section_id, title, level, content, start_line, end_line`
**Macro:** `read_doc_section(file_path, target_id)`

```
MDSection(file_path="docs/guide.md", section_id="installation")
MDSection(file_path="README.md", section_id="getting-started")
```

Returns the section and its children (subsections).

## Git

### GitChanges

Recent commit log. Replaces `git log --oneline`.

**Returns:** `hash, author, date, message`
**Macro:** `recent_changes(n := 10, repo := '.')`

```
GitChanges()              # last 10 commits
GitChanges(count="5")     # last 5 commits
```

### GitBranches

List all branches with the current branch marked.

**Returns:** `branch_name, hash, is_current, is_remote`
**Macro:** `branch_list(repo := '.')`

```
GitBranches()
```

### GitTags

List all tags with metadata.

**Returns:** `tag_name, hash, tagger_name, tagger_date, message, is_annotated`
**Macro:** `tag_list(repo := '.')`

```
GitTags()
```

### GitDiffSummary

File-level summary of changes between two git revisions.

**Returns:** `file_path, status, old_size, new_size`
**Macro:** `file_changes(from_rev, to_rev, repo := '.')`

```
GitDiffSummary(from_rev="HEAD~1", to_rev="HEAD")
GitDiffSummary(from_rev="main", to_rev="feature-branch")
```

### GitDiffFile

Line-level unified diff for a specific file between two revisions.

**Returns:** `seq, line_type, content`
**Macro:** `file_diff(file, from_rev, to_rev, repo := '.')`

```
GitDiffFile(file_path="src/main.py", from_rev="HEAD~1", to_rev="HEAD")
```

### GitShow

Show file content at a specific git revision. Replaces `git show rev:path`.

**Returns:** `file_path, ref, size_bytes, content`
**Macro:** `file_at_version(file, rev, repo := '.')`

```
GitShow(file="README.md", rev="HEAD~1")
GitShow(file="sql/repo.sql", rev="main")
```

### GitStatus

Working tree status: untracked and deleted files compared to HEAD.

**Returns:** `file_path, status`
**Macro:** `working_tree_status(repo := '.')`

```
GitStatus()
```

Does not detect content modifications — use GitDiffSummary for revision diffs.

## Conversations

Tools for analyzing Claude Code conversation history (JSONL files in `~/.claude/projects/`).

### ChatSessions

Browse conversation sessions with metadata, duration, tool usage, and token consumption.

**Returns:** `session_id, project_dir, slug, git_branch, started_at, duration, user_messages, total_tool_calls, distinct_tools_used, top_tool, total_tokens, avg_cache_hit_rate`
**Macro:** `session_summary()`

```
ChatSessions()                              # all recent sessions
ChatSessions(project="my-project")          # filter by project name
ChatSessions(days="7")                      # last week only
ChatSessions(days="30", limit="5")          # top 5 from last month
```

### ChatSearch

Full-text search across conversation messages.

**Returns:** `session_id, slug, role, content_preview, created_at`
**Macro:** `search_messages(search_term)`

```
ChatSearch(query="authentication")                    # search all messages
ChatSearch(query="bug fix", role="assistant")          # only assistant replies
ChatSearch(query="refactor", project="my-app", days="14")
```

### ChatToolUsage

Tool usage frequency across sessions. Shows which tools are used most.

**Returns:** `tool_name, total_calls, sessions, first_used, last_used`
**Macro:** `tool_frequency()`

```
ChatToolUsage()                              # all tool usage
ChatToolUsage(project="my-project")          # per-project breakdown
ChatToolUsage(session_id="<uuid>")           # single session
ChatToolUsage(days="7")                      # last week
```

### ChatDetail

Deep view of a single session: metadata, token costs, and per-tool breakdown.

**Returns:** `slug, project_dir, git_branch, started_at, duration, user_messages, assistant_messages, total_tokens, avg_cache_hit_rate, bash_calls, bash_replaceable_calls, tool_name, calls`
**Macro:** `session_summary()` + `tool_frequency()`

```
ChatDetail(session_id="<uuid>")
```

## Workflows

### Explore an Unfamiliar Codebase

1. `ProjectOverview()` — see languages and file counts at a glance
2. `ListFiles(pattern="**/*.py")` — see what files exist
3. `CodeStructure(file_pattern="src/**/*.py")` — understand what's defined where
4. `MDOutline(file_pattern="*.md")` — check for documentation
5. `MDSection(file_path="README.md", section_id="...")` — read relevant docs

### Understand a Function

1. `FindDefinitions(file_pattern="src/**/*.py", name_pattern="my_func%")` — find where it's defined
2. `ReadLines(file_path="src/module.py", lines="42-80")` — read the implementation
3. `FindCalls(file_pattern="src/**/*.py", name_pattern="my_func%")` — find where it's called

### Review Recent Changes

1. `GitChanges(count="5")` — see what changed recently
2. `GitDiffSummary(from_rev="HEAD~3", to_rev="HEAD")` — which files changed
3. `GitDiffFile(file_path="src/changed.py", from_rev="HEAD~1", to_rev="HEAD")` — line-level diff
4. `GitShow(file="src/changed.py", rev="HEAD~1")` — compare with previous version

### Analyze Dependencies

1. `FindImports(file_pattern="src/**/*.py")` — see all imports
2. `FindCalls(file_pattern="src/**/*.py", name_pattern="module%")` — find usage of a specific module

### Analyze Conversation Patterns

1. `ChatSessions(days="30")` — recent session overview
2. `ChatToolUsage(days="30")` — which tools get used most
3. `ChatDetail(session_id="<uuid>")` — drill into a specific session
4. `ChatSearch(query="error", days="7")` — find recent error discussions

## Macro Reference

The `query` tool lets you run arbitrary SQL using the underlying macros. This is useful for filtering, joining, or aggregating results beyond what individual tools expose.

**Sandbox caveat:** Filesystem-backed macros (glob patterns like `src/**/*.py`) may fail in the `query` tool due to `allowed_directories` restrictions. Use the dedicated MCP tools for file operations. Git-backed and conversation macros work directly in `query`.

### Files

| Macro | Signature |
|-------|-----------|
| `list_files` | `(pattern, commit := NULL)` |
| `read_source` | `(file_path, lines := NULL, ctx := 0, match := NULL)` |
| `read_source_batch` | `(file_pattern, lines := NULL, ctx := 0)` |
| `read_context` | `(file_path, center_line, ctx := 5)` |
| `file_line_count` | `(file_pattern)` |
| `project_overview` | `(root := '.')` |
| `read_as_table` | `(file_path, lim := 100)` |

### Code

| Macro | Signature |
|-------|-----------|
| `find_definitions` | `(file_pattern, name_pattern := '%')` |
| `find_calls` | `(file_pattern, name_pattern := '%')` |
| `find_imports` | `(file_pattern)` |
| `code_structure` | `(file_pattern)` |

### Docs

| Macro | Signature |
|-------|-----------|
| `doc_outline` | `(file_pattern, max_lvl := 3)` |
| `read_doc_section` | `(file_path, target_id)` |
| `find_code_examples` | `(file_pattern, lang := NULL)` |
| `doc_stats` | `(file_pattern)` |

### Git

| Macro | Signature |
|-------|-----------|
| `recent_changes` | `(n := 10, repo := '.')` |
| `branch_list` | `(repo := '.')` |
| `tag_list` | `(repo := '.')` |
| `repo_files` | `(rev := 'HEAD', repo := '.')` |
| `file_at_version` | `(file, rev, repo := '.')` |
| `file_changes` | `(from_rev, to_rev, repo := '.')` |
| `file_diff` | `(file, from_rev, to_rev, repo := '.')` |
| `working_tree_status` | `(repo := '.')` |

### Conversations

| Macro | Signature |
|-------|-----------|
| `sessions` | `()` |
| `messages` | `()` |
| `content_blocks` | `()` |
| `tool_calls` | `()` |
| `tool_results` | `()` |
| `token_usage` | `()` |
| `tool_frequency` | `()` |
| `bash_commands` | `()` |
| `session_summary` | `()` |
| `model_usage` | `()` |
| `search_messages` | `(search_term)` |
| `search_tool_inputs` | `(search_term)` |

### Help

| Macro | Signature |
|-------|-----------|
| `help` | `(target_id := NULL)` |

### Example queries

```sql
-- Recent commit history (git macros work in query)
SELECT * FROM recent_changes(5);

-- Tool usage frequency across conversations
SELECT tool_name, sum(call_count) AS total
FROM tool_frequency()
GROUP BY 1 ORDER BY 2 DESC;

-- Files changed between two revisions
SELECT * FROM file_changes('HEAD~3', 'HEAD');

-- Token usage by model
SELECT * FROM model_usage();
```

## Tips

### Supported Languages

Use `ast_supported_languages()` via the `query` tool to check the live list of languages supported by the code intelligence tools.

### Glob Patterns

- `*` matches within a directory: `src/*.py`
- `**` matches across directories: `src/**/*.py`
- Combine extensions: `src/**/*.{py,ts}`
- Git mode uses SQL LIKE: `%` for any sequence, `_` for single character

### Path Handling

- Paths are resolved relative to the project root
- Use absolute paths when outside the project
- Git mode paths are always repo-relative
- The sandbox restricts filesystem access to the project directory; use dedicated tools instead of raw SQL for file operations

### Output Format

All tools return markdown tables. When using the `query` tool, results are also formatted as markdown by default.

### Token Efficiency

- Use `ProjectOverview` first to understand what's in the project
- Use `MDOutline` before `MDSection` to avoid reading irrelevant docs
- Use `CodeStructure` before `ReadLines` to find the right file and line range
- Use `FindDefinitions` with `name_pattern` to narrow results
- Use `ReadLines` with `lines` and `match` to read only what you need
- Use `ListFiles` to verify paths before reading
