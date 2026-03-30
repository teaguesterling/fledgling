"""Fluent Editor API for composing AST-targeted edits."""

from __future__ import annotations

from typing import Optional

import duckdb

from fledgling.edit.changeset import Changeset
from fledgling.edit.locate import locate, match as _match, match_replace as _match_replace
from fledgling.edit.ops import Remove, Replace, Move
from fledgling.edit.region import Region
from fledgling.edit.transforms import (
    remove as _remove,
    replace_body as _replace_body,
    rename_in as _rename_in,
    move as _move,
)


class Editor:
    """Fluent interface for composing locate/match with transforms."""

    def __init__(self, con: duckdb.DuckDBPyConnection):
        self._con = con

    def definitions(
        self,
        file_pattern: str,
        name: Optional[str] = None,
        kind: str = "definition",
    ) -> Selection:
        """Select definitions by name/kind. Returns a Selection for chaining."""
        regions = locate(self._con, file_pattern, name=name, kind=kind,
                         resolve=True)
        return Selection(regions, self._con)

    def match(
        self,
        file_pattern: str,
        pattern: str,
        language: str,
        **kwargs,
    ) -> MatchSelection:
        """Select code by AST pattern. Returns a MatchSelection for chaining."""
        regions = _match(self._con, file_pattern, pattern, language,
                         resolve=True, **kwargs)
        return MatchSelection(regions, self._con)


class Selection:
    """A set of located Regions, ready for transforms."""

    def __init__(self, regions: list[Region], con: duckdb.DuckDBPyConnection):
        self._regions = regions
        self._con = con

    def remove(self) -> Changeset:
        """Remove all selected regions."""
        return Changeset([_remove(r) for r in self._regions])

    def rename(self, new_name: str) -> Changeset:
        """Rename the selected definitions (within their own content)."""
        ops = []
        for r in self._regions:
            if r.name and r.is_resolved:
                ops.append(_rename_in(r, r.name, new_name))
        return Changeset(ops)

    def replace_with(self, new_content: str) -> Changeset:
        """Replace all selected regions with new content."""
        return Changeset([_replace_body(r, new_content) for r in self._regions])

    def move_to(self, dest_file: str, before_line: int = 1) -> Changeset:
        """Move all selected regions to a destination file."""
        dst = Region.at(dest_file, before_line, before_line)
        return Changeset([_move(r, dst) for r in self._regions])


class MatchSelection:
    """A set of MatchRegions from ast_match, ready for transforms."""

    def __init__(self, regions, con):
        self._regions = regions
        self._con = con

    def remove(self) -> Changeset:
        """Remove all matches."""
        return Changeset([_remove(r) for r in self._regions])

    def replace_with(self, template: str) -> Changeset:
        """Replace matches using a template with __NAME__ wildcard substitution."""
        from fledgling.edit.template import template_replace
        ops = []
        for mr in self._regions:
            new_content = template_replace(mr, template)
            ops.append(_replace_body(mr, new_content))
        return Changeset(ops)
