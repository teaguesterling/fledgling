"""Shared formatting and truncation helpers for fledgling-pro.

Used by both server.py (auto-registered tools) and workflows.py
(compound tools) without circular imports.
"""

from __future__ import annotations


# ── Truncation config ──────────────────────────────────────────────
# These dicts live here so _truncate_rows can reference them without
# importing server.py.

_MAX_LINES = {
    "read_source": 200,
    "read_context": 50,
    "file_diff": 300,
    "file_at_version": 200,
}

_MAX_ROWS = {
    "find_definitions": 50,
    "find_in_ast": 50,
    "list_files": 100,
    "doc_outline": 50,
    "file_changes": 25,
    "recent_changes": 20,
}

_HINTS = {
    "read_source": "Use lines='N-M' to see a range, or match='keyword' to filter.",
    "read_context": "Use a smaller context window or match='keyword' to filter.",
    "file_diff": "Use a narrower revision range.",
    "file_at_version": "Use lines='N-M' to see a range.",
    "find_definitions": "Use name_pattern='%keyword%' to narrow, or file_pattern to scope.",
    "find_in_ast": "Use name='keyword' to narrow results.",
    "list_files": "Use a more specific glob pattern.",
    "doc_outline": "Use search='keyword' to filter.",
    "file_changes": "Use a narrower revision range.",
    "recent_changes": "Use a smaller count.",
}

_HEAD_TAIL = 5  # rows to show at each end of truncated output


def _truncate_rows(rows, max_rows, macro_name):
    """Truncate rows to head + tail with an omission message.

    Returns (display_rows, omission_line) where omission_line is None
    if no truncation occurred.
    """
    total = len(rows)
    if max_rows <= 0 or total <= max_rows:
        return rows, None
    # Not enough rows for a clean head/tail split — return all
    if total <= 2 * _HEAD_TAIL:
        return rows, None
    head = rows[:_HEAD_TAIL]
    tail = rows[-_HEAD_TAIL:]
    omitted = total - 2 * _HEAD_TAIL
    hint = _HINTS.get(macro_name, "")
    unit = "lines" if macro_name in _MAX_LINES else "rows"
    msg = f"--- omitted {omitted} of {total} {unit} ---"
    if hint:
        msg += f"\n{hint}"
    return head + tail, msg


def _format_markdown_table(cols: list[str], rows: list[tuple]) -> str:
    """Format query results as a markdown table."""
    # Calculate column widths
    widths = [len(c) for c in cols]
    str_rows = []
    for row in rows:
        str_row = [str(v) if v is not None else "" for v in row]
        str_rows.append(str_row)
        for i, v in enumerate(str_row):
            widths[i] = max(widths[i], len(v))

    # Build table
    lines = []
    header = "| " + " | ".join(c.ljust(widths[i]) for i, c in enumerate(cols)) + " |"
    sep = "|-" + "-|-".join("-" * widths[i] for i in range(len(cols))) + "-|"
    lines.append(header)
    lines.append(sep)
    for str_row in str_rows:
        line = "| " + " | ".join(v.ljust(widths[i]) for i, v in enumerate(str_row)) + " |"
        lines.append(line)
    return "\n".join(lines)
