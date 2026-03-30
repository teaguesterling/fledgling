# fledgling-edit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an AST-aware code editing package that uses fledgling's sitting_duck integration for precise targeting and applies text-level transforms with preview/diff/apply semantics.

**Architecture:** Three-layer design: Layer 0 is pure Python (Region, EditOp, Changeset — no DuckDB), Layer 1 bridges to fledgling for AST targeting (locate, match), Layer 2 provides surfaces (fluent Builder, MCP tools, CLI). All edits default to preview mode (return diff).

**Tech Stack:** Python 3.10+, DuckDB (via fledgling connection), sitting_duck (AST), duck_tails + scalarfs (in-memory diffing), difflib (stdlib), FastMCP (for MCP tools).

**Spec:** `docs/superpowers/specs/2026-03-29-fledgling-edit-design.md`

---

## File Structure

```
fledgling/edit/                     # new subpackage
  __init__.py                       # public API re-exports
  region.py                         # Region dataclass + MatchRegion + CapturedNode
  ops.py                            # EditOp base + Remove, Replace, InsertBefore, InsertAfter, Wrap, Move
  transforms.py                     # Stateless transform functions: remove(), replace_body(), etc.
  changeset.py                      # Changeset: validate, diff, preview, apply, db_diff, composition
  template.py                       # Template substitution engine (__NAME__ wildcard replacement)
  locate.py                         # Targeting bridge: locate(), match(), match_replace()
  builder.py                        # Fluent Editor API
  postprocess/__init__.py           # PostProcessor protocol + registry
  postprocess/python.py             # Python indentation adjustment
  mcp.py                            # MCP tool registration for fledgling-pro
  cli.py                            # CLI entry point (verb-noun, diff-to-stdout)

tests/
  test_edit_region.py               # Pure Python: Region, MatchRegion, CapturedNode
  test_edit_ops.py                  # Pure Python: EditOp hierarchy
  test_edit_transforms.py           # Pure Python: transform functions
  test_edit_changeset.py            # Pure Python: Changeset with constructed Regions
  test_edit_template.py             # Pure Python: template substitution
  test_edit_locate.py               # Requires fledgling connection: locate()
  test_edit_match.py                # Requires fledgling connection: match(), match_replace()
  test_edit_postprocess_python.py   # Pure Python: indentation adjustment
  test_edit_builder.py              # Integration: Builder API
  test_edit_mcp.py                  # Integration: MCP tools
```

---

### Task 1: Region and MatchRegion Data Classes

**Files:**
- Create: `fledgling/edit/__init__.py`
- Create: `fledgling/edit/region.py`
- Test: `tests/test_edit_region.py`

- [ ] **Step 1: Write failing tests for Region**

```python
# tests/test_edit_region.py
"""Tests for Region and MatchRegion data classes (pure Python, no DuckDB)."""

import pytest
from fledgling.edit.region import Region, MatchRegion, CapturedNode


class TestRegionConstruction:
    def test_region_all_none_by_default(self):
        r = Region()
        assert r.file_path is None
        assert r.content is None
        assert r.start_line is None

    def test_region_at_convenience(self):
        r = Region.at("src/main.py", 10, 25)
        assert r.file_path == "src/main.py"
        assert r.start_line == 10
        assert r.end_line == 25
        assert r.content is None

    def test_region_at_with_kwargs(self):
        r = Region.at("src/main.py", 10, 25, name="foo", kind="function")
        assert r.name == "foo"
        assert r.kind == "function"

    def test_region_of_convenience(self):
        r = Region.of("def hello(): pass")
        assert r.content == "def hello(): pass"
        assert r.file_path is None

    def test_region_of_with_kwargs(self):
        r = Region.of("import os", language="python")
        assert r.language == "python"

    def test_region_is_frozen(self):
        r = Region.at("f.py", 1, 5)
        with pytest.raises(AttributeError):
            r.file_path = "other.py"


class TestRegionPredicates:
    def test_is_located(self):
        assert Region.at("f.py", 1, 5).is_located
        assert not Region.of("code").is_located
        assert not Region().is_located

    def test_is_resolved(self):
        r = Region(file_path="f.py", start_line=1, end_line=5, content="code")
        assert r.is_resolved
        assert not Region.at("f.py", 1, 5).is_resolved

    def test_is_standalone(self):
        assert Region.of("code").is_standalone
        assert not Region.at("f.py", 1, 5).is_standalone


class TestRegionResolve:
    def test_resolve_reads_file(self, tmp_path):
        p = tmp_path / "test.py"
        p.write_text("line1\nline2\nline3\nline4\nline5\n")
        r = Region.at(str(p), 2, 4)
        resolved = r.resolve()
        assert resolved.is_resolved
        assert resolved.content == "line2\nline3\nline4\n"

    def test_resolve_noop_if_already_resolved(self):
        r = Region(file_path="f.py", start_line=1, end_line=1, content="x")
        assert r.resolve() is r

    def test_resolve_with_custom_reader(self):
        reader = lambda fp, sl, el: "custom content"
        r = Region.at("f.py", 1, 5)
        resolved = r.resolve(reader=reader)
        assert resolved.content == "custom content"

    def test_resolve_with_columns(self, tmp_path):
        p = tmp_path / "test.py"
        p.write_text("x = foo(bar)\n")
        r = Region(file_path=str(p), start_line=1, end_line=1,
                   start_column=5, end_column=13)
        resolved = r.resolve()
        assert resolved.content == "foo(bar)"


class TestRegionHashable:
    def test_region_in_set(self):
        r1 = Region.at("f.py", 1, 5)
        r2 = Region.at("f.py", 1, 5)
        assert r1 == r2
        assert len({r1, r2}) == 1


class TestMatchRegion:
    def test_match_region_has_captures(self):
        cap = CapturedNode(
            name="F", node_id=42, type="identifier",
            peek="my_func", start_line=10, end_line=10,
        )
        mr = MatchRegion(
            file_path="f.py", start_line=10, end_line=12,
            captures={"F": cap},
        )
        assert mr.captures["F"].peek == "my_func"
        assert mr.is_located

    def test_match_region_is_region(self):
        mr = MatchRegion(file_path="f.py", start_line=1, end_line=2)
        assert isinstance(mr, Region)

    def test_captured_node_fields(self):
        c = CapturedNode(
            name="X", node_id=7, type="string",
            peek='"hello"', start_line=5, end_line=5,
        )
        assert c.name == "X"
        assert c.node_id == 7
        assert c.peek == '"hello"'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_edit_region.py", "-v"])`
Expected: FAIL — `ModuleNotFoundError: No module named 'fledgling.edit'`

- [ ] **Step 3: Create package and implement Region**

```python
# fledgling/edit/__init__.py
"""fledgling-edit: AST-aware code editing for fledgling."""

from fledgling.edit.region import CapturedNode, MatchRegion, Region

__all__ = ["Region", "MatchRegion", "CapturedNode"]
```

```python
# fledgling/edit/region.py
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
        return line[start_column - 1 : end_column]
    # Multi-line with column bounds: first line from start_column,
    # middle lines fully, last line up to end_column
    result = []
    for i in range(start_line - 1, end_line):
        line = lines[i]
        if i == start_line - 1:
            result.append(line[start_column - 1 :])
        elif i == end_line - 1:
            result.append(line[: end_column])
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_edit_region.py", "-v"])`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add fledgling/edit/__init__.py fledgling/edit/region.py tests/test_edit_region.py
git commit -m "feat(edit): add Region, MatchRegion, and CapturedNode data classes"
```

---

### Task 2: EditOp Hierarchy

**Files:**
- Create: `fledgling/edit/ops.py`
- Modify: `fledgling/edit/__init__.py`
- Test: `tests/test_edit_ops.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_edit_ops.py
"""Tests for EditOp hierarchy (pure Python, no DuckDB)."""

