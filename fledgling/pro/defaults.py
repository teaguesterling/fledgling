"""Smart project-aware defaults for fledgling-pro tools.

Infers sensible default patterns (code globs, doc paths, git revisions)
from the project at server startup. Users can override via
.fledgling-python/config.toml. Explicit tool parameters always win.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProjectDefaults:
    """Inferred at server startup, cached for the session."""

    code_pattern: str = "**/*"
    doc_pattern: str = "**/*.md"
    main_branch: str = "main"
    from_rev: str = "HEAD~1"
    to_rev: str = "HEAD"
    languages: list[str] = field(default_factory=list)


def apply_defaults(
    defaults: ProjectDefaults,
    tool_name: str,
    kwargs: dict[str, object],
) -> dict[str, object]:
    """Substitute None params with smart defaults for a given tool.

    Returns a new dict — does not mutate the input.
    """
    mapping = TOOL_DEFAULTS.get(tool_name)
    if not mapping:
        return kwargs
    result = dict(kwargs)
    for param, field_name in mapping.items():
        if param in result and result[param] is None:
            result[param] = getattr(defaults, field_name)
    return result


# Tool name → {param_name: defaults_field_name}
TOOL_DEFAULTS: dict[str, dict[str, str]] = {
    "find_definitions":         {"file_pattern": "code_pattern"},
    "find_in_ast":              {"file_pattern": "code_pattern"},
    "code_structure":           {"file_pattern": "code_pattern"},
    "complexity_hotspots":      {"file_pattern": "code_pattern"},
    "changed_function_summary": {"file_pattern": "code_pattern"},
    "doc_outline":              {"file_pattern": "doc_pattern"},
    "file_changes":             {"from_rev": "from_rev", "to_rev": "to_rev"},
    "file_diff":                {"from_rev": "from_rev", "to_rev": "to_rev"},
    "structural_diff":          {"from_rev": "from_rev", "to_rev": "to_rev"},
}
