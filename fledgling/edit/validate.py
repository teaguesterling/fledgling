"""AST validation for generated code output."""

from __future__ import annotations

from typing import Optional

import duckdb


def validate_syntax(
    content: str,
    language: str,
    con: duckdb.DuckDBPyConnection,
) -> bool:
    """Validate that content parses without errors via sitting_duck.

    Uses parse_ast() to parse in-memory content. Returns True if the
    content parses successfully, False if there are syntax errors.
    """
    if not content.strip():
        return True
    try:
        rows = con.execute(
            "SELECT COUNT(*) FROM parse_ast(?, ?) WHERE type = 'ERROR'",
            [content, language],
        ).fetchone()
        return rows is not None and rows[0] == 0
    except duckdb.Error:
        return False