import pytest
from fledgling.edit.region import Region
from fledgling.edit.ops import (
    EditOp, Remove, Replace, InsertBefore, InsertAfter, Wrap, Move,
)


class TestRemove:
    def test_remove_has_region(self):
        r = Region.at("f.py", 10, 20, name="foo")
        op = Remove(region=r)
        assert op.region is r
        assert op.file_path == "f.py"
        assert op.start_line == 10

    def test_remove_is_editop(self):
        op = Remove(region=Region.at("f.py", 1, 5))
        assert isinstance(op, EditOp)


class TestReplace:
    def test_replace_has_new_content(self):
        r = Region.at("f.py", 10, 20)
        op = Replace(region=r, new_content="def bar(): pass\n")
        assert op.new_content == "def bar(): pass\n"
        assert op.file_path == "f.py"


class TestInsertBefore:
    def test_insert_before(self):
        r = Region.at("f.py", 10, 10)
        op = InsertBefore(region=r, content="# comment\n")
        assert op.content == "# comment\n"


class TestInsertAfter:
    def test_insert_after(self):
        r = Region.at("f.py", 10, 10)
        op = InsertAfter(region=r, content="\n# end\n")
        assert op.content == "\n# end\n"


class TestWrap:
    def test_wrap_has_before_and_after(self):
        r = Region.at("f.py", 10, 15)
        op = Wrap(region=r, before="try:\n    ", after="\nexcept: pass")
        assert op.before == "try:\n    "
        assert op.after == "\nexcept: pass"


class TestMove:
    def test_move_has_source_and_destination(self):
        src = Region.at("a.py", 10, 20, name="helper")
        dst = Region.at("b.py", 5, 5)
        op = Move(region=src, destination=dst)
        assert op.region is src
        assert op.destination is dst
        assert op.file_path == "a.py"

    def test_move_destination_must_be_located(self):
        src = Region.at("a.py", 10, 20)
        dst = Region.of("standalone content")
        with pytest.raises(ValueError, match="located"):
            Move(region=src, destination=dst)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_edit_ops.py", "-v"])`
Expected: FAIL — `ModuleNotFoundError: No module named 'fledgling.edit.ops'`

- [ ] **Step 3: Implement EditOp hierarchy**

```python
# fledgling/edit/ops.py
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
        if self.destination is not None and not self.destination.is_located:
            raise ValueError(
                "Move destination must be located (have file_path and lines)"
            )
```

Update `__init__.py`:

```python
# fledgling/edit/__init__.py
"""fledgling-edit: AST-aware code editing for fledgling."""

from fledgling.edit.region import CapturedNode, MatchRegion, Region
from fledgling.edit.ops import (
    EditOp, Remove, Replace, InsertBefore, InsertAfter, Wrap, Move,
)

__all__ = [
    "Region", "MatchRegion", "CapturedNode",
    "EditOp", "Remove", "Replace", "InsertBefore", "InsertAfter", "Wrap", "Move",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_edit_ops.py", "-v"])`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add fledgling/edit/ops.py fledgling/edit/__init__.py tests/test_edit_ops.py
git commit -m "feat(edit): add EditOp hierarchy (Remove, Replace, Insert, Wrap, Move)"
```

---

### Task 3: Transform Functions

**Files:**
- Create: `fledgling/edit/transforms.py`
- Modify: `fledgling/edit/__init__.py`
- Test: `tests/test_edit_transforms.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_edit_transforms.py
"""Tests for stateless transform functions (pure Python, no DuckDB)."""

from fledgling.edit.region import Region
from fledgling.edit.ops import (
    Remove, Replace, InsertBefore, InsertAfter, Wrap, Move,
)
from fledgling.edit.transforms import (
    remove, replace_body, insert_before, insert_after, wrap, move, rename_in,
)


class TestRemoveTransform:
    def test_remove_returns_remove_op(self):
        r = Region.at("f.py", 10, 20, name="foo")
        op = remove(r)
        assert isinstance(op, Remove)
        assert op.region is r


class TestReplaceBody:
    def test_replace_body_returns_replace_op(self):
        r = Region.at("f.py", 10, 20)
        op = replace_body(r, "def new_func(): pass\n")
        assert isinstance(op, Replace)
        assert op.new_content == "def new_func(): pass\n"


class TestInsertBefore:
    def test_insert_before_returns_op(self):
        r = Region.at("f.py", 10, 10)
        op = insert_before(r, "# Added comment\n")
        assert isinstance(op, InsertBefore)
        assert op.content == "# Added comment\n"


class TestInsertAfter:
    def test_insert_after_returns_op(self):
        r = Region.at("f.py", 10, 10)
        op = insert_after(r, "\n# Trailing\n")
        assert isinstance(op, InsertAfter)
        assert op.content == "\n# Trailing\n"


class TestWrap:
    def test_wrap_returns_op(self):
        r = Region.at("f.py", 10, 15)
        op = wrap(r, "try:\n", "\nexcept Exception: pass")
        assert isinstance(op, Wrap)
        assert op.before == "try:\n"
        assert op.after == "\nexcept Exception: pass"


class TestMove:
    def test_move_returns_op(self):
        src = Region.at("a.py", 10, 20, name="helper")
        dst = Region.at("b.py", 1, 1)
        op = move(src, dst)
        assert isinstance(op, Move)
        assert op.region is src
        assert op.destination is dst


class TestRenameIn:
    def test_rename_in_produces_replace(self):
        r = Region(file_path="f.py", start_line=1, end_line=1,
                   content="def old_name(): pass\n")
        op = rename_in(r, "old_name", "new_name")
        assert isinstance(op, Replace)
        assert op.new_content == "def new_name(): pass\n"

    def test_rename_in_replaces_all_occurrences(self):
        r = Region(file_path="f.py", start_line=1, end_line=2,
                   content="x = old_name()\nold_name.attr\n")
        op = rename_in(r, "old_name", "new_name")
        assert op.new_content == "x = new_name()\nnew_name.attr\n"

    def test_rename_in_does_not_replace_substrings(self):
        r = Region(file_path="f.py", start_line=1, end_line=1,
                   content="old_name_extended = 1\n")
        op = rename_in(r, "old_name", "new_name")
        # Should only replace whole words, not substrings
        assert "new_name_extended" not in op.new_content
        assert "old_name_extended" in op.new_content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_edit_transforms.py", "-v"])`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement transform functions**

```python
# fledgling/edit/transforms.py
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
```

Add to `__init__.py`:

```python
from fledgling.edit.transforms import (
    remove, replace_body, insert_before, insert_after, wrap, move, rename_in,
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_edit_transforms.py", "-v"])`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add fledgling/edit/transforms.py fledgling/edit/__init__.py tests/test_edit_transforms.py
git commit -m "feat(edit): add stateless transform functions"
```

---

### Task 4: Changeset — Preview, Diff, and Apply

This is the most complex component. The Changeset reads file content, applies
edits bottom-up, and produces diffs or writes files.

**Files:**
- Create: `fledgling/edit/changeset.py`
- Modify: `fledgling/edit/__init__.py`
- Test: `tests/test_edit_changeset.py`

- [ ] **Step 1: Write failing tests for single-edit operations**

```python
# tests/test_edit_changeset.py
"""Tests for Changeset (pure Python, no DuckDB)."""

import pytest
from fledgling.edit.region import Region
from fledgling.edit.ops import (
    Remove, Replace, InsertBefore, InsertAfter, Wrap, Move,
)
from fledgling.edit.changeset import Changeset


