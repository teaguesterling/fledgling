# P3-001: ReadAsTable Reader Override Parameter

**Status:** Not started
**Depends on:** P2-001 (Files Tools)
**Estimated scope:** Macro update + tool template update

## Goal

Add an optional `reader` parameter to `read_as_table` and the `ReadAsTable`
MCP tool that lets users override DuckDB's auto-detection with an explicit
reader function name.

## Motivation

DuckDB's auto-detection (`query_table()` / `FROM 'file'`) works well for
common formats but can't handle edge cases:
- Files with non-standard extensions (e.g. `.dat` that's actually CSV)
- Ambiguous formats where the wrong reader is chosen
- Explicit reader functions with specific options (e.g. `read_csv`)

## Design

### Macro Signature

```sql
read_as_table(file_path, lim := 100, reader := NULL)
```

### Resolution Logic

1. If `reader IS NULL` → use current auto-detection (`query_table(file_path)`)
2. If `table_function_exists(reader)` → call `reader(file_path)` directly
3. If `table_function_exists('read_' || reader)` → call `read_{reader}(file_path)`
4. Otherwise → error

### Examples

```sql
-- Auto-detect (current behavior)
SELECT * FROM read_as_table('data.csv');

-- Explicit reader function
SELECT * FROM read_as_table('data.dat', reader := 'read_csv_auto');

-- Shorthand with read_ prefix fallback
SELECT * FROM read_as_table('data.dat', reader := 'csv_auto');
```

## Implementation Challenges

### Dynamic Function Dispatch

DuckDB macros cannot dynamically call a function by name. The resolution
logic requires one of:

1. **Chain of CASE/UNION ALL branches** for known reader functions — simple
   but limited to a fixed set of supported readers.

2. **`duckdb_func_apply` extension** (see `~/Projects/duckdb_func_apply`) —
   enables dynamic function invocation by name. Would allow truly generic
   dispatch but adds an extension dependency.

3. **`query_table()` with formatted SQL** — construct a SQL string like
   `format('{}(''{}'')', reader, file_path)` and pass to `query_table()`.
   Needs testing to see if `query_table()` accepts function-call syntax.

### MCP Tool Template

The MCP tool template has additional constraints:
- `FROM $file_path` (current approach) bypasses Python namespace collisions
  but requires a string literal — can't wrap in dynamic function calls
- `query_table()` works for function dispatch but has the Python `import json`
  collision issue (see P2-001 notes)
- May need to use explicit reader functions (`read_csv_auto`, `read_json_auto`)
  in the tool template with extension-based dispatch as the default path

### `table_function_exists()` Check

DuckDB may not have a built-in `table_function_exists()` predicate. Alternatives:
- Query `duckdb_functions()` system table
- Use TRY/CATCH pattern (if available in macros)
- Skip validation and let DuckDB error naturally on invalid reader names

## Acceptance Criteria

- `read_as_table('file.csv')` still works (backward compatible)
- `read_as_table('file.dat', reader := 'read_csv_auto')` reads as CSV
- `read_as_table('file.dat', reader := 'csv_auto')` resolves to `read_csv_auto`
- `ReadAsTable` MCP tool accepts optional `reader` parameter
- Invalid reader names produce a clear error message
- Existing P2-001 tests continue to pass
