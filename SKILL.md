# Fledgling Skill Guide

Fledgling gives you structured, token-efficient access to the codebase you're working in. Instead of reading raw files and guessing at structure, you get targeted tools backed by SQL macros and real parsers (AST for code, markdown parser for docs, git for history).

## Quick Reference

### Tools

| Tool | Purpose | Key params |
|------|---------|------------|
| **ReadLines** | Read file content with line ranges, context, and match filtering | `file_path`, `lines`, `match`, `commit` |
| **FindDefinitions** | AST-based search for functions, classes, variables | `file_pattern`, `name_pattern` |
| **FindCode** | CSS selector search: `.func`, `#name`, `:has(...)`, `::callers` | `file_pattern`, `selector` |
| **ViewCode** | View source matched by CSS selector with context lines | `file_pattern`, `selector`, `context` |
| **SelectCode** | Render selector matches as markdown: file:range headings + full source blocks | `source`, `selector` |
| **CodeStructure** | Top-level overview: what's defined in each file | `file_pattern` |
| **ExploreProject** | First-contact briefing: languages, structure, docs, recent activity | `root`, `code_pattern`, `doc_pattern` |
| **InvestigateSymbol** | Deep dive: definitions, callers, call sites for a symbol | `name`, `file_pattern` |
| **ReviewChanges** | Change review: files and functions ranked by complexity | `from_rev`, `to_rev`, `file_pattern` |
| **SearchProject** | Multi-source search across definitions, calls, and docs | `pattern`, `file_pattern` |
| **MDOverview** | Browse all docs with keyword/regex search | `file_pattern`, `search` |
| **MDSection** | Read a markdown section by ID | `file_path`, `section_id` |
| **GitDiffSummary** | File-level change summary between revisions | `from_rev`, `to_rev` |
| **GitShow** | File content at a specific git revision | `file`, `rev` |
| **Help** | This guide (no args = outline, section_id = details) | `section` |
| **ChatSessions** | Browse conversation sessions | `project`, `days`, `limit` |
| **ChatSearch** | Search across conversation messages | `query`, `role` |
| **ChatToolUsage** | Tool usage frequency | `project`, `days` |
| **ChatDetail** | Deep view of a single session | `session_id` |
| **SearchContent** | BM25 full-text search over docs + code (requires rebuild first) | `query`, `kind`, `extractor`, `limit` |
| **SearchDocs** | BM25 search over markdown sections | `query`, `limit` |
| **SearchCode** | BM25 search over code (definition/comment/string) | `query`, `kind`, `limit` |
| **FtsStats** | Diagnostic: counts per extractor/kind in the FTS index | — |

### Query-Only Macros

These macros are available via the **query** tool. They provide the full power of Fledgling's SQL composability — you can join, filter, and aggregate across them.

| Macro | Purpose | Example |
|-------|---------|---------|
| `list_files(pattern)` | Find files by glob | `SELECT * FROM list_files('src/**/*.py')` |
| `project_overview(root)` | File counts by language | `SELECT * FROM project_overview('.')` |
| `read_as_table(path, limit)` | Preview CSV/JSON/Parquet as table | `SELECT * FROM read_as_table('data.csv')` |
| `find_calls(pattern, name)` | Find function call sites | `SELECT * FROM find_calls('src/**/*.py', 'connect')` |
| `find_imports(pattern)` | Find import statements | `SELECT * FROM find_imports('src/**/*.py')` |
| `complexity_hotspots(pattern, n)` | Functions ranked by cyclomatic complexity | `SELECT * FROM complexity_hotspots('src/**/*.py', 10)` |
| `function_callers(pattern, name)` | Who calls a function? | `SELECT * FROM function_callers('src/**/*.py', 'validate')` |
| `module_dependencies(pattern, pkg)` | Internal import graph with fan-in | `SELECT * FROM module_dependencies('src/**/*.py', 'myapp')` |
| `doc_outline(pattern, max_level)` | Markdown table of contents | `SELECT * FROM doc_outline('docs/**/*.md')` |
| `recent_changes(n, repo)` | Commit history | `SELECT * FROM recent_changes(10)` |
| `branch_list(repo)` | List branches | `SELECT * FROM branch_list()` |
| `tag_list(repo)` | List tags | `SELECT * FROM tag_list()` |
| `file_changes(from, to, repo)` | Files changed between revisions | `SELECT * FROM file_changes('HEAD~3', 'HEAD')` |
| `file_diff(file, from, to, repo)` | Line-level unified diff | `SELECT * FROM file_diff('src/main.py', 'HEAD~1', 'HEAD')` |
| `working_tree_status(repo)` | Untracked/deleted files | `SELECT * FROM working_tree_status()` |
| `structural_diff(file, from, to)` | Semantic diff: added/removed/modified definitions | `SELECT * FROM structural_diff('src/main.py', 'HEAD~1', 'HEAD')` |
| `changed_function_summary(from, to, pattern)` | Functions in changed files, ranked by cyclomatic complexity | `SELECT * FROM changed_function_summary('HEAD~5', 'HEAD', 'src/**/*.py')` |