SAMPLE_FILE = "def foo():\n    return 1\n\ndef bar():\n    return 2\n"
#               line 1         line 2     line 3  line 4        line 5


@pytest.fixture
def sample_file(tmp_path):
    p = tmp_path / "sample.py"
    p.write_text(SAMPLE_FILE)
    return str(p)


class TestChangesetPreviewSingleEdit:
    def test_remove(self, sample_file):
        r = Region.at(sample_file, 4, 5, content="def bar():\n    return 2\n")
        cs = Changeset([Remove(region=r)])
        result = cs.preview()
        assert sample_file in result
        assert "def bar" not in result[sample_file]
        assert "def foo" in result[sample_file]

    def test_replace(self, sample_file):
        r = Region.at(sample_file, 1, 2, content="def foo():\n    return 1\n")
        cs = Changeset([Replace(region=r, new_content="def foo():\n    return 42\n")])
        result = cs.preview()
        assert "return 42" in result[sample_file]
        assert "return 1" not in result[sample_file]

    def test_insert_before(self, sample_file):
        r = Region.at(sample_file, 4, 5)
        cs = Changeset([InsertBefore(region=r, content="# comment\n")])
        result = cs.preview()
        lines = result[sample_file].splitlines()
        bar_idx = next(i for i, l in enumerate(lines) if "def bar" in l)
        assert lines[bar_idx - 1] == "# comment"

    def test_insert_after(self, sample_file):
        r = Region.at(sample_file, 2, 2)
        cs = Changeset([InsertAfter(region=r, content="    # added\n")])
        result = cs.preview()
        lines = result[sample_file].splitlines()
        ret_idx = next(i for i, l in enumerate(lines) if "return 1" in l)
        assert "# added" in lines[ret_idx + 1]

    def test_wrap(self, sample_file):
        r = Region.at(sample_file, 1, 2, content="def foo():\n    return 1\n")
        cs = Changeset([Wrap(region=r, before="# BEGIN\n", after="# END\n")])
        result = cs.preview()
        text = result[sample_file]
        assert "# BEGIN\ndef foo" in text
        assert "return 1\n# END" in text


class TestChangesetPreviewMultiEdit:
    def test_two_removes_same_file(self, sample_file):
        r1 = Region.at(sample_file, 1, 2, content="def foo():\n    return 1\n")
        r2 = Region.at(sample_file, 4, 5, content="def bar():\n    return 2\n")
        cs = Changeset([Remove(region=r1), Remove(region=r2)])
        result = cs.preview()
        # Only the blank line between them should remain
        assert "def foo" not in result[sample_file]
        assert "def bar" not in result[sample_file]

    def test_multi_edit_preserves_unmodified_lines(self, sample_file):
        r = Region.at(sample_file, 1, 2, content="def foo():\n    return 1\n")
        cs = Changeset([Remove(region=r)])
        result = cs.preview()
        assert "def bar" in result[sample_file]


class TestChangesetPreviewMove:
    def test_move_between_files(self, tmp_path):
        a = tmp_path / "a.py"
        b = tmp_path / "b.py"
        a.write_text("def helper():\n    pass\n\ndef main():\n    pass\n")
        b.write_text("# utils\n")

        src = Region.at(str(a), 1, 2, content="def helper():\n    pass\n")
        dst = Region.at(str(b), 1, 1)
        cs = Changeset([Move(region=src, destination=dst)])
        result = cs.preview()
        assert "def helper" not in result[str(a)]
        assert "def helper" in result[str(b)]


class TestChangesetDiff:
    def test_diff_shows_unified_format(self, sample_file):
        r = Region.at(sample_file, 1, 2, content="def foo():\n    return 1\n")
        cs = Changeset([Replace(region=r, new_content="def foo():\n    return 42\n")])
        diff = cs.diff()
        assert "---" in diff
        assert "+++" in diff
        assert "-    return 1" in diff
        assert "+    return 42" in diff


class TestChangesetApply:
    def test_apply_writes_file(self, sample_file):
        r = Region.at(sample_file, 1, 2, content="def foo():\n    return 1\n")
        cs = Changeset([Replace(region=r, new_content="def foo():\n    return 42\n")])
        modified = cs.apply()
        assert sample_file in modified
        with open(sample_file) as f:
            assert "return 42" in f.read()

    def test_apply_returns_affected_paths(self, sample_file):
        r = Region.at(sample_file, 1, 2, content="def foo():\n    return 1\n")
        cs = Changeset([Remove(region=r)])
        modified = cs.apply()
        assert modified == [sample_file]


class TestChangesetValidate:
    def test_overlapping_regions_warns(self, sample_file):
        r1 = Region.at(sample_file, 1, 3)
        r2 = Region.at(sample_file, 2, 5)
        cs = Changeset([Remove(region=r1), Remove(region=r2)])
        warnings = cs.validate()
        assert len(warnings) > 0
        assert "overlap" in warnings[0].lower()

    def test_non_overlapping_no_warnings(self, sample_file):
        r1 = Region.at(sample_file, 1, 2)
        r2 = Region.at(sample_file, 4, 5)
        cs = Changeset([Remove(region=r1), Remove(region=r2)])
        assert cs.validate() == []


class TestChangesetComposition:
    def test_add_merges_ops(self, sample_file):
        r1 = Region.at(sample_file, 1, 2)
        r2 = Region.at(sample_file, 4, 5)
        cs1 = Changeset([Remove(region=r1)])
        cs2 = Changeset([Remove(region=r2)])
        combined = cs1 + cs2
        assert len(combined.ops) == 2

    def test_files_affected(self, tmp_path):
        a = tmp_path / "a.py"
        b = tmp_path / "b.py"
        a.write_text("x\n")
        b.write_text("y\n")
        cs = Changeset([
            Remove(region=Region.at(str(a), 1, 1)),
            Remove(region=Region.at(str(b), 1, 1)),
        ])
        assert cs.files_affected() == {str(a), str(b)}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_edit_changeset.py", "-v"])`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement Changeset**

```python
# fledgling/edit/changeset.py
"""Changeset: coordinate multiple edits with preview, diff, and apply."""

from __future__ import annotations

import difflib
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
        """Write changes to disk. Returns list of modified file paths."""
        previewed = self.preview()
        modified = []
        for file_path, new_content in sorted(previewed.items()):
            with open(file_path, "w") as f:
                f.write(new_content)
            modified.append(file_path)
        return modified

    def validate(self) -> list[str]:
        """Check for problems. Returns list of warning strings."""
        warnings = []
        expanded = _expand_ops(self.ops)
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
                if end_a > start_b:
                    warnings.append(
                        f"Overlap in {file_path}: region ending at line "
                        f"{end_a} overlaps with region starting at line "
                        f"{start_b}"
                    )
        return warnings

    def db_diff(self, con) -> str:
        """Compute diff using scalarfs + duck_tails (in-memory, no temp files)."""
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
    """Expand Move ops into Remove + InsertBefore pairs."""
    expanded = []
    for op in ops:
        if isinstance(op, Move):
            # Remove from source
            expanded.append(Remove(region=op.region))
            # Insert before destination
            content = op.region.content
            if content is None:
                raise ValueError("Move requires resolved source Region (with content)")
            expanded.append(InsertBefore(region=op.destination, content=content))
        else:
            expanded.append(op)
    return expanded


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
```

Add to `__init__.py`:

```python
from fledgling.edit.changeset import Changeset
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_edit_changeset.py", "-v"])`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add fledgling/edit/changeset.py fledgling/edit/__init__.py tests/test_edit_changeset.py
git commit -m "feat(edit): add Changeset with preview, diff, apply, and validation"
```

---

### Task 5: Template Engine

**Files:**
- Create: `fledgling/edit/template.py`
- Modify: `fledgling/edit/__init__.py`
- Test: `tests/test_edit_template.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_edit_template.py
"""Tests for template substitution engine (pure Python, no DuckDB)."""

