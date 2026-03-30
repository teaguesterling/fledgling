"""fledgling-edit: AST-aware code editing for fledgling.

Usage::

    from fledgling.edit import Editor, Region, Changeset

    # Fluent builder
    ed = Editor(con)
    ed.definitions("**/*.py", "old_func").rename("new_func").diff()

    # Core primitives
    from fledgling.edit import locate, match, match_replace
    regions = locate(con, "**/*.py", name="my_func", kind="function")

    # Transforms
    from fledgling.edit import remove, replace_body, move
    cs = Changeset([remove(r) for r in regions])
    cs.diff()
"""

from fledgling.edit.region import CapturedNode, MatchRegion, Region
from fledgling.edit.ops import (
    EditOp, Remove, Replace, InsertBefore, InsertAfter, Wrap, Move,
)
from fledgling.edit.transforms import (
    remove, replace_body, insert_before, insert_after, wrap, move, rename_in,
)
from fledgling.edit.changeset import Changeset
from fledgling.edit.template import template_replace
from fledgling.edit.builder import Editor
from fledgling.edit.validate import validate_syntax

# Targeting bridge imports (require fledgling connection at call time)
from fledgling.edit.locate import locate, match, match_replace

__all__ = [
    # Data classes
    "Region", "MatchRegion", "CapturedNode",
    # Operations
    "EditOp", "Remove", "Replace", "InsertBefore", "InsertAfter", "Wrap", "Move",
    # Transforms
    "remove", "replace_body", "insert_before", "insert_after",
    "wrap", "move", "rename_in",
    # Coordination
    "Changeset",
    # Template
    "template_replace",
    # Validation
    "validate_syntax",
    # Builder
    "Editor",
    # Targeting
    "locate", "match", "match_replace",
]
