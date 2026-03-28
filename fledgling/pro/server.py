"""Fledgling Pro: FastMCP server wrapping fledgling's SQL macros.

Auto-generates MCP tools from every fledgling table macro. Each tool
accepts the macro's parameters and returns results as formatted text.

Usage::

    # As a module
    python -m fledgling.pro.server

    # Programmatic
    from fledgling.pro.server import create_server
    mcp = create_server()
    mcp.run()

    # With custom config
    mcp = create_server(root="/path/to/project", modules=["source", "code"])
    mcp.run()
"""

from __future__ import annotations

import os
from typing import Optional

import fledgling
from fledgling.connection import Connection


# ── Tool descriptions for known macros ───────────────────────────────
# Override auto-generated descriptions for key tools.

_DESCRIPTIONS = {
    "find_definitions": "Find function, class, and module definitions by AST analysis. Use name_pattern with SQL LIKE wildcards (%).",
    "find_in_ast": "Search code by semantic category: calls, imports, definitions, loops, conditionals, strings, comments.",
    "code_structure": "Structural overview with complexity metrics. Good first step for unfamiliar code.",
    "list_files": "Find files by glob pattern.",
    "read_source": "Read file lines with optional range, context, and match filtering.",
    "read_context": "Read lines centered around a specific line number.",
    "project_overview": "File counts by language for the project.",
    "doc_outline": "Markdown section outlines with optional keyword/regex search.",
    "read_doc_section": "Read a specific markdown section by ID.",
    "recent_changes": "Git commit history.",
    "file_changes": "Files changed between two git revisions.",
    "file_diff": "Line-level unified diff between revisions.",
    "file_at_version": "File content at a specific git revision.",
    "branch_list": "List git branches.",
    "tag_list": "List git tags.",
    "working_tree_status": "Untracked and modified files.",
    "structural_diff": "Semantic diff: added/removed/modified definitions between revisions.",
    "changed_function_summary": "Changed functions ranked by complexity between revisions.",
    "complexity_hotspots": "Most complex functions in the codebase.",
    "sessions": "Claude Code conversation sessions.",
    "messages": "Flattened conversation messages.",
    "tool_calls": "Tool usage from conversations.",
    "search_messages": "Full-text search across conversation content.",
    "help": "Fledgling skill guide. No args for outline, section ID for details.",
    "dr_fledgling": "Runtime diagnostics: version, profile, modules, extensions.",
}

# Macros to skip (internal, too low-level, or require table references)
_SKIP = {
    # sitting_duck ast_* macros (take table references, not file paths)
    "ast_ancestors", "ast_call_arguments", "ast_children", "ast_class_members",
    "ast_containing_line", "ast_dead_code", "ast_definitions", "ast_descendants",
    "ast_function_metrics", "ast_function_scope", "ast_functions_containing",
    "ast_in_range", "ast_match", "ast_nesting_analysis", "ast_pattern",
    "ast_security_audit", "ast_siblings", "ast_definition_parent",
    # Other extension macros
    "duckdb_logs_parsed", "duckdb_profiling_settings",
    "histogram", "histogram_values",
    # Fledgling internal/low-level
    "load_conversations",
    "read_source_batch",  # read_source covers this
    "file_line_count",    # project_overview is better
    "content_blocks",     # too low-level
    "tool_results",       # too low-level
    "token_usage",        # too low-level
    "tool_frequency",     # ChatToolUsage covers this
    "bash_commands",      # too low-level
    "session_summary",    # ChatDetail covers this
    "model_usage",        # too low-level
    "search_tool_inputs", # too low-level
    "find_calls",         # find_in_ast covers this
    "find_imports",       # find_in_ast covers this
    "find_code_examples", # niche
    "doc_stats",          # niche
    "repo_files",         # list_files covers this
    "module_dependencies", # niche
    "function_callers",   # niche
}

# Output format hints — which macros return content vs. structure
_TEXT_FORMAT = {
    "read_source", "read_context", "file_diff", "file_at_version",
    "find_in_ast", "read_doc_section", "help",
}

# ── Token-aware truncation ──────────────────────────────────────────
# Default row limits by tool.  0 = no limit.

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

