# Fledgling Documentation

**MCP tools that help AI agents get their bearings in a codebase — unified SQL views over code, git, docs, and conversations, powered by DuckDB.**

> **Install:** `curl -sL https://teaguesterling.github.io/fledgling/install.sql | duckdb`
>
> Or use the [interactive installer](https://teaguesterling.github.io/fledgling/) to customize modules and profile.

## Three Layers

| Layer | Install | What you get |
|-------|---------|-------------|
| **SQL macros** | `curl \| duckdb` | 14 MCP tools, 20+ query macros, pure DuckDB, zero Python |
| **Python API** | `pip install fledgling` | `fledgling.connect()`, macros as methods, CLI |
| **FastMCP Pro** | `pip install fledgling[pro]` | Smart defaults, caching, workflows, kibitzer |

## MCP Tools (14)

| Tool | Purpose |
|------|---------|
| [ReadLines](macros/source.md) | File content with line ranges, context, and match filtering |
| [FindDefinitions](macros/code.md) | AST search for functions/classes/modules (30 languages) |
| [FindInAST](macros/code.md) | Semantic search: calls, imports, loops, conditionals, strings, comments |
| [CodeStructure](macros/code.md) | Structural overview with cyclomatic complexity metrics |
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
`find_definitions` `find_calls` `find_imports` `find_in_ast` `code_structure` `complexity_hotspots` `function_callers` `module_dependencies`

### [Docs](macros/docs.md)
`doc_outline` `read_doc_section` `find_code_examples` `doc_stats`

### [Git](macros/repo.md)
`recent_changes` `branch_list` `tag_list` `repo_files` `file_at_version` `file_changes` `file_diff` `working_tree_status` `structural_diff` `changed_function_summary`

### [Conversations](macros/conversations.md)
`sessions` `messages` `content_blocks` `tool_calls` `tool_results` `token_usage` `tool_frequency` `bash_commands` `session_summary` `model_usage` `search_messages` `search_tool_inputs`

## Fledgling Pro

The `fledgling[pro]` package adds a [FastMCP](https://gofastmcp.com) server with coordination intelligence:

| Feature | Description |
|---------|-------------|
| **Smart Defaults** | Auto-detects language, doc directory, git branch |
| **Token Awareness** | Auto-truncation with head/tail, narrowing hints, bypass on explicit ranges |
| **Compound Workflows** | `explore`, `investigate`, `review`, `search` — multi-macro in one call |
| **MCP Resources** | Project overview, docs outline, git state — always available without tool calls |
| **Prompt Templates** | Context-aware exploration, investigation, and review workflows |
| **Session State** | Caching, access log, agent kibitzer (suggests better tool usage) |

## Python API

```python
import fledgling

con = fledgling.connect()                                    # auto-discovers .fledgling-init.sql
con.find_definitions("**/*.py", name_pattern="parse%").show()  # macros as methods
con.recent_changes(5).select("hash, message").df()             # returns pandas DataFrame
con.code_structure("src/**/*.py").filter("cyclomatic_complexity > 5").show()

# Module-level for quick scripting
from fledgling.tools import find_definitions
find_definitions("**/*.py").show()
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
- [Product Specification](vision/PRODUCT_SPEC.md)
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

- 523 tests across SQL macros, MCP tools, CLI, Python API, and FastMCP server
- 14 MCP tools (duckdb_mcp) + 30 tools (FastMCP pro) + 4 resources + 3 prompts
- Requires DuckDB >= 1.5.0
