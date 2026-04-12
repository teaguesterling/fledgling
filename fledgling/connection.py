"""Fledgling DuckDB connection API.

The canonical way to get a fledgling-enabled DuckDB connection from Python.
Used by tests, fledgling-pro (FastMCP), and direct Python consumers.

Public surface:

  Top-level verbs:
    connect(init=None, ...)  — new DuckDBPyConnection, configured, wrapped
    attach(con, ...)         — configure an existing connection
    configure(con, ...)      — the mid-level verb; sugar over the building blocks
    lockdown(con, ...)       — irreversible filesystem/config lockdown

  Compose helpers (building blocks):
    load_extensions(con)
    set_session_root(con, root)
    load_macros(con, modules=..., sql_dir=...)
    apply_local_init(con, root=..., init_path=...)  — overlay, returns bool

Three configuration modes for `connect()`:

  1. Explicit init file: connect(init='path/to/file.sql')
     Executes the specified file directly, does NOT load from sources.
     Use when the user is in full control of the init sequence.

  2. Auto-discover (default): connect() or connect(root=...)
     Loads standard sources first, then applies `.fledgling-init.sql` from
     the project root as an overlay if present. The overlay can add
     project-specific macros/variables without forking the core set.

  3. No overlay: connect(init=False)
     Loads standard sources only, never looks for a project init file.
"""

import os
import re
from pathlib import Path
from typing import Optional

import duckdb


# ── Init file execution ──────────────────────────────────────────────


def _execute_init_file(
    con: duckdb.DuckDBPyConnection,
    init_path: str,
    root: Optional[str] = None,
):
    """Execute a .fledgling-init.sql file through the Python API.

    The installed init file is a flat SQL file (no .read commands) assembled
    by the installer. We execute it statement by statement, skipping:
    - Dot-commands (.headers, .mode, .output)
    - mcp_server_start (not needed in Python context)
    - PRAGMA mcp_publish_tool (tool publications are MCP-only)
    - Statements using getenv() (CLI-only; we pre-set the variables instead)
    """
    # Pre-set variables that the init file normally gets from getenv()
    root = root or os.path.dirname(os.path.abspath(init_path))
    con.execute("SET VARIABLE session_root = ?", [root])
    con.execute("SET VARIABLE conversations_root = ?",
                [str(Path.home() / ".claude" / "projects")])

    sql = Path(init_path).read_text()

    for stmt in _split_sql(sql):
        # Skip dot-commands
        if stmt.startswith("."):
            continue
        # Skip MCP server start
        if "mcp_server_start" in stmt:
            continue
        # Skip MCP tool publications
        if "mcp_publish_tool" in stmt:
            continue
        # Skip getenv() calls (we pre-set the variables above)
        if "getenv(" in stmt:
            continue
        con.execute(stmt + ";")


# ── SQL source file loading ──────────────────────────────────────────


def _find_sql_dir() -> Optional[Path]:
    """Find the SQL directory from package data or repo layout."""
    for candidate in [
        Path(__file__).parent / "sql",               # pip installed (package data)
        Path(__file__).parent.parent / "sql",         # development (repo root)
    ]:
        if candidate.exists() and (candidate / "sandbox.sql").exists():
            return candidate
    return None


def _load_sql_file(con: duckdb.DuckDBPyConnection, path: Path):
    """Load a SQL file, stripping comment-only lines before splitting."""
    sql = path.read_text()
    for stmt in _split_sql(sql):
        if stmt.startswith("."):
            continue
        con.execute(stmt + ";")


# ── SQL splitting ────────────────────────────────────────────────────


def _split_sql(sql: str) -> list[str]:
    """Split SQL text into statements, stripping comment-only lines.

    Handles the same edge cases as conftest.load_sql:
    - Comment-only lines (may contain semicolons) are stripped
    - Empty statements are skipped
    - Dot-commands are preserved as single "statements"
    """
    # Separate dot-commands (they don't end with ;)
    result = []
    # Strip comment-only lines
    lines = [l for l in sql.split("\n") if not l.strip().startswith("--")]
    cleaned = "\n".join(lines)

    # Split on semicolons
    for stmt in cleaned.split(";"):
        stmt = stmt.strip()
        if stmt:
            # Check if any line in this "statement" is a dot-command
            for line in stmt.split("\n"):
                line = line.strip()
                if line.startswith("."):
                    result.append(line)
            # The non-dot content is the SQL statement
            non_dot = "\n".join(
                l for l in stmt.split("\n") if not l.strip().startswith(".")
            ).strip()
            if non_dot:
                result.append(non_dot)

    return result


