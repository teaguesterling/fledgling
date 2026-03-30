"""Changeset: coordinate multiple edits with preview, diff, and apply."""

from __future__ import annotations

import difflib
import os
import tempfile
from collections import defaultdict
from typing import Callable, Optional

from fledgling.edit.ops import (
    EditOp, Remove, Replace, InsertBefore, InsertAfter, Wrap, Move,
)
from fledgling.edit.region import Region


class Changeset:
    """A group of edits applied atomically.

    Handles multi-edit coordination: when multiple edits target the same
    file, they are applied bottom-up (highest start_line first) so earlier
    edits don't shift later ones.
    """

    def __init__(
        self,
        ops: list[EditOp],
        reader: Optional[Callable[[str], str]] = None,
    ):
        self.ops = list(ops)
        self._reader = reader or _read_file

    def preview(self) -> dict[str, str]:
        """Return {file_path: new_content} for all affected files."""
        # Expand Move ops into Remove + InsertBefore pairs
        expanded = _expand_ops(self.ops)

        # Group by file
        by_file: dict[str, list[EditOp]] = defaultdict(list)
        for op in expanded:
            if op.file_path:
                by_file[op.file_path].append(op)

        result = {}
        for file_path, file_ops in by_file.items():
            lines = self._reader(file_path).splitlines(keepends=True)
            # Sort bottom-up (highest start_line first) for stable application
            file_ops.sort(key=lambda op: -(op.start_line or 0))
            for op in file_ops:
                lines = _apply_op(lines, op)
            result[file_path] = "".join(lines)
        return result

    def diff(self) -> str:
        """Return a unified diff of all changes."""
        previewed = self.preview()
        diffs = []
        for file_path, new_content in sorted(previewed.items()):
            old_content = self._reader(file_path)
            old_lines = old_content.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)
            file_diff = difflib.unified_diff(
                old_lines, new_lines,
                fromfile=file_path, tofile=file_path,
            )
            diffs.extend(file_diff)
        return "".join(diffs)

    def apply(self) -> list[str]:
        """Write changes to disk. Returns list of modified file paths.

        Uses write-to-temp-then-rename for atomic writes per file.
        """
        previewed = self.preview()
        modified = []
        for file_path, new_content in sorted(previewed.items()):
            dir_name = os.path.dirname(file_path) or "."
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            try:
                with os.fdopen(fd, "w") as f:
                    f.write(new_content)
                os.replace(tmp_path, file_path)
            except BaseException:
                os.unlink(tmp_path)
                raise
            modified.append(file_path)
        return modified

    def validate(self) -> list[str]:
        """Check for problems. Returns list of warning strings."""
        warnings = []
        try:
            expanded = _expand_ops(self.ops)
        except ValueError as e:
            warnings.append(str(e))
            expanded = [op for op in self.ops if not isinstance(op, Move)]
        by_file: dict[str, list[EditOp]] = defaultdict(list)
        for op in expanded:
            if op.file_path:
                by_file[op.file_path].append(op)

        for file_path, file_ops in by_file.items():
            # Check for overlapping regions
            regions = [
                (op.start_line, op.region.end_line)
                for op in file_ops
                if op.start_line is not None and op.region.end_line is not None
            ]
            regions.sort()
            for i in range(len(regions) - 1):
                _, end_a = regions[i]
                start_b, _ = regions[i + 1]
                if end_a >= start_b:
                    warnings.append(
                        f"Overlap in {file_path}: region ending at line "
                        f"{end_a} overlaps with region starting at line "
                        f"{start_b}"
                    )
        return warnings

    def db_diff(self, con) -> str:
        """Compute diff using scalarfs + duck_tails (in-memory, no temp files).

        Requires a fledgling connection with scalarfs and duck_tails loaded.
        Not available from CLI or bare DuckDB connections.
        """
        previewed = self.preview()
        diffs = []
        for file_path, new_content in sorted(previewed.items()):
            old_content = self._reader(file_path)
            result = con.execute(
                "SELECT diff_text FROM read_git_diff("
                "to_scalarfs_uri(?), to_scalarfs_uri(?))",
                [old_content, new_content],
            ).fetchone()
            if result and result[0]:
                diffs.append(f"--- {file_path}\n+++ {file_path}\n{result[0]}")
        return "\n".join(diffs)

    def __add__(self, other: Changeset) -> Changeset:
        return Changeset(self.ops + other.ops, reader=self._reader)

    def files_affected(self) -> set[str]:
        expanded = _expand_ops(self.ops)
        paths = set()
        for op in expanded:
            if op.file_path:
                paths.add(op.file_path)
        return paths

    def filter(self, pred: Callable[[EditOp], bool]) -> Changeset:
        return Changeset([op for op in self.ops if pred(op)], reader=self._reader)


def _read_file(file_path: str) -> str:
    with open(file_path) as f:
        return f.read()


def _expand_ops(ops: list[EditOp]) -> list[EditOp]:
    """Expand Move ops into Remove + InsertBefore pairs.

    When moving code, applies language-specific post-processing
    (e.g., indentation adjustment) if a post-processor is registered.
    """
    expanded = []
    for op in ops:
        if isinstance(op, Move):
            # Remove from source
            expanded.append(Remove(region=op.region))
            # Insert before destination
            content = op.region.content
            if content is None:
                raise ValueError("Move requires resolved source Region (with content)")
            # Apply post-processing (e.g., indentation adjustment)
            content = _postprocess_move(content, op.region, op.destination)
            expanded.append(InsertBefore(region=op.destination, content=content))
        else:
            expanded.append(op)
    return expanded


def _postprocess_move(content: str, source: Region, destination: Region) -> str:
    """Apply language-aware post-processing when moving code."""
    from fledgling.edit.postprocess import get_postprocessor

    language = source.language
    if language is None and source.file_path:
        # Infer language from file extension
        ext = source.file_path.rsplit(".", 1)[-1] if "." in source.file_path else ""
        language = {"py": "python", "js": "javascript", "ts": "typescript"}.get(ext)

    if language:
        pp = get_postprocessor(language)
        if pp:
            content = pp.adjust_indentation(content, destination)
    return content


def _apply_op(lines: list[str], op: EditOp) -> list[str]:
    """Apply a single EditOp to a list of lines. Lines are 1-indexed in the op."""
    start = op.start_line
    end = op.region.end_line
    if start is None or end is None:
        return lines

    # Convert to 0-indexed
    si = start - 1
    ei = end  # end is inclusive in Region, exclusive in slice

    if isinstance(op, Remove):
        return lines[:si] + lines[ei:]

    elif isinstance(op, Replace):
        new_lines = op.new_content.splitlines(keepends=True)
        # Ensure trailing newline if original region had one
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"
        return lines[:si] + new_lines + lines[ei:]

    elif isinstance(op, InsertBefore):
        new_lines = op.content.splitlines(keepends=True)
        return lines[:si] + new_lines + lines[si:]

    elif isinstance(op, InsertAfter):
        new_lines = op.content.splitlines(keepends=True)
        return lines[:ei] + new_lines + lines[ei:]

    elif isinstance(op, Wrap):
        before_lines = op.before.splitlines(keepends=True)
        after_lines = op.after.splitlines(keepends=True)
        region_lines = lines[si:ei]
        return lines[:si] + before_lines + region_lines + after_lines + lines[ei:]

    else:
        raise TypeError(f"Unknown EditOp type: {type(op)}")
