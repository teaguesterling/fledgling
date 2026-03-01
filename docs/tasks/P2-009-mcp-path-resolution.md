# P2-009: MCP Path Resolution and Server Launch Cleanup

**Status:** Not started
**Priority:** P2 (required before production release)
**Depends on:** P2-008 (MVP validation)

## Problem

Two related issues make the current MCP integration fragile and hard to maintain:

### 1. `getvariable()` is unavailable in MCP tool execution context

`duckdb_mcp` executes tool SQL templates in a context where `getvariable()` returns
NULL. This means the `resolve()` macro — which depends on
`getvariable('session_root')` — cannot work in tool templates. Every tool that
accepts a file path must instead inline a `CASE WHEN $p[1] = '/' THEN $p ELSE
'<embedded_root>/' || $p END` expression at publish time.

This is currently duplicated across 9 tool templates in 3 files (`files.sql`,
`code.sql`, `docs.sql`). Adding or modifying a tool requires remembering this
pattern, and getting the quoting right inside `mcp_publish_tool()` string
literals is error-prone.

### 2. `PWD` not set when Claude Code spawns MCP servers

Claude Code spawns `duckdb` via `child_process` without a shell, so the `PWD`
environment variable is not set. The init script's fallback chain
(`getvariable('session_root')` > `FLEDGLING_ROOT` > `PWD`) fails silently,
leaving `session_root` as NULL.

Current workaround: `.mcp.json` uses `sh -c "exec duckdb -init ..."` to get a
shell that sets `PWD`. This works but adds an unnecessary process layer and
looks wrong to anyone reading the config.

## Current Workarounds

- **Inline path resolution** in every tool template via embedded `session_root`
  at publish time (verbose, 9 duplicated expressions)
- **`sh -c` wrapper** in `.mcp.json` to ensure `PWD` is set (fragile, non-obvious)
- **`CURRENT_TIMESTAMP::TIMESTAMP` cast** in conversation tools to work around
  `TIMESTAMPTZ - INTERVAL` not being supported in MCP context

## Options to Evaluate

### Option A: Upstream fix — `getvariable()` in MCP context

File an issue against `duckdb_mcp` requesting that `getvariable()` work inside
tool SQL templates. This would let `resolve()` work natively and eliminate all
inline path resolution.

**Pros:** Cleanest fix, zero code on our side, benefits all duckdb_mcp users.
**Cons:** Depends on upstream timeline. May have security implications they need
to consider (tool templates accessing arbitrary variables).

### Option B: Publish-time `_resolve()` helper

Create a SQL scalar macro at init time that hardcodes `session_root`:

```sql
-- Generated at init time, after session_root is set
CREATE OR REPLACE MACRO _resolve(p) AS
    CASE WHEN p IS NULL THEN NULL
         WHEN p[1] = '/' THEN p
         ELSE '/actual/session/root/' || p
    END;
```

This wouldn't work if DuckDB evaluates macros lazily (referencing the variable
at call time, not definition time). Needs testing to confirm whether scalar
macro bodies are captured or deferred.

**Pros:** Single definition, all tool templates just call `_resolve($param)`.
**Cons:** May not work due to macro evaluation semantics. Adds a second
`resolve` variant that could confuse contributors.

### Option C: Wrapper shell script

Replace `sh -c "exec duckdb -init ..."` with a proper `scripts/serve.sh`:

```sh
#!/bin/sh
# Fledgling MCP server launcher
# Sets PWD and session_root reliably before starting DuckDB
cd "${FLEDGLING_ROOT:-.}" || exit 1
exec duckdb -init init-fledgling.sql
```

`.mcp.json` becomes:

```json
{
  "command": "./scripts/serve.sh",
  "cwd": "."
}
```

**Pros:** Clean `.mcp.json`, single place for launch logic, can add logging or
error handling. Portable across shells.
**Cons:** Doesn't fix the `getvariable()` issue (still need inline resolution
in tool templates). Adds a file to maintain.

### Option D: DuckDB extension for path resolution

Write a small DuckDB extension that provides `resolve_path(root, path)` as a
native function. Unlike macros, extension functions are always available in any
execution context including MCP tools.

**Pros:** Works everywhere, proper function semantics, could add features like
path normalization or symlink resolution.
**Cons:** New build dependency, extension maintenance burden, increases
packaging complexity (P3-006).

### Option E: Template generation

Generate tool SQL files from templates at build/init time, substituting
`session_root` into the SQL before loading. Could use `sed`, `envsubst`, or a
small Python script.

**Pros:** Clean tool templates (just use `$SESSION_ROOT/` prefix), no runtime
workarounds.
**Cons:** Adds a build step, complicates the init flow, generated files could
get stale.

## Recommended Approach

Evaluate in this order:

1. **Test Option B first** — if scalar macros capture values at definition time,
   this is the lowest-effort fix. One macro definition replaces 9 inline
   expressions.
2. **Implement Option C regardless** — a wrapper script is better than `sh -c`
   in `.mcp.json` even if other fixes land.
3. **File Option A upstream** — even if we solve it locally, the upstream fix
   benefits the ecosystem.
4. **Option D as fallback** — only if macro capture doesn't work and we need a
   clean long-term solution.
5. **Option E as last resort** — template generation adds complexity that should
   be avoided unless nothing else works.

## Acceptance Criteria

- [ ] Relative paths work in all tool templates without inline CASE expressions
- [ ] `.mcp.json` does not require `sh -c` wrapper
- [ ] `resolve()` or equivalent works in MCP tool execution context
- [ ] All existing tests pass
- [ ] CLAUDE.md updated to document the chosen approach
- [ ] DuckDB quirk documented (or removed if upstream fixes land)

## Files Affected

- `sql/tools/files.sql` — 3 inline path resolutions
- `sql/tools/code.sql` — 4 inline path resolutions
- `sql/tools/docs.sql` — 2 inline path resolutions
- `sql/tools/conversations.sql` — TIMESTAMPTZ cast workaround
- `sql/sandbox.sql` — `resolve()` macro definition
- `.mcp.json` — `sh -c` wrapper
- `config/claude-code.example.json` — example config
- `init-fledgling-base.sql` — session_root initialization
- `CLAUDE.md` — quirk documentation
