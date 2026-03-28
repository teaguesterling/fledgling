"""Python function wrappers for fledgling SQL macros.

Uses DuckDB's relational API (table_function, Relation chaining)
instead of SQL string building. Each macro becomes a callable that
returns a DuckDBPyRelation — composable, lazy, and type-safe.

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

from typing import Any, Optional

import duckdb


class Tools:
    """Python wrappers for fledgling SQL macros.

    Auto-discovers table macros from the DuckDB connection and creates
    callable attributes for each one. Each call returns a DuckDBPyRelation
    that can be further chained (.filter, .limit, .order, .df, .show, etc).
    """

    def __init__(self, con: duckdb.DuckDBPyConnection):
        self._con = con
        self._macros: dict[str, list[str]] = {}
        self._discover()

    def _discover(self):
        """Discover table macros from the connection."""
        rows = self._con.execute("""
            SELECT function_name, parameters
            FROM duckdb_functions()
            WHERE function_type = 'table_macro'
              AND schema_name = 'main'
              AND function_name NOT LIKE '\\_%%' ESCAPE '\\'
            ORDER BY function_name
        """).fetchall()
        for name, params in rows:
            self._macros[name] = params

    def __getattr__(self, name: str) -> _MacroCall:
        if name.startswith("_"):
            raise AttributeError(name)
        if name in self._macros:
            return _MacroCall(self._con, name, self._macros[name])
        raise AttributeError(
            f"No macro '{name}'. Available: {', '.join(sorted(self._macros))}"
        )

    def __dir__(self):
        return sorted(set(super().__dir__()) | set(self._macros))

    def list(self) -> list[dict]:
        """List all available macros with their parameters."""
        return [
            {"name": name, "params": params}
            for name, params in sorted(self._macros.items())
        ]


class _MacroCall:
    """Callable wrapper for a single SQL table macro.

    Returns a DuckDBPyRelation for composable query chaining.
    """

    def __init__(
        self,
        con: duckdb.DuckDBPyConnection,
        name: str,
        params: list[str],
    ):
        self._con = con
        self._name = name
        self._params = params
        self.__name__ = name
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