## Tools

### ReadLines

Read file content with precision. Replaces cat/head/tail with structured output.

**Returns:** `line_number, content`

```
ReadLines(file_path="src/main.py")                    # whole file
ReadLines(file_path="src/main.py", lines="10-25")     # line range
ReadLines(file_path="src/main.py", lines="42", ctx="5")  # line 42 +/- 5 lines
ReadLines(file_path="src/main.py", match="import")    # only matching lines
ReadLines(file_path="src/main.py", lines="1-50", match="def")  # combined
ReadLines(file_path="src/main.py", commit="HEAD~1")   # previous version
```

### FindDefinitions

Find where things are defined: functions, classes, methods, variables. AST-based, not text matching.

**Returns:** `file_path, name, kind, start_line, end_line, signature`

```
FindDefinitions(file_pattern="src/**/*.py")                # all definitions
FindDefinitions(file_pattern="src/**/*.py", name_pattern="parse%")  # names starting with "parse"
FindDefinitions(file_pattern="lib/*.ts", name_pattern="%Handler")   # names ending with "Handler"
```

The `name_pattern` uses SQL LIKE wildcards: `%` matches any sequence, `_` matches one character.

### CodeStructure

High-level overview of what's defined in files, with line counts. Good first step to understand unfamiliar code.

**Returns:** `file_path, name, kind, start_line, end_line, line_count`

```
CodeStructure(file_pattern="src/**/*.py")
CodeStructure(file_pattern="lib/auth.ts")
```

### MDSection

Read a specific markdown section by ID. Use `doc_outline()` via the query tool to discover section IDs first.

**Returns:** `section_id, title, level, content, start_line, end_line`

```
MDSection(file_path="docs/guide.md", section_id="installation")
MDSection(file_path="README.md", section_id="getting-started")
```

### GitDiffSummary

File-level summary of changes between two git revisions. For function-level analysis, use `structural_diff()` or `changed_function_summary()` via the query tool.

**Returns:** `file_path, status, old_size, new_size`

```
GitDiffSummary(from_rev="HEAD~1", to_rev="HEAD")
GitDiffSummary(from_rev="main", to_rev="feature-branch")
```

### GitShow

Show file content at a specific git revision. Replaces `git show rev:path`.

**Returns:** `file_path, ref, size_bytes, content`

```
GitShow(file="README.md", rev="HEAD~1")
GitShow(file="sql/repo.sql", rev="main")
```

### Help

This guide. Call with no args to see the section outline, or pass a section ID for details.

```
Help()                              # outline
Help(section="workflows")           # specific section
```

## Code Intelligence

All code tools use AST parsing (via sitting_duck), not text matching. They work across 30 languages including Python, JavaScript, TypeScript, Rust, Go, Java, C/C++, Ruby, and more.

Use `ast_supported_languages()` via the `query` tool for the live list.

### Composing Macros

The real power of Fledgling is composing macros via the query tool. Examples:

```sql
-- Complex functions in recently changed files
SELECT h.file_path, h.name, h.cyclomatic, h.lines
FROM complexity_hotspots('src/**/*.py') h
WHERE h.file_path IN (
    SELECT file_path FROM changed_function_summary('main', 'HEAD', 'src/**/*.py')
);

-- Module dependency fan-in (what's the most-imported module?)
SELECT target_module, fan_in
FROM module_dependencies('src/**/*.py', 'myapp')
ORDER BY fan_in DESC;

-- Functions over 20 lines with high complexity
SELECT file_path, name, cyclomatic, lines
FROM complexity_hotspots('src/**/*.py', 100)
WHERE cyclomatic > 10 AND lines > 20;
```

## Workflows

### Explore an Unfamiliar Codebase

**Quick (one call):** `ExploreProject()` — returns languages, top-complexity definitions, doc outline, and recent git activity in one structured result.

**Detailed (step-by-step):**
1. `CodeStructure(file_pattern="src/**/*.py")` — see what's defined where
2. `ReadLines(file_path="src/main.py")` — read key files
3. `MDOverview(file_pattern="*.md")` — find docs
4. `MDSection(file_path="README.md", section_id="...")` — read relevant docs

### Understand a Function

**Quick (one call):** `InvestigateSymbol(name="my_func")` — returns definitions, callers, and call sites in one result.

**Detailed (step-by-step):**
1. `FindDefinitions(file_pattern="src/**/*.py", name_pattern="my_func%")` — find it
2. `ReadLines(file_path="src/module.py", lines="42-80")` — read implementation
3. Use query tool: `SELECT * FROM function_callers('src/**/*.py', 'my_func')` — who calls it?

### Review Recent Changes

