"""Template substitution engine for match/replace operations.

Uses the same __NAME__ wildcard syntax as ast_match patterns.
Captures from the match are substituted by name. Wildcards use
UPPERCASE to distinguish from Python's __dunder__ methods.
"""

from __future__ import annotations

import re

from fledgling.edit.region import MatchRegion

# Match __UPPERCASE_NAME__ wildcards (sitting_duck convention).
# Must be all uppercase letters/digits/underscores between the double underscores.
# This avoids matching Python dunders like __init__ (which are lowercase).
_WILDCARD_RE = re.compile(r"__([A-Z][A-Z0-9_]*)__")


def template_replace(match_region: MatchRegion, template: str) -> str:
    """Substitute captures into a template string.

    __NAME__ in the template is replaced with the peek (source text)
    of the corresponding capture from the match. Names must be
    UPPERCASE (matching sitting_duck wildcard convention).

    Raises KeyError if a wildcard in the template has no matching capture.
    """
    if not template:
        return template

    captures = match_region.captures or {}

    def replacer(m: re.Match) -> str:
        name = m.group(1)
        if name not in captures:
            raise KeyError(
                f"Template wildcard __{name}__ has no matching capture. "
                f"Available captures: {sorted(captures.keys())}"
            )
        return captures[name].peek

    return _WILDCARD_RE.sub(replacer, template)
