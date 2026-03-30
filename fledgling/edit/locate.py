"""Targeting bridge: locate() connects fledgling AST queries to Regions."""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

import duckdb

from fledgling.edit.region import Region


# Kinds that map to find_definitions with a predicate filter
_DEFINITION_KINDS = {"definition", "function", "class"}

# Kinds that map to find_in_ast
_AST_KINDS = {"import", "call", "loop", "conditional", "string", "comment"}

# Map kind -> find_in_ast kind parameter
_AST_KIND_MAP = {
    "import": "imports",
    "call": "calls",
    "loop": "loops",
    "conditional": "conditionals",
    "string": "strings",
    "comment": "comments",
}


def locate(
    con: duckdb.DuckDBPyConnection,
    file_pattern: str,
    name: Optional[str] = None,
    kind: Optional[str] = None,
    resolve: bool = True,
    columns: bool = False,
) -> list[Region]:
    """Name/kind-based targeting via fledgling SQL macros.

    Args:
        con: A fledgling-enabled DuckDB connection (with sitting_duck + macros loaded).
        file_pattern: File path or glob pattern for files.
        name: Name or SQL LIKE pattern to filter by.
        kind: What to find -- "definition", "function", "class", "import",
              "call", "loop", "conditional", "string", "comment".
        resolve: Whether to fill in content from the file.
        columns: Whether to request column positions (source='full').

    Returns:
        List of Region objects.
    """
    if kind and kind not in _DEFINITION_KINDS and kind not in _AST_KINDS:
        raise ValueError(
            f"Unknown kind: {kind!r}. Must be one of: "
            f"{sorted(_DEFINITION_KINDS | _AST_KINDS)}"
        )

    if kind in _DEFINITION_KINDS:
        return _locate_definitions(con, file_pattern, name, kind, resolve, columns)
    elif kind in _AST_KINDS:
        return _locate_ast(con, file_pattern, name, kind, resolve, columns)
    elif name:
        return _locate_definitions(con, file_pattern, name, "definition",
                                   resolve, columns)
    else:
        raise ValueError("Must provide kind and/or name")


def _locate_definitions(
    con, file_pattern, name, kind, resolve, columns,
) -> list[Region]:
    """Locate via find_definitions macro."""
    name_pattern = name or "%"

    rows = con.execute(
        "SELECT file_path, name, kind, start_line, end_line, signature "
        "FROM find_definitions(?, ?)",
        [file_pattern, name_pattern],
    ).fetchall()

    # find_definitions returns kind values like "DEFINITION_FUNCTION",
    # "DEFINITION_METHOD", "DEFINITION_CLASS", etc.
    if kind == "function":
        rows = [r for r in rows if "FUNCTION" in r[2].upper() or "METHOD" in r[2].upper()]
    elif kind == "class":
        rows = [r for r in rows if "CLASS" in r[2].upper()]

    regions = []
    for file_path, rname, rkind, start_line, end_line, sig in rows:
        normalized_kind = kind if kind != "definition" else _normalize_kind(rkind)
        r = Region(
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            name=rname,
            kind=normalized_kind,
        )
        if columns:
            r = _add_columns(con, r)
        if resolve:
            r = r.resolve()
        regions.append(r)
    return regions


def _normalize_kind(raw_kind: str) -> str:
    """Normalize SQL kind values to simple names."""
    raw = raw_kind.upper()
    if "FUNCTION" in raw or "METHOD" in raw:
        return "function"
    elif "CLASS" in raw:
        return "class"
    elif "MODULE" in raw:
        return "module"
    elif "VARIABLE" in raw:
        return "variable"
    return raw_kind.lower()


def _locate_ast(
    con, file_pattern, name, kind, resolve, columns,
) -> list[Region]:
    """Locate via find_in_ast macro."""
    ast_kind = _AST_KIND_MAP[kind]
    name_pattern = name or "%"

    rows = con.execute(
        "SELECT file_path, name, start_line, context "
        "FROM find_in_ast(?, ?, ?)",
        [file_pattern, ast_kind, name_pattern],
    ).fetchall()

    regions = []
    for file_path, rname, start_line, context in rows:
        r = Region(
            file_path=file_path,
            start_line=start_line,
            end_line=start_line,  # single-line approximation
            name=rname,
            kind=kind,
        )
        if columns:
            r = _add_columns(con, r)
        if resolve:
            r = r.resolve()
        regions.append(r)
    return regions


def _add_columns(con, region: Region) -> Region:
    """Re-query with source='full' to get column positions."""
    rows = con.execute(
        "SELECT start_column, end_column FROM read_ast(?, source := 'full') "
        "WHERE file_path = ? AND start_line = ? AND name = ? LIMIT 1",
        [region.file_path, region.file_path, region.start_line,
         region.name or ""],
    ).fetchall()
    if rows:
        return replace(region, start_column=rows[0][0], end_column=rows[0][1])
    return region
