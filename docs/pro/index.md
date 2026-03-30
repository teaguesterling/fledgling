# Fledgling Pro

**The FastMCP coordination layer on top of fledgling's SQL macros.**

Fledgling Pro wraps the same DuckDB macros as the pure-SQL MCP server but adds intelligence: smart defaults, token awareness, compound workflows, session caching, prompt templates, and a kibitzer that suggests better tool usage.

```bash
pip install fledgling[pro]
fledgling-pro                    # start MCP server
python -m fledgling.pro          # same thing
```

## Why Pro?

The base fledgling server (pure DuckDB) is a faithful SQL execution engine. You call a tool, you get results. Pro adds the layer between "tool call" and "results" where intelligence lives:

| Base fledgling | Fledgling Pro |
|----------------|---------------|
| Agent calls `find_definitions('**/*.py')` in a Rust project → empty results | Auto-defaults to `'**/*.rs'` based on project analysis |
| Agent reads a 3000-line file → 3000 lines of output | Auto-truncates to 200 lines with "use lines='N-M' to narrow" |
| Agent calls project_overview, then code_structure, then doc_outline → 3 round trips | `explore()` does all three in one call |
| Agent calls the same query 5 times in a session → 5 DuckDB queries | Session cache returns cached result with a note |
| Agent uses bash grep when FindDefinitions would be better → no feedback | Kibitzer suggests "Try FindDefinitions for structural search" |

## Configuration

### MCP Server (.mcp.json)

```json
{
  "mcpServers": {
    "fledgling": {
      "command": "fledgling-pro",
      "cwd": "."
    }
  }
}
```

### Project Config (.fledgling.toml)

Optional — Pro infers everything it can. Override when the inference is wrong:

```toml
[defaults]
code_pattern = "src/**/*.py"      # override auto-detected language
doc_pattern = "documentation/**/*.md"  # override auto-detected doc dir
main_branch = "develop"            # override auto-detected default branch
```

### Programmatic

```python
from fledgling.pro.server import create_server

mcp = create_server(
    root="/path/to/project",
    modules=["source", "code", "repo"],
    profile="analyst",
)
mcp.run()
```

## Features

### Smart Defaults

On startup, Pro analyzes the project and caches defaults:

- **Code pattern** — dominant language from `project_overview()` → `'**/*.py'`, `'**/*.rs'`, etc.
- **Doc pattern** — scans for `docs/`, `documentation/`, `doc/` → `'docs/**/*.md'`
- **Main branch** — reads git HEAD → `'main'` or `'master'`

Tools use these defaults when called without explicit patterns. Explicit arguments always override.

```python
# Agent calls with no pattern → Pro fills in '**/*.py' (detected)
find_definitions()

# Agent provides pattern → Pro uses it as-is
find_definitions(file_pattern="lib/**/*.rb")
```

### Token-Aware Output

Every tool has configurable truncation:

| Tool type | Default limit | Parameter |
|-----------|--------------|-----------|
| Content tools (read_source, file_diff) | 200 lines | `max_lines` |
| Discovery tools (find_definitions, list_files) | 50 rows | `max_results` |
| Git tools (file_changes, recent_changes) | 20-25 rows | `max_results` |

Truncated output shows head + tail with an actionable hint:

```
   1  import os
   2  import sys
   3  ...
   5  def main():
--- omitted 1847 of 2000 lines ---
Use lines='N-M' to see a range, or match='keyword' to filter.
1996      return result
1997
1998  if __name__ == "__main__":
1999      main()
2000
```

**Bypass:** providing a narrowing parameter (e.g., `lines`, `match`, `name_pattern`) disables truncation — the agent is already being specific.

### Compound Workflows

Single tools that orchestrate multiple macros:

#### `explore(path?)`
First-contact codebase briefing. Returns:
- Languages and file counts
- Top definitions by complexity
- Documentation outline
- Recent git activity

#### `investigate(name, file_pattern?)`
Deep dive on a function or symbol. Returns:
- Definition location and source code
- Who calls it (call sites)
- What it calls

#### `review(from_rev?, to_rev?, file_pattern?)`
Code review prep. Returns:
- Changed files with sizes
- Changed functions ranked by complexity
- Diffs for top changed files

#### `search(query, file_pattern?)`
Multi-source search. Returns:
- Matching definitions
- Matching call sites
- Matching doc sections

### MCP Resources

Always-available context — no tool call needed:

| Resource URI | Content |
|-------------|---------|
| `fledgling://project` | Languages, file counts, top-level directory listing |
| `fledgling://diagnostics` | Version, profile, modules, extensions |
| `fledgling://docs` | Documentation outline (all markdown files) |
| `fledgling://git` | Branches, recent commits, working tree status |
| `fledgling://session` | What the agent has explored this session |

### Prompt Templates

Context-aware workflow instructions the agent can request:

#### `explore(path?)`
Returns exploration instructions with project overview and suggested starting points pre-filled.

#### `investigate(symptom)`
Returns debugging workflow with relevant definitions pre-found and next-step suggestions.

#### `review(from_rev?, to_rev?)`
Returns review checklist with change summary and complexity deltas pre-loaded.

### Session State

#### Caching
Repeated identical queries return cached results:
```
(cached — same as 2 minutes ago)
   42  def parse_config(path):
```

Cache TTL varies by tool: `project_overview` caches for the session, `working_tree_status` caches for 10 seconds.

#### Access Log
Tracks every tool call. Exposed via the `fledgling://session` resource.

#### Agent Kibitzer
Observes tool usage and suggests improvements:

| Pattern observed | Suggestion |
|-----------------|-----------|
| 3+ ReadLines on same file with different `match` | "Try FindInAST for structural search" |
| ReadLines without `lines` on file > 200 lines | "This file has N lines. Use lines='N-M'" |
| find_definitions returning 50+ results | "Use name_pattern to narrow" |
| Repeated identical calls | Shows cached result instead |

#### User Kibitzer
Analyzes workflow patterns across sessions via the `suggest_improvements` tool:
- Detects bash-heavy usage → suggests structured tools
- Detects missing CLAUDE.md guidance → suggests additions
- Detects unused tool categories → suggests trying them

## Architecture

```
fledgling-pro (FastMCP 3.x)
├── server.py          — create_server(), tool registration, resources
├── defaults.py        — ProjectDefaults, infer_defaults(), apply_defaults()
├── workflows.py       — explore, investigate, review, search
├── prompts.py         — MCP prompt templates
├── session.py         — SessionCache, AccessLog
├── formatting.py      — markdown tables, text output, truncation
└── __main__.py        — python -m fledgling.pro entry point

Uses:
├── fledgling.connect()    — DuckDB connection with macros loaded
├── fledgling.tools.Tools  — macro discovery and Python wrappers
└── fastmcp.FastMCP        — MCP server framework
```

Pro doesn't duplicate any SQL — it calls the same macros through `fledgling.connect()`. The value-add is entirely in the coordination layer.

## Comparison

| | Base (duckdb_mcp) | Pro (FastMCP) |
|-|-------------------|---------------|
| **Runtime** | DuckDB CLI only | Python + DuckDB |
| **Install** | `curl \| duckdb` | `pip install fledgling[pro]` |
| **Tools** | 14 | 30 (14 base + workflows + kibitzer) |
| **Resources** | 0 | 5 |
| **Prompts** | 0 | 3 |
| **Smart defaults** | No | Yes |
| **Truncation** | No | Yes |
| **Caching** | No | Yes |
| **Kibitzer** | No | Yes |
| **Sandbox** | `allowed_directories` | Python process boundary |
| **Extensions** | All DuckDB community | All DuckDB community |
