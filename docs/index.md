# Fledgling Documentation

**MCP tools that help AI agents get their bearings in a codebase — unified SQL views over code, git, docs, and conversations, powered by DuckDB.**

> **Install:** `curl -sL https://raw.githubusercontent.com/teaguesterling/fledgling/main/sql/install-fledgling.sql | duckdb`
>
> Or use the [interactive installer](https://teaguesterling.github.io/fledgling/) to customize modules and profile.

## Two Layers

| Layer | Install | What you get |
|-------|---------|-------------|
| **SQL macros** | `curl \| duckdb` | 20 MCP tools, 30+ query macros, pure DuckDB, zero Python |
| **Python API** | `pip install fledgling-mcp` | `fledgling.connect()`, macros as methods, CLI, `attach`/`lockdown`/`configure` |

## Ecosystem

| Package | What it does | Install |
|---------|-------------|---------|
| **fledgling** | SQL macro foundation + Python connection API | `pip install fledgling-mcp` |
| [**pluckit**](https://github.com/teaguesterling/pluckit) | Fluent Python API — CSS selectors, jQuery-style chaining, mutations | `pip install ast-pluckit` |
| [**squawkit**](https://github.com/teaguesterling/squawkit) | MCP server with smart defaults, caching, workflows, prompts | `pip install squawkit` (coming soon) |

## MCP Tools (20)

| Tool | Purpose |
|------|---------|
| [ReadLines](macros/source.md) | File content with line ranges, context, and match filtering |
| [FindDefinitions](macros/code.md) | AST search for functions/classes/modules (30 languages) |
| [FindCode](macros/code.md) | CSS selector search: `.func`, `#name`, `:has(...)`, `::callers` |
| [ViewCode](macros/code.md) | View source matched by CSS selector with context lines |
| SelectCode | Render selector matches as markdown: headings + full source blocks |
| [CodeStructure](macros/code.md) | Structural overview with cyclomatic complexity metrics |
| ExploreProject | First-contact briefing: languages, structure, docs, recent activity |
| InvestigateSymbol | Deep dive: definitions, callers, call sites for a symbol |
| ReviewChanges | Change review: files and functions ranked by complexity |
| SearchProject | Multi-source search across definitions, calls, and docs |
| [MDOverview](macros/docs.md) | Browse documentation with keyword/regex search |
| [MDSection](macros/docs.md) | Read a markdown section by ID |
| [GitDiffSummary](macros/repo.md) | File-level change summary between revisions |
| [GitDiffFile](macros/repo.md) | Line-level unified diff |
| [GitShow](macros/repo.md) | File content at a git revision |
| Help | Built-in skill guide with workflows and macro catalog |
| [ChatSessions](macros/conversations.md) | Browse Claude Code conversation sessions |
| [ChatSearch](macros/conversations.md) | Full-text search across conversations |
| [ChatToolUsage](macros/conversations.md) | Tool usage frequency |
| [ChatDetail](macros/conversations.md) | Deep view of a single session |

## SQL Macros by Tier

### [Files](macros/source.md)
`list_files` `read_source` `read_source_batch` `read_context` `file_line_count` `project_overview` `read_as_table`

### [Code](macros/code.md)
`find_definitions` `find_calls` `find_imports` `find_code` `find_code_grep` `view_code` `view_code_text` `code_structure` `find_class_members` `complexity_hotspots` `function_callers` `module_dependencies`

### Workflows
`explore_query` `investigate_query` `review_query` `search_query` `pss_render`

### [Docs](macros/docs.md)
`doc_outline` `read_doc_section` `find_code_examples` `doc_stats`

### [Git](macros/repo.md)
`recent_changes` `branch_list` `tag_list` `repo_files` `file_at_version` `file_changes` `file_diff` `working_tree_status` `structural_diff` `changed_function_summary`

### [Conversations](macros/conversations.md)
`sessions` `messages` `content_blocks` `tool_calls` `tool_results` `token_usage` `tool_frequency` `bash_commands` `session_summary` `model_usage` `search_messages` `search_tool_inputs`

## Python API

```python
import fledgling

con = fledgling.connect()                                    # auto-discovers .fledgling-init.sql
con.find_definitions("**/*.py", name_pattern="parse%").show()  # macros as methods
con.recent_changes(5).select("hash, message").df()             # returns pandas DataFrame

# Composable init for advanced use
raw = duckdb.connect()
fledgling.attach(raw, root="/my/project")
fledgling.lockdown(raw, allowed_dirs=["/my/project"])
```

## CLI

```bash
fledgling find-definitions 'src/**/*.py' '%parse%'
fledgling recent-changes 10 -c hash,message -f csv
fledgling CodeStructure '**/*.rs'                    # PascalCase works too
fledgling query "SELECT * FROM complexity_hotspots('**/*.py', 10)"
fledgling update                                      # preserves config
eval "$(fledgling --completions bash)"                # tab completion
```

## Coming Soon

- **[fledgling-edit](edit/index.md)** — AST-aware code editing: rename, remove, move, and pattern-rewrite using structural targets *(experimental)*
- **Kit Management** — Quartermaster pattern: curated tool subsets per task type with model-aware configuration

## Reference

- [Getting Started](getting-started.md)
- [GitHub Repository](https://github.com/teaguesterling/fledgling)
- [Interactive Installer](https://teaguesterling.github.io/fledgling/)

## Extensions

Fledgling composes these DuckDB community extensions:

| Extension | Purpose |
|-----------|---------|
| [`read_lines`](https://duckdb.org/community_extensions/extensions/read_lines) | Line-level file access with ranges and context |
| [`sitting_duck`](https://github.com/teaguesterling/sitting_duck) | AST parsing and semantic code analysis (30 languages) |
| [`duckdb_markdown`](https://github.com/teaguesterling/duckdb_markdown) | Markdown section/block parsing and extraction |
| [`duck_tails`](https://github.com/teaguesterling/duck_tails) | Git repository state as queryable tables |
| [`duckdb_mcp`](https://github.com/teaguesterling/duckdb_mcp) | MCP server infrastructure and tool publishing |

## Stats

- 539 tests across SQL macros, MCP tools, CLI, Python API, and e2e integration
- 20 MCP tools + 30+ query macros
- Requires DuckDB >= 1.5.0
