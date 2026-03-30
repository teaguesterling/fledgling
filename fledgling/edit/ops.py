"""EditOp hierarchy — each operation type carries exactly the data it needs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fledgling.edit.region import Region


@dataclass(frozen=True)
class EditOp:
    """Base for all edit operations."""

    region: Region

    @property
    def file_path(self) -> Optional[str]:
        return self.region.file_path

    @property
    def start_line(self) -> Optional[int]:
        return self.region.start_line


@dataclass(frozen=True)
class Remove(EditOp):
    """Delete the region's content."""

    pass


@dataclass(frozen=True)
class Replace(EditOp):
    """Replace the region's content with new text."""

    new_content: str = ""


@dataclass(frozen=True)
class InsertBefore(EditOp):
    """Insert text before the region."""

    content: str = ""


@dataclass(frozen=True)
class InsertAfter(EditOp):
    """Insert text after the region."""

    content: str = ""


@dataclass(frozen=True)
class Wrap(EditOp):
    """Wrap the region with before/after text."""

    before: str = ""
    after: str = ""


@dataclass(frozen=True)
class Move(EditOp):
    """Move the region to a new location.

    The source content is removed and inserted BEFORE the destination
    region. Destination must have a location (file + lines).
    """

    destination: Region = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.destination is None:
            raise ValueError("Move requires a destination Region")
        if not self.destination.is_located:
            raise ValueError(
                "Move destination must be located (have file_path and lines)"
            )
