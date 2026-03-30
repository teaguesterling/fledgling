"""Targeting bridge: locate() connects fledgling AST queries to Regions."""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

import duckdb

from fledgling.edit.region import CapturedNode, MatchRegion, Region


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


def match(
    con: duckdb.DuckDBPyConnection,
    file_pattern: str,
    pattern: str,
    language: str,
    resolve: bool = True,
    columns: bool = False,
    match_by: str = "type",
    depth_fuzz: int = 0,
) -> list[MatchRegion]:
    """Pattern-based targeting via ast_match.

    Args:
        con: A fledgling-enabled DuckDB connection.
        file_pattern: Glob pattern for files.
        pattern: Code pattern with __NAME__ wildcards.
        language: Language for pattern parsing (e.g., "python").
        resolve: Whether to fill in content.
        columns: Whether to request column positions.
        match_by: Matching strategy -- "type" or "semantic_type".
        depth_fuzz: Allow +/- N levels of depth difference.

    Returns:
        List of MatchRegion objects with named captures.
    """
    # Create temp table with AST for the file pattern
    source_param = "'full'" if columns else "'lines'"
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE _edit_ast AS
        SELECT * FROM read_ast(?, source={source_param})
    """, [file_pattern])

    # Run ast_match
    rows = con.execute(
        "SELECT match_id, file_path, start_line, end_line, peek, captures "
        "FROM ast_match('_edit_ast', ?, ?, match_by := ?, depth_fuzz := ?)",
        [pattern, language, match_by, depth_fuzz],
    ).fetchall()

    regions = []
    for match_id, file_path, start_line, end_line, peek, captures_map in rows:
        # Parse captures map into CapturedNode objects
        captures = _parse_captures(captures_map)

        sc = None
        ec = None
        if columns:
            col_rows = con.execute(
                "SELECT start_column, end_column FROM _edit_ast "
                "WHERE file_path = ? AND start_line = ? LIMIT 1",
                [file_path, start_line],
            ).fetchall()
            if col_rows:
                sc, ec = col_rows[0]

        mr = MatchRegion(
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            start_column=sc,
            end_column=ec,
            name=peek,
            captures=captures,
        )
        if resolve:
            mr = mr.resolve()
        regions.append(mr)

    con.execute("DROP TABLE IF EXISTS _edit_ast")
    return regions


def _parse_captures(captures_map) -> dict[str, CapturedNode]:
    """Parse the DuckDB MAP type from ast_match into CapturedNode objects.

    The captures MAP from ast_match is MAP(VARCHAR, STRUCT[]).
    DuckDB's Python API returns this as a dict where keys are capture names
    and values are lists of structs (represented as dicts in Python).
    """
    captures = {}
    if not captures_map:
        return captures

    # DuckDB MAP comes back as dict in Python API
    if isinstance(captures_map, dict):
        items = captures_map.items()
    elif isinstance(captures_map, list):
        # Some DuckDB versions return MAP as list of key-value pairs
        items = captures_map
    else:
        return captures

    for cap_name, cap_data in items:
        # cap_data is typically a list of structs (one per captured node)
        if isinstance(cap_data, list) and cap_data:
            c = cap_data[0]
        elif isinstance(cap_data, dict):
            c = cap_data
        else:
            continue

        # Extract fields from the struct (dict in Python)
        if isinstance(c, dict):
            captures[cap_name] = CapturedNode(
                name=c.get("capture", cap_name),
                node_id=c.get("node_id", 0),
                type=c.get("type", ""),
                peek=c.get("peek", ""),
                start_line=c.get("start_line", 0),
                end_line=c.get("end_line", 0),
            )
        else:
            # Fallback: treat as opaque value
            captures[cap_name] = CapturedNode(
                name=cap_name,
                node_id=0,
                type="",
                peek=str(c),
                start_line=0,
                end_line=0,
            )
    return captures


def match_replace(
    con: duckdb.DuckDBPyConnection,
    file_pattern: str,
    pattern: str,
    template: str,
    language: str,
    **match_kwargs,
):
    """Match a pattern and substitute captures into a template.

    Returns a Changeset with Replace ops for each match.
    """
    from fledgling.edit.changeset import Changeset
    from fledgling.edit.ops import Remove, Replace
    from fledgling.edit.template import template_replace as _template_replace

    matches = match(con, file_pattern, pattern, language,
                    resolve=True, **match_kwargs)

    ops = []
    for mr in matches:
        if template == "":
            ops.append(Remove(region=mr))
        else:
            new_content = _template_replace(mr, template)
            ops.append(Replace(region=mr, new_content=new_content))

    return Changeset(ops)
