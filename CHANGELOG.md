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
