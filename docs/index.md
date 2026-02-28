# Fledgling

**MCP tools that help AI agents get their bearings in a codebase — unified SQL views over code, git, docs, and conversations, powered by DuckDB.**

## What is Fledgling?

Fledgling is a DuckDB-powered [MCP](https://modelcontextprotocol.io/) server that gives AI agents navigational awareness of development environments. Instead of agents running bash commands (`cat`, `grep`, `git log`) that produce unstructured text, Fledgling provides structured, composable SQL macros exposed as MCP tools.

It composes several DuckDB community extensions into a single queryable surface:

| Tier | Extension | What it provides |
|------|-----------|------------------|
| **Source Retrieval** | `read_lines` | Line-level file access with ranges and context |
| **Code Intelligence** | `sitting_duck` | AST-based code analysis (27 languages) |
| **Documentation** | `duckdb_markdown` | Markdown section/block parsing and extraction |
| **Repository** | `duck_tails` | Git repository state as queryable tables |
| **Conversations** | DuckDB JSON | Claude Code conversation log analysis |

## Why?

AI coding assistants spend significant tokens on low-level bash commands for tasks that are fundamentally *data retrieval*. Fledgling replaces those with structured, composable queries:

```sql
-- Instead of: cat src/parser.py | sed -n '40,50p'
SELECT * FROM read_context('src/parser.py', 45, 5);

-- Instead of: grep -rn "def parse" src/
SELECT * FROM find_definitions('src/**/*.py', '%parse%');

-- Instead of: git log --oneline -n 10
SELECT * FROM recent_changes(10);

-- Cross-tier: definitions in large files
SELECT d.name, d.file_path, f.line_count
FROM find_definitions('src/**/*.py') d
JOIN file_line_count('src/**/*.py') f ON d.file_path = f.file_path
WHERE f.line_count > 100;
```

## Status

**Alpha** — SQL macros, MCP tool publications, and path sandboxing are working.

- 151 tests across 5 macro tiers + MCP integration + sandbox
- 8 of 11 MCP tools published (code, docs, git complete; file tools pending)
- Conversation analysis macros fully tested
- See the [Product Spec](vision/PRODUCT_SPEC.md) for the full design

## Quick Links

- [Getting Started](getting-started.md)
- [Macro Reference](macros/source.md)
- [Product Specification](vision/PRODUCT_SPEC.md)
- [GitHub Repository](https://github.com/teaguesterling/source-sextant)
