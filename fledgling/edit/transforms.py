"""Stateless transform functions that produce EditOps from Regions."""

from __future__ import annotations

import re

from fledgling.edit.region import Region
from fledgling.edit.ops import (
    Remove, Replace, InsertBefore, InsertAfter, Wrap, Move,
)


def remove(region: Region) -> Remove:
    """Delete the region's content."""
    return Remove(region=region)


def replace_body(region: Region, new_body: str) -> Replace:
    """Replace the region's content with new text."""
    return Replace(region=region, new_content=new_body)


def insert_before(region: Region, text: str) -> InsertBefore:
    """Insert text before the region."""
    return InsertBefore(region=region, content=text)


def insert_after(region: Region, text: str) -> InsertAfter:
    """Insert text after the region."""
    return InsertAfter(region=region, content=text)


def wrap(region: Region, before: str, after: str) -> Wrap:
    """Wrap the region with before/after text."""
    return Wrap(region=region, before=before, after=after)


def move(region: Region, destination: Region) -> Move:
    """Move the region to a new location."""
    return Move(region=region, destination=destination)


def rename_in(region: Region, old_name: str, new_name: str) -> Replace:
    """Rename occurrences of old_name within the region's content.

    Uses word-boundary matching to avoid replacing substrings.
    Requires the region to have content (be resolved).
    """
    if region.content is None:
        raise ValueError("rename_in requires a resolved Region (with content)")
    new_content = re.sub(
        r"\b" + re.escape(old_name) + r"\b",
        new_name,
        region.content,
    )
    return Replace(region=region, new_content=new_content)