import pytest
from fledgling.edit.region import MatchRegion, CapturedNode
from fledgling.edit.template import template_replace


def _cap(name, peek, **kw):
    """Shorthand for CapturedNode construction."""
    return CapturedNode(
        name=name, peek=peek,
        node_id=kw.get("node_id", 0),
        type=kw.get("type", "identifier"),
        start_line=kw.get("start_line", 1),
        end_line=kw.get("end_line", 1),
    )


class TestTemplateReplace:
    def test_simple_substitution(self):
        mr = MatchRegion(captures={"F": _cap("F", "old_func")})
        result = template_replace(mr, "__F__()")
        assert result == "old_func()"

    def test_multiple_captures(self):
        mr = MatchRegion(captures={
            "F": _cap("F", "my_func"),
            "ARGS": _cap("ARGS", "x, y, z"),
        })
        result = template_replace(mr, "new_func(__ARGS__)")
        assert result == "new_func(x, y, z)"

    def test_capture_used_twice(self):
        mr = MatchRegion(captures={"X": _cap("X", "val")})
        result = template_replace(mr, "__X__ + __X__")
        assert result == "val + val"

    def test_no_captures_returns_template_unchanged(self):
        mr = MatchRegion(captures={})
        result = template_replace(mr, "literal code")
        assert result == "literal code"

    def test_unmatched_wildcard_raises(self):
        mr = MatchRegion(captures={"F": _cap("F", "func")})
        with pytest.raises(KeyError, match="MISSING"):
            template_replace(mr, "__MISSING__()")

    def test_empty_template(self):
        mr = MatchRegion(captures={"F": _cap("F", "func")})
        result = template_replace(mr, "")
        assert result == ""

    def test_multiline_capture(self):
        body = "    x = 1\n    y = 2\n    return x + y"
        mr = MatchRegion(captures={"BODY": _cap("BODY", body)})
        result = template_replace(mr, "def wrapper():\n__BODY__")
        assert result == "def wrapper():\n    x = 1\n    y = 2\n    return x + y"

    def test_preserves_non_wildcard_dunders(self):
        """Python __init__ should NOT be treated as a wildcard."""
        mr = MatchRegion(captures={})
        result = template_replace(mr, "self.__init__()")
        assert result == "self.__init__()"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_edit_template.py", "-v"])`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement template engine**

```python
# fledgling/edit/template.py
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
```

Add to `__init__.py`:

```python
from fledgling.edit.template import template_replace
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_edit_template.py", "-v"])`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add fledgling/edit/template.py fledgling/edit/__init__.py tests/test_edit_template.py
git commit -m "feat(edit): add template substitution engine for match/replace"
```

---

### Task 6: Targeting Bridge — locate()

This is the first layer that depends on DuckDB/fledgling.

**Files:**
- Create: `fledgling/edit/locate.py`
- Modify: `fledgling/edit/__init__.py`
- Test: `tests/test_edit_locate.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_edit_locate.py
"""Tests for targeting bridge (requires fledgling DuckDB connection)."""

import os
import pytest
import duckdb

# Reuse conftest fixtures
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from fledgling.edit.locate import locate
from fledgling.edit.region import Region


@pytest.fixture
def code_con():
    """DuckDB connection with sitting_duck + code macros + source macros."""
    con = duckdb.connect(":memory:")
    con.execute("LOAD sitting_duck")
    con.execute("LOAD read_lines")
    sql_dir = os.path.join(PROJECT_ROOT, "sql")
    for f in ["source.sql", "code.sql"]:
        _load_sql(con, os.path.join(sql_dir, f))
    return con


def _load_sql(con, path):
    with open(path) as f:
        sql = f.read()
    lines = [l for l in sql.split("\n") if not l.strip().startswith("--")]
    cleaned = "\n".join(lines)
    for stmt in cleaned.split(";"):
        stmt = stmt.strip()
        if stmt:
            con.execute(stmt + ";")


class TestLocateDefinitions:
    def test_find_function_by_name(self, code_con):
        regions = locate(code_con, "tests/conftest.py", name="load_sql",
                         kind="function")
        assert len(regions) >= 1
        r = regions[0]
        assert r.is_located
        assert r.name == "load_sql"
        assert r.kind == "function"
        assert r.file_path.endswith("conftest.py")

    def test_find_function_resolves_content(self, code_con):
        regions = locate(code_con, "tests/conftest.py", name="load_sql",
                         kind="function", resolve=True)
        r = regions[0]
        assert r.is_resolved
        assert "def load_sql" in r.content

    def test_find_function_no_resolve(self, code_con):
        regions = locate(code_con, "tests/conftest.py", name="load_sql",
                         kind="function", resolve=False)
        r = regions[0]
        assert r.is_located
        assert not r.is_resolved

    def test_find_class_by_kind(self, code_con):
        # fledgling/tools.py has class Tools
        regions = locate(code_con, "fledgling/tools.py", kind="class")
        names = [r.name for r in regions]
        assert "Tools" in names

    def test_find_definition_by_name_pattern(self, code_con):
        regions = locate(code_con, "tests/conftest.py", name="con%",
                         kind="definition")
        names = [r.name for r in regions]
        assert "con" in names

    def test_find_with_columns(self, code_con):
        regions = locate(code_con, "tests/conftest.py", name="load_sql",
                         kind="function", columns=True)
        r = regions[0]
        assert r.start_column is not None


class TestLocateByKind:
    def test_find_imports(self, code_con):
        regions = locate(code_con, "tests/conftest.py", kind="import")
        assert len(regions) > 0
        for r in regions:
            assert r.kind == "import"

    def test_find_calls(self, code_con):
        regions = locate(code_con, "tests/conftest.py", kind="call",
                         name="load_sql")
        assert len(regions) > 0

    def test_unknown_kind_raises(self, code_con):
        with pytest.raises(ValueError, match="kind"):
            locate(code_con, "**/*.py", kind="unknown_thing")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_edit_locate.py", "-v"])`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement locate()**

