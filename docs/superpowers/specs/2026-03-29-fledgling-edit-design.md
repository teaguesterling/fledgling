# fledgling-edit: AST-Aware Code Editing

**Date:** 2026-03-29
**Status:** Design
**Scope:** New add-on package for fledgling providing smart, AST-targeted code modification tools.

## Problem

AI agents and automation scripts need to modify code structurally — rename
a function, remove a definition, move code between files, apply a pattern-based
rewrite across a codebase. Today they work at the text level: raw line numbers,
string matching, manual splicing. This is fragile, error-prone, and doesn't
compose well.

Fledgling already provides rich AST-aware *read* capabilities via sitting_duck
(semantic search, pattern matching, structural diff). This package adds the
*write* side: targeted code edits driven by AST intelligence.

## Design Principles

1. **AST targets, text transforms.** Use sitting_duck to *locate* code
   precisely (by name, kind, or structural pattern). Apply edits as text-level
   operations on the located regions. Validate output by re-parsing through
   sitting_duck.
2. **Layer 0 is pure Python.** The core primitives (Region, EditOp, Changeset)
   have no DuckDB dependency and are testable in isolation.
3. **Three effect modes.** Every edit can be previewed (return diff), inspected
   (return new content), or applied (write file). Default is preview.
4. **Language-agnostic core, language-specific post-processors.** The editing
   engine works on text regions. Language-specific concerns (indentation,
   import updates) are handled by pluggable post-processors.
5. **Seed in fledgling, extract later.** Lives in `fledgling/edit/` initially.
   Designed for eventual extraction as a standalone package.

## Architecture

### Three Layers

```
Layer 0: Core primitives (pure Python, no DuckDB)
  Region, EditOp hierarchy, Changeset, transforms, template engine

Layer 1: Targeting bridge (depends on fledgling)
  locate() — name/kind-based, wraps find_definitions / find_in_ast
  match()  — pattern-based, wraps ast_match with captures

Layer 2: Surfaces (depends on Layer 0 + 1)
  Builder API — fluent Editor interface
  MCP tools  — exposed via fledgling-pro FastMCP
  CLI        — verb-noun command line interface
```

## Layer 0: Core Primitives

### Region

A located span of code, with all fields optional to support three usage
patterns: location reference (no content), fully resolved (location + content),
and standalone content (no location).

```python
@dataclass(frozen=True)
class Region:
    # Location (optional — standalone content has no location)
    file_path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    start_column: int | None = None
    end_column: int | None = None

    # Content (optional — can be resolved lazily from location)
    content: str | None = None

    # Metadata (from AST, all optional)
    name: str | None = None
    kind: str | None = None
    language: str | None = None

    # Convenience constructors
    @staticmethod
    def at(file_path, start_line, end_line, **kw) -> Region: ...

    @staticmethod
    def of(content, **kw) -> Region: ...

    # Predicates
    @property
    def is_located(self) -> bool: ...     # has file + lines

    @property
    def is_resolved(self) -> bool: ...    # has file + lines + content

    @property
    def is_standalone(self) -> bool: ...  # has content, no location

    # Lazy resolution
    def resolve(self, reader=None) -> Region:
        """Fill in content from file if missing."""
        ...
```

Column positions are available when sitting_duck is queried with
`source='full'`. They enable sub-line precision for edits within a single
line (e.g., renaming a variable in a multi-assignment).

### EditOp Hierarchy

Small sealed hierarchy — each operation type carries exactly the data it needs:

```python
class EditOp:
    """Base for all edit operations."""
    region: Region

    @property
    def file_path(self) -> str | None: ...
    @property
    def start_line(self) -> int | None: ...

class Remove(EditOp):
    """Delete the region's content."""
    region: Region

class Replace(EditOp):
    """Replace the region's content with new text."""
    region: Region
    new_content: str

class InsertBefore(EditOp):
    """Insert text before the region."""
    region: Region
    content: str

class InsertAfter(EditOp):
    """Insert text after the region."""
    region: Region
    content: str

class Wrap(EditOp):
    """Wrap the region with before/after text."""
    region: Region
    before: str
    after: str

class Move(EditOp):
    """Move the region to a new location.

    The source content is removed and inserted BEFORE the destination
    region. If destination is standalone (no location), raises an error —
    a destination location is required.
    """
    region: Region          # source (where to take from)
    destination: Region     # target (insert before this location)
```

