"""Fledgling DuckDB connection API.

The canonical way to get a fledgling-enabled DuckDB connection from Python.
Used by tests, fledgling-pro (FastMCP), and direct Python consumers.

Three configuration modes:
  1. From an installed .fledgling-init.sql (zero-config for installed projects)
  2. From explicit parameters (programmatic use)
  3. From SQL source files (development / package data)
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


def _load_from_sources(
    con: duckdb.DuckDBPyConnection,
    sql_dir: Path,
    root: str,
    profile: str,
    modules: list[str],
):
    """Load fledgling from SQL source files (dev mode / package data)."""
    # Extensions
    for ext in ["read_lines", "sitting_duck", "markdown", "duck_tails"]:
        con.execute(f"LOAD {ext}")

    # Variables (parameterized where possible)
    con.execute("SET VARIABLE session_root = ?", [root])
    con.execute("SET VARIABLE conversations_root = ?",
                [str(Path.home() / ".claude" / "projects")])
    from fledgling import __version__
    con.execute("SET VARIABLE fledgling_version = ?", [__version__])
    con.execute("SET VARIABLE fledgling_profile = ?", [profile])
    con.execute("SET VARIABLE fledgling_modules = ?", [modules])

    # Literal-backed macros (must be string literals for MCP context)
    con.execute(f"""CREATE OR REPLACE MACRO _resolve(p) AS
        CASE WHEN p IS NULL THEN NULL
             WHEN p[1] = '/' THEN p
             ELSE '{root}/' || p
        END""")
    con.execute(f"CREATE OR REPLACE MACRO _session_root() AS '{root}'")

    # Help path
    for help_candidate in [
        Path(root) / ".fledgling-help.md",
        sql_dir.parent / "SKILL.md",
    ]:
        if help_candidate.exists():
            con.execute("SET VARIABLE _help_path = ?", [str(help_candidate)])
            break

    # Load modules in order
    for module in modules:
        path = sql_dir / f"{module}.sql"
        if path.exists():
            _load_sql_file(con, path)


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


# ── Public API ───────────────────────────────────────────────────────


_DEFAULT_MODULES = [
    "sandbox", "dr_fledgling",
    "source", "code", "docs", "repo", "structural",
    "conversations", "help",
]


def connect(
    init: Optional[str | bool] = None,
    root: Optional[str] = None,
    profile: str = "analyst",
    modules: Optional[list[str]] = None,
    extensions: bool = True,
) -> duckdb.DuckDBPyConnection:
    """Create a DuckDB connection with fledgling macros loaded.

    Configuration priority:
      1. Explicit ``init`` path — execute that file directly
      2. Auto-discover .fledgling-init.sql in ``root`` (or CWD)
      3. Load from SQL source files (package data or repo)

    Examples::

        # Auto-discover (installed project)
        con = fledgling.connect()

        # Explicit init file
        con = fledgling.connect(init=".fledgling-init.sql")

        # Programmatic (no init file needed)
        con = fledgling.connect(root="/path/to/project", profile="core")

        # Minimal (specific modules only)
        con = fledgling.connect(modules=["source", "code"])

    Args:
        init: Path to a .fledgling-init.sql file, or False to skip init
            file discovery and load from SQL sources instead. None (default)
            auto-discovers .fledgling-init.sql in the project root.
        root: Project root for path resolution. Defaults to CWD.
        profile: Security profile ('analyst' or 'core'). Only used when
            loading from sources (not from init file).
        modules: SQL modules to load. None = all. Only used when loading
            from sources.
        extensions: Whether to load DuckDB extensions. Set False if
            extensions are already loaded (e.g., in tests).

    Returns:
        A DuckDB connection with all fledgling macros available.
    """
    root = root or os.getcwd()
    con = duckdb.connect(":memory:")

    # Mode 1: Explicit init file
    if init is not None and init is not False:
        _execute_init_file(con, init, root)
        return con

    # Mode 2: Auto-discover init file in project root (unless init=False)
    if init is not False:
        init_path = Path(root) / ".fledgling-init.sql"
        if init_path.exists():
            _execute_init_file(con, str(init_path), root)
            return con

    # Mode 3: Load from SQL sources
    sql_dir = _find_sql_dir()
    if sql_dir is None:
        raise FileNotFoundError(
            "No fledgling init file or SQL sources found. "
            "Run 'fledgling install' or 'pip install fledgling' first."
        )

    _load_from_sources(
        con, sql_dir, root, profile,
        modules if modules is not None else _DEFAULT_MODULES,
    )
    return con