```python
# fledgling/edit/locate.py
"""Targeting bridge: locate() and match() connect fledgling AST queries to Regions."""

from __future__ import annotations

from typing import Optional

import duckdb

from fledgling.edit.region import CapturedNode, MatchRegion, Region


# Kinds that map to find_definitions with a predicate filter
_DEFINITION_KINDS = {"definition", "function", "class"}

# Kinds that map to find_in_ast
_AST_KINDS = {"import", "call", "loop", "conditional", "string", "comment"}

# Map kind -> find_in_ast kind parameter
_AST_KIND_MAP = {
    "import": "imports",
    "call": "calls",
    "loop": "loops",
    "conditional": "conditionals",
    "string": "strings",
    "comment": "comments",
}


def locate(
    con: duckdb.DuckDBPyConnection,
    file_pattern: str,
    name: Optional[str] = None,
    kind: Optional[str] = None,
    resolve: bool = True,
    columns: bool = False,
) -> list[Region]:
    """Name/kind-based targeting via fledgling SQL macros.

    Args:
        con: A fledgling-enabled DuckDB connection (with sitting_duck + macros loaded).
        file_pattern: Glob pattern for files (e.g., "**/*.py").
        name: Name or SQL LIKE pattern to filter by.
        kind: What to find — "definition", "function", "class", "import",
              "call", "loop", "conditional", "string", "comment".
        resolve: Whether to fill in content from the file.
        columns: Whether to request column positions (source='full').

    Returns:
        List of Region objects.
    """
    if kind and kind not in _DEFINITION_KINDS and kind not in _AST_KINDS:
        raise ValueError(
            f"Unknown kind: {kind!r}. Must be one of: "
            f"{sorted(_DEFINITION_KINDS | _AST_KINDS)}"
        )

    if kind in _DEFINITION_KINDS:
        return _locate_definitions(con, file_pattern, name, kind, resolve, columns)
    elif kind in _AST_KINDS:
        return _locate_ast(con, file_pattern, name, kind, resolve, columns)
    elif name:
        # Default to definition search if name given but no kind
        return _locate_definitions(con, file_pattern, name, "definition",
                                   resolve, columns)
    else:
        raise ValueError("Must provide kind and/or name")


def _locate_definitions(
    con, file_pattern, name, kind, resolve, columns,
) -> list[Region]:
    """Locate via find_definitions macro."""
    name_pattern = name or "%"

    rows = con.execute(
        "SELECT file_path, name, kind, start_line, end_line, signature "
        "FROM find_definitions(?, ?)",
        [file_pattern, name_pattern],
    ).fetchall()

    # Filter by specific kind if not generic "definition"
    if kind == "function":
        rows = [r for r in rows if r[2] == "function"]
    elif kind == "class":
        rows = [r for r in rows if r[2] == "class"]

    regions = []
    for file_path, rname, rkind, start_line, end_line, sig in rows:
        r = Region(
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            name=rname,
            kind=rkind,
        )
        if columns:
            r = _add_columns(con, r, file_pattern)
        if resolve:
            r = r.resolve()
        regions.append(r)
    return regions


def _locate_ast(
    con, file_pattern, name, kind, resolve, columns,
) -> list[Region]:
    """Locate via find_in_ast macro."""
    ast_kind = _AST_KIND_MAP[kind]
    name_pattern = name or "%"

    rows = con.execute(
        "SELECT file_path, name, start_line, context "
        "FROM find_in_ast(?, ?, ?)",
        [file_pattern, ast_kind, name_pattern],
    ).fetchall()

    regions = []
    for file_path, rname, start_line, context in rows:
        # find_in_ast returns start_line but not end_line for most kinds.
        # Use start_line as both for single-line matches.
        r = Region(
            file_path=file_path,
            start_line=start_line,
            end_line=start_line,  # single-line approximation
            name=rname,
            kind=kind,
        )
        if columns:
            r = _add_columns(con, r, file_pattern)
        if resolve:
            r = r.resolve()
        regions.append(r)
    return regions


def _add_columns(con, region: Region, file_pattern: str) -> Region:
    """Re-query with source='full' to get column positions."""
    from dataclasses import replace
    rows = con.execute(
        "SELECT start_column, end_column FROM read_ast(?, source='full') "
        "WHERE file_path = ? AND start_line = ? AND name = ? LIMIT 1",
        [file_pattern, region.file_path, region.start_line,
         region.name or ""],
    ).fetchall()
    if rows:
        return replace(region, start_column=rows[0][0], end_column=rows[0][1])
    return region


def match(
    con: duckdb.DuckDBPyConnection,
    file_pattern: str,
    pattern: str,
    language: str,
    resolve: bool = True,
    columns: bool = False,
    match_by: str = "type",
    depth_fuzz: int = 0,
) -> list[MatchRegion]:
    """Pattern-based targeting via ast_match.

    Args:
        con: A fledgling-enabled DuckDB connection.
        file_pattern: Glob pattern for files.
        pattern: Code pattern with __NAME__ wildcards.
        language: Language for pattern parsing (e.g., "python").
        resolve: Whether to fill in content.
        columns: Whether to request column positions.
        match_by: Matching strategy — "type" or "semantic_type".
        depth_fuzz: Allow +/- N levels of depth difference.

    Returns:
        List of MatchRegion objects with named captures.
    """
    # Create temp table with AST for the file pattern
    source_param = "'full'" if columns else "'lines'"
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE _edit_ast AS
        SELECT * FROM read_ast(?, source={source_param})
    """, [file_pattern])

    # Run ast_match
    rows = con.execute(
        "SELECT match_id, file_path, start_line, end_line, peek, captures "
        "FROM ast_match('_edit_ast', ?, ?, match_by := ?, depth_fuzz := ?)",
        [pattern, language, match_by, depth_fuzz],
    ).fetchall()

    regions = []
    for match_id, file_path, start_line, end_line, peek, captures_map in rows:
        # Parse captures map into CapturedNode objects
        captures = {}
        if captures_map:
            for cap_name, cap_list in captures_map.items():
                # Each capture value is a list of structs; take the first
                if cap_list:
                    c = cap_list[0] if isinstance(cap_list, list) else cap_list
                    captures[cap_name] = CapturedNode(
                        name=c["capture"] if isinstance(c, dict) else cap_name,
                        node_id=c["node_id"] if isinstance(c, dict) else 0,
                        type=c["type"] if isinstance(c, dict) else "",
                        peek=c["peek"] if isinstance(c, dict) else str(c),
                        start_line=c["start_line"] if isinstance(c, dict) else start_line,
                        end_line=c["end_line"] if isinstance(c, dict) else end_line,
                    )

        sc = None
        ec = None
        if columns:
            # Columns are in the AST table
            col_rows = con.execute(
                "SELECT start_column, end_column FROM _edit_ast "
                "WHERE file_path = ? AND start_line = ? LIMIT 1",
                [file_path, start_line],
            ).fetchall()
            if col_rows:
                sc, ec = col_rows[0]

        mr = MatchRegion(
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            start_column=sc,
            end_column=ec,
            name=peek,
            captures=captures,
        )
        if resolve:
            mr = mr.resolve()
        regions.append(mr)

    con.execute("DROP TABLE IF EXISTS _edit_ast")
    return regions


def match_replace(
    con: duckdb.DuckDBPyConnection,
    file_pattern: str,
    pattern: str,
    template: str,
    language: str,
    **match_kwargs,
):
    """Match a pattern and substitute captures into a template.

    Returns a Changeset with Replace ops for each match.
    """
    from fledgling.edit.changeset import Changeset
    from fledgling.edit.ops import Remove, Replace
    from fledgling.edit.template import template_replace as _template_replace

    matches = match(con, file_pattern, pattern, language,
                    resolve=True, **match_kwargs)

    ops = []
    for mr in matches:
        if template == "":
            # Empty template means remove
            ops.append(Remove(region=mr))
        else:
            new_content = _template_replace(mr, template)
            ops.append(Replace(region=mr, new_content=new_content))

    return Changeset(ops)
```

Add to `__init__.py`:

```python
from fledgling.edit.locate import locate, match, match_replace
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_edit_locate.py", "-v"])`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add fledgling/edit/locate.py fledgling/edit/__init__.py tests/test_edit_locate.py
git commit -m "feat(edit): add locate() targeting bridge"
```

---

### Task 7: Targeting Bridge — match() and match_replace()

**Files:**
- Modify: `fledgling/edit/locate.py` (already has match/match_replace from Task 6)
- Test: `tests/test_edit_match.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_edit_match.py
"""Tests for match() and match_replace() (requires fledgling DuckDB connection)."""

import os
import pytest
import duckdb

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from fledgling.edit.locate import match, match_replace
from fledgling.edit.region import MatchRegion


@pytest.fixture
def ast_con(tmp_path):
    """DuckDB connection with sitting_duck, pointed at a temp Python file."""
    con = duckdb.connect(":memory:")
    con.execute("LOAD sitting_duck")
    con.execute("LOAD read_lines")

    # Create a test file with known patterns
    test_file = tmp_path / "example.py"
    test_file.write_text(
        "def greet(name):\n"
        "    print(name)\n"
        "\n"
        "def farewell(name):\n"
        "    print('bye ' + name)\n"
        "\n"
        "greet('world')\n"
        "farewell('world')\n"
    )
    # Load code macros
    sql_dir = os.path.join(PROJECT_ROOT, "sql")
    for f in ["source.sql", "code.sql"]:
        _load_sql(con, os.path.join(sql_dir, f))

    return con, str(tmp_path)


