"""Fledgling Pro: Compound workflow tools.

Orchestrate multiple fledgling SQL macros in a single call, returning
formatted markdown briefings. Supplements individual tools — shortcuts
for common multi-step patterns.
"""

from __future__ import annotations

import inspect
import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from fledgling.connection import Connection
    from fledgling.pro.defaults import ProjectDefaults

log = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────


def _format_briefing(title: str, sections: list[tuple[str, str]]) -> str:
    """Join (heading, content) pairs into a markdown briefing."""
    parts = [f"## {title}\n"]
    for heading, content in sections:
        parts.append(f"### {heading}\n{content}\n")
    return "\n".join(parts)


def _section(heading: str, fn):
    """Run fn() with error handling, return (heading, content) tuple.

    Returns "(no data)" for empty/None results,
    "(could not load)" on exceptions.
    """
    try:
        content = fn()
        if not content:
            return (heading, "(no data)")
        return (heading, content)
    except Exception:
        log.debug("section %s failed", heading, exc_info=True)
        return (heading, "(could not load)")


def _has_module(con, module_name: str) -> bool:
    """Check if a SQL module is loaded in the connection."""
    try:
        modules = con.execute(
            "SELECT getvariable('fledgling_modules')"
        ).fetchone()[0]
        return module_name in (modules or [])
    except Exception:
        return False


def _table(con, macro_name, kwargs, max_rows=0):
    """Call a macro and format as a markdown table with optional truncation."""
    from fledgling.pro.server import _format_markdown_table, _truncate_rows
    rel = getattr(con, macro_name)(**kwargs)
    cols = rel.columns
    rows = rel.fetchall()
    if not rows:
        return ""
    if max_rows > 0:
        rows, omission = _truncate_rows(rows, max_rows, macro_name)
        result = _format_markdown_table(cols, rows)
        if omission:
            result += "\n" + omission
        return result
    return _format_markdown_table(cols, rows)


def _sorted_table(con, macro_name, kwargs, col_index, max_rows, descending=True):
    """Call a macro, sort by column, truncate, and format as markdown table."""
    from fledgling.pro.server import _format_markdown_table
    rel = getattr(con, macro_name)(**kwargs)
    cols = rel.columns
    rows = rel.fetchall()
    if not rows:
        return ""
    rows.sort(key=lambda r: r[col_index] or 0, reverse=descending)
    if max_rows > 0:
        rows = rows[:max_rows]
    return _format_markdown_table(cols, rows)


# ── Compound tools ─────────────────────────────────────────────────


def explore(con, defaults, path=None):
    """First-contact codebase briefing."""
    sections = []

    sections.append(_section("Languages", lambda: _table(
        con, "project_overview", {},
    )))

    sections.append(_section("Key Definitions (top 20 by complexity)", lambda: _sorted_table(
        con, "code_structure",
        {"file_pattern": defaults.code_pattern},
        col_index=8,  # cyclomatic_complexity
        max_rows=20,
    )))

    sections.append(_section("Documentation", lambda: _table(
        con, "doc_outline",
        {"file_pattern": defaults.doc_pattern},
        max_rows=15,
    )))

    sections.append(_section("Recent Activity", lambda: _table(
        con, "recent_changes", {"n": 5},
    )))

    return _format_briefing("Explore", sections)


