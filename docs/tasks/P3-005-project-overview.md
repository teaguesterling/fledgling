# P3-005: ProjectOverview Tool

**Status:** Not started
**Depends on:** P2-001 (ListFiles), P2-002 (CodeStructure)
**Estimated scope:** New macro + tool publication

## Motivation

The original P2-006 spec envisioned an `explore` tool that gives agents a
quick project overview — language breakdown, file counts per directory,
largest files, total lines. Currently, an agent can call `ListFiles` and
`CodeStructure` separately, but there's no single tool that answers "what is
this project?"

This is the most common first query when an agent connects to an unfamiliar
codebase. Having a structured overview avoids the agent issuing 3-4 exploratory
calls to build a mental model.

## Design

A `project_overview` macro that aggregates `list_files()` output with
metadata from the filesystem:

```sql
CREATE OR REPLACE MACRO project_overview(root_pattern := '**/*') AS TABLE
    WITH file_list AS (
        SELECT
            file_path,
            -- Extract directory and extension
            regexp_extract(file_path, '(.*)/[^/]+$', 1) AS directory,
            regexp_extract(file_path, '\.([^.]+)$', 1) AS extension,
            -- File metadata via read_lines or stat
            ...
        FROM list_files(root_pattern)
    )
    SELECT
        count(*) AS total_files,
        -- Language breakdown (by extension)
        -- Directory summary (top N by file count)
        -- Largest files
        ...
```

### Open questions

- Should this use `glob()` directly or go through `list_files()`?
  `list_files()` respects git-awareness; `glob()` hits the filesystem.
  For a project overview, filesystem is probably right (we want to see
  everything, including untracked files).
- How to detect language from extension? A simple mapping macro or CTE
  (`py` → Python, `js` → JavaScript, etc.) is sufficient for MVP.
- Should it include line counts? This requires reading every file
  (`file_line_count()`), which could be slow on large repos. Consider
  making it optional or capping at N files.

## Tools

| Tool | Required Params | Optional Params | Maps To |
|------|----------------|-----------------|---------|
| ProjectOverview | — | path | `project_overview(path)` |

## Files

| File | Action | Description |
|------|--------|-------------|
| `sql/source.sql` | Update | Add `project_overview()` macro |
| `sql/tools/files.sql` | Update | Add `mcp_publish_tool()` call |
| `tests/test_source.py` | Update | Macro-level tests |
| `tests/test_mcp_server.py` | Update | MCP tool test |

## Acceptance Criteria

- `TestProjectOverview` tests pass in `test_mcp_server.py`:
  - Returns file count, language breakdown for the fledgling repo itself
  - Language breakdown includes at least SQL and Python
  - Optional path parameter scopes to a subdirectory
- `TestProjectOverviewMacro` tests pass in `test_source.py`:
  - Aggregation is correct for known fixture data
  - Empty directory returns zero counts
- Existing tests unaffected