# Parameters that indicate the user narrowed their query — skip truncation.
_RANGE_PARAMS = {
    "read_source": {"lines", "match"},
    "find_definitions": {"name_pattern"},
    "find_in_ast": {"name"},
    "doc_outline": {"search"},
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
    msg = f"--- omitted {omitted} of {total} rows ---"
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


def create_server(
    name: str = "fledgling",
    root: Optional[str] = None,
    init: Optional[str | bool] = None,
    modules: Optional[list[str]] = None,
    profile: str = "analyst",
) -> FastMCP:
    """Create a FastMCP server with fledgling tools.

    Args:
        name: Server name.
        root: Project root. Defaults to CWD.
        init: Init file path, False for sources, None for auto-discover.
        modules: SQL modules to load (when using sources).
        profile: Security profile.

    Returns:
        A FastMCP server instance ready to .run().
    """
    from fastmcp import FastMCP

    con = fledgling.connect(init=init, root=root, modules=modules, profile=profile)
    mcp = FastMCP(name)

    # Register each macro as an MCP tool
    for macro_info in con._tools.list():
        macro_name = macro_info["name"]
        params = macro_info["params"]

        if macro_name in _SKIP:
            continue

        _register_tool(mcp, con, macro_name, params)

    return mcp


def _register_tool(
    mcp: FastMCP,
    con: Connection,
    macro_name: str,
    params: list[str],
):
    """Register a single macro as an MCP tool."""
    description = _DESCRIPTIONS.get(
        macro_name,
        f"Query: {macro_name}({', '.join(params)})"
    )
    is_text = macro_name in _TEXT_FORMAT

    # Determine truncation config for this macro
    if macro_name in _MAX_LINES:
        limit_param = "max_lines"
        default_limit = _MAX_LINES[macro_name]
    elif macro_name in _MAX_ROWS:
        limit_param = "max_results"
        default_limit = _MAX_ROWS[macro_name]
    else:
        limit_param = None
        default_limit = 0

    range_params = _RANGE_PARAMS.get(macro_name, set())

    # Build the tool function dynamically
    # FastMCP uses the function signature for parameter schema
    async def tool_fn(**kwargs) -> str:
        # Extract truncation parameter before passing to SQL macro
        max_rows = default_limit
        if limit_param and limit_param in kwargs:
            val = kwargs.pop(limit_param)
            if val is not None:
                try:
                    max_rows = int(val)
                except (TypeError, ValueError):
                    pass  # keep default_limit

        # Skip truncation if user provided a range-narrowing parameter
        if range_params and any(kwargs.get(p) is not None for p in range_params):
            max_rows = 0

        # Remove None values (optional params not provided)
        filtered = {k: v for k, v in kwargs.items() if v is not None}
        # Convert string numbers to int where needed
        for k, v in filtered.items():
            if isinstance(v, str) and v.isdigit():
                filtered[k] = int(v)
        macro = getattr(con, macro_name)
        rel = macro(**filtered)

        cols = rel.columns
        rows = rel.fetchall()
        if not rows:
            return "(no results)"

        # Apply truncation
        omission = None
        if limit_param and max_rows > 0:
            rows, omission = _truncate_rows(rows, max_rows, macro_name)

        if is_text:
            # Plain text output
            if len(cols) == 1:
                lines = [str(r[0]) for r in rows]
            elif "line_number" in cols and "content" in cols:
                # Line-oriented: line_number + content → cat -n style
                ln_idx = cols.index("line_number")
                ct_idx = cols.index("content")
                lines = [f"{r[ln_idx]:4d}  {r[ct_idx]}" for r in rows]
            else:
                # Generic multi-column text
                lines = []
                for row in rows:
                    parts = [str(v) for v in row if v is not None]
                    lines.append("  ".join(parts))
            if omission:
                lines.insert(_HEAD_TAIL, omission)
            return "\n".join(lines)
        else:
            # Markdown table
            result = _format_markdown_table(cols, rows)
            if omission:
                # Insert omission after header (2 lines) + head rows
                md_lines = result.split("\n")
                insert_at = 2 + _HEAD_TAIL  # header + separator + head rows
                md_lines.insert(insert_at, omission)
                result = "\n".join(md_lines)
            return result

    # Set function metadata for FastMCP
    tool_fn.__name__ = macro_name
    tool_fn.__qualname__ = macro_name
    tool_fn.__doc__ = description

    # Build parameter annotations for FastMCP schema generation
    import typing
    annotations = {}
    for p in params:
        annotations[p] = Optional[str]
    if limit_param:
        annotations[limit_param] = Optional[int]
    tool_fn.__annotations__ = {**annotations, "return": str}

    # Create proper signature with Optional[str] defaults
    import inspect
    sig_params = [
        inspect.Parameter(
            p,
            inspect.Parameter.KEYWORD_ONLY,
            default=None,
            annotation=Optional[str],
        )
        for p in params
    ]
    if limit_param:
        sig_params.append(inspect.Parameter(
            limit_param,
            inspect.Parameter.KEYWORD_ONLY,
            default=None,
            annotation=Optional[int],
        ))
    tool_fn.__signature__ = inspect.Signature(
        sig_params,
        return_annotation=str,
    )

    mcp.add_tool(tool_fn)


# ── Entry point ──────────────────────────────────────────────────────

def main():
    """Run the fledgling MCP server."""
    mcp = create_server()
    mcp.run()


if __name__ == "__main__":
    main()