**Quick (one call):** `ReviewChanges(from_rev="HEAD~3", to_rev="HEAD")` — returns changed files and functions ranked by complexity.

**Detailed (step-by-step):**
1. `GitDiffSummary(from_rev="HEAD~3", to_rev="HEAD")` — which files changed
2. Use query tool: `SELECT * FROM changed_function_summary('HEAD~3', 'HEAD', 'src/**/*.py')` — what functions are affected
3. Use query tool: `SELECT * FROM complexity_hotspots('src/**/*.py', 10)` — what's risky
4. `ReadLines(file_path="src/changed.py", lines="42-80")` — read the changes

### Search Across Sources

**Quick (one call):** `SearchProject(pattern="parse%")` — searches definitions, call sites, and docs simultaneously.

### View Code by Selector

Use CSS selectors to find and view code structurally:

```
FindCode(file_pattern="src/**/*.py", selector=".func#validate")
ViewCode(file_pattern="src/**/*.py", selector=".func:has(.call#execute)")
SelectCode(source="src/**/*.py", selector=".class > .func")
```

Selector syntax: `.func`, `.class`, `.call`, `.import`, `#name`, `:has(child)`, `:not(...)`, `::callers`, `::callees`, `A > B` (direct child), `A ~ B` (sibling).

### Analyze Architecture

1. Use query tool: `SELECT * FROM module_dependencies('src/**/*.py', 'myapp')` — import graph
2. `CodeStructure(file_pattern="src/core/*.py")` — core module structure
3. Use query tool: `SELECT * FROM complexity_hotspots('src/**/*.py', 20)` — complexity hotspots

## Macro Reference

All macros are available via the **query** tool.

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
| `find_code` | `(file_pattern, selector, lang := NULL)` |
| `find_code_grep` | `(file_pattern, selector, lang := NULL)` |
| `view_code` | `(file_pattern, selector, lang := NULL, ctx := 0)` |
| `view_code_text` | `(file_pattern, selector, lang := NULL, ctx := 0)` |
| `code_structure` | `(file_pattern)` |
| `find_class_members` | `(file_path, class_node_id)` |
| `complexity_hotspots` | `(file_pattern, n := 20)` |
| `function_callers` | `(file_pattern, func_name)` |
| `module_dependencies` | `(file_pattern, package_prefix)` |

### Structural Analysis

| Macro | Signature |
|-------|-----------|
| `structural_diff` | `(file, from_rev, to_rev, repo := '.')` |
| `changed_function_summary` | `(from_rev, to_rev, file_pattern, repo := '.')` |

### Workflows

| Macro | Signature |
|-------|-----------|
| `explore_query` | `(root := '.', code_pattern := '**/*.py', doc_pattern := 'docs/**/*.md', top_n := 20, recent_n := 10)` |
| `investigate_query` | `(name, file_pattern := '**/*.py')` |
| `review_query` | `(from_rev := 'HEAD~1', to_rev := 'HEAD', file_pattern := '**/*.py', repo := '.', top_n := 20)` |
| `search_query` | `(pattern, file_pattern := '**/*.py', doc_pattern := 'docs/**/*.md', top_n := 50)` |
| `pss_render` | `(source, selector)` |
| `ast_select_render` | `(source, selector)` |

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

## Tips

### Supported Languages

Use `ast_supported_languages()` via the `query` tool to check the live list of languages supported by the code intelligence tools.

### Glob Patterns

- `*` matches within a directory: `src/*.py`
- `**` matches across directories: `src/**/*.py`
- Combine extensions: `src/**/*.{py,ts}`

### Path Handling

- Paths are resolved relative to the project root
- Use absolute paths when outside the project
- Git mode paths are always repo-relative
- The sandbox restricts filesystem access to the project directory; use dedicated tools instead of raw SQL for file operations

### Discovering Macro Schemas

Use the `describe` tool to inspect what columns a macro returns:

```
describe(query="SELECT * FROM complexity_hotspots('test', 1)")
```

This reveals column names and types, making it easier to compose macros via joins.

### Data File Formats

`read_as_table(path)` auto-detects format by extension:

| Extension | Reader | Built-in? |
|-----------|--------|-----------|
| `.csv`, `.tsv` | `read_csv_auto` | Yes |
| `.json`, `.jsonl` | `read_json_auto` | Yes |
| `.parquet`, `.pq` | `read_parquet` | Yes |

Unsupported extensions fall back to CSV. For other formats, use the query tool with DuckDB's native readers directly (e.g., `SELECT * FROM 'data.xlsx'` if the spatial extension is installed).

### Token Efficiency

- Use `CodeStructure` first to understand what's in a file before reading it
- Use `FindDefinitions` with `name_pattern` to narrow results
- Use `FindCode` with CSS selectors for targeted structural searches (`.call#execute`, `.import`, `:has(...)`)
- Use `ReadLines` with `lines` and `match` to read only what you need
- Use `doc_outline()` via query before `MDSection` to find the right section
