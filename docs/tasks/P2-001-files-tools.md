# P2-001: Files Tools (ListFiles, ReadLines, ReadAsTable)

**Status:** Not started
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
macro prepends `session_root` for relative paths, passes absolute paths through.

```sql
-- In tool SQL templates:
resolve($file_path)          -- single file
resolve($file_pattern)       -- glob pattern
```

Git mode (`commit` param) uses repo-relative paths, which `duck_tails`
resolves against the repo root. These do NOT need `resolve()`.

## New/Updated Macros

### list_files(pattern, commit)

Filesystem mode (commit is NULL): wrap `glob()` to list matching files.
Git mode (commit provided): query `git_tree()` filtered by `file_path LIKE pattern`.

```sql
CREATE OR REPLACE MACRO list_files(pattern, commit := NULL) AS TABLE
    SELECT * FROM (
        SELECT file_path
        FROM glob(pattern)
        WHERE commit IS NULL
        UNION ALL
        SELECT file_path
        FROM git_tree('.', commit)
        WHERE commit IS NOT NULL
          AND file_path LIKE pattern
    )
    ORDER BY file_path;
```

Note: glob uses shell syntax (`*.sql`), git mode uses SQL LIKE (`%.sql`).
The tool description must document this difference.

### read_source — add match and commit params

Extend existing macro. Existing calls (without match/commit) must still work.

```sql
CREATE OR REPLACE MACRO read_source(file_path, lines := NULL, ctx := 0,
                                     match := NULL, commit := NULL) AS TABLE
    SELECT line_number, content
    FROM read_lines(
        CASE WHEN commit IS NULL THEN file_path
             ELSE git_uri('.', file_path, commit)
        END,
        lines, context := ctx
    )
    WHERE match IS NULL OR content ILIKE '%' || match || '%';
```

**Risk:** `read_lines()` may not support `git://` URIs. Fallback: use
`git_read()` + `string_split()` for commit mode.

### read_as_table(file_path, lim)

Use DuckDB's auto-detection via replacement scan.

```sql
CREATE OR REPLACE MACRO read_as_table(file_path, lim := 100) AS TABLE
    SELECT * FROM query_table(file_path) LIMIT lim;
```

**Risk:** `FROM $param` may not work with string substitution in
mcp_publish_tool templates. Fallback: use explicit `read_csv_auto()`.

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
