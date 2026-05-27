## 0.11.1

### Fixed
- **Pin `duckdb==1.5.2`.** The unbounded `duckdb>=1.5.0` let a fresh
  `pip install fledgling-mcp` pull duckdb **1.5.3**, whose community extensions
  (`read_lines`, `sitting_duck`, `markdown`, `duck_tails`) aren't available — so
  `rebuild_fts()` / `build_cache()` / all FTS failed on a clean install with
  `Extension ".../v1.5.3/.../read_lines.duckdb_extension" not found`. 1.5.2 (the fleet-wide pin) has the extensions; verified a fresh install + persist round-trip
  works under the pin. (Affected 0.10.0 and 0.11.0 too.)

## 0.11.0

### Added — persistent fact substrate (workstream C)
A file-backed cache so the AST/FTS index is built once and *attached* on reuse,
instead of rebuilt in-memory every connect (~4 s → ~0.3 s cache hit, >10×):

- `connect(persist=<path>, read_only=<bool>)` — default `persist=None` keeps the
  historical in-memory (`:memory:`) behavior. With `persist`, the macros, AST/FTS
  tables, and FTS index live in the file. A read-only reader issues **no** catalog
  writes: configuration is skipped (macros are already persisted) and only the
  query-side extension (`fts`) is loaded, so a cache-hit query stays well under a
  hook-time budget.
- `build_cache(persist, root=None, *, force=False, ...)` — the single-writer
  builder. Idempotent + staleness-aware: rebuilds only when the project content
  key changed, else returns `False`. Readers then `connect(persist=..., read_only=True)`.
- `cache_is_fresh(persist, root=None)` — read-only freshness probe.
- Staleness is keyed on **git content** (HEAD + uncommitted source changes), not
  mtime (a worktree re-checkout gives fresh mtimes but identical content). The
  cache file and its sidecars are excluded from the key so it never invalidates
  itself.

### Performance
- `Tools` discovery (an `mcp_list_tools()` + catalog scan, ~80 ms) is now **lazy** —
  deferred to first access of `.tools`/macros. A read-only reader that only queries
  via `con.con` never pays it, so `connect()` is ~80 ms cheaper across the board
  (read-only cache-hit `connect` ~130 ms → ~50 ms).

Single-writer (DuckDB-enforced); a last-good-snapshot fallback for readers racing
a build, and incremental (per-file) rebuild, are deferred to a later release.

# Changelog

## 0.10.0

### Public API (new — SemVer-stable from here)
fledgling now declares a stable connection contract so downstream packages
(pluckit, squackit) stop coupling to private internals:

- `Connection.con` → the underlying raw `duckdb.DuckDBPyConnection`
  (replaces the internal `._con`, which remains as a deprecated alias).
- `Connection.tools` → the `Tools` registry (replaces `._tools`, deprecated alias).
- `Connection.ensure_fts(**kwargs)` → idempotent FTS build; builds the
  `fts.content` index on first call or if empty/missing, no-op thereafter.
  This is the public home of the lazy-rebuild that FTS tools need (previously
  re-implemented in squackit by poking `._con` + a private `_fts_built` flag).
- `Tools.list() -> list[ToolInfo]` and the `ToolInfo` dataclass
  (`macro_name`, `params`, …) are now documented as public API.

### Fixed (folds in the 0.9.1 bugfix work)
- `pro/server.py`: `_tools.list()` yields `ToolInfo` dataclasses, not dicts —
  use attribute access (`.macro_name`/`.params`), not `["name"]`/`["params"]`.
- `sql/source.sql`: `read_source_text` relativizes `file_path` before `git_uri()`
  so an already-absolute (`_resolve`'d) path doesn't double the repo root.
- tests: `pluckit.plugins` → `pluckit.pluckins`; `FindInAST` → `FindCode`;
  `GitDiffFile` output now carries a `# file:range` header.

### Notes
- `._con` / `._tools` are kept as working aliases for a transition; they will
  be removed in a future major. New code should use `.con` / `.tools`.
