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

from fastmcp import FastMCP

import fledgling
from fledgling.connection import Connection
from fledgling.pro.defaults import (
    ProjectDefaults, apply_defaults, infer_defaults, load_config,
)


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
    "read_source", "read_context", "file_diff", "find_in_ast",
    "read_doc_section", "help",
}


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
    con = fledgling.connect(init=init, root=root, modules=modules, profile=profile)
    mcp = FastMCP(name)

    # Infer smart defaults, merge with config file overrides
    project_root = root or os.getcwd()
    overrides = load_config(project_root)
    defaults = infer_defaults(con, overrides=overrides)
    mcp._defaults = defaults

    # Register each macro as an MCP tool
    for macro_info in con._tools.list():
        macro_name = macro_info["name"]
        params = macro_info["params"]

        if macro_name in _SKIP:
            continue

        _register_tool(mcp, con, macro_name, params, defaults)

    return mcp


def _register_tool(
    mcp: FastMCP,
    con: Connection,
    macro_name: str,
    params: list[str],
    defaults: ProjectDefaults,
):
    """Register a single macro as an MCP tool."""
    description = _DESCRIPTIONS.get(
        macro_name,
        f"Query: {macro_name}({', '.join(params)})"
    )
    is_text = macro_name in _TEXT_FORMAT

    # Build the tool function dynamically
    # FastMCP uses the function signature for parameter schema
    async def tool_fn(**kwargs) -> str:
        # Apply smart defaults for None params
        kwargs = apply_defaults(defaults, macro_name, kwargs)
        # Remove remaining None values (optional params not provided)
        filtered = {k: v for k, v in kwargs.items() if v is not None}
        # Convert string numbers to int where needed
        for k, v in filtered.items():
            if isinstance(v, str) and v.isdigit():
                filtered[k] = int(v)
        macro = getattr(con, macro_name)
        try:
            rel = macro(**filtered)
            rows = rel.fetchall()
        except Exception as e:
            # DuckDB raises IO errors for globs matching zero files,
            # invalid paths, etc. — treat as empty results.
            err = str(e).lower()
            if "no file" in err or "does not exist" in err or "read_ast" in err:
                return "(no results)"
            raise
        if not rows:
            return "(no results)"

        cols = rel.columns
        if is_text:
            # Plain text output
            if len(cols) == 1:
                return "\n".join(str(r[0]) for r in rows)
            # Line-oriented: line_number + content → cat -n style
            if "line_number" in cols and "content" in cols:
                ln_idx = cols.index("line_number")
                ct_idx = cols.index("content")
                return "\n".join(
                    f"{r[ln_idx]:4d}  {r[ct_idx]}" for r in rows
                )
            # Generic multi-column text
            lines = []
            for row in rows:
                parts = [str(v) for v in row if v is not None]
                lines.append("  ".join(parts))
            return "\n".join(lines)
        else:
            # Markdown table
            return _format_markdown_table(cols, rows)

    # Set function metadata for FastMCP
    tool_fn.__name__ = macro_name
    tool_fn.__qualname__ = macro_name
    tool_fn.__doc__ = description

    # Build parameter annotations for FastMCP schema generation
    import typing
    annotations = {}
    for p in params:
        annotations[p] = Optional[str]
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
