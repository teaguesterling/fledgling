# source-sextant

MCP tools that help AI agents get their bearings in a codebase — unified SQL views over code, git, docs, and conversations, powered by DuckDB.

## What is this?

Source Sextant is a DuckDB-powered [MCP](https://modelcontextprotocol.io/) server that gives AI agents navigational awareness of development environments. It composes several DuckDB community extensions into a single queryable SQL surface:

| Tier | Extension | What it provides |
|------|-----------|------------------|
| Source Retrieval | [`read_lines`](https://duckdb.org/community_extensions/extensions/read_lines) | Line-level file access with ranges and context |
| Code Intelligence | [`sitting_duck`](https://github.com/teaguesterling/sitting_duck) | AST-based code analysis (27 languages) |
| Documentation | [`duckdb_markdown`](https://github.com/teaguesterling/duckdb_markdown) | Markdown section/block parsing and extraction |
| Repository | [`duck_tails`](https://github.com/teaguesterling/duck_tails) | Git repository state as queryable tables |
| Conversations | DuckDB JSON | Claude Code conversation log analysis |

Instead of agents running `cat`, `grep`, `git log`, and other bash commands that produce unstructured text, Source Sextant provides structured, composable SQL macros exposed as MCP tools.

## Status

Alpha. SQL macros and tests are working across all tiers. MCP server integration is next.

- 63 passing tests across 4 macro tiers
- Conversation schema drafted (testing in progress)
- See [docs/vision/PRODUCT_SPEC.md](docs/vision/PRODUCT_SPEC.md) for the full specification

## Quick Example

```sql
-- Find all Python function definitions matching a pattern
SELECT * FROM find_definitions('src/**/*.py', '%parse%');

-- Read specific lines with context
SELECT * FROM read_context('src/parser.py', 42, 5);

-- Get the "Installation" section from a README without reading the whole file
SELECT * FROM read_doc_section('README.md', 'installation');

-- What changed in src/ in the last 5 commits?
SELECT * FROM recent_changes(5, '.');

-- Cross-tier composition: functions that changed recently
SELECT d.name, d.file_path, c.message
FROM find_definitions('src/**/*.py') d
JOIN recent_changes(3) c ON d.file_path = ANY(c.files_changed);
```

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
