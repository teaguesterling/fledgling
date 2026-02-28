# Fledgling

A sandboxed DuckDB runtime for AI coding agents. Structured tools for code, git, docs, and self-analysis — plus access to 140+ DuckDB extensions through SQL.

## Before and After

Your agent wastes tokens parsing text. Fledgling gives it purpose-built MCP tools that return structured data.

**Find a function definition**

Before — grep returns raw text the agent has to parse:
```
grep -rn 'def parse_config' src/
src/config.py:42:def parse_config(path: str, strict: bool = False) -> Config:
src/legacy/config.py:18:def parse_config(raw: dict) -> LegacyConfig:
```

After — the agent calls `FindDefinitions`:
```
FindDefinitions(file_pattern="src/**/*.py", name_pattern="parse_config%")
```
```
| file_path            | name         | kind     | start_line | end_line | signature                                                    |
|----------------------|--------------|----------|------------|----------|--------------------------------------------------------------|
| src/config.py        | parse_config | function | 42         | 68       | def parse_config(path: str, strict: bool = False) -> Config  |
| src/legacy/config.py | parse_config | function | 18         | 31       | def parse_config(raw: dict) -> LegacyConfig                  |
```

No text parsing. The agent gets the file, the line range, the kind, and the full signature in one call across 27 languages.

**Read code with context**

Before — sed and mental arithmetic:
```
sed -n '37,47p' src/parser.py
```

After — the agent calls `ReadLines`:
```
ReadLines(file_path="src/parser.py", lines="42", ctx="5")
```

Returns numbered lines centered on line 42 with 5 lines of context. No counting, no off-by-one errors.

**Check recent commits**

Before — git log, then git show, then parse both:
```
git log --oneline -10
```

After — the agent calls `GitChanges`:
```
GitChanges(count="10")
```

Returns structured rows with hash, author, date, and message — ready to reason about, not parse.

**Find a markdown section**

Before — read the entire file, scan for the heading:
```
cat README.md
```

After — the agent calls `MDSection`:
```
MDSection(file_path="README.md", section_id="installation")
```

Returns just the matched section. No wasted tokens on the rest of the document.

## What's Included

Fledgling publishes these MCP tools out of the box:

| MCP Tool | What it does | Replaces |
|----------|-------------|----------|
| `FindDefinitions` | Find function, class, and variable definitions across 27 languages | `grep -rn "def ..."` |
| `FindCalls` | Find where functions are called | `grep` for call sites |
| `FindImports` | Find import/include/require statements | `grep` for imports |
| `CodeStructure` | Top-level overview of definitions in a file or directory | reading whole files |
| `ListFiles` | List files by glob pattern or git revision | `find`, `ls`, `git ls-files` |
| `ReadLines` | Read file lines with optional range, context, and filtering | `cat`, `head`, `tail`, `sed -n` |
| `ReadAsTable` | Preview CSV/JSON files as structured tables | `cat data.csv \| head` |
| `MDOutline` | Get the heading structure of a markdown document | scanning the whole file |
| `MDSection` | Extract a specific section by ID (use MDOutline to find IDs) | reading the whole file |
| `GitChanges` | Recent commit history | `git log` |
| `GitBranches` | List branches with current branch marked | `git branch` |

Every tool returns structured markdown tables. No text parsing, no token waste.

### The quiet part

Fledgling also exposes a general-purpose SQL query tool backed by the full DuckDB engine. This means your agent can query anything DuckDB can read — Parquet, CSV, JSON, and any community extension loaded before sandbox lockdown.

There are [140+ community extensions](https://duckdb.org/community_extensions/list_of_extensions): Google Sheets, Elasticsearch, HDF5 scientific data, genomics formats, web archives, and more. All accessible through one MCP server, all via SQL.

The purpose-built tools get your agent productive. The SQL layer is there when it needs to go further.

## How It Works

Fledgling is a DuckDB init script. No Python runtime, no Node, no build step. It loads extensions, defines SQL macros, publishes them as MCP tools, locks down the sandbox, and starts an MCP server:

```
duckdb -init init-fledgling.sql
```

Everything runs read-only inside a filesystem sandbox restricted to your project directory. The agent gets structured access to your code — it can't write files, make network calls, or escape the sandbox.

## Configuration

Add Fledgling to Claude Code's `settings.json`:

```json
{
  "mcpServers": {
    "fledgling": {
      "command": "duckdb",
      "args": ["-init", "/path/to/init-fledgling.sql"]
    }
  }
}
```

Or set a custom project root:

```json
{
  "mcpServers": {
    "fledgling": {
      "command": "duckdb",
      "args": ["-init", "/path/to/init-fledgling.sql"],
      "env": {
        "FLEDGLING_ROOT": "/path/to/your/project"
      }
    }
  }
}
```

## Status

Alpha. All 11 MCP tools published and working.

- 151 tests across 5 macro tiers + MCP integration + sandbox
- Conversation analysis macros tested separately (31 tests, not loaded by default)
- See [docs/vision/PRODUCT_SPEC.md](docs/vision/PRODUCT_SPEC.md) for the full specification

## Requirements

- [DuckDB](https://duckdb.org/) >= 1.4.4
- Community extensions are installed automatically

## Development

```bash
pip install duckdb pytest
pytest
```

## Why "Fledgling"?

From the 1996 film *Fly Away Home* — a girl raises orphaned geese and teaches them their migration route by leading them with an ultralight aircraft. The geese imprint on her, learn the path, and eventually fly it on their own.

Fledgling gives AI agents structured tools so they can learn to navigate your codebase. A fledgling is a young bird learning to fly. This tool is what gets it airborne.

## License

Apache-2.0
