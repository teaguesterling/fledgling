# P2-007: Profile Integration and Polish

**Status:** Not started
**Depends on:** P2-006 (security profiles)
**Estimated scope:** Config updates + documentation + smoke tests

## Goal

Take the profile mechanism from P2-006 and make it usable: update the example
config so users can select a profile, document how to write custom profiles,
and verify the end-to-end `duckdb -init` experience works for both profiles.

This is the review/polish pass that turns the mechanism into a feature.

## Files

| File | Action | Description |
|------|--------|-------------|
| `config/claude-code.example.json` | Update | Add profile-specific config examples |
| `config/claude-code-analyst.example.json` | Create | Analyst profile config variant |
| `sql/profiles/core.sql` | Review | Add header comment documenting the convention |
| `sql/profiles/analyst.sql` | Review | Add header comment documenting the convention |

## Technical Details

### Config examples

The existing `config/claude-code.example.json` uses the monolithic
`init-fledgling.sql`. Update it to use the core entry point by default,
and provide an analyst variant:

```json
{
  "mcpServers": {
    "fledgling": {
      "command": "duckdb",
      "args": ["-init", "/path/to/fledgling/init-fledgling-core.sql"],
      "cwd": "/path/to/your/project"
    }
  }
}
```

### Custom profile convention

Document in profile SQL files (as header comments) the contract a profile
must satisfy (already added in P2-006, review for completeness):

1. Set `memory_limit` (DuckDB setting)
2. Set `mcp_server_options` variable (JSON string passed to `mcp_server_start()`)

The `mcp_server_options` JSON controls built-in duckdb_mcp tools:
`enable_query_tool`, `enable_describe_tool`, `enable_list_tables_tool`,
`enable_database_info_tool`, `enable_export_tool`, `enable_execute_tool`,
and `default_result_format`.

Users create a custom profile by copying `core.sql`, modifying it, and
pointing a new entry-point init script at it. The profile format is plain
SQL — no special DSL.

### Smoke tests

Manual verification (not automated) that these work:

1. `duckdb -init init-fledgling-core.sql` starts, tools are discoverable,
   query tool is absent
2. `duckdb -init init-fledgling-analyst.sql` starts, all tools present
   including query
3. Original `init-fledgling.sql` still works (backward compat)

These could become automated tests later, but for P2-007 a manual pass
during review is sufficient. The automated enforcement lives in P2-006's
`test_profiles.py`.

### Severance Protocol notes

Leave a breadcrumb for future work: a comment in the profile directory
(or a `README.md` if warranted) noting that the Innie/Outie distinction
maps to profile selection, and that `fledgling-outie.sql` is the planned
next profile.

## Acceptance Criteria

- `config/claude-code.example.json` uses core profile by default
- Analyst config variant exists and is correct
- Profile SQL files have header comments documenting the convention
- All three init scripts (`core`, `analyst`, legacy) start without errors
  (manual smoke test)
- Existing automated tests unaffected
- A developer unfamiliar with the codebase could create a custom profile
  by reading the comments in `core.sql` alone