### Changeset

Groups multiple edits for atomic preview/apply. Handles the coordination
problem: multiple edits in one file need line-offset adjustment.

```python
class Changeset:
    ops: list[EditOp]

    def __init__(self, ops, reader=None): ...

    # Effects
    def diff(self) -> str                     # unified diff via difflib
    def preview(self) -> dict[str, str]       # {file_path: new_content}
    def apply(self) -> list[str]              # write files, return modified paths

    # Validation
    def validate(self) -> list[str]           # warnings (overlapping regions, etc.)

    # Optional DuckDB-powered diff
    def db_diff(self, con) -> str             # scalarfs + duck_tails

    # Composition
    def __add__(self, other) -> Changeset     # merge two changesets
    def files_affected(self) -> set[str]      # unique file paths
    def filter(self, pred) -> Changeset       # subset of ops
```

**Multi-edit coordination:** Edits within a file are applied bottom-up
(highest start_line first) so earlier edits don't shift later ones.
`validate()` detects overlapping regions before apply.

**Move decomposition:** A `Move` internally becomes a `Remove` at the source
and an `InsertBefore`/`InsertAfter` at the destination during `preview()`
and `apply()`. The `Move` semantics are preserved in `diff()` output so the
user sees "moved from A to B."

**DuckDB diff path:** Uses `scalarfs` + `duck_tails` for in-memory diffing:

```python
def db_diff(self, con) -> str:
    # For each modified file:
    result = con.sql("""
        SELECT diff_text FROM read_git_diff(
            to_scalarfs_uri(?), to_scalarfs_uri(?)
        )
    """, [old_content, new_content])
```

### Transform Functions

Stateless functions that produce `EditOp`s from `Region`s:

```python
def remove(region: Region) -> Remove
def replace_body(region: Region, new_body: str) -> Replace
def insert_before(region: Region, text: str) -> InsertBefore
def insert_after(region: Region, text: str) -> InsertAfter
def wrap(region: Region, before: str, after: str) -> Wrap
def move(region: Region, destination: Region) -> Move
def rename_in(region: Region, old_name: str, new_name: str) -> Replace
```

### Template Engine

For pattern match/replace, the template engine substitutes captured AST nodes
into replacement templates using the same `__NAME__` wildcard syntax as
`ast_match` patterns:

```python
def template_replace(match_region: MatchRegion, template: str) -> str:
    """Substitute captures into a template string.

    __NAME__ in the template is replaced with the peek (source text)
    of the corresponding capture from the match.
    """
```

Examples:

```python
# Pattern: "old_api(__ARGS__)"  ->  Template: "new_api(__ARGS__)"
# Capture ARGS="x, y, z"       ->  Output: "new_api(x, y, z)"

# Pattern: "db.execute(__Q__)"
# Template: "try:\n    db.execute(__Q__)\nexcept DatabaseError:\n    raise"
```

Indentation-aware substitution is handled in collaboration with language-specific
post-processors (see below).

### AST Validation

After any transform that produces new content, optionally validate by parsing
the result through sitting_duck:

```python
def validate_syntax(content: str, language: str, con=None) -> bool:
    """Parse content via sitting_duck's parse_ast and check for errors."""
```

This implements the "trust but verify" approach: generate code via text
templates, validate it parses correctly.

## Layer 1: Targeting Bridge

Two entry points that connect fledgling's read-side intelligence to Regions:

### locate()

Name/kind-based targeting. Wraps `find_definitions` and `find_in_ast`.

```python
def locate(
    con,
    file_pattern: str,
    name: str | None = None,
    kind: str | None = None,    # "definition", "function", "class",
                                # "import", "call", "loop", etc.
    resolve: bool = True,       # fill in content from file
    columns: bool = False,      # request column positions (source='full')
) -> list[Region]:
```

