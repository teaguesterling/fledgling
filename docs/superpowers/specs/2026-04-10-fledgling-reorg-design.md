# Fledgling Reorg: SQL Macros, fledgling-python Extraction, and Pro Package Split

**Date:** 2026-04-10
**Status:** Design agreed (brainstorm). Implementation plan pending.
**Scope:** Changes to fledgling itself. squackit and pluckit slices are in separate specs.

## Context

`fledgling/pro/` currently mixes three concerns in one subpackage: FastMCP server wiring (MCP protocol), Python intelligence (smart defaults, truncation, caching, access log, kibitzer), and workflow composition (explore/investigate/review/search). Some of the "intelligence" could be expressed as SQL macros; some should be Python but not MCP-specific; some is inherently MCP-bound. Conflating them blocks reuse by non-MCP consumers (notebook users, CLI tools, lackpy interpreters) and ties language-agnostic composition to a Python runtime.

Lackpy's 2026-04-10 `sql-macro-reorg-prep` doc anticipated this reorg but did not decide it. This spec decides fledgling's slice.

## Target layering

```
Layer 0   DuckDB extensions (sitting_duck, markdown, webbed, read_lines, ...)
Layer 1   fledgling              — SQL macros, language-agnostic
Layer 2   fledgling-python       — thin Python bundler over fledgling
Layer 3a  pluckit                — fluent Python API (jQuery-like, stateless)
Layer 3b  squackit               — stateful MCP server + intelligence layer
Layer 4   Consumers              — lackpy, agents, kibitzers, notebook users
```

Dependencies are strictly downward. No layer skips. squackit depends on pluckit; pluckit depends on fledgling-python; fledgling-python bundles fledgling's SQL files.

**Organizing rule.** Composition of primitives via SQL → fledgling macro (language-agnostic). Requires C++ for correctness or performance → DuckDB extension. Python code wrapping SQL for Python consumers → fledgling-python or pluckit. Stateful, opinionated, or MCP-protocol-bound → squackit.

## Changes inside fledgling

### 1. New SQL workflow macros

Six new composed macros land in fledgling. Each is pure SQL — composition of existing primitives. They become the *query* half of what `fledgling/pro/workflows.py` currently does in Python. The *workflow* half (cache, formatting, hints, session state) moves to squackit as Python wrappers.

| Macro | Composes | Purpose |
|---|---|---|
| `pss_render(source, selector)` | `ast_select`, `ast_get_source`, `db_heading`, `db_code`, `db_assemble`, `duck_blocks_to_md` | Pluckit Source Selections — selector-as-heading + matches-as-code-blocks markdown. Currently built in Python inside pluckit/lackpy. |
| `ast_select_render(source, selector)` | Same as above | Ast-select result rendering in the heading-per-selector format currently produced by lackpy's `AstSelectInterpreter`. |
| `explore_query(root := NULL)` | `project_overview`, `code_structure`, `doc_outline`, `recent_changes` | First-contact briefing data: languages, top complexity, doc outline, git activity. |
| `investigate_query(name, file_pattern := NULL)` | `find_definitions`, `find_calls`, `find_call_sites` | Definition + callers + callees for a symbol. |
| `review_query(from_rev := NULL, to_rev := NULL, file_pattern := NULL)` | `changed_files`, `changed_function_summary`, `file_changes` | Changed files, complexity deltas, top diffs. |
| `search_query(pattern, file_pattern := NULL)` | `find_definitions`, `find_calls`, `find_doc_sections` | Multi-source search over definitions, call sites, and docs. |

**File placement:**
- Macros: `sql/workflows.sql` (new tier file; follows the macro-file conventions in `CLAUDE.md`)
- Tool publications: `sql/tools/workflows.sql`
- Tests: `tests/test_workflows.py`