def investigate(con, defaults, name, file_pattern=None):
    """Deep dive on a specific function or symbol."""
    from fledgling.pro.server import _format_markdown_table
    file_pattern = file_pattern or defaults.code_pattern

    # 1. Find definitions matching the name
    try:
        rel = con.find_definitions(
            file_pattern=file_pattern, name_pattern=f"%{name}%",
        )
        defs = rel.fetchall()
        def_cols = rel.columns
    except Exception:
        defs = []
        def_cols = []

    if not defs:
        return f"No definition found for '{name}'. Try a broader pattern or check spelling."

    sections = []

    # Definition table
    sections.append(("Definition", _format_markdown_table(def_cols, defs[:10])))

    # 2. Read source of first definition
    first = defs[0]
    # find_definitions columns: file_path, name, kind, start_line, end_line, signature
    fp_idx = def_cols.index("file_path")
    sl_idx = def_cols.index("start_line")
    el_idx = def_cols.index("end_line")
    def_file = first[fp_idx]
    start_line = first[sl_idx]
    end_line = first[el_idx]

    def _source():
        rel = con.read_source(
            file_path=def_file,
            lines=f"{start_line}-{end_line}",
        )
        rows = rel.fetchall()
        if not rows:
            return ""
        cols = rel.columns
        ln_idx = cols.index("line_number")
        ct_idx = cols.index("content")
        lines = [f"{r[ln_idx]:4d}  {r[ct_idx]}" for r in rows[:50]]
        return "\n".join(lines)

    sections.append(_section("Source", _source))

    # 3. Who calls this function
    sections.append(_section("Called by", lambda: _table(
        con, "function_callers",
        {"file_pattern": file_pattern, "func_name": name},
        max_rows=15,
    )))

    # 4. What this function calls (find_in_ast filtered to function's line range)
    def _calls():
        rel = con.find_in_ast(
            file_pattern=file_pattern, kind="calls",
        )
        rows = rel.fetchall()
        if not rows:
            return ""
        cols = rel.columns
        fp_i = cols.index("file_path")
        sl_i = cols.index("start_line")
        # Filter to lines within the function's range and file
        filtered = [
            r for r in rows
            if r[fp_i] == def_file
            and start_line <= r[sl_i] <= end_line
        ]
        if not filtered:
            return ""
        return _format_markdown_table(cols, filtered[:10])

    sections.append(_section("Calls", _calls))

    return _format_briefing(f"Investigating: {name}", sections)


def review(con, defaults, from_rev=None, to_rev=None, file_pattern=None):
    """Code review prep for a revision range."""
    from fledgling.pro.server import _format_markdown_table
    from_rev = from_rev or defaults.from_rev
    to_rev = to_rev or defaults.to_rev
    file_pattern = file_pattern or defaults.code_pattern

    sections = []

    # 1. Changed files
    # Also capture rows for diff section
    change_rows = []

    def _changes():
        nonlocal change_rows
        rel = con.file_changes(from_rev=from_rev, to_rev=to_rev)
        cols = rel.columns
        rows = rel.fetchall()
        change_rows = rows
        if not rows:
            return ""
        from fledgling.pro.server import _truncate_rows
        rows_display, omission = _truncate_rows(rows, 25, "file_changes")
        result = _format_markdown_table(cols, rows_display)
        if omission:
            result += "\n" + omission
        return result

    sections.append(_section("Changed Files", _changes))

    # 2. Changed functions by complexity
    sections.append(_section("Changed Functions", lambda: _table(
        con, "changed_function_summary",
        {"from_rev": from_rev, "to_rev": to_rev, "file_pattern": file_pattern},
        max_rows=20,
    )))

    # 3. Diffs for top 3 most-changed files
    def _diffs():
        if not change_rows:
            return ""
        # Sort by size delta, skip deleted files (new_size is None)
        # file_changes columns: file_path, status, old_size, new_size
        candidates = [
            r for r in change_rows if r[1] != "deleted"
        ]
        candidates.sort(
            key=lambda r: abs((r[3] or 0) - (r[2] or 0)),
            reverse=True,
        )
        top_files = [r[0] for r in candidates[:3]]

        parts = []
        for fp in top_files:
            try:
                rel = con.file_diff(
                    file=fp, from_rev=from_rev, to_rev=to_rev,
                )
                rows = rel.fetchall()
                if not rows:
                    continue
                cols = rel.columns
                # file_diff columns: seq, line_type, content
                ct_idx = cols.index("content")
                lt_idx = cols.index("line_type")
                lines = []
                for r in rows[:100]:
                    prefix = {"add": "+", "del": "-", "ctx": " "}.get(
                        r[lt_idx], " "
                    )
                    lines.append(f"{prefix} {r[ct_idx]}")
                if len(rows) > 100:
                    lines.append(f"--- omitted {len(rows) - 100} of {len(rows)} lines ---")
                parts.append(f"**{fp}**\n```\n" + "\n".join(lines) + "\n```")
            except Exception:
                log.debug("diff failed for %s", fp, exc_info=True)
                continue
        return "\n\n".join(parts) if parts else ""

    sections.append(_section("Diffs", _diffs))

    return _format_briefing(f"Review: {from_rev}..{to_rev}", sections)