| `kind` | Backed by |
|--------|-----------|
| `"definition"`, `"function"`, `"class"` | `find_definitions()` |
| `"import"`, `"call"`, `"loop"`, `"conditional"`, `"string"`, `"comment"` | `find_in_ast()` |

### match()

Pattern-based targeting via `ast_match`. Returns `MatchRegion` objects with
named captures.

```python
def match(
    con,
    file_pattern: str,
    pattern: str,
    language: str,
    resolve: bool = True,
    columns: bool = False,
    match_by: str = "type",        # or "semantic_type" for cross-language
    depth_fuzz: int = 0,
) -> list[MatchRegion]:

@dataclass(frozen=True)
class MatchRegion(Region):
    """A Region produced by ast_match, with named captures."""
    captures: dict[str, CapturedNode] | None = None

@dataclass(frozen=True)
class CapturedNode:
    name: str            # capture name (e.g., "F", "X")
    node_id: int
    type: str
    peek: str            # source text of captured node
    start_line: int
    end_line: int
```

### match_replace()

High-level operation that combines pattern matching with template substitution:

```python
def match_replace(
    con,
    file_pattern: str,
    pattern: str,
    template: str,
    language: str,
    **match_kwargs,
) -> Changeset:
    """Match a pattern, substitute captures into template, return Changeset."""
```

Examples:

```python
# Rename API call, preserving arguments
match_replace(con, "**/*.py",
    pattern="deprecated_func(__ARGS__)",
    template="new_func(__ARGS__)",
    language="python")

# Wrap calls in error handling
match_replace(con, "**/*.py",
    pattern="db.execute(__Q__)",
    template="""try:
    db.execute(__Q__)
except DatabaseError as e:
    log.error(e)
    raise""",
    language="python")
```

### sitting_duck Parameters Used

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `source` | `'full'` | Adds `start_column`, `end_column` for sub-line edits |
| `source` | `'lines'` | Default — line-level positions only |
| `structure` | `'full'` | Tree columns for depth/parent-aware operations |
| `context` | `'native'` | Full semantic extraction (names, signatures) |

## Language-Specific Post-Processors

A pluggable protocol for language-specific concerns, invoked automatically
during `Changeset.preview()` and `Changeset.apply()` for `Move` operations
and other transforms that change structural context.

```python
class PostProcessor(Protocol):
    def adjust_indentation(
        self, content: str, target_context: Region | None
    ) -> str: ...

    def adjust_imports(
        self, content: str, source_file: str, dest_file: str
    ) -> list[EditOp] | None: ...

POST_PROCESSORS: dict[str, PostProcessor] = {
    "python": PythonPostProcessor(),
}
```

### Python Post-Processor (v1)

- **Dedent on extract:** Moving a method out of a class strips one indent level.
- **Indent on insert:** Moving a function into a class adds one indent level.
- **Context detection:** Uses the destination Region's AST depth/parent to
  infer the target indent level.

Future post-processors: Go (package declarations, gofmt), Rust (mod
declarations), JavaScript (export statements).

### Future: duck_sitter Extension

A future tree-sitter-based code generation extension (`duck_sitter`) could
replace text-level post-processing with grammar-driven unparsing. Research
shows no general-purpose tree-sitter unparser exists today (explicitly out of
scope per the tree-sitter project). The closest approaches are:

- **GrammaTech SEL** — grammar-driven unparse in Common Lisp
- **Topiary** — tree-sitter + declarative formatting rules
- **ast-grep / GritQL** — text splicing with indentation awareness

Original style preservation is largely a post-processing step and can be
addressed incrementally.

## Layer 2: Surfaces

### Builder API

Fluent interface for composing locate/match with transforms:

