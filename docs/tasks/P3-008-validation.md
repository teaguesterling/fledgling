# P3-008: Validation Suite

**Status:** Complete
**Branch:** `chore/P3-008-validation`

## Motivation

With all tool tiers implemented (files, code, docs, git, conversations) plus
profiles, sandbox, and packaging, a systematic validation pass was needed to
verify every tool works correctly end-to-end through the MCP server and to
identify quality improvements.

## Approach

59 test prompts in `tests/data/validation-prompts/` organized by category
(01-files through 08-integration). Each prompt exercises a specific tool
capability and was run manually through the MCP tools.

## Results

- **58/59 pass**
- **1 known failure:** test 7.4 (query read-only enforcement, duckdb_mcp#34)
  — requires upstream fix in duckdb_mcp's query tool handler

## Issues Filed

### Fledgling

- **#35** — Improve code intelligence tools: reduce noise, merge overlapping
  tools, expose metrics
  - FindDefinitions: filter to top-level definitions, reduce sitting_duck#37 noise
  - FindImports + FindCalls → FindInAST with `kind` parameter
  - CodeStructure: expose sitting_duck metrics (descendant_count, complexity)
  - ReadAsTable: extension guidance + customization

### duckdb_mcp

- **#54** — Markdown output format should escape `|` in cell values
- **#55** — Add plain text output format for `mcp_publish_tool`

## Output Format Strategy

Established during validation review — three output formats by tool type:

| Format | Use case | Tools |
|---|---|---|
| `markdown` | Tabular data with short values | ListFiles, ProjectOverview, FindDefinitions, GitChanges, etc. |
| `json` | Metadata + large content blobs | GitShow, MDSection |
| `text` (pending #55) | Line-oriented content (agent reads, not parses) | ReadLines, GitDiffFile |

ReadLines and GitDiffFile use `json` as interim until `text` format is
available upstream.