# ── Defaults ─────────────────────────────────────────────────────────


_DEFAULT_MODULES = [
    "sandbox", "dr_fledgling",
    "source", "code", "docs", "repo", "structural", "workflows",
    "conversations", "help",
]

_DEFAULT_EXTENSIONS = ["read_lines", "sitting_duck", "markdown", "duck_tails"]


# ── Compose helpers (Delta 4) ────────────────────────────────────────


def load_extensions(
    con: duckdb.DuckDBPyConnection,
    extensions: Optional[list[str]] = None,
) -> None:
    """Load DuckDB extensions required by fledgling macros.

    Defaults to `_DEFAULT_EXTENSIONS`. Pass an explicit list to load a
    different set, or an empty list to skip extension loading entirely.
    """
    if extensions is None:
        extensions = _DEFAULT_EXTENSIONS
    for ext in extensions:
        con.execute(f"LOAD {ext}")


def set_session_root(
    con: duckdb.DuckDBPyConnection,
    root: str,
) -> None:
    """Bake `root` into session variables and the `_resolve`/`_session_root` macros.

    These literal-backed macros exist because `getvariable()` returns NULL
    inside the MCP tool execution context; tool templates need the value
    baked in as a string literal at macro-definition time.

    Also sets `conversations_root` to `~/.claude/projects`.
    """
    con.execute("SET VARIABLE session_root = ?", [root])
    con.execute("SET VARIABLE conversations_root = ?",
                [str(Path.home() / ".claude" / "projects")])
    con.execute(f"""CREATE OR REPLACE MACRO _resolve(p) AS
        CASE WHEN p IS NULL THEN NULL
             WHEN p[1] = '/' THEN p
             ELSE '{root}/' || p
        END""")
    con.execute(f"CREATE OR REPLACE MACRO _session_root() AS '{root}'")


def load_macros(
    con: duckdb.DuckDBPyConnection,
    modules: Optional[list[str]] = None,
    sql_dir: Optional[Path] = None,
) -> None:
    """Load fledgling SQL macro modules from their `.sql` files.

    Args:
        con: The connection to load macros into.
        modules: Module names to load, in dependency order. Defaults to
            `_DEFAULT_MODULES`. Modules whose `.sql` file does not exist
            are silently skipped.
        sql_dir: Directory containing the `.sql` files. If None, auto-
            discovered via `_find_sql_dir()`.

    Raises:
        FileNotFoundError: if `sql_dir` is None and auto-discovery fails.
    """
    if modules is None:
        modules = _DEFAULT_MODULES
    if sql_dir is None:
        sql_dir = _find_sql_dir()
    if sql_dir is None:
        raise FileNotFoundError(
            "No fledgling SQL sources found. "
            "Run 'fledgling install' or 'pip install fledgling-mcp' first."
        )
    for module in modules:
        path = sql_dir / f"{module}.sql"
        if path.exists():
            _load_sql_file(con, path)


def apply_local_init(
    con: duckdb.DuckDBPyConnection,
    root: Optional[str] = None,
    init_path: Optional[str] = None,
) -> bool:
    """Apply a project-local `.fledgling-init.sql` as an overlay.

    Looks for `.fledgling-init.sql` in `root` (or `init_path` if provided)
    and executes it via `_execute_init_file()`. Standard sources should
    already be loaded — this layer is additive, not replacement.

    Returns:
        True if an init file was found and applied, False otherwise.
    """
    if init_path is not None:
        path = Path(init_path)
    else:
        path = Path(root or os.getcwd()) / ".fledgling-init.sql"
    if not path.exists():
        return False
    _execute_init_file(con, str(path), root)
    return True


# ── Mid-level verb (Delta 5) ─────────────────────────────────────────


