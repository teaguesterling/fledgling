# Fledgling

MCP tools that help AI agents get their bearings in a codebase — unified SQL views over code, git, docs, and conversations, powered by DuckDB.

**Three ways to run:**

```bash
# Zero-dependency MCP server (pure DuckDB, no Python)
curl -sL https://raw.githubusercontent.com/teaguesterling/fledgling/main/sql/install-fledgling.sql | duckdb

# Python API
pip install fledgling-mcp
python -c "import fledgling; fledgling.connect().find_definitions('**/*.py').show()"

# FastMCP server with smart defaults, caching, and compound workflows
pip install fledgling-mcp[pro]
fledgling-pro
```

## Before and After

Your agent wastes tokens parsing text. Fledgling gives it purpose-built tools that return structured data.

**Find a function definition**

Before — grep returns raw text the agent has to parse:
```
grep -rn 'def parse_config' src/
src/config.py:42:def parse_config(path: str, strict: bool = False) -> Config:
```

After — the agent calls `FindDefinitions`:
```
FindDefinitions(file_pattern="src/**/*.py", name_pattern="parse_config%")

| file_path     | name         | kind                | start_line | end_line | signature                                   |
|---------------|--------------|---------------------|------------|----------|---------------------------------------------|
| src/config.py | parse_config | DEFINITION_FUNCTION | 42         | 68       | def parse_config(path: str, strict: ...) -> |
```

**Compose queries across domains**

```sql
-- Functions in recently changed files, ranked by cyclomatic complexity
SELECT * FROM changed_function_summary('HEAD~3', 'HEAD', 'src/**/*.py')
```

Code analysis + git history in one call. No shell pipelines, no string parsing.

## What's Included

### MCP Tools (22)

| Tool | What it does |
|------|-------------|
| `ReadLines` | Read file lines with range, context, and match filtering |
| `FindDefinitions` | AST-based search for functions/classes across 30 languages |
| `FindInAST` | Semantic code search: calls, imports, loops, conditionals, strings, comments |
| `FindCode` | CSS selector search over the AST: `.func`, `#name`, `:has(...)`, `::callers` |
| `ViewCode` | View source matched by CSS selector with context lines |
| `CodeStructure` | Structural overview with cyclomatic complexity metrics |
| `ExploreProject` | First-contact briefing: languages, structure, docs, recent activity |
| `InvestigateSymbol` | Deep dive: definitions, callers, and call sites for a symbol |
| `ReviewChanges` | Change review: affected files and functions ranked by complexity |
| `SearchProject` | Multi-source search across definitions, calls, and docs |
| `PssRender` | Render CSS selector matches as markdown with file:range headings |
| `AstSelectRender` | Selector-grouped rendering with per-match sub-headings |
| `MDOverview` | Browse all docs with keyword/regex search |
| `MDSection` | Read a specific markdown section by ID |
| `GitDiffSummary` | File-level change summary between revisions |
| `GitDiffFile` | Line-level unified diff |
| `GitShow` | File content at a specific git revision |
| `Help` | Built-in skill guide with workflows and macro catalog |
| `ChatSessions` | Browse Claude Code conversation sessions |
| `ChatSearch` | Full-text search across conversation messages |
| `ChatToolUsage` | Tool usage patterns |
| `ChatDetail` | Deep view of a single session |

Plus 30+ composable SQL macros via the query tool: `explore_query`, `investigate_query`, `review_query`, `search_query`, `pss_render`, `ast_select_render`, `find_class_members`, `complexity_hotspots`, `function_callers`, `module_dependencies`, `structural_diff`, `doc_outline`, and more.

### Fledgling Pro (FastMCP)

The `fledgling[pro]` package adds a FastMCP server with:

- **Smart defaults** — auto-detects your project's language, doc directory, and git branch
- **Token-aware output** — auto-truncation with hints ("use lines='N-M' to narrow")
- **Compound workflows** — `explore`, `investigate`, `review`, `search` in one call
- **MCP resources** — project overview, docs, git state always available without tool calls
- **Prompt templates** — context-aware exploration, investigation, and review workflows
- **Session state** — caching, access log, and kibitzer (suggests better tool usage)

