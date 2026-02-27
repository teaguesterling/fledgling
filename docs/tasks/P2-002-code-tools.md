# P2-002: Code Tools (FindDefinitions, FindCalls, FindImports, CodeStructure)

**Status:** Not started
**Depends on:** None (can be implemented independently)
**Estimated scope:** Tool publications only — existing macros match signatures

## Goal

Publish 4 MCP tools for AST-based code intelligence. All macros already exist
in `code.sql` with matching signatures. This task only creates the tool
publication file.

## Tools

| Tool | Required Params | Optional Params | Maps To |
|------|----------------|-----------------|---------|
| FindDefinitions | file_pattern | name_pattern | `find_definitions(file_pattern, name_pattern)` |
| FindCalls | file_pattern | name_pattern | `find_calls(file_pattern, name_pattern)` |
| FindImports | file_pattern | — | `find_imports(file_pattern)` |
| CodeStructure | file_pattern | — | `code_structure(file_pattern)` |

## Files

| File | Action | Description |
|------|--------|-------------|
| `sql/code.sql` | No change | Macros already match tool signatures |
| `sql/tools/code.sql` | Create | 4 `mcp_publish_tool()` calls |

## Path Resolution

All tool SQL templates use `resolve($file_pattern)` to convert relative
glob patterns to absolute paths for the DuckDB sandbox (see P2-005).

```sql
-- Example: FindDefinitions template
SELECT * FROM find_definitions(
    resolve($file_pattern),
    COALESCE(NULLIF($name_pattern, 'null'), '%')
)
```

## Tool Publications (sql/tools/code.sql)

Straightforward macro wrappers. FindDefinitions and FindCalls have one optional
param each (`name_pattern`, defaults to `'%'` which matches everything).

Tool descriptions should emphasize:
- **FindDefinitions**: "AST-based, not grep. Finds functions, classes, variables."
- **FindCalls**: "Find where functions/methods are called."
- **FindImports**: "Find import/include/require statements."
- **CodeStructure**: "Top-level overview: definitions with line counts."

For `name_pattern`, the default `'%'` is a SQL LIKE wildcard matching
everything. The NULLIF workaround must map null to `'%'`:
```
COALESCE(NULLIF($name_pattern, 'null'), '%')
```

## Acceptance Criteria

These tests in `test_mcp_server.py` must pass:
- `TestFindDefinitions` (2 tests): finds functions, filters by name
- `TestFindCalls` (1 test): finds call sites
- `TestFindImports` (1 test): finds imports
- `TestCodeStructure` (1 test): returns overview

Existing `test_code.py` (13 tests) unaffected.