def _load_sql(con, path):
    with open(path) as f:
        sql = f.read()
    lines = [l for l in sql.split("\n") if not l.strip().startswith("--")]
    cleaned = "\n".join(lines)
    for stmt in cleaned.split(";"):
        stmt = stmt.strip()
        if stmt:
            con.execute(stmt + ";")


class TestMatch:
    def test_match_function_pattern(self, ast_con):
        con, dir_path = ast_con
        pattern = os.path.join(dir_path, "example.py")
        regions = match(con, pattern, "print(__X__)", "python")
        assert len(regions) >= 2
        for r in regions:
            assert isinstance(r, MatchRegion)
            assert "X" in r.captures

    def test_match_captures_content(self, ast_con):
        con, dir_path = ast_con
        pattern = os.path.join(dir_path, "example.py")
        regions = match(con, pattern, "greet(__X__)", "python")
        assert len(regions) >= 1
        # The capture should contain the argument
        x_peek = regions[0].captures["X"].peek
        assert "world" in x_peek


class TestMatchReplace:
    def test_match_replace_produces_changeset(self, ast_con):
        con, dir_path = ast_con
        fp = os.path.join(dir_path, "example.py")
        cs = match_replace(con, fp, "greet(__X__)", "hello(__X__)", "python")
        assert len(cs.ops) >= 1
        diff = cs.diff()
        assert "-greet(" in diff or "greet" in diff

    def test_match_replace_empty_template_removes(self, ast_con):
        con, dir_path = ast_con
        fp = os.path.join(dir_path, "example.py")
        cs = match_replace(con, fp, "greet(__X__)", "", "python")
        from fledgling.edit.ops import Remove
        assert any(isinstance(op, Remove) for op in cs.ops)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_edit_match.py", "-v"])`
Expected: FAIL (match/match_replace are implemented but may need adjustment based on actual ast_match output format)

- [ ] **Step 3: Adjust match() implementation based on actual ast_match output**

The captures map from `ast_match` returns DuckDB MAP type. Run the tests and
fix any serialization issues between DuckDB's MAP/STRUCT types and Python dicts.
The exact shape of captures depends on the duckdb Python API's handling of
nested MAP(VARCHAR, STRUCT[]) types.

- [ ] **Step 4: Run tests to verify they pass**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_edit_match.py", "-v"])`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_edit_match.py fledgling/edit/locate.py
git commit -m "feat(edit): add match() and match_replace() with ast_match integration"
```

---

### Task 8: Python Post-Processor

**Files:**
- Create: `fledgling/edit/postprocess/__init__.py`
- Create: `fledgling/edit/postprocess/python.py`
- Test: `tests/test_edit_postprocess_python.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_edit_postprocess_python.py
"""Tests for Python post-processor (pure Python, no DuckDB)."""

import textwrap
import pytest
from fledgling.edit.postprocess import PostProcessor, get_postprocessor
from fledgling.edit.postprocess.python import PythonPostProcessor
from fledgling.edit.region import Region


class TestPythonIndentation:
    def test_dedent_method_to_function(self):
        """Moving a method out of a class should strip one indent level."""
        pp = PythonPostProcessor()
        content = "    def helper(self):\n        return 1\n"
        # Target context: top-level (depth 0)
        target = Region.at("utils.py", 1, 1)
        result = pp.adjust_indentation(content, target)
        assert result == "def helper(self):\n    return 1\n"

    def test_indent_function_to_method(self):
        """Moving a function into a class should add one indent level."""
        pp = PythonPostProcessor()
        content = "def helper():\n    return 1\n"
        # Target context: inside a class (depth 1, indented)
        target = Region(file_path="cls.py", start_line=5, end_line=5,
                        content="    def existing(self):\n")
        result = pp.adjust_indentation(content, target)
        assert result == "    def helper():\n        return 1\n"

    def test_no_change_when_already_correct(self):
        pp = PythonPostProcessor()
        content = "def helper():\n    return 1\n"
        target = Region.at("top.py", 1, 1)
        result = pp.adjust_indentation(content, target)
        assert result == content

    def test_deeply_nested_dedent(self):
        pp = PythonPostProcessor()
        content = "        def inner():\n            pass\n"
        target = Region.at("top.py", 1, 1)
        result = pp.adjust_indentation(content, target)
        assert result == "def inner():\n    pass\n"


class TestPostProcessorRegistry:
    def test_get_python(self):
        pp = get_postprocessor("python")
        assert isinstance(pp, PythonPostProcessor)

    def test_get_unknown_returns_none(self):
        assert get_postprocessor("brainfuck") is None

    def test_protocol_compliance(self):
        pp = PythonPostProcessor()
        assert isinstance(pp, PostProcessor)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_edit_postprocess_python.py", "-v"])`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement post-processor protocol and Python implementation**

```python
# fledgling/edit/postprocess/__init__.py
"""Language-specific post-processors for code edits."""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from fledgling.edit.region import Region


@runtime_checkable
class PostProcessor(Protocol):
    """Protocol for language-specific post-processing of edits."""

    def adjust_indentation(
        self, content: str, target_context: Optional[Region],
    ) -> str:
        """Adjust indentation of content to match the target context."""
        ...


_REGISTRY: dict[str, PostProcessor] = {}


def register_postprocessor(language: str, pp: PostProcessor) -> None:
    _REGISTRY[language] = pp


def get_postprocessor(language: str) -> Optional[PostProcessor]:
    return _REGISTRY.get(language)


# Auto-register built-in post-processors
def _init_registry():
    from fledgling.edit.postprocess.python import PythonPostProcessor
    register_postprocessor("python", PythonPostProcessor())

_init_registry()
```

```python
# fledgling/edit/postprocess/python.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_edit_postprocess_python.py", "-v"])`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add fledgling/edit/postprocess/__init__.py fledgling/edit/postprocess/python.py \
       tests/test_edit_postprocess_python.py
git commit -m "feat(edit): add Python post-processor for indentation adjustment"
```

---

### Task 9: Builder API

**Files:**
- Create: `fledgling/edit/builder.py`
- Modify: `fledgling/edit/__init__.py`
- Test: `tests/test_edit_builder.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_edit_builder.py
"""Tests for fluent Editor/Builder API (integration, requires DuckDB)."""

import os
import pytest
import duckdb

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from fledgling.edit.builder import Editor
from fledgling.edit.changeset import Changeset


@pytest.fixture
def editor(tmp_path):
    """Editor with a fledgling-enabled connection and test files."""
    con = duckdb.connect(":memory:")
    con.execute("LOAD sitting_duck")
    con.execute("LOAD read_lines")
    sql_dir = os.path.join(PROJECT_ROOT, "sql")
    for f in ["source.sql", "code.sql"]:
        _load_sql(con, os.path.join(sql_dir, f))

    # Create test files
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text(
        "def old_func():\n"
        "    return 1\n"
        "\n"
        "def keep_me():\n"
        "    return 2\n"
    )
    (src / "utils.py").write_text("# utilities\n")

    return Editor(con), str(tmp_path)


def _load_sql(con, path):
    with open(path) as f:
        sql = f.read()
    lines = [l for l in sql.split("\n") if not l.strip().startswith("--")]
    cleaned = "\n".join(lines)
    for stmt in cleaned.split(";"):
        stmt = stmt.strip()
        if stmt:
            con.execute(stmt + ";")


