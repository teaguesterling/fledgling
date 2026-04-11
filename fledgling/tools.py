"""Python function wrappers for fledgling SQL macros.

Uses DuckDB's relational API (table_function, Relation chaining)
instead of SQL string building. Each macro becomes a callable that
returns a DuckDBPyRelation — composable, lazy, and type-safe.

Discovery strategy:

    1. **MCP publication registry (preferred)** — when duckdb_mcp exposes
       the no-arg `mcp_list_tools()` table function (present in b1eb63d+),
       query it for the curated user-facing surface. This gives wrappers
       rich metadata: description for the docstring, plus the intentional
       list of "user tools" chosen by tool publications. Internal helper
       macros (anything not published) do not become wrappers.

    2. **Catalog scan (fallback)** — when the registry is unavailable
       (older duckdb_mcp, duckdb_mcp not loaded, zero publications),
       fall back to scanning `duckdb_functions()` for table_macros in
       the main schema with no leading underscore. Every table macro
       becomes a wrapper. No descriptions.

The fallback keeps the Python API usable in any environment; the curated
path lights up automatically when the environment supports it.

Usage::

    import fledgling

    # Via connection wrapper
    con = fledgling.connect()
    con.find_definitions("**/*.py").show()
    con.recent_changes(5).limit(3).df()

    # Module-level (lazy default connection)
    from fledgling.tools import find_definitions, recent_changes
    find_definitions("**/*.py").show()
    recent_changes(5).df()
"""

from __future__ import annotations

import re
from typing import Any, Optional

import duckdb


# Regex: extract the first `FROM macro_name(...)` occurrence in a tool's
# sql_template. Used to map MCP tool publications back to their underlying
# table macro. Tolerates leading whitespace and multi-line templates.
_MACRO_NAME_RE = re.compile(r"\bFROM\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", re.IGNORECASE)


class Tools:
    """Python wrappers for fledgling SQL macros.

    Auto-discovers table macros from the DuckDB connection and creates
    callable attributes for each one. Each call returns a DuckDBPyRelation
    that can be further chained (.filter, .limit, .order, .df, .show, etc).

    When duckdb_mcp's `mcp_list_tools()` no-arg table function is available
    and has user-published tools, discovery uses that as the curated surface
    and attaches tool descriptions to wrapper docstrings. Otherwise it falls
    back to scanning the full duckdb_functions() catalog.
    """

    def __init__(self, con: duckdb.DuckDBPyConnection):
        self._con = con
        self._macros: dict[str, list[str]] = {}
        self._descriptions: dict[str, str] = {}
        self._source: str = "unknown"  # "mcp_registry" or "catalog"
        self._discover()

    # ── Discovery ────────────────────────────────────────────────────

    def _discover(self):
        """Populate `self._macros` from the MCP registry, or catalog as fallback."""
        curated = self._try_mcp_registry()
        all_macros = self._read_all_table_macros()

        if curated:
            # Curated path: intersect the two sources. The macro list comes
            # from the catalog (so we get accurate parameter names from the
            # SQL signature); the filter comes from MCP publications (so we
            # only expose tools the user actually published).
            curated_names, descriptions = curated
            self._macros = {
                name: params
                for name, params in all_macros.items()
                if name in curated_names
            }
            self._descriptions = descriptions
            self._source = "mcp_registry"
        else:
            # Fallback: expose all non-underscore table macros, no descriptions.
            self._macros = {
                name: params
                for name, params in all_macros.items()
                if not name.startswith("_")
            }
            self._descriptions = {}
            self._source = "catalog"

    def _try_mcp_registry(self) -> Optional[tuple[set[str], dict[str, str]]]:
        """Query the MCP publication registry via `mcp_list_tools()`.

        Returns:
            (curated_macro_names, macro_name -> description) if the
            registry is available and has user publications, otherwise None.
        """
        # Feature-detect: does the no-arg mcp_list_tools() table function exist?
        try:
            row = self._con.execute(
                """
                SELECT 1
                FROM duckdb_functions()
                WHERE function_name = 'mcp_list_tools'
                  AND len(parameters) = 0
                LIMIT 1
                """
            ).fetchone()
        except Exception:
            return None
        if row is None:
            return None

        # Query the registry. Filter out built-in duckdb_mcp tools
        # (query, describe, list_tables) which aren't fledgling publications.
        try:
            rows = self._con.execute(
                """
                SELECT name, description, sql_template
                FROM mcp_list_tools()
                WHERE NOT is_builtin
                """
            ).fetchall()
        except Exception:
            return None

        if not rows:
            # Registry is there but no user publications — fall back to
            # catalog rather than strand the user with an empty API.
            return None

        curated: set[str] = set()
        descriptions: dict[str, str] = {}
        for tool_name, description, sql_template in rows:
            macro_name = _extract_macro_name(sql_template)
            if macro_name is None:
                continue
            if macro_name.startswith("_"):
                continue
            curated.add(macro_name)
            if description:
                # If two tools wrap the same macro (rare), the first description wins.
                descriptions.setdefault(macro_name, description)

        if not curated:
            return None
        return curated, descriptions

    def _read_all_table_macros(self) -> dict[str, list[str]]:
        """Read every table macro in the main schema (no filtering)."""
        rows = self._con.execute(
            """
            SELECT function_name, parameters
            FROM duckdb_functions()
            WHERE function_type = 'table_macro'
              AND schema_name = 'main'
            ORDER BY function_name
            """
        ).fetchall()
        return {name: params for name, params in rows}

    # ── Attribute access ─────────────────────────────────────────────

    def __getattr__(self, name: str) -> _MacroCall:
        if name.startswith("_"):
            raise AttributeError(name)
        if name in self._macros:
            return _MacroCall(
                self._con,
                name,
                self._macros[name],
                description=self._descriptions.get(name),
            )
        raise AttributeError(
            f"No macro '{name}'. Available: {', '.join(sorted(self._macros))}"
        )

    def __dir__(self):
        return sorted(set(super().__dir__()) | set(self._macros))

    def list(self) -> list[dict]:
        """List all available macros with their parameters and descriptions."""
        return [
            {
                "name": name,
                "params": params,
                "description": self._descriptions.get(name),
            }
            for name, params in sorted(self._macros.items())
        ]


