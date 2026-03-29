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

import inspect
import os
from typing import Optional

import fledgling
from fledgling.connection import Connection
from fledgling.pro.defaults import (
    ProjectDefaults, apply_defaults, infer_defaults, load_config,
)
from fledgling.pro.formatting import (
    _format_markdown_table,
    _truncate_rows,
    _HEAD_TAIL,
    _HINTS,
    _MAX_LINES,
    _MAX_ROWS,
)
from fledgling.pro.prompts import register_prompts
from fledgling.pro.workflows import register_workflows


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

# Params that should be coerced from string to int.
# MCP sends all values as strings; only these are genuinely numeric.
_NUMERIC_PARAMS = {
    "n", "max_lvl", "ctx", "center_line", "lim", "start_line", "end_line",
    "context_lines", "limit",
}

# Parameters that indicate the user narrowed their query — skip truncation.
_RANGE_PARAMS = {
    "read_source": {"lines", "match"},
    "find_definitions": {"name_pattern"},
    "find_in_ast": {"name"},
    "doc_outline": {"search"},
}


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

    # Infer smart defaults, merge with config file overrides
    project_root = root or os.getcwd()
    overrides = load_config(project_root)
    defaults = infer_defaults(con, overrides=overrides, root=project_root)
    mcp._defaults = defaults

    # Register each macro as an MCP tool
    for macro_info in con._tools.list():
        macro_name = macro_info["name"]
        params = macro_info["params"]

        if macro_name in _SKIP:
            continue

        _register_tool(mcp, con, macro_name, params, defaults)

    # ── MCP Resources ───────────────────────────────────────────────
    # Static/slow-changing context available without tool calls.

    @mcp.resource("fledgling://project",
                  name="project",
                  description="Project overview — languages, file counts, directory structure.")
    def project_resource() -> str:
        sections = []

        overview = con.project_overview()
        sections.append("## Languages\n")
        sections.append(_format_markdown_table(overview.columns, overview.fetchall()))

        top_level = con.list_files("*")
        sections.append("\n## Top-Level Files\n")
        sections.append(_format_markdown_table(top_level.columns, top_level.fetchall()))

        return "\n".join(sections)

    @mcp.resource("fledgling://diagnostics",
                  name="diagnostics",
                  description="Fledgling version, profile, loaded modules, extensions.")
    def diagnostics_resource() -> str:
        diag = con.dr_fledgling()
        return _format_markdown_table(diag.columns, diag.fetchall())

    @mcp.resource("fledgling://docs",
                  name="docs",
                  description="Documentation outline — all markdown files with section headings.")
    def docs_resource() -> str:
        outline = con.doc_outline("**/*.md")
        return _format_markdown_table(outline.columns, outline.fetchall())

    @mcp.resource("fledgling://git",
                  name="git",
                  description="Current branch, recent commits, and working tree status.")
    def git_resource() -> str:
        sections = []

        branches = con.branch_list()
        sections.append("## Branches\n")
        sections.append(_format_markdown_table(branches.columns, branches.fetchall()))

        commits = con.recent_changes(5)
        sections.append("\n## Recent Commits\n")
        sections.append(_format_markdown_table(commits.columns, commits.fetchall()))

        status = con.working_tree_status()
        status_cols = status.columns
        status_rows = status.fetchall()
        sections.append("\n## Working Tree Status\n")
        if status_rows:
            sections.append(_format_markdown_table(status_cols, status_rows))
        else:
            sections.append("Clean working tree.")

        return "\n".join(sections)

    # Register compound workflow tools
    register_workflows(mcp, con, defaults)

    # Register MCP prompt templates
    register_prompts(mcp, con, defaults)

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
        # Apply smart defaults for None params
        kwargs = apply_defaults(defaults, macro_name, kwargs)

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

        # Remove None values; coerce known numeric params to int.
        # Only _NUMERIC_PARAMS are coerced — blanket isdigit() would
        # break git SHAs like "1234567".
        filtered = {}
        for k, v in kwargs.items():
            if v is None:
                continue
            if k in _NUMERIC_PARAMS and isinstance(v, str) and v.isdigit():
                filtered[k] = int(v)
            else:
                filtered[k] = v

        macro = getattr(con, macro_name)
        try:
            rel = macro(**filtered)
            cols = rel.columns
            rows = rel.fetchall()
        except Exception as e:
            # DuckDB raises IOException (sitting_duck) or
            # InvalidInputException (markdown) for globs matching
            # zero files. Treat as empty results.
            etype = type(e).__name__
            if etype in ("IOException", "InvalidInputException"):
                return "(no results)"
            raise
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
    annotations = {}
    for p in params:
        annotations[p] = Optional[str]
    if limit_param:
        annotations[limit_param] = Optional[int]
    tool_fn.__annotations__ = {**annotations, "return": str}

    # Create proper signature with Optional[str] defaults
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
