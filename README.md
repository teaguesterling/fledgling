# Fledgling

MCP tools that help AI agents get their bearings in a codebase — unified SQL views over code, git, docs, and conversations, powered by DuckDB.

**Two ways to run:**

```bash
# Zero-dependency MCP server (pure DuckDB, no Python)
curl -sL https://raw.githubusercontent.com/teaguesterling/fledgling/main/sql/install-fledgling.sql | duckdb

# Python API
pip install fledgling-mcp
python -c "import fledgling; fledgling.connect().find_definitions('**/*.py').show()"
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

**View code by CSS selector**

```
SelectCode(source="src/**/*.py", selector=".func#parse_config")
```

Returns markdown with `# file:range` headings and fenced code blocks — full source bodies, not just signatures.

**Compose queries across domains**

```sql
-- Functions in recently changed files, ranked by cyclomatic complexity
SELECT * FROM changed_function_summary('HEAD~3', 'HEAD', 'src/**/*.py')
```

Code analysis + git history in one call. No shell pipelines, no string parsing.

## What's Included

### MCP Tools (20)

| Tool | What it does |
|------|-------------|
| `ReadLines` | Read file lines with range, context, and match filtering |
| `FindDefinitions` | AST-based search for functions/classes across 30 languages |
| `FindCode` | CSS selector search: `.func`, `#name`, `:has(...)`, `::callers` |
| `ViewCode` | View source matched by CSS selector with context lines |
| `SelectCode` | Render selector matches as markdown: headings + full source blocks |
| `CodeStructure` | Structural overview with cyclomatic complexity metrics |
| `ExploreProject` | First-contact briefing: languages, structure, docs, recent activity |
| `InvestigateSymbol` | Deep dive: definitions, callers, and call sites for a symbol |
| `ReviewChanges` | Change review: affected files and functions ranked by complexity |
| `SearchProject` | Multi-source search across definitions, calls, and docs |
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

Plus 30+ composable SQL macros via the query tool: `explore_query`, `investigate_query`, `review_query`, `search_query`, `pss_render`, `find_class_members`, `complexity_hotspots`, `function_callers`, `module_dependencies`, `structural_diff`, `doc_outline`, and more.

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
pip install fledgling-mcp
```

### Requirements

- [DuckDB](https://duckdb.org/) >= 1.5.0 (CLI for MCP server, Python package for API)
- Community extensions installed automatically

## Ecosystem

Fledgling is the SQL macro foundation. Two companion packages build on it:

| Package | What it does | Install |
|---------|-------------|---------|
| [**pluckit**](https://github.com/teaguesterling/pluckit) | Fluent Python API — CSS selectors over ASTs, jQuery-style chaining, code mutations | `pip install ast-pluckit` |
| [**squawkit**](https://github.com/teaguesterling/squawkit) | MCP server with smart defaults, caching, workflows, prompts, and session state | `pip install squawkit` (coming soon) |

### Architecture

```
┌─────────────────────────────────────────┐
│  squawkit (FastMCP)                     │  pip install squawkit
│  Smart defaults, caching, workflows,    │
│  prompts, kibitzer, resources           │
│                                         │
│  ┌───────────────────────────────────┐  │
│  │  pluckit (fluent Python API)      │  │  pip install ast-pluckit
│  │  CSS selectors, jQuery-style      │  │
│  │  chaining, code mutations         │  │
│  │                                   │  │
│  │  ┌─────────────────────────────┐  │  │
│  │  │  fledgling (SQL + Python)   │  │  │  pip install fledgling-mcp
│  │  │  20 MCP tools, 30+ macros   │  │  │  or: curl | duckdb
│  │  │  fledgling.connect()        │  │  │
│  │  │  read_lines, sitting_duck,  │  │  │
│  │  │  duck_tails, markdown       │  │  │
│  │  └─────────────────────────────┘  │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

Dependencies flow strictly downward. Fledgling has no dependency on pluckit or squawkit. Pluckit has an optional soft-dep on fledgling. Squawkit depends on pluckit.

## Development

```bash
git clone https://github.com/teaguesterling/fledgling.git
cd fledgling
pip install -e .
pip install duckdb pytest
pytest
```

539 tests across SQL macros, MCP integration, CLI, Python API, and e2e integration.

## Coming Soon

- **[fledgling-edit](docs/superpowers/specs/2026-03-29-fledgling-edit-design.md)** — AST-aware code editing with pattern matching and template substitution
- **Kit management** — Quartermaster pattern: curated tool subsets per task type with model-aware configuration

## Why "Fledgling"?

From the 1996 film *Fly Away Home* — a girl raises orphaned geese and teaches them their migration route by leading them with an ultralight aircraft. The geese imprint on her, learn the path, and eventually fly it on their own.

Fledgling gives AI agents structured tools so they can learn to navigate your codebase. A fledgling is a young bird learning to fly. This tool is what gets it airborne.

## License

Apache-2.0
