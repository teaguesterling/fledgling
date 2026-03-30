# fledgling-edit: AST-Aware Code Editing

> **Experimental** — this feature is in design/early implementation. The API will change. See the [full design spec](../superpowers/specs/2026-03-29-fledgling-edit-design.md) and [implementation plan](../superpowers/plans/2026-03-29-fledgling-edit-impl.md) for details.

## What is it?

fledgling-edit adds the *write* side to fledgling's read-only AST intelligence. Agents can modify code structurally — rename a function, remove a definition, apply pattern-based rewrites across a codebase — using AST targets instead of raw line numbers.

## Why?

Fledgling already locates code precisely:
```python
con.find_definitions("**/*.py", name_pattern="parse_config%")
# → src/config.py:42-68, DEFINITION_FUNCTION
```

fledgling-edit lets you *act* on what you found:
```python
from fledgling.edit import Editor

editor = Editor(con)
editor.rename("parse_config", "load_config", pattern="src/**/*.py")
editor.preview()   # show diff
editor.apply()     # write changes
```

## Architecture

Three layers — each usable independently:

```
Layer 0: Core (pure Python, no DuckDB)
  Region, EditOp, Changeset, template engine

Layer 1: Targeting bridge (uses fledgling)
  locate() — find by name/kind via find_definitions / find_in_ast
  match()  — pattern match via ast_match with captures

Layer 2: Surfaces
  Builder API — fluent Editor interface
  MCP tools   — exposed via fledgling-pro
  CLI         — fledgling rename, fledgling remove, etc.
```

## Edit Operations

| Operation | What it does |
|-----------|-------------|
| **Remove** | Delete a definition (function, class, import) |
| **Replace** | Swap a region's content with new text |
| **InsertBefore** | Add code before a target |
| **InsertAfter** | Add code after a target |
| **Wrap** | Surround a region (e.g., wrap in try/except) |
| **Move** | Relocate code between files |

## Key Feature: match_replace

The power tool — pattern match with template substitution:

```python
# Rename all logging calls from print() to logger.info()
editor.match_replace(
    pattern="print(__ARGS__)",
    replacement="logger.info(__ARGS__)",
    files="src/**/*.py",
)
```

The `__NAME__` wildcards match sitting_duck's `ast_match` syntax. Captures from the pattern are substituted into the replacement template.

## Safety

- All edits default to **preview mode** (return diff, don't write)
- Re-parses output through sitting_duck to validate AST integrity
- Language-specific post-processors handle indentation (Python first)
- Changeset can be inspected, modified, or discarded before applying

## Status

| Component | Status |
|-----------|--------|
| Design spec | Complete |
| Implementation plan | Complete (15 tasks) |
| Layer 0 core | Not started |
| Layer 1 targeting | Not started |
| Layer 2 surfaces | Not started |

## Links

- [Design Spec](../superpowers/specs/2026-03-29-fledgling-edit-design.md) — full architecture and API design
- [Implementation Plan](../superpowers/plans/2026-03-29-fledgling-edit-impl.md) — task breakdown with TDD steps