def search(con, defaults, query, file_pattern=None):
    """Multi-source search across code, docs, and git."""
    file_pattern = file_pattern or defaults.code_pattern

    sections = []

    # 1. Definitions matching the query
    sections.append(_section("Definitions", lambda: _table(
        con, "find_definitions",
        {"file_pattern": file_pattern, "name_pattern": f"%{query}%"},
        max_rows=10,
    )))

    # 2. Call sites matching the query
    sections.append(_section("Call Sites", lambda: _table(
        con, "find_in_ast",
        {"file_pattern": file_pattern, "kind": "calls",
         "name_pattern": f"%{query}%"},
        max_rows=10,
    )))

    # 3. Documentation sections matching the query
    sections.append(_section("Documentation", lambda: _table(
        con, "doc_outline",
        {"file_pattern": defaults.doc_pattern, "search": query},
        max_rows=10,
    )))

    # 4. Conversation search (only if conversations module loaded)
    if _has_module(con, "conversations"):
        sections.append(_section("Conversations", lambda: _table(
            con, "search_messages",
            {"search_term": query},
            max_rows=10,
        )))

    return _format_briefing(f'Search: "{query}"', sections)


# ── Registration ───────────────────────────────────────────────────


def register_workflows(mcp, con, defaults):
    """Register compound workflow tools on the FastMCP server."""

    async def explore_tool(*, path: Optional[str] = None) -> str:
        return explore(con, defaults, path=path)

    explore_tool.__name__ = "explore"
    explore_tool.__qualname__ = "explore"
    explore_tool.__doc__ = "First-contact codebase briefing: languages, key definitions, docs, recent activity."
    explore_tool.__annotations__ = {"path": Optional[str], "return": str}
    explore_tool.__signature__ = inspect.Signature(
        [inspect.Parameter("path", inspect.Parameter.KEYWORD_ONLY,
                           default=None, annotation=Optional[str])],
        return_annotation=str,
    )
    mcp.add_tool(explore_tool)

    async def investigate_tool(
        *, name: str, file_pattern: Optional[str] = None,
    ) -> str:
        return investigate(con, defaults, name=name, file_pattern=file_pattern)

    investigate_tool.__name__ = "investigate"
    investigate_tool.__qualname__ = "investigate"
    investigate_tool.__doc__ = "Deep dive on a function or symbol: definition, source, callers, callees."
    investigate_tool.__annotations__ = {
        "name": str, "file_pattern": Optional[str], "return": str,
    }
    investigate_tool.__signature__ = inspect.Signature(
        [
            inspect.Parameter("name", inspect.Parameter.KEYWORD_ONLY,
                              annotation=str),
            inspect.Parameter("file_pattern", inspect.Parameter.KEYWORD_ONLY,
                              default=None, annotation=Optional[str]),
        ],
        return_annotation=str,
    )
    mcp.add_tool(investigate_tool)

    async def review_tool(
        *,
        from_rev: Optional[str] = None,
        to_rev: Optional[str] = None,
        file_pattern: Optional[str] = None,
    ) -> str:
        return review(con, defaults, from_rev=from_rev, to_rev=to_rev,
                       file_pattern=file_pattern)

    review_tool.__name__ = "review"
    review_tool.__qualname__ = "review"
    review_tool.__doc__ = "Code review prep: changed files, changed functions by complexity, diffs for top changed files."
    review_tool.__annotations__ = {
        "from_rev": Optional[str], "to_rev": Optional[str],
        "file_pattern": Optional[str], "return": str,
    }
    review_tool.__signature__ = inspect.Signature(
        [
            inspect.Parameter("from_rev", inspect.Parameter.KEYWORD_ONLY,
                              default=None, annotation=Optional[str]),
            inspect.Parameter("to_rev", inspect.Parameter.KEYWORD_ONLY,
                              default=None, annotation=Optional[str]),
            inspect.Parameter("file_pattern", inspect.Parameter.KEYWORD_ONLY,
                              default=None, annotation=Optional[str]),
        ],
        return_annotation=str,
    )
    mcp.add_tool(review_tool)

    async def search_tool(
        *, query: str, file_pattern: Optional[str] = None,
    ) -> str:
        return search(con, defaults, query=query, file_pattern=file_pattern)

    search_tool.__name__ = "search"
    search_tool.__qualname__ = "search"
    search_tool.__doc__ = "Multi-source search across definitions, call sites, documentation, and conversations."
    search_tool.__annotations__ = {
        "query": str, "file_pattern": Optional[str], "return": str,
    }
    search_tool.__signature__ = inspect.Signature(
        [
            inspect.Parameter("query", inspect.Parameter.KEYWORD_ONLY,
                              annotation=str),
            inspect.Parameter("file_pattern", inspect.Parameter.KEYWORD_ONLY,
                              default=None, annotation=Optional[str]),
        ],
        return_annotation=str,
    )
    mcp.add_tool(search_tool)
