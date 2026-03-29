"""Smart project-aware defaults for fledgling-pro tools.

Infers sensible default patterns (code globs, doc paths, git revisions)
from the project at server startup. Users can override via
.fledgling-python/config.toml. Explicit tool parameters always win.
"""

from __future__ import annotations

import logging
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from fledgling.connection import Connection


@dataclass
class ProjectDefaults:
    """Inferred at server startup, cached for the session."""

    code_pattern: str = "**/*"
    doc_pattern: str = "**/*.md"
    main_branch: str = "main"
    from_rev: str = "HEAD~1"
    to_rev: str = "HEAD"
    languages: list[str] = field(default_factory=list)

    def scoped_code_pattern(self, path: str) -> str:
        """Scope the code pattern to a subdirectory path."""
        filename_glob = self.code_pattern.split("/")[-1]
        return f"{path}/**/{filename_glob}"


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
        return dict(kwargs)
    result = dict(kwargs)
    for param, field_name in mapping.items():
        if result.get(param) is None:
            result[param] = getattr(defaults, field_name)
    return result


def load_config(root: str | Path) -> dict[str, str]:
    """Read defaults overrides from .fledgling-python/config.toml.

    Returns the [defaults] section as a flat dict, or {} if the file
    doesn't exist or has no [defaults] section.
    """
    config_path = Path(root) / ".fledgling-python" / "config.toml"
    if not config_path.is_file():
        return {}
    with open(config_path, "rb") as f:
        data = tomllib.load(f)
    return dict(data.get("defaults", {}))


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


# ── Language detection ──────────────────────────────────────────────

# Language name (as returned by project_overview) → file extensions.
# Hardcoded for now; will be replaced by sitting_duck's extension listing
# when available.
LANGUAGE_EXTENSIONS: dict[str, list[str]] = {
    "Python": ["py", "pyi"],
    "JavaScript": ["js", "jsx", "mjs"],
    "TypeScript": ["ts", "tsx"],
    "Rust": ["rs"],
    "Go": ["go"],
    "Java": ["java"],
    "Ruby": ["rb"],
    "C": ["c"],
    "C++": ["cpp", "cc"],
    "C/C++": ["h", "hpp"],
    "SQL": ["sql"],
    "Shell": ["sh", "bash", "zsh"],
    "Kotlin": ["kt", "kts"],
    "Swift": ["swift"],
    "Dart": ["dart"],
    "PHP": ["php"],
    "Lua": ["lua"],
    "Zig": ["zig"],
    "R": ["r", "R"],
    "C#": ["cs"],
    "HCL": ["hcl", "tf"],
}

# Directories to check for docs, in priority order.
_DOC_DIRS = ["docs", "documentation", "doc", "wiki"]


def _code_glob(extensions: list[str]) -> str:
    """Build a glob pattern from a list of extensions.

    Uses only the primary (first) extension because DuckDB's glob()
    does not support brace expansion (e.g. ``**/*.{py,pyi}``).
    """
    return f"**/*.{extensions[0]}"


def _find_doc_dir(con: Connection) -> str | None:
    """Check for common doc directories using list_files."""
    for d in _DOC_DIRS:
        try:
            rows = con.list_files(f"{d}/*").fetchall()
            if rows:
                return d
        except Exception:
            log.debug("doc dir probe failed for %s", d, exc_info=True)
            continue
    return None


def _infer_main_branch(root: str | Path) -> str:
    """Detect the default branch from git remote HEAD."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "origin/HEAD"],
            capture_output=True, text=True, cwd=str(root), timeout=5,
        )
        if result.returncode == 0:
            # Output is "origin/main" or "origin/master" — strip prefix
            branch = result.stdout.strip().removeprefix("origin/")
            if branch:
                return branch
    except Exception:
        log.debug("git main branch detection failed", exc_info=True)
    return "main"


def infer_defaults(
    con: Connection,
    overrides: dict[str, str] | None = None,
    root: str | Path | None = None,
) -> ProjectDefaults:
    """Analyze the project and build smart defaults.

    Args:
        con: A fledgling Connection to the project.
        overrides: Values from config file that override inference.
        root: Project root for git operations. Defaults to cwd.

    Returns:
        ProjectDefaults with inferred + overridden values.
    """
    overrides = overrides or {}

    # ── Code pattern ────────────────────────────────────────────
    code_pattern = "**/*"
    languages: list[str] = []
    try:
        rows = con.project_overview().fetchall()
        # rows are (language, extension, file_count) ordered by count DESC
        if rows:
            # Group by language, sum file counts
            lang_counts: dict[str, int] = {}
            for lang, _ext, count in rows:
                lang_counts[lang] = lang_counts.get(lang, 0) + count
            languages = sorted(lang_counts.keys())
            # Find the top language that we have extension mappings for
            ranked = sorted(lang_counts, key=lang_counts.get, reverse=True)  # type: ignore[arg-type]
            for lang in ranked:
                if lang in LANGUAGE_EXTENSIONS:
                    code_pattern = _code_glob(LANGUAGE_EXTENSIONS[lang])
                    break
    except Exception:
        log.debug("project_overview inference failed", exc_info=True)

    # ── Doc pattern ─────────────────────────────────────────────
    doc_dir = _find_doc_dir(con)
    doc_pattern = f"{doc_dir}/**/*.md" if doc_dir else "**/*.md"

    # ── Main branch ─────────────────────────────────────────────
    main_branch = _infer_main_branch(root or ".")

    # ── Build defaults, apply overrides ─────────────────────────
    defaults = ProjectDefaults(
        code_pattern=code_pattern,
        doc_pattern=doc_pattern,
        main_branch=main_branch,
        languages=languages,
    )

    for key, value in overrides.items():
        if hasattr(defaults, key):
            setattr(defaults, key, value)

    return defaults