def configure(
    con: duckdb.DuckDBPyConnection,
    root: Optional[str] = None,
    profile: str = "analyst",
    modules: Optional[list[str]] = None,
    extensions: bool = True,
    overlay: bool = True,
) -> None:
    """Apply fledgling configuration to an existing DuckDB connection.

    Composes the Delta 4 building blocks into a single opinionated setup:
    extensions, session variables, metadata, help path, macros, and
    (optionally) a project-local `.fledgling-init.sql` overlay.

    Args:
        con: The connection to configure.
        root: Project root. Defaults to CWD.
        profile: Security profile label ('analyst' or 'core'). Written
            into the `fledgling_profile` session variable; enforcement
            happens via profile SQL files or the MCP server, not here.
        modules: SQL modules to load. Defaults to `_DEFAULT_MODULES`.
        extensions: If True (default), load DuckDB extensions. Set False
            when extensions are already loaded (tests).
        overlay: If True (default), apply `.fledgling-init.sql` overlay
            from `root` if present. Set False to skip.
    """
    root = root or os.getcwd()
    if extensions:
        load_extensions(con)
    set_session_root(con, root)

    # Metadata variables (consumed by dr_fledgling and profile SQL)
    from fledgling import __version__
    con.execute("SET VARIABLE fledgling_version = ?", [__version__])
    con.execute("SET VARIABLE fledgling_profile = ?", [profile])
    mods = list(modules) if modules is not None else list(_DEFAULT_MODULES)
    con.execute("SET VARIABLE fledgling_modules = ?", [mods])

    # Help path (optional; help.sql uses it for Help tool)
    sql_dir = _find_sql_dir()
    if sql_dir is not None:
        for help_candidate in [
            Path(root) / ".fledgling-help.md",
            sql_dir.parent / "SKILL.md",
        ]:
            if help_candidate.exists():
                con.execute("SET VARIABLE _help_path = ?", [str(help_candidate)])
                break

    load_macros(con, modules=mods, sql_dir=sql_dir)

    if overlay:
        apply_local_init(con, root=root)


# ── Lockdown (Delta 3) ───────────────────────────────────────────────


def lockdown(
    con: duckdb.DuckDBPyConnection,
    allowed_dirs: Optional[list[str]] = None,
    lock_config: bool = True,
) -> None:
    """Apply filesystem and configuration lockdown to a fledgling connection.

    Mirrors the SQL-side lockdown in `init/init-fledgling-{core,analyst}.sql`:
    sets allowed_directories, disables external access, and (by default)
    locks configuration so no further settings can change.

    This is irreversible within the connection lifetime.

    Args:
        con: The connection to lock down. Accepts a Connection proxy or
            a raw DuckDBPyConnection.
        allowed_dirs: Directories to permit filesystem access to. If None,
            reads `session_root` from the connection and defaults to
            `[session_root, 'git://']`. Otherwise uses the list as-is.
        lock_config: If True (default), also set `lock_configuration = true`
            so no further config changes are permitted. Set False for
            notebook/scripting use cases that still need to adjust other
            settings.
    """
    if allowed_dirs is None:
        row = con.execute("SELECT getvariable('session_root')").fetchone()
        session_root = row[0] if row else None
        dirs = [session_root, "git://"] if session_root else ["git://"]
    else:
        dirs = list(allowed_dirs)
    dirs_literal = "[" + ", ".join(f"'{d}'" for d in dirs) + "]"
    con.execute(f"SET allowed_directories = {dirs_literal}")
    con.execute("SET enable_external_access = false")
    if lock_config:
        con.execute("SET lock_configuration = true")


# ── Top-level verbs (Delta 3) ────────────────────────────────────────


