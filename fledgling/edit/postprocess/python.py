"""Python-specific post-processor for indentation adjustment."""

from __future__ import annotations

import textwrap
from typing import Optional

from fledgling.edit.region import Region


class PythonPostProcessor:
    """Adjusts Python code indentation when moving between scopes."""

    def adjust_indentation(
        self, content: str, target_context: Optional[Region],
    ) -> str:
        """Adjust indentation to match the target context.

        Detects the current indentation of the content and the target
        indentation from the target context, then re-indents.
        """
        if not content.strip():
            return content

        # Detect current indent level (from first non-empty line)
        current_indent = _detect_indent(content)

        # Detect target indent level
        target_indent = _detect_target_indent(target_context)

        if current_indent == target_indent:
            return content

        # Dedent fully, then re-indent to target level
        dedented = textwrap.dedent(content)
        if target_indent == 0:
            return dedented

        indent_str = " " * target_indent
        lines = dedented.splitlines(keepends=True)
        result = []
        for line in lines:
            if line.strip():  # Non-empty line
                result.append(indent_str + line)
            else:
                result.append(line)  # Preserve blank lines as-is
        return "".join(result)


def _detect_indent(content: str) -> int:
    """Detect the indentation level of the first non-empty line."""
    for line in content.splitlines():
        stripped = line.lstrip()
        if stripped:
            return len(line) - len(stripped)
    return 0


def _detect_target_indent(target_context: Optional[Region]) -> int:
    """Detect target indentation from the context region."""
    if target_context is None:
        return 0

    # If the target has content, detect its indent level
    if target_context.content:
        return _detect_indent(target_context.content)

    # Default: top-level
    return 0
