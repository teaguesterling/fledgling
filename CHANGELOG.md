## 0.13.1 - 2026-08-15

### Fixed — root-defaulting macros broke under the new sandbox (#53)
Regression from #49/#50 in 0.13.0. Sandboxing restricts
`allowed_directories` to the connection's root, but 16 macros defaulted their
`root`/`repo` parameter to `'.'`, which resolves against the *process* CWD. Any
caller connecting with `root != cwd` — the normal library pattern, a server
pointed at a project while running elsewhere — got
`Permission Error: Cannot access file "./**/*"` from `project_overview()` and
every other root-defaulting macro. Callers that wrap these in `try/except`
degraded silently instead of reporting it.

Defaults now use `_session_root()`. Each affected module also declares
`CREATE MACRO IF NOT EXISTS _session_root() AS '.'`, since the macro is
otherwise only defined by `connect()` and a module loaded into a bare
connection could not parse its own defaults. The sandbox is not widened —
tests assert paths outside the root are still blocked.

## 0.13.0 - 2026-08-15

### Changed — Python `connect()` / `pro.server` sandboxed by default (#49)
The shipped CLI server (`duckdb -init init-fledgling-*.sql`) has always locked
the filesystem down at startup; the Python API did not, so `fledgling.connect()`
and `python -m fledgling.pro.server` ran with external access enabled (a LOW
consistency gap — not the shipped entrypoint). `connect()` now applies
`lockdown()` by default on every path (modes 1–3 and the read-only cache
reader): `allowed_directories = [root, 'git://'] (+ extra_dirs)`,
`enable_external_access = false`, `lock_configuration = true`.

- **Opt-out is explicit:** `connect(sandbox=False)` (also plumbed through
  `create_server`). `attach()`/`configure()` still never lock a caller-owned
  connection — call `fledgling.lockdown(con)` yourself (now documented).
- `lockdown()` is now idempotent: a no-op on an already-locked/externally-
  disabled connection (init files may lock themselves), and its default
  allow-list honors the `extra_dirs` session variable like the init scripts.
- Sandboxed read-only cache readers eagerly `LOAD fts` (~18 ms) because
  lockdown disables the lazy autoload; `sandbox=False` restores the old
  lazy behavior.
- The edit CLI sandboxes to CWD plus the directories implied by its target
  paths/patterns (it legitimately edits user-named files outside CWD).
- Regression tests in `tests/test_sandbox.py::TestConnectLockdown` pin the
  refusal (`read_source('/etc/hostname')` raises), the positive path (index
  queries under `root` still work), and the opt-out.

### Fixed — rendered source was double-spaced (#51)
`read_lines()` returns `content` with its trailing newline attached. Both
renderers interpolate that into a numbered line and then join the results with
a newline, so every rendered line ended in two: reading any file through
`read_source` came back double-spaced, and every line-counting caller saw twice
the lines it asked for.

Fixed at both boundaries, which had drifted into copies of each other:
`read_source_text`'s printf in `sql/source.sql`, and its Python mirror in
`pro/server.py`. The MCP path uses only the latter, so fixing the macro alone
changed nothing — they must stay in step. `view_code_text` in `sql/code.sql`
had the same defect.

### Fixed — `Tools._source` reported `"unknown"` (#51)
Discovery is deferred to first access and `_macros` / `_tool_info` are
properties that call `_ensure_discovered()`, but `_source` was a plain
attribute still holding its `"unknown"` initializer. Reading it before anything
else touched the object returned that initializer instead of where the macros
came from. Now a lazy property like its siblings.

### Changed — `duckdb` requirement relaxed to `>=1.5.2,<1.6` (#51)
DuckDB extensions install **per DuckDB version**
(`~/.duckdb/extensions/v<VER>/...`), so pinning an exact patch strands the
install on whatever extension builds exist for that one version. On 1.5.2 the
newest published `sitting_duck` is `f7b9c60`, which returns `0` for every
`start_column`; reinstalling cannot fix it, because newer builds are published
only for newer DuckDB. That is a silent wrong-answer failure, not an install
error. Verified on 1.5.5.

### Fixed — flaky diff-marker test (#52)
`test_diff_markers_present` built its line list with `text.strip()`, but a
context line's marker *is* a space, so the strip removed it from the first line
only. The test passed or failed according to what the previous commit happened
to touch.

## 0.12.0

### Added — vendor/submodule-aware project discovery (#47)
`project_overview` and the new `source_files` macro now exclude dependency,
build, cache, and third-party trees by default, so discovery reflects a
project's own code instead of drowning in its vendored deps. On a DuckDB
extension with `duckdb/` + `rdkit/` git submodules, `project_overview` dropped
from **21,916 files to 71**; a `**/*.cpp` listing from **3,296 to 12**.

- `_is_vendored_path(file_path)` — scalar predicate; the single source of truth
  for "what to ignore". A path denylist (`.venv`, `node_modules`, `build`,
  `dist`, `CMakeFiles`, `*-prefix`, `__pycache__`, caches, …) **plus** checked-in
  third-party conventions (`vendor`, `third_party`, `External`, `googletest`)
  that git-awareness alone can't distinguish.
- `_submodule_prefixes(root)` — the git-aware half: parses `root/.gitmodules` to
  exclude submodule trees, whose directory names are arbitrary (`duckdb/`,
  `rdkit/`) and which no denylist could catch. Reads via
  `read_lines(..., ignore_errors := true)`, so a missing `.gitmodules` (no
  submodules, or not a git repo) yields no rows rather than an IO error.
- `source_files(root, pattern := '**/*', include_ignored := false)` — the
  filtered discovery surface: `glob` minus `_is_vendored_path` minus
  `_submodule_prefixes`. Glob-based, so brand-new **uncommitted** files are still
  surfaced (unlike a pure git-tracked listing) and it works in non-git dirs.
- `project_overview(root, include_ignored := false)` — gains the same filtering
  (via `source_files`) plus an `include_ignored := true` opt-out that restores
  the old count-everything behavior.

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