**Return shape.** Each `*_query` macro returns a single row with nested `LIST`/`STRUCT` columns — one struct field per composed section (e.g. `{ languages: LIST, top_defs: LIST, docs: LIST, recent: LIST }`). DuckDB handles this cleanly, and squackit's Python wrapper unpacks the struct into the briefing format. UNION-with-discriminator and multi-result-set were considered and rejected (UNION breaks column heterogeneity; multi-result-set is not idiomatic in DuckDB table macros).

**Out of scope.** Multi-rule pss sheets (selector table + iteration) and HTML rendering via the `webbed` extension. Both noted in lackpy's reorg-prep doc as follow-up. `pss_render`'s multi-format (`format := 'markdown' | 'html'`) can be deferred until the `webbed` integration is validated.

### 2. fledgling-python extraction — API deltas

**Current state.** `fledgling/connection.py` and `fledgling/tools.py` already implement:

- `fledgling.connect()` at the root module
- `Connection` proxy wrapping `DuckDBPyConnection` with `__getattr__` delegation
- `Tools` class that auto-discovers macros via `duckdb_functions()` and generates `_MacroCall` wrappers returning `DuckDBPyRelation`
- Three init modes (explicit init file, auto-discover `.fledgling-init.sql`, load from SQL sources)
- Module-level lazy API (`from fledgling.tools import find_definitions`)

The infrastructure for fledgling-python is substantially in place. What's needed before extraction is a set of refinements to the existing code.

**Delta 1 — switch wrapper source to MCP tool publications.** `Tools._discover()` currently queries `duckdb_functions()` filtered to `function_type = 'table_macro'`. Change it to introspect the registry written by `mcp_publish_tool()`. Benefits:

- Curated user-facing surface only (internal helper macros stop appearing as wrappers)
- Docstrings generated from MCP tool descriptions
- Parameter types and required/optional flags from JSON schemas
- Single source of truth: macros users should see are exactly the ones published as tools

A user who wants a custom `.fledgling-init.sql` macro auto-wrapped declares it via `mcp_publish_tool` too. Cost is one extra call; benefit is intentional surface area.

**Delta 2 — `.fledgling-init.sql` becomes overlay, not replacement.** Current `_execute_init_file()` runs *instead of* `_load_from_sources()` when a project init file exists. New semantics:

- Standard sources always load first (bundled SQL files via `_find_sql_dir()`)
- `.fledgling-init.sql`, if present, is applied *after* as a project-specific overlay
- Absent `.fledgling-init.sql` is never an error
- `init=False` skips the overlay; `init='/path/to/file'` uses an explicit overlay path

This matches the "fledgling-python bundles everything parametrically" rule: projects add stuff on top; they never have to bypass the standard init to get a working connection.

**Delta 3 — add `attach()` and `lockdown()` as top-level verbs.**

```python
import fledgling

# attach: configure an existing DuckDBPyConnection
existing = duckdb.connect(":memory:")
fledgling.attach(existing, profile='analyst')

# lockdown: always explicit, always last
fledgling.lockdown(con, allowed_dirs=['/project/root', 'git://'])
```

`connect()` currently always creates a fresh `:memory:` connection; `attach()` fills the gap for users who already have a connection (notebook workflows, test harnesses, embedding in larger applications). `lockdown()` is currently only performed by the SQL init files (`init/init-fledgling-{core,analyst}.sql`); a Python verb is needed so notebook and script users can opt in without loading a profile-specific init file.

**Delta 4 — promote compose helpers to public root.** `_load_from_sources()` does extensions + variables + literal-baking + module loading inline. Split into public top-level functions so the compose case is a first-class API, not an escape hatch:

```python
fledgling.load_extensions(con)
fledgling.load_macros(con, modules=['source', 'code'])
fledgling.set_session_root(con, root='/path')    # bakes _resolve/_session_root literals
fledgling.apply_local_init(con, root='/path')    # optional .fledgling-init.sql overlay
```

