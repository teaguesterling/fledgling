# Fledgling

MCP tools that help AI agents get their bearings in a codebase — structured retrieval over code, git, docs, and conversations, powered by DuckDB.

## The Problem

AI coding agents retrieve data through shell commands. To find where `parse_config` is defined, an agent runs `grep -rn 'def parse_config' src/`, gets back raw text with line numbers and file paths mashed together, and then reads the file to get context around the match. To understand a function's signature, it reads the whole file and scans for it. To check git history, it runs `git log`, parses the output, then runs `git show` on each commit.

Every one of these steps produces unstructured text the agent has to parse before it can reason about the answer. Tokens spent on text parsing are tokens not spent on solving your problem.

## What Fledgling Does

Fledgling replaces shell-command-and-parse with purpose-built MCP tools that return structured results. Each tool is backed by a DuckDB community extension that understands the data format natively:

| Capability | Replaces | Extension |
|-----------|----------|-----------|
| **Source Retrieval** — read lines, ranges, batches across files | `cat`, `head`, `tail`, `sed -n` | [`read_lines`](https://duckdb.org/community_extensions/extensions/read_lines) |
| **Code Intelligence** — find definitions, calls, imports across 27 languages | `grep -rn "def ..."`, `find -name` | [`sitting_duck`](https://github.com/teaguesterling/sitting_duck) |
| **Documentation** — read specific markdown sections, extract code examples | reading entire files to find one section | [`duckdb_markdown`](https://github.com/teaguesterling/duckdb_markdown) |
| **Repository** — query commits, branches, tags, file history | `git log`, `git diff`, `git show` | [`duck_tails`](https://github.com/teaguesterling/duck_tails) |
| **Conversations** — analyze Claude Code session history, tool usage, token costs | *(nothing — this capability didn't exist)* | DuckDB JSON |

## Examples

**Code Intelligence** — instead of `grep -rn 'def parse' src/`:
```sql
SELECT * FROM find_definitions('src/**/*.py', 'parse%');
```
Returns structured rows with file path, name, kind (function/class/method), line range, and signature — no text parsing needed.

**Source Retrieval** — instead of `sed -n '37,47p' src/parser.py`:
```sql
SELECT * FROM read_context('src/parser.py', 42, 5);
```
Returns numbered lines centered on line 42 with 5 lines of context in each direction.

**Documentation** — instead of reading an entire file to find one section:
```sql
SELECT * FROM read_doc_section('README.md', 'installation');
```
Returns just the matched section's content, with title and line range.

**Repository** — instead of `git log --oneline -10`:
```sql
SELECT * FROM recent_changes(10);
```
Returns structured rows with hash, author, date, and message.

**Conversations** — no shell equivalent:
```sql
SELECT * FROM bash_commands() WHERE replaceable_by IS NOT NULL;
```
Analyzes an agent's own bash usage to find commands Fledgling could replace.

## How It Works

Fledgling is a DuckDB init script. It loads extensions, defines SQL macros, publishes them as MCP tools, and starts a server:

```
duckdb -init init-fledgling.sql
```

Configure it in Claude Code's `settings.json`:

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

Everything is read-only. Fledgling retrieves and analyzes — it never modifies files or makes git writes.

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
