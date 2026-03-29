"""Fledgling Pro: MCP prompt templates.

Parameterized workflow instructions with live project data pre-filled.
Each prompt calls the corresponding P4-004 workflow function to gather
context, then embeds it into condensed instructions derived from the
skill guides in skills/.

The agent uses prompts to learn *how* to approach a task; it uses
compound tools to get the *information* for the task.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fledgling.pro.workflows import explore, investigate, review

if TYPE_CHECKING:
    from fastmcp import FastMCP
    from fledgling.connection import Connection
    from fledgling.pro.defaults import ProjectDefaults

log = logging.getLogger(__name__)


# ── Templates ─────────────────────────────────────────────────────
# Condensed from skills/*.md — actionable steps with {briefing}
# placeholder for live data and tool suggestions pre-filled with
# the project's inferred patterns.

EXPLORE_TEMPLATE = """\
## Explore Codebase

You are exploring {scope}. Below is a pre-loaded briefing followed by \
a workflow for deeper exploration.

### Project Briefing

{briefing}

### Exploration Workflow

Work top-down through these phases:

**Phase 1: Landscape** (loaded above)
Review the Languages, Key Definitions, and Documentation sections. \
Note the dominant language and most complex definitions.

**Phase 2: Architecture**
- `CodeStructure('{code_pattern}')` — definitions per file, complexity
- `FindDefinitions('{code_pattern}')` — functions, classes, modules

**Phase 3: Dependencies**
- `FindInAST('{code_pattern}', 'imports')` — external dependencies
- `FindInAST('{code_pattern}', 'calls')` — internal call graph

**Phase 4: History**
- `recent_changes(20)` — commit history
- `GitDiffSummary(from_rev='HEAD~10', to_rev='HEAD')` — changed files
- `changed_function_summary('HEAD~10', 'HEAD', '{code_pattern}')` — semantic changes

**Phase 5: Deep Dive**
- `ReadLines(file_path='...', lines='42-60')` — specific range
- `MDSection(file_path='...', section_id='...')` — doc sections

### Anti-Patterns
- Use `ReadLines` with line ranges, not `cat` or `head`
- Use `FindDefinitions` then `ReadLines`, not `grep -r`
- Use `list_files` with globs, not `find . -name`
"""

INVESTIGATE_TEMPLATE = """\
## Investigate Issue

You are investigating: **{symptom}**

### Initial Findings

{briefing}

### Investigation Workflow

**Step 1: Locate** (findings above)
Review the definitions and source above. If not found, try:
- `FindDefinitions('{code_pattern}', '%{symptom}%')` — broader search
- `ReadLines(file_path='...', match='{symptom}')` — grep-like search

**Step 2: Understand the Code**
- `ReadLines(file_path='...', lines='42', ctx='10')` — context around a line
- `CodeStructure('...')` — file overview with complexity

**Step 3: Check History**
- `GitDiffSummary(from_rev='HEAD~20', to_rev='HEAD')` — what files changed
- `GitDiffFile(file='...', from_rev='HEAD~5', to_rev='HEAD')` — line-level diff
- `changed_function_summary('HEAD~10', 'HEAD', '{code_pattern}')` — complexity changes

**Step 4: Trace Dependencies**
- `FindInAST('...', 'imports')` — external dependencies
- `FindInAST('...', 'calls')` — function calls made

**Step 5: Check Related Code**
- `FindDefinitions('{code_pattern}', '%similar_name%')` — related functions
- `function_callers('{code_pattern}', 'func_name')` — callers

### Key Principles
- Locate before reading — find the right file and line first
- History is data — check what changed recently
- Compose queries — use the query tool for complex joins
"""

REVIEW_TEMPLATE = """\
## Review Changes

You are reviewing: **{rev_range}**

### Change Summary

{briefing}

### Review Checklist

**Step 1: File-Level Overview** (loaded above)
Review Changed Files. Prioritize largest changes; note new/deleted files.

**Step 2: Function-Level Analysis** (loaded above)
Review Changed Functions. Focus on:
- High-complexity new functions (need most scrutiny)
- Functions where complexity increased
- Deleted functions (check for orphaned callers)

**Step 3: Read Diffs** (top diffs loaded above)
For additional files:
- `GitDiffFile(file='...', from_rev='{from_rev}', to_rev='{to_rev}')`

**Step 4: Understand Context**
- `ReadLines(file_path='...', lines='42', ctx='15')` — surrounding code
- `CodeStructure('...')` — file structure

**Step 5: Check Impact**
- `function_callers('{code_pattern}', 'func_name')` — callers of changed functions
- `FindInAST('...', 'imports')` — dependency changes

**Step 6: Compare Versions**
- `GitShow(file='...', rev='{from_rev}')` — old implementation

### Review Quality Checks
- New functions without tests? Check `changed_function_summary` where change_status='added'
- Complexity increases above 5? Inspect those functions
- Large new files (>5000 bytes)? Consider splitting
"""


# ── Registration ──────────────────────────────────────────────────


def register_prompts(mcp: FastMCP, con: Connection, defaults: ProjectDefaults):
    """Register MCP prompt templates on the FastMCP server."""

    @mcp.prompt(
        name="explore",
        description="Exploration workflow with live project data: languages, "
                    "key definitions, docs, recent activity, and step-by-step "
                    "guidance for deeper exploration.",
    )
    def explore_prompt(path: str | None = None) -> str:
        scope = f"path: {path}" if path else "the full project"
        code_pattern = (
            f"{path}/**/{defaults.code_pattern.split('/')[-1]}"
            if path else defaults.code_pattern
        )
        try:
            briefing = explore(con, defaults, path=path)
        except Exception:
            log.debug("explore prompt: data gathering failed", exc_info=True)
            briefing = "(Project data could not be loaded. Use the tools below to gather context manually.)"

        return EXPLORE_TEMPLATE.format(
            scope=scope,
            briefing=briefing,
            code_pattern=code_pattern,
        )

    @mcp.prompt(
        name="investigate",
        description="Investigation workflow with pre-found definitions and "
                    "source code for a symptom (error message, function name, "
                    "or file path), plus step-by-step debugging guidance.",
    )
    def investigate_prompt(symptom: str) -> str:
        code_pattern = defaults.code_pattern
        try:
            briefing = investigate(con, defaults, name=symptom)
        except Exception:
            log.debug("investigate prompt: data gathering failed", exc_info=True)
            briefing = f"(Could not find data for '{symptom}'. Use the tools below to search manually.)"

        return INVESTIGATE_TEMPLATE.format(
            symptom=symptom,
            briefing=briefing,
            code_pattern=code_pattern,
        )

    @mcp.prompt(
        name="review",
        description="Code review checklist with pre-loaded change summary, "
                    "complexity deltas, and diffs, plus step-by-step review "
                    "guidance.",
    )
    def review_prompt(from_rev: str | None = None, to_rev: str | None = None) -> str:
        effective_from = from_rev or defaults.from_rev
        effective_to = to_rev or defaults.to_rev
        rev_range = f"{effective_from}..{effective_to}"
        code_pattern = defaults.code_pattern

        try:
            briefing = review(con, defaults, from_rev=from_rev, to_rev=to_rev)
        except Exception:
            log.debug("review prompt: data gathering failed", exc_info=True)
            briefing = "(Change data could not be loaded. Use the tools below to gather context manually.)"

        return REVIEW_TEMPLATE.format(
            rev_range=rev_range,
            briefing=briefing,
            from_rev=effective_from,
            to_rev=effective_to,
            code_pattern=code_pattern,
        )