**Delta 5 — add `fledgling.configure(con, **kwargs)` as the mid-level verb.** Sugar over the building blocks.

```python
fledgling.configure(con, profile='analyst', modules=['source', 'code'], session_root='/path')
```

`connect()` and `attach()` are thin wrappers over `configure()`. The naming replaces the earlier working name "bootstrap" with "configure" because it reads better as a verb applied to an existing connection.

**Default `_resolve()` behavior when no `session_root` is supplied.** `fledgling.connect()` with no `root` argument bakes `os.getcwd()` as the `_resolve()`/`_session_root()` literal at bootstrap time. If the user later calls `set_session_root()` with a different root, the literals are re-created (the macros are `CREATE OR REPLACE`). Most ergonomic; documented explicitly so nothing is surprising.

### 3. Dissolve `fledgling/pro/`

Once squackit exists and absorbs the relevant modules, `fledgling/pro/` is deleted. The mapping:

| Current file | New home | Notes |
|---|---|---|
| `db.py` | **fledgling-python** | Near-duplicate of `connection.py` — unified in extraction, not migrated as a separate file. |
| `defaults.py` | **squackit/defaults.py** | Project inference is squackit's job. |
| `formatting.py` | **squackit/formatting.py** | Truncation and briefing assembly. |
| `workflows.py` | **split** | Query composition → SQL macros (section 1). Workflow objects (cache, formatting, hints) → `squackit/workflows.py`. |
| `session.py` | **squackit/session.py** | Plus persistence to disk for lackpy kibitzer consumption. |
| `prompts.py` | **squackit/prompts.py** | MCP prompt templates. |
| `server.py` | **squackit/server.py** | FastMCP server wiring. |
| `__main__.py` | **squackit/__main__.py** | Entry point. |

**Tests:** `tests/test_pro_*.py` either move to squackit or are deleted if their behavior is covered by squackit's own tests.

**Packaging:** the `fledgling-mcp[pro]` extra is removed from fledgling's `pyproject.toml`. Users who want the intelligence layer install `squackit` directly.

## Migration order (sketch)

Full cross-repo sequencing belongs in the implementation plan. Rough order:

1. **Land new SQL workflow macros in fledgling** (section 1). Backwards-compatible — no other repo sees a change.
2. **Land `connection.py`/`tools.py` refinements** (section 2 deltas 1–5). Backwards-compatible — existing `fledgling.connect()` callers keep working; the proxy gains new capabilities.
3. **Extract `fledgling-python` as its own repo/package.** Fledgling starts depending on it. `fledgling.connect()` becomes a re-export from `fledgling_python.connect()`.
4. **Create squackit** (see squackit design spec). Depends on `fledgling-python` transitively via pluckit.
5. **Remove `fledgling/pro/` from fledgling.** The `[pro]` extra stops existing; users migrate to installing `squackit` directly.

Between steps 4 and 5, `fledgling[pro]` and `squackit` exist in parallel. This is deliberate — it lets consumers migrate at their own pace rather than flipping the world at once.

## Open questions

- **Access log persistence format.** Where squackit writes the access log affects whether lackpy's kibitzer can consume it easily. Decided in the squackit spec (DuckDB file at `~/.squackit/sessions/<session_id>.duckdb`); noted here because it's a cross-package assumption.
- **Version floor for pluckit adopting fledgling-python.** Pluckit's spec will pin a minimum fledgling-python version that includes the new SQL workflow macros. TBD until first release.

## Cross-references

- **squackit design:** `~/Projects/squackit/docs/superpowers/specs/2026-04-10-squackit-design.md`
- **pluckit integration:** `~/Projects/pluckit/main/docs/superpowers/specs/2026-04-10-fledgling-python-integration-design.md`
- **lackpy reorg-prep (anticipatory):** `~/Projects/lackpy/trees/feature/interpreter-plugins/docs/superpowers/specs/2026-04-10-sql-macro-reorg-prep.md`
