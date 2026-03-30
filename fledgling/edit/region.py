"""Region data classes for representing code spans."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, Optional


def _default_reader(file_path: str, start_line: int, end_line: int) -> str:
    """Read lines from a file. Lines are 1-indexed, inclusive."""
    with open(file_path) as f:
        lines = f.readlines()
    # 1-indexed, inclusive range
    selected = lines[start_line - 1 : end_line]
    return "".join(selected)


def _column_reader(file_path: str, start_line: int, end_line: int,
                   start_column: int, end_column: int) -> str:
    """Read a column-bounded region. Columns are 1-indexed."""
    with open(file_path) as f:
        lines = f.readlines()
    if start_line == end_line:
        line = lines[start_line - 1]
        # start_column is 1-indexed inclusive; end_column is 1-indexed exclusive
        return line[start_column - 1 : end_column - 1]
    # Multi-line with column bounds: first line from start_column,
    # middle lines fully, last line up to end_column (exclusive)
    result = []
    for i in range(start_line - 1, end_line):
        line = lines[i]
        if i == start_line - 1:
            result.append(line[start_column - 1 :])
        elif i == end_line - 1:
            result.append(line[: end_column - 1])
        else:
            result.append(line)
    return "".join(result)


@dataclass(frozen=True)
class Region:
    """A located span of code in a file.

    All fields optional to support three usage patterns:
    - Location reference: file_path + lines, no content
    - Fully resolved: file_path + lines + content
    - Standalone content: content only, no location
    """

    # Location
    file_path: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    start_column: Optional[int] = None
    end_column: Optional[int] = None

    # Content
    content: Optional[str] = None

    # Metadata
    name: Optional[str] = None
    kind: Optional[str] = None
    language: Optional[str] = None

    @staticmethod
    def at(file_path: str, start_line: int, end_line: int, **kw) -> Region:
        """Create a location reference (no content)."""
        return Region(file_path=file_path, start_line=start_line,
                      end_line=end_line, **kw)

    @staticmethod
    def of(content: str, **kw) -> Region:
        """Create standalone content (no location)."""
        return Region(content=content, **kw)

    @property
    def is_located(self) -> bool:
        """Has file path and line numbers."""
        return (self.file_path is not None
                and self.start_line is not None
                and self.end_line is not None)

    @property
    def is_resolved(self) -> bool:
        """Has file path, line numbers, and content."""
        return self.is_located and self.content is not None

    @property
    def is_standalone(self) -> bool:
        """Has content but no location."""
        return self.content is not None and not self.is_located

    def resolve(self, reader: Optional[Callable] = None) -> Region:
        """Fill in content from file if missing.

        Returns self if already resolved. Uses the provided reader function,
        or reads from the filesystem by default.

        reader signature: (file_path, start_line, end_line) -> str
        """
        if self.is_resolved:
            return self
        if not self.is_located:
            raise ValueError("Cannot resolve a Region without a location")

        if reader is not None:
            content = reader(self.file_path, self.start_line, self.end_line)
        elif self.start_column is not None and self.end_column is not None:
            content = _column_reader(
                self.file_path, self.start_line, self.end_line,
                self.start_column, self.end_column,
            )
        else:
            content = _default_reader(
                self.file_path, self.start_line, self.end_line,
            )
        return replace(self, content=content)


@dataclass(frozen=True)
class CapturedNode:
    """A node captured by ast_match pattern matching."""

    name: str
    node_id: int
    type: str
    peek: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class MatchRegion(Region):
    """A Region produced by ast_match, with named captures."""

    captures: Optional[dict[str, CapturedNode]] = None
