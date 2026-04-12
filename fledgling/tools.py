"""Python function wrappers for fledgling SQL macros.

Uses DuckDB's relational API (table_function, Relation chaining)
instead of SQL string building. Each macro becomes a callable that
returns a DuckDBPyRelation — composable, lazy, and type-safe.

Discovery strategy:

    1. **MCP publication registry (preferred)** — when duckdb_mcp exposes
       the no-arg `mcp_list_tools()` table function (present in b1eb63d+),
       query it for the curated user-facing surface. This gives wrappers
       rich metadata: description, parameter JSON schemas, required params,
       output format, and the intentional list of "user tools" chosen by
       tool publications. Internal helper macros (anything not published)
       do not become wrappers.

    2. **Catalog scan (fallback)** — when the registry is unavailable
       (older duckdb_mcp, duckdb_mcp not loaded, zero publications),
       fall back to scanning `duckdb_functions()` for table_macros in
       the main schema with no leading underscore. Every table macro
       becomes a wrapper. No descriptions or MCP metadata.

The fallback keeps the Python API usable in any environment; the curated
path lights up automatically when the environment supports it.

Usage::

    import fledgling

    # Via connection wrapper
    con = fledgling.connect()
    con.find_definitions("**/*.py").show()
    con.recent_changes(5).limit(3).df()

    # Iterate over available tools
    for tool in con._tools:
        print(f"{tool.macro_name}: {tool.description}")
        if tool.required:
            print(f"  required: {tool.required}")

    # Module-level for quick scripting
    from fledgling.tools import find_definitions, recent_changes
    find_definitions("**/*.py").show()
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional

import duckdb


# Regex: extract the first `FROM macro_name(...)` occurrence in a tool's
# sql_template. Used to map MCP tool publications back to their underlying
# table macro. Tolerates leading whitespace and multi-line templates.
_MACRO_NAME_RE = re.compile(r"\bFROM\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", re.IGNORECASE)


@dataclass
class ToolInfo:
    """Metadata about a fledgling SQL macro, optionally enriched with MCP
    tool publication data.

    Always populated (from duckdb_functions catalog):
        macro_name, params

    Populated when the MCP publication registry is available:
        tool_name, description, sql_template, parameters_schema, required, format
    """

    # Always available
    macro_name: str
    params: list[str] = field(default_factory=list)

    # MCP publication metadata (None when discovered via catalog fallback)
    tool_name: Optional[str] = None
    description: Optional[str] = None
    sql_template: Optional[str] = None
    parameters_schema: Optional[dict[str, Any]] = None
    required: Optional[list[str]] = None
    format: Optional[str] = None


class Tools:
    """Python wrappers for fledgling SQL macros.

    Auto-discovers table macros from the DuckDB connection and creates
    callable attributes for each one. Each call returns a DuckDBPyRelation
    that can be further chained (.filter, .limit, .order, .df, .show, etc).

    Iterable: ``for tool in tools`` yields :class:`ToolInfo` objects.
    Sized: ``len(tools)`` returns the number of available macros.
    """

    def __init__(self, con: duckdb.DuckDBPyConnection):
        self._con = con
        self._macros: dict[str, list[str]] = {}
        self._tool_info: dict[str, ToolInfo] = {}
        self._source: str = "unknown"  # "mcp_registry" or "catalog"
        self._discover()

    # ── Discovery ────────────────────────────────────────────────────

    def _discover(self):
        """Populate `self._macros` and `self._tool_info` from the MCP
        registry, or catalog as fallback."""
        mcp_tools = self._try_mcp_registry()
        all_macros = self._read_all_table_macros()

        if mcp_tools:
            # Curated path: intersect MCP publications with the catalog.
            # Macro params come from the catalog (accurate SQL signature);
            # everything else comes from the MCP publication.
            self._macros = {
                name: params
                for name, params in all_macros.items()
                if name in mcp_tools
            }
            for name, params in self._macros.items():
                info = mcp_tools[name]
                info.params = params
                self._tool_info[name] = info
            self._source = "mcp_registry"
        else:
            # Fallback: expose all non-underscore table macros, no metadata.
            self._macros = {
                name: params
                for name, params in all_macros.items()
                if not name.startswith("_")
            }
            self._tool_info = {
                name: ToolInfo(macro_name=name, params=params)
                for name, params in self._macros.items()
            }
            self._source = "catalog"

    def _try_mcp_registry(self) -> Optional[dict[str, ToolInfo]]:
        """Query the MCP publication registry via `mcp_list_tools()`.

        Returns:
            dict mapping macro_name → ToolInfo (without params, which are
            filled in from the catalog later), or None if the registry
            is unavailable.
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

        # Query the full registry. Filter out built-in duckdb_mcp tools.
        try:
            rows = self._con.execute(
                """
                SELECT name, description, sql_template, parameters,
                       required, format
                FROM mcp_list_tools()
                WHERE NOT is_builtin
                """
            ).fetchall()
        except Exception:
            return None

        if not rows:
            return None

        result: dict[str, ToolInfo] = {}
        for tool_name, description, sql_template, params_json, required_json, fmt in rows:
            macro_name = _extract_macro_name(sql_template)
            if macro_name is None:
                continue
            if macro_name.startswith("_"):
                continue

            # Parse JSON strings into Python objects
            parameters_schema = _parse_json(params_json)
            required = _parse_json(required_json)
            if isinstance(required, str):
                # Sometimes the required field comes back as a raw string
                required = _parse_json(required)
            if not isinstance(required, list):
                required = None

            # First publication for a macro wins (rare for duplicates)
            if macro_name not in result:
                result[macro_name] = ToolInfo(
                    macro_name=macro_name,
                    tool_name=tool_name,
                    description=description,
                    sql_template=sql_template,
                    parameters_schema=parameters_schema if isinstance(parameters_schema, dict) else None,
                    required=required,
                    format=fmt,
                )

        return result if result else None

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
        if name in self._tool_info:
            info = self._tool_info[name]
            return _MacroCall(self._con, info)
        raise AttributeError(
            f"No macro '{name}'. Available: {', '.join(sorted(self._macros))}"
        )

    def __dir__(self):
        return sorted(set(super().__dir__()) | set(self._macros))

    def __iter__(self) -> Iterator[ToolInfo]:
        """Iterate over available tools, yielding ToolInfo objects."""
        return iter(
            self._tool_info[name]
            for name in sorted(self._tool_info)
        )

    def __len__(self) -> int:
        return len(self._macros)

    def list(self) -> list[ToolInfo]:
        """List all available tools with full metadata.

        Returns a list of :class:`ToolInfo` objects sorted by macro name.
        """
        return [self._tool_info[name] for name in sorted(self._tool_info)]

    def get(self, macro_name: str) -> Optional[ToolInfo]:
        """Get metadata for a specific macro by name, or None."""
        return self._tool_info.get(macro_name)


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


def _parse_json(value: Optional[str]) -> Any:
    """Parse a JSON string, returning None on failure."""
    if value is None:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


class _MacroCall:
    """Callable wrapper for a single SQL table macro.

    Returns a DuckDBPyRelation for composable query chaining.
    """

    def __init__(
        self,
        con: duckdb.DuckDBPyConnection,
        info: ToolInfo,
    ):
        self._con = con
        self._info = info
        self._name = info.macro_name
        self._params = info.params
        self.__name__ = info.macro_name
        if info.description:
            self.__doc__ = f"{info.description}\n\nCall {info.macro_name}({', '.join(info.params)}) → DuckDBPyRelation"
        else:
            self.__doc__ = f"Call {info.macro_name}({', '.join(info.params)}) → DuckDBPyRelation"

    @property
    def tool_info(self) -> ToolInfo:
        """The full ToolInfo metadata for this macro."""
        return self._info

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