### Python API

```python
import fledgling

# Create a connection with all macros loaded
con = fledgling.connect()

# Macros as methods — return composable DuckDB Relations
con.find_definitions("**/*.py", name_pattern="parse%").show()
con.recent_changes(5).select("hash, message").df()
con.code_structure("src/**/*.py").filter("cyclomatic_complexity > 5").show()

# Attach to an existing DuckDB connection
import duckdb
raw = duckdb.connect("my.db")
con = fledgling.attach(raw, root="/my/project")

# Compose your own init sequence
raw = duckdb.connect()
fledgling.load_extensions(raw)
fledgling.set_session_root(raw, root="/my/project")
fledgling.load_macros(raw, modules=["sandbox", "source", "code"])
# ... do custom setup ...
fledgling.lockdown(raw, allowed_dirs=["/my/project"])

# Module-level for quick scripting
from fledgling.tools import find_definitions, recent_changes
find_definitions("**/*.py").show()
```

### CLI for Humans

```bash
fledgling find-definitions 'src/**/*.py' '%parse%'
fledgling recent-changes 10 -c hash,message
fledgling CodeStructure '**/*.rs' -f csv
fledgling query "SELECT * FROM complexity_hotspots('**/*.py', 10)"
fledgling help
fledgling update   # preserves your module/profile config
```

Tab completion: `eval "$(fledgling --completions bash)"`

## Install

### Per-project (recommended)

```bash
curl -sL https://raw.githubusercontent.com/teaguesterling/fledgling/main/sql/install-fledgling.sql | duckdb
```

Creates `.fledgling-init.sql`, `.fledgling-help.md`, and `.mcp.json` in your project root. Customize modules and profile on the [install page](https://teaguesterling.github.io/fledgling/).

### Via pip

```bash
pip install fledgling-mcp          # CLI + Python API
pip install fledgling-mcp[pro]     # + FastMCP server
```

### Requirements

- [DuckDB](https://duckdb.org/) >= 1.5.0 (CLI for MCP server, Python package for API)
- Community extensions installed automatically

## Architecture

```
┌─────────────────────────────────────────┐
│  squawkit (FastMCP)                     │  pip install squawkit
│  Smart defaults, caching, workflows,    │  (migrating from fledgling-mcp[pro])
│  prompts, kibitzer, resources           │
│                                         │
│  ┌───────────────────────────────────┐  │
│  │  fledgling (Python API)           │  │  pip install fledgling-mcp
│  │  fledgling.connect() / attach()   │  │
│  │  configure() / lockdown()         │  │
│  │                                   │  │
│  │  ┌─────────────────────────────┐  │  │
│  │  │  SQL macros (DuckDB)        │  │  │  curl | duckdb
│  │  │  22 MCP tools               │  │  │
│  │  │  read_lines, sitting_duck,  │  │  │
│  │  │  duck_tails, duckdb_markdown│  │  │
│  │  └─────────────────────────────┘  │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

The SQL macros are the foundation — pure DuckDB, zero Python dependency, sandboxed read-only. The Python API wraps them as composable Relations. The FastMCP layer adds coordination intelligence.

## Development

```bash
git clone https://github.com/teaguesterling/fledgling.git
cd fledgling
pip install -e ".[pro]"
pip install duckdb pytest
pytest
```

539 tests across SQL macros, MCP integration, CLI, Python API, and FastMCP server.

## Coming Soon

- **fledgling-edit** — AST-aware code editing with pattern matching and template substitution ([design spec](docs/superpowers/specs/2026-03-29-fledgling-edit-design.md))
- **Kit management** — Quartermaster pattern: curated tool subsets per task type with model-aware configuration

## Why "Fledgling"?

From the 1996 film *Fly Away Home* — a girl raises orphaned geese and teaches them their migration route by leading them with an ultralight aircraft. The geese imprint on her, learn the path, and eventually fly it on their own.

Fledgling gives AI agents structured tools so they can learn to navigate your codebase. A fledgling is a young bird learning to fly. This tool is what gets it airborne.

## License

Apache-2.0