def _extract_macro_name(sql_template: Optional[str]) -> Optional[str]:
    """Extract the underlying macro name from a tool's SQL template.

    Looks for the first `FROM macro_name(` occurrence. Returns None when
    the template has no matching pattern (e.g., a tool using a bare
    SELECT without a table function).
    """
    if not sql_template:
        return None
    match = _MACRO_NAME_RE.search(sql_template)
    return match.group(1) if match else None


class _MacroCall:
    """Callable wrapper for a single SQL table macro.

    Returns a DuckDBPyRelation for composable query chaining.
    """

    def __init__(
        self,
        con: duckdb.DuckDBPyConnection,
        name: str,
        params: list[str],
        description: Optional[str] = None,
    ):
        self._con = con
        self._name = name
        self._params = params
        self._description = description
        self.__name__ = name
        if description:
            self.__doc__ = f"{description}\n\nCall {name}({', '.join(params)}) → DuckDBPyRelation"
        else:
            self.__doc__ = f"Call {name}({', '.join(params)}) → DuckDBPyRelation"

    def __call__(self, *args, **kwargs) -> duckdb.DuckDBPyRelation:
        """Execute the macro and return a composable Relation.

        Positional args map to macro parameters in order.
        Keyword args become named parameters (key := value).

        Returns a DuckDBPyRelation that supports:
          .show()       — print results
          .df()         — pandas DataFrame
          .fetchall()   — list of tuples
          .filter(expr) — add WHERE clause
          .limit(n)     — restrict rows
          .order(expr)  — sort results
          .columns      — column names
          .shape        — (rows, cols) tuple
        """
        # Build SQL using parameterized approach
        # table_function() works for positional args but not named params,
        # so we use con.sql() with the args properly escaped
        sql_args = []
        for val in args:
            sql_args.append(_to_sql_literal(val))
        for key, val in kwargs.items():
            sql_args.append(f"{key} := {_to_sql_literal(val)}")

        sql = f"SELECT * FROM {self._name}({', '.join(sql_args)})"
        return self._con.sql(sql)

    def __repr__(self):
        return f"<fledgling.{self._name}({', '.join(self._params)})>"


def _to_sql_literal(val: Any) -> str:
    """Convert a Python value to a SQL literal."""
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        return str(val)
    if isinstance(val, str):
        escaped = val.replace("'", "''")
        return f"'{escaped}'"
    if isinstance(val, (list, tuple)):
        items = ", ".join(_to_sql_literal(v) for v in val)
        return f"[{items}]"
    return f"'{val}'"


# ── Module-level lazy API ────────────────────────────────────────────

_default_tools: Optional[Tools] = None


def _get_default_tools() -> Tools:
    global _default_tools
    if _default_tools is None:
        import fledgling
        con = fledgling.connect()
        _default_tools = con._tools
    return _default_tools


def __getattr__(name: str):
    """Module-level attribute access — lazily creates a default connection."""
    # Don't intercept class/internal lookups (prevents circular import)
    if name.startswith("_") or name[0].isupper():
        raise AttributeError(name)
    tools = _get_default_tools()
    if name in tools._macros:
        return getattr(tools, name)
    raise AttributeError(f"module 'fledgling.tools' has no attribute '{name}'")
