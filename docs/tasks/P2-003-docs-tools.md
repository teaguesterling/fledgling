# P2-003: Docs Tools (MDOutline, MDSection)

**Status:** Not started
**Depends on:** None (can be implemented independently)
**Estimated scope:** Tool publications only — existing macros match signatures

## Goal

Publish 2 MCP tools for structured markdown access. Both macros exist in
`docs.sql` with matching signatures.

## Tools

| Tool | Required Params | Optional Params | Maps To |
|------|----------------|-----------------|---------|
| MDOutline | file_pattern | max_level | `doc_outline(file_pattern, max_lvl)` |
| MDSection | file_path, section_id | — | `read_doc_section(file_path, section_id)` |

## Files

| File | Action | Description |
|------|--------|-------------|
| `sql/docs.sql` | No change | Macros already match tool signatures |
| `sql/tools/docs.sql` | Create | 2 `mcp_publish_tool()` calls |

## Path Resolution

All tool SQL templates use `resolve()` for file path params (see P2-005).

```sql
-- MDOutline
SELECT * FROM doc_outline(resolve($file_pattern), ...)

-- MDSection
SELECT * FROM read_doc_section(resolve($file_path), $section_id)
```

## Tool Publications (sql/tools/docs.sql)

MDOutline has one optional param (`max_level`, defaults to 3). MDSection has
two required params and no optional ones.

For `max_level`, the NULLIF + cast pattern:
```
COALESCE(TRY_CAST(NULLIF($max_level, 'null') AS INT), 3)
```

Tool descriptions should emphasize:
- **MDOutline**: "Table of contents for markdown files. Use before reading
  sections to decide what's relevant."
- **MDSection**: "Read a specific section by ID. Use doc_outline first to
  discover section IDs."

## Acceptance Criteria

These tests in `test_mcp_server.py` must pass:
- `TestMDOutline` (2 tests): returns headings, max_level filter
- `TestMDSection` (1 test): reads specific section

Existing `test_docs.py` (16 tests) unaffected.
