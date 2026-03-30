"""fledgling-edit: AST-aware code editing for fledgling."""

from fledgling.edit.region import CapturedNode, MatchRegion, Region
from fledgling.edit.ops import (
    EditOp, Remove, Replace, InsertBefore, InsertAfter, Wrap, Move,
)
from fledgling.edit.transforms import (
    remove, replace_body, insert_before, insert_after, wrap, move, rename_in,
)
from fledgling.edit.changeset import Changeset
from fledgling.edit.template import template_replace
from fledgling.edit.locate import locate, match, match_replace

__all__ = [
    "Region", "MatchRegion", "CapturedNode",
    "EditOp", "Remove", "Replace", "InsertBefore", "InsertAfter", "Wrap", "Move",
    "remove", "replace_body", "insert_before", "insert_after", "wrap", "move", "rename_in",
    "Changeset",
    "template_replace",
    "locate",
    "match",
    "match_replace",
]