class TestEditorDefinitions:
    def test_definitions_returns_selection(self, editor):
        ed, base = editor
        fp = os.path.join(base, "src", "main.py")
        sel = ed.definitions(fp, "old_func")
        assert sel is not None

    def test_remove_returns_changeset(self, editor):
        ed, base = editor
        fp = os.path.join(base, "src", "main.py")
        cs = ed.definitions(fp, "old_func").remove()
        assert isinstance(cs, Changeset)

    def test_remove_diff_shows_removal(self, editor):
        ed, base = editor
        fp = os.path.join(base, "src", "main.py")
        diff = ed.definitions(fp, "old_func").remove().diff()
        assert "-def old_func" in diff

    def test_rename_diff(self, editor):
        ed, base = editor
        fp = os.path.join(base, "src", "main.py")
        diff = ed.definitions(fp, "old_func").rename("new_func").diff()
        assert "+def new_func" in diff
        assert "-def old_func" in diff


class TestEditorComposition:
    def test_add_changesets(self, editor):
        ed, base = editor
        fp = os.path.join(base, "src", "main.py")
        cs1 = ed.definitions(fp, "old_func").remove()
        cs2 = ed.definitions(fp, "keep_me").remove()
        combined = cs1 + cs2
        assert len(combined.ops) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_edit_builder.py", "-v"])`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement Builder API**

```python
# fledgling/edit/builder.py
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
        """Replace matches using a template with __CAPTURE__ substitution."""
        from fledgling.edit.template import template_replace
        ops = []
        for mr in self._regions:
            new_content = template_replace(mr, template)
            ops.append(_replace_body(mr, new_content))
        return Changeset(ops)
```

Add to `__init__.py`:

```python
from fledgling.edit.builder import Editor
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_edit_builder.py", "-v"])`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add fledgling/edit/builder.py fledgling/edit/__init__.py tests/test_edit_builder.py
git commit -m "feat(edit): add fluent Editor/Builder API"
```

---

### Task 10: MCP Tool Registration

**Files:**
- Create: `fledgling/edit/mcp.py`
- Test: `tests/test_edit_mcp.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_edit_mcp.py
"""Tests for MCP tool registration (integration)."""

import os
import pytest

# Skip if fastmcp not available
fastmcp = pytest.importorskip("fastmcp")

from fledgling.edit.mcp import register_edit_tools


@pytest.fixture
def mcp_server(tmp_path):
    """FastMCP server with edit tools registered."""
    import duckdb
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    con = duckdb.connect(":memory:")
    con.execute("LOAD sitting_duck")
    con.execute("LOAD read_lines")
    sql_dir = os.path.join(PROJECT_ROOT, "sql")
    for f in ["source.sql", "code.sql"]:
        _load_sql(con, os.path.join(sql_dir, f))

    mcp = fastmcp.FastMCP("test-edit")
    register_edit_tools(mcp, con)
    return mcp


def _load_sql(con, path):
    with open(path) as f:
        sql = f.read()
    lines = [l for l in sql.split("\n") if not l.strip().startswith("--")]
    cleaned = "\n".join(lines)
    for stmt in cleaned.split(";"):
        stmt = stmt.strip()
        if stmt:
            con.execute(stmt + ";")


class TestEditToolsRegistered:
    def test_tools_are_registered(self, mcp_server):
        tool_names = [t.name for t in mcp_server._tool_manager.list_tools()]
        assert "EditDefinition" in tool_names
        assert "RemoveDefinition" in tool_names
        assert "MoveDefinition" in tool_names
        assert "RenameSymbol" in tool_names
        assert "MatchReplace" in tool_names
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_edit_mcp.py", "-v"])`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement MCP tool registration**

```python
# fledgling/edit/mcp.py
"""MCP tool registration for fledgling-edit."""

from __future__ import annotations

from typing import Optional

import duckdb


def register_edit_tools(mcp, con: duckdb.DuckDBPyConnection) -> None:
    """Register fledgling-edit tools on a FastMCP server.

    All tools default to mode="preview" (return diff).
    Use mode="apply" to write changes to disk.
    """
    from fledgling.edit.builder import Editor

    ed = Editor(con)

    @mcp.tool()
    async def EditDefinition(
        file_pattern: str,
        name: str,
        new_content: str,
        mode: str = "preview",
    ) -> str:
        """Replace a definition's body by name.

        Args:
            file_pattern: Glob pattern (e.g., "**/*.py").
            name: Definition name to find.
            new_content: The new code to replace the definition with.
            mode: "preview" returns diff, "apply" writes files.
        """
        cs = ed.definitions(file_pattern, name).replace_with(new_content)
        if mode == "apply":
            paths = cs.apply()
            return f"Applied to: {', '.join(paths)}"
        return cs.diff() or "No changes."

    @mcp.tool()
    async def RemoveDefinition(
        file_pattern: str,
        name: str,
        mode: str = "preview",
    ) -> str:
        """Remove a definition by name.

        Args:
            file_pattern: Glob pattern.
            name: Definition name to remove.
            mode: "preview" returns diff, "apply" writes files.
        """
        cs = ed.definitions(file_pattern, name).remove()
        if mode == "apply":
            paths = cs.apply()
            return f"Applied to: {', '.join(paths)}"
        return cs.diff() or "No changes."

    @mcp.tool()
    async def MoveDefinition(
        file_pattern: str,
        name: str,
        destination_file: str,
        mode: str = "preview",
    ) -> str:
        """Move a definition to another file.

        Args:
            file_pattern: Glob pattern for source files.
            name: Definition name to move.
            destination_file: Target file path.
            mode: "preview" returns diff, "apply" writes files.
        """
        cs = ed.definitions(file_pattern, name).move_to(destination_file)
        if mode == "apply":
            paths = cs.apply()
            return f"Applied to: {', '.join(paths)}"
        return cs.diff() or "No changes."

    @mcp.tool()
    async def RenameSymbol(
        file_pattern: str,
        name: str,
        new_name: str,
        mode: str = "preview",
    ) -> str:
        """Rename a definition (within its own body).

        Args:
            file_pattern: Glob pattern.
            name: Current name.
            new_name: New name.
            mode: "preview" returns diff, "apply" writes files.
        """
        cs = ed.definitions(file_pattern, name).rename(new_name)
        if mode == "apply":
            paths = cs.apply()
            return f"Applied to: {', '.join(paths)}"
        return cs.diff() or "No changes."

    @mcp.tool()
    async def MatchReplace(
        file_pattern: str,
        pattern: str,
        template: str,
        language: str,
        mode: str = "preview",
    ) -> str:
        """Pattern match/replace using AST matching with template substitution.

        Use __NAME__ wildcards in the pattern to capture AST nodes.
        Use the same __NAME__ wildcards in the template to substitute
        the captured source text.

        Args:
            file_pattern: Glob pattern.
            pattern: Code pattern with __NAME__ wildcards.
            template: Replacement template (empty string to remove matches).
            language: Language for pattern parsing (e.g., "python").
            mode: "preview" returns diff, "apply" writes files.
        """
        from fledgling.edit.locate import match_replace as _match_replace
        cs = _match_replace(con, file_pattern, pattern, template, language)
        if mode == "apply":
            paths = cs.apply()
            return f"Applied to: {', '.join(paths)}"
        return cs.diff() or "No changes."
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_edit_mcp.py", "-v"])`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add fledgling/edit/mcp.py tests/test_edit_mcp.py
git commit -m "feat(edit): add MCP tool registration (EditDefinition, RemoveDefinition, etc.)"
```

---

### Task 11: CLI Entry Point

**Files:**
- Create: `fledgling/edit/cli.py`
- Test: `tests/test_edit_cli.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_edit_cli.py
"""Smoke tests for fledgling-edit CLI."""