def connect(
    init: Optional[str | bool] = None,
    root: Optional[str] = None,
    profile: str = "analyst",
    modules: Optional[list[str]] = None,
    extensions: bool = True,
) -> "Connection":
    """Create a DuckDB connection with fledgling macros loaded.

    Three modes:

      1. **Explicit init file** (``init='path'``) — execute that file directly
         without loading standard sources. Use when the init file is
         authoritative (installer-generated or user-controlled).

      2. **Auto-discover with overlay** (``init=None``, default) — load
         standard sources, then apply ``.fledgling-init.sql`` from ``root``
         as an overlay if it exists. Project-local additions layer on top
         of the core macro set.

      3. **Sources only** (``init=False``) — load standard sources without
         looking for an overlay file.

    Examples::

        # Auto-discover: sources + project overlay (if present)
        con = fledgling.connect()

        # Explicit init file (user-authoritative)
        con = fledgling.connect(init=".fledgling-init.sql")

        # Programmatic (no overlay discovery)
        con = fledgling.connect(init=False, root="/path/to/project", profile="core")

        # Minimal (specific modules only)
        con = fledgling.connect(init=False, modules=["sandbox", "source"])

    Args:
        init: Path to a `.fledgling-init.sql` file (Mode 1), `False` to
            skip overlay discovery (Mode 3), or None (default) for the
            auto-discover overlay behavior (Mode 2).
        root: Project root. Defaults to CWD.
        profile: Security profile ('analyst' or 'core'). See `configure()`.
        modules: SQL modules to load. Defaults to `_DEFAULT_MODULES`.
            Only used in Modes 2 and 3.
        extensions: Whether to load DuckDB extensions. Set False if
            extensions are already loaded (e.g., in tests).

    Returns:
        A `Connection` proxy wrapping the new DuckDB connection with all
        fledgling macros available as method calls.
    """
    root = root or os.getcwd()
    raw = duckdb.connect(":memory:")

    # Mode 1: explicit init file — user is authoritative, no source loading
    if init is not None and init is not False:
        _execute_init_file(raw, init, root)
        return Connection(raw)

    # Mode 2 / Mode 3: load from sources, optional overlay
    overlay_enabled = init is not False
    configure(
        raw,
        root=root,
        profile=profile,
        modules=modules,
        extensions=extensions,
        overlay=overlay_enabled,
    )
    return Connection(raw)


def attach(
    con: duckdb.DuckDBPyConnection,
    root: Optional[str] = None,
    profile: str = "analyst",
    modules: Optional[list[str]] = None,
    extensions: bool = True,
    overlay: bool = True,
) -> "Connection":
    """Configure an existing DuckDBPyConnection with fledgling.

    Use when you already have a connection (notebook, test harness,
    embedding in a larger application) and want to attach fledgling's
    macros and variables without creating a new :memory: database.

    Example::

        raw = duckdb.connect("my.db")
        con = fledgling.attach(raw, root="/my/project")
        con.find_definitions("**/*.py").show()

    Args:
        con: An existing DuckDB connection to configure.
        root, profile, modules, extensions, overlay: See `configure()`.

    Returns:
        A `Connection` proxy wrapping `con` for macro access.
    """
    configure(
        con,
        root=root,
        profile=profile,
        modules=modules,
        extensions=extensions,
        overlay=overlay,
    )
    return Connection(con)


# ── Connection proxy ─────────────────────────────────────────────────


class Connection:
    """Fledgling-enhanced DuckDB connection.

    Wraps a DuckDB connection and adds macro methods as attributes.
    All standard DuckDB connection methods (execute, sql, table_function,
    etc.) are delegated to the underlying connection.

    Macros are callable directly::

        con.find_definitions("**/*.py").show()
        con.recent_changes(5).limit(3).df()

    The full Tools object is available at ``con._tools``. Tools uses the
    MCP publication registry (via duckdb_mcp's `mcp_list_tools()` table
    function) to expose only curated user-facing macros with descriptions,
    falling back to a full catalog scan when the registry is unavailable
    (older duckdb_mcp, duckdb_mcp not loaded, zero publications).
    """

    def __init__(self, con: duckdb.DuckDBPyConnection):
        from fledgling.tools import Tools
        self._con = con
        self._tools = Tools(con)

    def __getattr__(self, name: str):
        # First check macros
        if not name.startswith("_") and hasattr(self._tools, '_macros') and name in self._tools._macros:
            return getattr(self._tools, name)
        # Then delegate to underlying DuckDB connection
        return getattr(self._con, name)

    def __dir__(self):
        duckdb_attrs = set(dir(self._con))
        macro_names = set(self._tools._macros) if hasattr(self._tools, '_macros') else set()
        return sorted(duckdb_attrs | macro_names | {"_con", "_tools"})
