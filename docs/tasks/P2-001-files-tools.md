# P2-001: Files Tools (ListFiles, ReadLines, ReadAsTable)

**Status:** Implemented
**Depends on:** None (can be implemented first)
**Estimated scope:** New macros + tool publications

## Goal

Publish 3 MCP tools for file access: listing, reading lines, and previewing
data files. This is the most complex category because it requires new macros
in `source.sql` alongside the tool publications.

## Tools

| Tool | Required Params | Optional Params | Maps To |
|------|----------------|-----------------|---------|
| ListFiles | pattern | commit | `list_files()` (new) |
| ReadLines | file_path | lines, ctx, match, commit | `read_source()` (updated) |
| ReadAsTable | file_path | limit | `read_as_table()` (new) |

## Files

| File | Action | Description |
|------|--------|-------------|
| `sql/source.sql` | Update | Add `list_files`, `read_as_table`; update `read_source` with match/commit |
| `sql/tools/files.sql` | Create | 3 `mcp_publish_tool()` calls |

## Path Resolution

All tool SQL templates must use `resolve($file_path)` to convert relative
paths to absolute (required for DuckDB sandbox, see P2-005). The `resolve()`
macro prepends `sextant_root` for relative paths, passes absolute paths through.

```sql
-- In tool SQL templates:
resolve($file_path)          -- single file
resolve($file_pattern)       -- glob pattern
```

Git mode (`commit` param) uses repo-relative paths, which `duck_tails`
resolves against the repo root. These do NOT need `resolve()`.

## New/Updated Macros

### list_files(pattern)

Filesystem only: wraps `glob()` to list matching files. Git mode dispatch
is handled by the tool template (see below) because `git_tree()` requires
`duck_tails`, and `source.sql` must stay extension-independent so
`test_source.py` can test it with only `read_lines` loaded.

```sql
CREATE OR REPLACE MACRO list_files(pattern) AS TABLE
    SELECT file AS file_path
    FROM glob(pattern)
    ORDER BY file_path;
```

Note: glob uses shell syntax (`*.sql`), git mode uses SQL LIKE (`%.sql`).
The tool template handles git dispatch via UNION ALL with WHERE guards.

### read_source — add match param

Extend existing macro with `match` filter. Existing calls still work.
`commit` param is NOT in the macro (would require `duck_tails` dependency);
git dispatch is handled by the tool template instead.

```sql
CREATE OR REPLACE MACRO read_source(file_path, lines := NULL, ctx := 0,
                                     match := NULL) AS TABLE
    SELECT line_number, content
    FROM read_lines(file_path, lines, context := ctx)
    WHERE match IS NULL OR content ILIKE '%' || match || '%';
```

**Resolved risk:** `read_lines()` supports `git_uri()` paths — verified.
The tool template passes `git_uri('.', $file_path, $commit)` as the
`file_path` argument.

### read_as_table(file_path, lim)

Uses DuckDB's `query_table()` for auto-detection.

```sql
CREATE OR REPLACE MACRO read_as_table(file_path, lim := 100) AS TABLE
    SELECT * FROM query_table(file_path) LIMIT lim;
```

**Known issue:** `query_table()` collides with Python's `import json`
module (Python replacement scan finds the module before file scan). The
MCP tool uses `FROM $file_path` (string replacement scan) instead, which
bypasses Python namespace entirely but cannot support path resolution
(DuckDB's FROM requires a string literal, not an expression).

## Tool Publications (sql/tools/files.sql)

Each tool uses `NULLIF($param, 'null')` for optional params (duckdb_mcp#19
workaround). Integer params also need `TRY_CAST(... AS INT)`.

Key patterns:
- Path resolution: `resolve($file_path)` for filesystem, bare for git
- String optional: `NULLIF($param, 'null')`
- Integer optional with default: `COALESCE(TRY_CAST(NULLIF($param, 'null') AS INT), default)`
- Git dispatch: `CASE WHEN ... IS NULL THEN resolve(path) ELSE git_uri('.', path, rev) END`

Example for ReadLines:
```sql
SELECT mcp_publish_tool(
    'ReadLines',
    'Read lines from a file with optional filtering. Replaces cat/head/tail.',
    'SELECT * FROM read_source(
        CASE WHEN NULLIF($commit, ''null'') IS NULL
             THEN resolve($file_path)
             ELSE $file_path END,
        NULLIF($lines, ''null''),
        COALESCE(TRY_CAST(NULLIF($ctx, ''null'') AS INT), 0),
        NULLIF($match, ''null''),
        NULLIF($commit, ''null'')
    )',
    ...
);
```

## Acceptance Criteria

These tests in `test_mcp_server.py` must pass:
- `TestListFiles` (3 tests): glob, git files, empty results
- `TestReadLines` (6 tests): whole file, ranges, context, match, git, composition
- `TestReadAsTable` (3 tests): CSV, JSON, limit

Existing `test_source.py` (13 tests) must continue to pass unchanged.