import os
import subprocess
import pytest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def test_file(tmp_path):
    p = tmp_path / "sample.py"
    p.write_text("def old_func():\n    return 1\n\ndef keep():\n    pass\n")
    return str(p)


class TestCLI:
    def test_help(self):
        result = subprocess.run(
            ["python", "-m", "fledgling.edit.cli", "--help"],
            capture_output=True, text=True, cwd=PROJECT_ROOT,
        )
        assert result.returncode == 0
        assert "fledgling-edit" in result.stdout or "usage" in result.stdout.lower()

    def test_remove_preview(self, test_file):
        result = subprocess.run(
            ["python", "-m", "fledgling.edit.cli", "remove", test_file, "old_func"],
            capture_output=True, text=True, cwd=PROJECT_ROOT,
        )
        assert result.returncode == 0
        assert "-def old_func" in result.stdout

    def test_rename_preview(self, test_file):
        result = subprocess.run(
            ["python", "-m", "fledgling.edit.cli", "rename", test_file,
             "old_func", "new_func"],
            capture_output=True, text=True, cwd=PROJECT_ROOT,
        )
        assert result.returncode == 0
        assert "+def new_func" in result.stdout
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_edit_cli.py", "-v"])`
Expected: FAIL — module not found or help text wrong

- [ ] **Step 3: Implement CLI**

```python
# fledgling/edit/cli.py
"""CLI entry point for fledgling-edit.

Usage:
    python -m fledgling.edit.cli rename "**/*.py" old_name new_name
    python -m fledgling.edit.cli remove "**/*.py" MyClass --apply
    python -m fledgling.edit.cli match-replace "**/*.py" "pattern" "template" --lang python
    python -m fledgling.edit.cli move "src/main.py" helper "src/utils.py" --apply
"""

from __future__ import annotations

import argparse
import sys

import duckdb


def _make_connection():
    """Create a fledgling-enabled DuckDB connection."""
    import fledgling
    return fledgling.connect()


def _make_editor(con):
    from fledgling.edit.builder import Editor
    return Editor(con)


def cmd_rename(args):
    con = _make_connection()
    ed = _make_editor(con)
    cs = ed.definitions(args.file_pattern, args.name).rename(args.new_name)
    if args.apply:
        paths = cs.apply()
        print(f"Applied to: {', '.join(paths)}")
    else:
        print(cs.diff())


def cmd_remove(args):
    con = _make_connection()
    ed = _make_editor(con)
    cs = ed.definitions(args.file_pattern, args.name).remove()
    if args.apply:
        paths = cs.apply()
        print(f"Applied to: {', '.join(paths)}")
    else:
        print(cs.diff())


def cmd_move(args):
    con = _make_connection()
    ed = _make_editor(con)
    cs = ed.definitions(args.file_pattern, args.name).move_to(args.destination)
    if args.apply:
        paths = cs.apply()
        print(f"Applied to: {', '.join(paths)}")
    else:
        print(cs.diff())


def cmd_match_replace(args):
    con = _make_connection()
    from fledgling.edit.locate import match_replace
    cs = match_replace(con, args.file_pattern, args.pattern, args.template,
                       args.lang)
    if args.apply:
        paths = cs.apply()
        print(f"Applied to: {', '.join(paths)}")
    else:
        print(cs.diff())


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="fledgling-edit",
        description="AST-aware code editing tools",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # rename
    p = sub.add_parser("rename", help="Rename a definition")
    p.add_argument("file_pattern", help="Glob pattern for files")
    p.add_argument("name", help="Current name")
    p.add_argument("new_name", help="New name")
    p.add_argument("--apply", action="store_true", help="Write changes")
    p.set_defaults(func=cmd_rename)

    # remove
    p = sub.add_parser("remove", help="Remove a definition")
    p.add_argument("file_pattern", help="Glob pattern for files")
    p.add_argument("name", help="Name to remove")
    p.add_argument("--apply", action="store_true", help="Write changes")
    p.set_defaults(func=cmd_remove)

    # move
    p = sub.add_parser("move", help="Move a definition to another file")
    p.add_argument("file_pattern", help="Source glob pattern")
    p.add_argument("name", help="Definition name")
    p.add_argument("destination", help="Destination file path")
    p.add_argument("--apply", action="store_true", help="Write changes")
    p.set_defaults(func=cmd_move)

    # match-replace
    p = sub.add_parser("match-replace", help="Pattern match/replace")
    p.add_argument("file_pattern", help="Glob pattern for files")
    p.add_argument("pattern", help="Code pattern with __NAME__ wildcards")
    p.add_argument("template", help="Replacement template (empty to remove)")
    p.add_argument("--lang", required=True, help="Language (e.g., python)")
    p.add_argument("--apply", action="store_true", help="Write changes")
    p.set_defaults(func=cmd_match_replace)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_edit_cli.py", "-v"])`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add fledgling/edit/cli.py tests/test_edit_cli.py
git commit -m "feat(edit): add CLI entry point (rename, remove, move, match-replace)"
```

---

### Task 12: AST Validation Helper

**Files:**
- Create: `fledgling/edit/validate.py`
- Modify: `fledgling/edit/__init__.py`
- Test: added to `tests/test_edit_locate.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_edit_locate.py`:

```python
from fledgling.edit.validate import validate_syntax


class TestValidateSyntax:
    def test_valid_python(self, code_con):
        assert validate_syntax("def foo(): pass\n", "python", code_con) is True

    def test_invalid_python(self, code_con):
        assert validate_syntax("def (broken syntax\n", "python", code_con) is False

    def test_empty_content(self, code_con):
        assert validate_syntax("", "python", code_con) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_edit_locate.py::TestValidateSyntax", "-v"])`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement validate_syntax**

```python
# fledgling/edit/validate.py
"""AST validation for generated code output."""

from __future__ import annotations

from typing import Optional

import duckdb


def validate_syntax(
    content: str,
    language: str,
    con: duckdb.DuckDBPyConnection,
) -> bool:
    """Validate that content parses without errors via sitting_duck.

    Uses parse_ast() to parse in-memory content. Returns True if the
    content parses successfully, False if there are syntax errors.
    """
    if not content.strip():
        return True
    try:
        rows = con.execute(
            "SELECT COUNT(*) FROM parse_ast(?, ?)",
            [content, language],
        ).fetchone()
        return rows is not None and rows[0] > 0
    except duckdb.Error:
        return False
```

Add to `__init__.py`:

```python
from fledgling.edit.validate import validate_syntax
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_edit_locate.py::TestValidateSyntax", "-v"])`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add fledgling/edit/validate.py fledgling/edit/__init__.py tests/test_edit_locate.py
git commit -m "feat(edit): add validate_syntax() for AST validation of generated code"
```

---

### Task 13: Package Public API and Final Integration

**Files:**
- Modify: `fledgling/edit/__init__.py` (final exports)
- Modify: `fledgling/__init__.py` (optional top-level access)

- [ ] **Step 1: Finalize `__init__.py` exports**

```python
# fledgling/edit/__init__.py
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
```

- [ ] **Step 2: Run all edit tests together**

Run: `mcp__blq_mcp__run(command="test", extra=["-k", "test_edit", "-v"])`
Expected: All PASS

- [ ] **Step 3: Run the full test suite to verify no regressions**

Run: `mcp__blq_mcp__run(command="test", extra=["-v"])`
Expected: All existing tests still pass, all new tests pass

- [ ] **Step 4: Commit**

```bash
git add fledgling/edit/__init__.py
git commit -m "feat(edit): finalize public API exports"
```
