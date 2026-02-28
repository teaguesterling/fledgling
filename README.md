# Source Sextant

MCP tools that help AI agents get their bearings in a codebase — unified SQL views over code, git, docs, and conversations, powered by DuckDB.

## The Problem

AI coding assistants navigate codebases through bash commands: `cat`, `grep`, `git log`, `sed -n '10,20p'`. These commands produce unstructured text the agent has to parse, require bash whitelisting in your settings, and can't compose with each other.

When an agent wants "all function definitions matching `parse` in files that changed this week," it has to run `git log`, parse the output, run `grep` on each file, parse *that* output, and stitch it together. Each step burns tokens on text parsing instead of actual reasoning.

## What Source Sextant Does

Source Sextant gives agents purpose-built MCP tools backed by structured SQL, so they spend tokens on reasoning instead of parsing text. It composes five DuckDB community extensions into a single queryable surface:

| Capability | Replaces | Extension |
|-----------|----------|-----------|
| **Source Retrieval** — read lines, ranges, batches across files | `cat`, `head`, `tail`, `sed -n` | [`read_lines`](https://duckdb.org/community_extensions/extensions/read_lines) |
| **Code Intelligence** — find definitions, calls, imports across 27 languages | `grep -rn "def ..."`, `find -name` | [`sitting_duck`](https://github.com/teaguesterling/sitting_duck) |
| **Documentation** — read specific markdown sections, extract code examples | reading entire files to find one section | [`duckdb_markdown`](https://github.com/teaguesterling/duckdb_markdown) |
| **Repository** — query commits, branches, tags, file history | `git log`, `git diff`, `git show` | [`duck_tails`](https://github.com/teaguesterling/duck_tails) |
| **Conversations** — analyze Claude Code session history, tool usage, token costs | *(nothing — this capability didn't exist)* | DuckDB JSON |

Because everything shares a DuckDB connection, tiers also compose through SQL joins:

```sql
-- Definitions in large files — find code hotspots worth splitting up
SELECT d.name, d.kind, d.file_path, f.line_count
FROM find_definitions('src/**/*.py') d
JOIN file_line_count('src/**/*.py') f ON d.file_path = f.file_path
WHERE f.line_count > 200;
```

## How It Works

Source Sextant is a DuckDB init script — not a traditional application. It loads extensions, defines SQL macros, publishes them as MCP tools, and starts a server:

```
duckdb -init init-source-sextant.sql
```

Configure it in Claude Code's `settings.json`:

```json
{
  "mcpServers": {
    "source_sextant": {
      "command": "duckdb",
      "args": ["-init", "/path/to/init-source-sextant.sql"]
    }
  }
}
```

The architecture has two layers:

1. **SQL macros** (`sql/<tier>.sql`) — reusable, independently testable DuckDB macros containing all the logic
2. **Tool publications** (`sql/tools/<tier>.sql`) — thin wrappers that expose macros as MCP tools via `mcp_publish_tool()`

Everything is read-only. Source Sextant retrieves and analyzes — it never modifies files or makes git writes.

## Quick Examples

```sql
-- Find all Python function definitions matching a pattern
SELECT * FROM find_definitions('src/**/*.py', '%parse%');

-- Read specific lines with context (great for investigating errors)
SELECT * FROM read_context('src/parser.py', 42, 5);

-- Get just the "Installation" section from a README
SELECT * FROM read_doc_section('README.md', 'installation');

-- What changed in src/ in the last 5 commits?
SELECT * FROM recent_changes(5, '.');

-- Which bash commands does the agent use most, and which ones could Source Sextant replace?
SELECT * FROM bash_commands() WHERE replaceable_by IS NOT NULL;
```

## Status

Alpha. SQL macros, MCP tool publications, and path sandboxing are working.

- 151 tests across 5 macro tiers + MCP integration + sandbox
- 8 of 11 MCP tools published (code, docs, git tools complete; file tools pending)
- Conversation analysis macros fully tested (31 tests)
- See [docs/vision/PRODUCT_SPEC.md](docs/vision/PRODUCT_SPEC.md) for the full specification

## Requirements

- [DuckDB](https://duckdb.org/) >= 1.4.4
- Community extensions: `read_lines`, `sitting_duck`, `duckdb_markdown`, `duck_tails`, `duckdb_mcp`

## Development

```bash
# Install test dependencies
pip install duckdb pytest

# Run tests
pytest
```

## License

Apache-2.0