```python
from fledgling_edit import Editor

ed = Editor(con)

# Definition-level
ed.definitions("**/*.py", "old_func").rename("new_func").preview()
ed.definitions("**/*.py", "MyClass").remove().diff()
ed.definitions("src/**/*.py", "helper").move_to("src/utils.py").apply()

# Pattern match/replace
ed.match("**/*.py", "dangerous_call(__X__)", "python").remove().diff()
ed.match("**/*.py", "old_api(__ARGS__)", "python") \
  .replace_with("new_api(__ARGS__)").apply()

# Composing changesets
cs = (ed.definitions("**/*.py", "func_a").remove()
      + ed.definitions("**/*.py", "func_b").remove())
cs.diff()
cs.apply()
```

### MCP Tools

Exposed via fledgling-pro's FastMCP server. All tools default to `mode="preview"`.

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `EditDefinition` | Replace a definition's body | `file_pattern`, `name`, `new_content`, `mode` |
| `RemoveDefinition` | Remove a definition | `file_pattern`, `name`, `mode` |
| `MoveDefinition` | Move a definition to another file | `file_pattern`, `name`, `destination_file`, `mode` |
| `RenameSymbol` | Rename a definition + its call sites | `file_pattern`, `name`, `new_name`, `mode` |
| `MatchReplace` | Pattern match/replace with templates | `file_pattern`, `pattern`, `template`, `language`, `mode` |

`MatchReplace` is the power tool — it subsumes most of the others for agents
comfortable writing patterns. The named tools exist for discoverability.

### CLI

Verb-noun pattern, diff to stdout by default, `--apply` to write:

```bash
fledgling-edit rename "**/*.py" old_func new_func
fledgling-edit remove "**/*.py" MyClass --apply
fledgling-edit match-replace "**/*.py" "dangerous(__X__)" "" --lang python
fledgling-edit move "src/main.py" helper_func "src/utils.py" --apply
```

## Package Structure

```
fledgling/edit/
  __init__.py                   # public API
  region.py                     # Region dataclass
  ops.py                        # EditOp hierarchy
  changeset.py                  # Changeset: validate, diff, preview, apply
  transforms.py                 # Stateless transform functions
  locate.py                     # Targeting bridge: locate(), match()
  template.py                   # Template substitution for match_replace
  builder.py                    # Fluent Editor API
  postprocess/
    __init__.py                 # PostProcessor protocol + registry
    python.py                   # Python: indentation adjustment
  cli.py                        # CLI entry point
  mcp.py                        # MCP tool registration

tests/
  test_region.py                # Pure Python, no DuckDB
  test_ops.py                   # Pure Python
  test_changeset.py             # Pure Python (constructed Regions)
  test_transforms.py            # Pure Python
  test_template.py              # Template substitution
  test_locate.py                # Requires fledgling connection
  test_match.py                 # Requires fledgling connection
  test_builder.py               # Integration
  test_postprocess_python.py    # Python indentation
  test_mcp_tools.py             # MCP integration
  test_cli.py                   # CLI smoke tests
```

Test split mirrors the layering: Layer 0 tests are pure Python with zero
DuckDB dependency. Layer 1 tests need a fledgling connection. Surface tests
are integration.

## v1 Scope

**In scope:**
- Core primitives (Region, EditOp hierarchy, Changeset)
- All transform functions (remove, replace, insert_before/after, wrap, move, rename_in)
- Template engine for match_replace
- Targeting bridge: locate() and match()
- Builder API
- MCP tools (definition-level + MatchReplace)
- CLI
- Python post-processor (indentation)
- AST validation of generated output

**Out of scope (future):**
- Additional language post-processors (Go, Rust, JS)
- duck_sitter grammar-driven unparse extension
- Import-cascade operations (auto-update imports on move)
- Structural transforms (extract function, inline function)
- Query-driven edits ("remove all unused imports")
- Batch/pattern operations ("rename all camelCase to snake_case")
- Class-level operations (add/remove members)
- Annotation operations (add/remove decorators, docstrings)

## Key Dependencies

- **fledgling** — DuckDB connection, SQL macros (find_definitions, find_in_ast)
- **sitting_duck** — AST parsing (read_ast, ast_match, parse_ast for validation)
- **duck_tails** — diff computation (read_git_diff via scalarfs)
- **scalarfs** — in-memory blob-as-file for DuckDB diff path
- **difflib** (stdlib) — Python-native unified diff (primary diff path)
