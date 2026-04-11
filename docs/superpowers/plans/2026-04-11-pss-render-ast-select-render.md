# Plan 2b: `pss_render` + `ast_select_render` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development. Steps use `- [ ]` checkbox syntax.

**Goal:** Add two SQL-composed rendering macros to `sql/workflows.sql` (Phase 2a tier) that use `ast_select` + the `markdown` extension's `duck_blocks_to_md` to render selector-based code queries as markdown. These are the SQL successors to lackpy's Python-side `AstSelectInterpreter` and `Plucker.view()` markdown assembly.

**Architecture:** Each macro is a single-row SQL macro returning one `md` column (the rendered markdown). Blocks are assembled from `ast_select` rows into `STRUCT`s that `duck_blocks_to_md` knows how to serialize. The two macros differ in the heading layout: `pss_render` puts `file:range` per match; `ast_select_render` groups matches under a selector heading with per-match sub-headings.

**Tech Stack:** DuckDB 1.5.x, sitting_duck (ast_select + ast_get_source), markdown (duck_blocks_to_md).

---

## BLOCKER

**`ast_select` is not yet in the released community sitting_duck extension** (verified 2026-04-11 against `sitting_duck 2e104b6` — latest in community repo). The macros in `sql/code.sql` that use `ast_select` (`find_code`, `view_code`) fail at macro-definition time with `Catalog Error: Table Function with name ast_select does not exist`.

**Do not begin implementation until one of:**

- `ast_select` lands in community sitting_duck (check with `SELECT function_name FROM duckdb_functions() WHERE function_name = 'ast_select'` after `LOAD sitting_duck`)
- A development build of sitting_duck with `ast_select` is available and installed via `FORCE INSTALL sitting_duck FROM '/local/path'`

Once unblocked, Task 0 of this plan verifies the prerequisite.

---

## Scope boundaries

**In scope:**

- Two new macros in `sql/workflows.sql`: `pss_render(source, selector)` and `ast_select_render(source, selector)`
- Two new tool publications in `sql/tools/workflows.sql`: `PssRender` and `AstSelectRender` (or similar tool names — finalize at implementation)
- Tests for both macros in `tests/test_workflows.py` (extend the existing file)
- Updates to `workflows_macros` fixture in `conftest.py` if needed (it already loads code.sql via `load_sql_filtered`; once `ast_select` is available the filter can be removed)

**Out of scope (deferred to follow-up plans):**

- **Multi-rule selector sheets** — `pss_render(source, sheet)` where `sheet` is a table of (selector, show_mode) rows, iterating with `db_blocks_merge`. Noted in the lackpy reorg-prep doc as follow-up.
- **HTML output format** — `pss_render(source, selector, format := 'html')` using the `webbed` extension's `duck_blocks_to_html`. Requires `webbed` extension availability and CASE dispatch on format.
- **Deletion of pluckit's Python-side rendering** — separate plan, part of pluckit's fledgling-python integration.

---

## Background: `duck_blocks_to_md` input shape

From probing the installed `markdown` extension on 2026-04-11:

```
duck_blocks_to_md(
    STRUCT(
        kind VARCHAR,
        element_type VARCHAR,
        "content" VARCHAR,
        "level" INTEGER,
        "encoding" VARCHAR,
        attributes MAP(VARCHAR, VARCHAR),
        element_order INTEGER
    )[]
) → md
```

### Verified working block shapes

**Heading (level 1–6):**

```sql
{
    kind: 'heading',
    element_type: 'heading',
    content: 'Title Text',
    level: 2,                -- 1..6 = #..######
    encoding: 'plain',
    attributes: MAP{},
    element_order: 1
}
```

Produces `## Title Text\n\n`.

**Paragraph:**

```sql
{
    kind: 'paragraph',
    element_type: 'paragraph',
    content: 'Body text.',
    level: 0,
    encoding: 'plain',
    attributes: MAP{},
    element_order: 2
}
```

Produces `Body text.\n\n`.

### Unknowns to resolve at implementation time

**Code block fencing** — my probe used `kind='code', element_type='code_block', attributes=MAP{'language':'python'}` and the output was *not* fenced (raw content emitted). The right combination of `kind`/`element_type`/`encoding` for language-tagged code fences is not yet known. Task 1 Step 2 below walks through discovering the right values.

---

## File structure

Files modified (all existing from Plan 2a):

- `sql/workflows.sql` — append two new `CREATE OR REPLACE MACRO` statements after the four `*_query` macros
- `sql/tools/workflows.sql` — append two new `PRAGMA mcp_publish_tool` statements
- `tests/test_workflows.py` — append new `TestPssRender` and `TestAstSelectRender` classes
- `tests/conftest.py` — once `ast_select` is available, remove the `skip_macros=['find_code','view_code']` filter from the `workflows_macros` fixture (no longer needed)

No new files required.

---

## Task 0: Verify the environment prerequisite

**Files:** none modified

- [ ] **Step 1: Check `ast_select` is available**

Run:
```bash
python -c "
import duckdb
c = duckdb.connect()
c.execute('LOAD sitting_duck')
r = c.execute(\"SELECT function_name FROM duckdb_functions() WHERE function_name = 'ast_select'\").fetchall()
print('ast_select available:', bool(r))
"
```
Expected: `ast_select available: True`. If False, **stop** — this plan cannot execute. Either install a newer sitting_duck or wait for the community release.

- [ ] **Step 2: Verify `find_code` loads without error**

Run:
```bash
python -c "
import duckdb
c = duckdb.connect()
c.execute('LOAD sitting_duck')
c.execute(open('/mnt/aux-data/teague/Projects/source-sextant/main/sql/code.sql').read())
print('code.sql loaded fully')
"
```
Expected: no `CatalogException`. If it still fails, the `ast_select` version may be a stub without the expected signature — report back and stop.

- [ ] **Step 3: Remove the test-only workaround in `conftest.py`**

Edit `tests/conftest.py` — find the `workflows_macros` fixture and change:

```python
load_sql_filtered(con, "code.sql", skip_macros=["find_code", "view_code"])
```

back to:

```python
load_sql(con, "code.sql")
```

Then delete the `load_sql_filtered` helper and its import if nothing else uses it.

Run `python -m pytest tests/test_workflows.py -v` — the existing 14 tests should still pass. If not, the `find_code`/`view_code` macros' signature has changed — stop and investigate.

- [ ] **Step 4: Commit the cleanup**

```bash
git add tests/conftest.py && \
git commit -m "chore: remove find_code/view_code loader filter — ast_select now available"
```

---

## Task 1: Figure out the code-block struct shape

**Files:** none modified (exploration task)

The Plan 2a probe confirmed headings and paragraphs; code blocks with language tags were not fenced. Before writing the macros, you need to know the exact `kind`/`element_type`/`encoding` values that produce fenced code output.

- [ ] **Step 1: Try the obvious variants**

Run each of these and inspect the output for fence markers (\`\`\`):

```python
import duckdb
c = duckdb.connect(); c.execute('LOAD markdown')

variants = [
    ('code', 'code_block', 'plain'),
    ('code', 'fenced_code_block', 'plain'),
    ('code', 'code', 'plain'),
    ('code_block', 'code_block', 'plain'),
    ('pre', 'code_block', 'plain'),
    ('code', 'code_block', 'fenced'),
]
for kind, etype, enc in variants:
    sql = f"""SELECT duck_blocks_to_md([
      {{'kind':'{kind}', 'element_type':'{etype}', 'content':'def foo():\\n    pass',
        'level':0, 'encoding':'{enc}', 'attributes':MAP{{'language':'python'}},
        'element_order':1
      }}::STRUCT(kind VARCHAR, element_type VARCHAR, "content" VARCHAR, "level" INTEGER, "encoding" VARCHAR, attributes MAP(VARCHAR, VARCHAR), element_order INTEGER)
    ])"""
    try:
        r = c.execute(sql).fetchone()[0]
        fenced = '```' in r
        print(f"({kind!r:<10}, {etype!r:<20}, {enc!r:<8}) fenced={fenced}  {r[:60]!r}")
    except Exception as e:
        print(f"({kind!r:<10}, {etype!r:<20}, {enc!r:<8}) ERROR: {str(e)[:60]}")
```

Record the first combination that produces fenced output. If none work, check the `markdown` extension's source for the block serialization function (the extension repo is `duckdb-community/markdown` or similar) to find the expected values.

- [ ] **Step 2: Document the result in a comment at the top of `sql/workflows.sql`**

Add near the top of the file (after the existing tier comment):

```sql
-- Block struct shapes accepted by duck_blocks_to_md:
--   Heading:   kind='heading',   element_type='heading',    level=1..6
--   Paragraph: kind='paragraph', element_type='paragraph',  level=0
--   Code:      kind='<discovered>', element_type='<discovered>', attributes=MAP{'language':<lang>}
-- (Code block values determined during Plan 2b Task 1 — YYYY-MM-DD.)
```

---

## Task 2: Write `pss_render`

**Files:**
- Modify: `sql/workflows.sql` — append the macro

`pss_render` returns a single-row, single-column (`md`) result. For each row from `ast_select(source, selector)`, it produces two blocks: a level-1 heading with `file:start-end` and a code block containing the source text at that range.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_workflows.py`:

```python
class TestPssRender:
    """pss_render composes ast_select + ast_get_source + duck_blocks_to_md."""

    def test_returns_single_row(self, workflows_macros):
        rows = workflows_macros.execute(
            "SELECT * FROM pss_render(?, '.func')",
            [f"{PROJECT_ROOT}/fledgling/connection.py"],
        ).fetchall()
        assert len(rows) == 1

    def test_result_is_markdown(self, workflows_macros):
        row = workflows_macros.execute(
            "SELECT * FROM pss_render(?, '.func')",
            [f"{PROJECT_ROOT}/fledgling/connection.py"],
        ).fetchone()
        md_text = row[0]
        assert isinstance(md_text, str)
        assert len(md_text) > 0

    def test_contains_headings_for_matches(self, workflows_macros):
        row = workflows_macros.execute(
            "SELECT * FROM pss_render(?, '.func')",
            [f"{PROJECT_ROOT}/fledgling/connection.py"],
        ).fetchone()
        md_text = row[0]
        # Each match produces a level-1 heading with file:range
        assert "# " in md_text
        assert "connection.py" in md_text

    def test_empty_selector_returns_valid_md(self, workflows_macros):
        """Selector with no matches returns an empty markdown document, not an error."""
        row = workflows_macros.execute(
            "SELECT * FROM pss_render(?, '.func#nonexistent_symbol_xyz')",
            [f"{PROJECT_ROOT}/fledgling/connection.py"],
        ).fetchone()
        # Should not raise; empty result is acceptable
        assert row[0] is not None or row[0] == ""
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_workflows.py::TestPssRender -v
```
Expected: all four tests FAIL (`pss_render` does not exist yet — `CatalogException: Table Function with name pss_render does not exist`).

- [ ] **Step 3: Append the macro to `sql/workflows.sql`**

Append after the existing `search_query` macro (at the bottom of the file):

```sql
-- pss_render: Render selector query results as markdown.
-- Each matching ast_select row becomes two blocks: a level-1 heading
-- with file:start-end, and a code block with the source text.
--
-- Depends on: sitting_duck (ast_select, ast_get_source),
--             markdown (duck_blocks_to_md).
--
-- Examples:
--   SELECT * FROM pss_render('**/*.py', '.func');
--   SELECT * FROM pss_render('src/**/*.py', '.class:has(.func#validate)');
CREATE OR REPLACE MACRO pss_render(source, selector) AS TABLE
    WITH matches AS (
        SELECT
            file_path,
            start_line,
            end_line,
            COALESCE(language, 'text') AS language,
            ast_get_source(file_path, start_line, end_line) AS source_text,
            row_number() OVER (ORDER BY file_path, start_line) AS ord
        FROM ast_select(source, selector)
    ),
    blocks AS (
        SELECT LIST({
            kind: 'heading',
            element_type: 'heading',
            content: m.file_path || ':' || m.start_line || '-' || m.end_line,
            level: 1,
            encoding: 'plain',
            attributes: MAP{},
            element_order: m.ord * 2 - 1
        }::STRUCT(kind VARCHAR, element_type VARCHAR, "content" VARCHAR, "level" INTEGER, "encoding" VARCHAR, attributes MAP(VARCHAR, VARCHAR), element_order INTEGER))
        ||
        LIST({
            kind: '<CODE_KIND>',            -- from Task 1
            element_type: '<CODE_ELEMENT_TYPE>',
            content: m.source_text,
            level: 0,
            encoding: '<CODE_ENCODING>',
            attributes: MAP{'language': m.language},
            element_order: m.ord * 2
        }::STRUCT(kind VARCHAR, element_type VARCHAR, "content" VARCHAR, "level" INTEGER, "encoding" VARCHAR, attributes MAP(VARCHAR, VARCHAR), element_order INTEGER))
            AS items
        FROM matches m
    )
    SELECT duck_blocks_to_md(items) AS result
    FROM blocks;
```

Replace `<CODE_KIND>`, `<CODE_ELEMENT_TYPE>`, `<CODE_ENCODING>` with the values discovered in Task 1.

**Implementation note:** if the `LIST({...}) || LIST({...})` concatenation doesn't aggregate per-row blocks correctly (LIST inside a projection is per-row, not aggregate), switch to `FLATTEN(LIST_VALUE(struct_heading, struct_code))` inside the SELECT and aggregate with `array_agg` outside. DuckDB's block-list construction idioms need a quick check — see the adjacent `explore_query` / `investigate_query` patterns in `sql/workflows.sql` for the CTE+LIST approach that is known to work.

- [ ] **Step 4: Run the test to verify it passes**

```bash
python -m pytest tests/test_workflows.py::TestPssRender -v
```
Expected: all four tests PASS. If `test_contains_headings_for_matches` fails because `connection.py` is not in the output, the selector `'.func'` may not match any definitions in that file — update the test to use a file you know has function definitions, or a broader selector.

- [ ] **Step 5: Commit**

```bash
git add sql/workflows.sql tests/test_workflows.py && \
git commit -m "feat: add pss_render macro — selector-to-markdown rendering"
```

---

## Task 3: Write `ast_select_render`

**Files:**
- Modify: `sql/workflows.sql` — append the macro
- Modify: `tests/test_workflows.py` — append `TestAstSelectRender` class

`ast_select_render` differs from `pss_render` in layout:

1. A single level-1 heading at the top with the selector itself (e.g., `` `.func#validate` ``)
2. One level-2 heading per match with `qualified_name` (or `name`) + ` — ` + `file:start-end`
3. One code block per match with the source text

The lackpy reorg-prep doc sketched this shape; it's the heading-per-selector format lackpy's `AstSelectInterpreter` currently produces in Python.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_workflows.py`:

```python
class TestAstSelectRender:
    """ast_select_render: selector heading + per-match sub-headings + code."""

    def test_returns_single_row(self, workflows_macros):
        rows = workflows_macros.execute(
            "SELECT * FROM ast_select_render(?, '.func')",
            [f"{PROJECT_ROOT}/fledgling/connection.py"],
        ).fetchall()
        assert len(rows) == 1

    def test_selector_as_level_1_heading(self, workflows_macros):
        row = workflows_macros.execute(
            "SELECT * FROM ast_select_render(?, '.func')",
            [f"{PROJECT_ROOT}/fledgling/connection.py"],
        ).fetchone()
        md_text = row[0]
        # The selector itself should appear as a level-1 heading at the top
        assert md_text.lstrip().startswith("# ")
        assert ".func" in md_text.split("\n")[0]

    def test_per_match_level_2_headings(self, workflows_macros):
        row = workflows_macros.execute(
            "SELECT * FROM ast_select_render(?, '.func')",
            [f"{PROJECT_ROOT}/fledgling/connection.py"],
        ).fetchone()
        md_text = row[0]
        # At least one level-2 heading per match
        assert "## " in md_text
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_workflows.py::TestAstSelectRender -v
```
Expected: all three tests FAIL (`ast_select_render` does not exist yet).

- [ ] **Step 3: Append the macro to `sql/workflows.sql`**

```sql
-- ast_select_render: Render selector query results as markdown with
-- a selector-level heading and per-match sub-headings.
--
-- Matches lackpy's AstSelectInterpreter output format. Differs from
-- pss_render by grouping all matches under one selector heading.
--
-- Depends on: sitting_duck (ast_select, ast_get_source),
--             markdown (duck_blocks_to_md).
--
-- Examples:
--   SELECT * FROM ast_select_render('**/*.py', '.func#validate');
--   SELECT * FROM ast_select_render('src/**/*.py', '.class::callers');
CREATE OR REPLACE MACRO ast_select_render(source, selector) AS TABLE
    WITH
        header AS (
            SELECT [{
                kind: 'heading',
                element_type: 'heading',
                content: '`' || selector || '`',
                level: 1,
                encoding: 'plain',
                attributes: MAP{},
                element_order: 0
            }::STRUCT(kind VARCHAR, element_type VARCHAR, "content" VARCHAR, "level" INTEGER, "encoding" VARCHAR, attributes MAP(VARCHAR, VARCHAR), element_order INTEGER)] AS items
        ),
        matches AS (
            SELECT
                file_path,
                start_line,
                end_line,
                COALESCE(language, 'text') AS language,
                COALESCE(qualified_name, name) AS symbol,
                ast_get_source(file_path, start_line, end_line) AS source_text,
                row_number() OVER (ORDER BY file_path, start_line) AS ord
            FROM ast_select(source, selector)
        ),
        match_blocks AS (
            -- Two blocks per match: sub-heading + code
            SELECT LIST({
                kind: 'heading',
                element_type: 'heading',
                content: m.symbol || ' — ' || m.file_path || ':' || m.start_line || '-' || m.end_line,
                level: 2,
                encoding: 'plain',
                attributes: MAP{},
                element_order: m.ord * 2
            }::STRUCT(kind VARCHAR, element_type VARCHAR, "content" VARCHAR, "level" INTEGER, "encoding" VARCHAR, attributes MAP(VARCHAR, VARCHAR), element_order INTEGER))
            ||
            LIST({
                kind: '<CODE_KIND>',
                element_type: '<CODE_ELEMENT_TYPE>',
                content: m.source_text,
                level: 0,
                encoding: '<CODE_ENCODING>',
                attributes: MAP{'language': m.language},
                element_order: m.ord * 2 + 1
            }::STRUCT(kind VARCHAR, element_type VARCHAR, "content" VARCHAR, "level" INTEGER, "encoding" VARCHAR, attributes MAP(VARCHAR, VARCHAR), element_order INTEGER))
                AS items
            FROM matches m
        )
    SELECT duck_blocks_to_md(
        header.items || match_blocks.items
    ) AS result
    FROM header, match_blocks;
```

Replace `<CODE_*>` placeholders as before. Same caveat about LIST aggregation idioms.

- [ ] **Step 4: Run the test to verify it passes**

```bash
python -m pytest tests/test_workflows.py::TestAstSelectRender -v
```
Expected: all three tests PASS.

- [ ] **Step 5: Commit**

```bash
git add sql/workflows.sql tests/test_workflows.py && \
git commit -m "feat: add ast_select_render macro — selector heading + per-match blocks"
```

---

## Task 4: Publish as MCP tools

**Files:**
- Modify: `sql/tools/workflows.sql` — append two new tool publications

- [ ] **Step 1: Append tool publications**

Add to the end of `sql/tools/workflows.sql`:

```sql
PRAGMA mcp_publish_tool(
    'PssRender',
    'Render selector query results as markdown. Each match becomes a file:range heading followed by a code block with the source text. Use to view code matched by a CSS selector with full context.',
    'SELECT * FROM pss_render(
        _resolve($source),
        $selector
    )',
    '{"source": {"type": "string", "description": "Glob pattern for files to search (e.g. src/**/*.py)"}, "selector": {"type": "string", "description": "CSS selector: .func, #name, :has(...), ::callers, etc."}}',
    '["source", "selector"]',
    'text'
);

PRAGMA mcp_publish_tool(
    'AstSelectRender',
    'Render selector query results grouped under a selector heading with per-match sub-headings. Same matches as PssRender but with lackpy-compatible output layout.',
    'SELECT * FROM ast_select_render(
        _resolve($source),
        $selector
    )',
    '{"source": {"type": "string", "description": "Glob pattern for files to search (e.g. src/**/*.py)"}, "selector": {"type": "string", "description": "CSS selector: .func, #name, :has(...), ::callers, etc."}}',
    '["source", "selector"]',
    'text'
);
```

**Format choice:** `'text'` — both macros return a single markdown string in a single column, not a structured table. Line-oriented text output (one line per row, first column only) is the cleanest MCP output for this.

- [ ] **Step 2: Verify the tool publications parse**

```bash
python << 'EOF'
import duckdb, os, re
REPO = '/mnt/aux-data/teague/Projects/source-sextant/main'
c = duckdb.connect()
for ext in ['duckdb_mcp', 'read_lines', 'sitting_duck', 'markdown', 'duck_tails']:
    c.execute(f'LOAD {ext}')
c.execute(f"CREATE OR REPLACE MACRO _resolve(p) AS CASE WHEN p IS NULL THEN NULL WHEN p[1] = '/' THEN p ELSE '{REPO}/' || p END")
c.execute(f"CREATE OR REPLACE MACRO _session_root() AS '{REPO}'")
c.execute(f"SET VARIABLE session_root = '{REPO}'")
def load(f):
    for stmt in open(os.path.join(REPO, 'sql', f)).read().split(';'):
        s = stmt.strip()
        if s and not s.startswith('--'):
            c.execute(s + ';')
load('sandbox.sql')
load('source.sql')
load('code.sql')
load('docs.sql')
load('repo.sql')
load('structural.sql')
load('workflows.sql')
load('tools/workflows.sql')
print('6 tool publications registered (was 4, +PssRender +AstSelectRender)')
EOF
```

Expected: runs without error.

- [ ] **Step 3: Commit**

```bash
git add sql/tools/workflows.sql && \
git commit -m "feat: publish PssRender and AstSelectRender as MCP tools"
```

---

## Task 5: Integration check

**Files:** none modified

Final verification that everything works together.

- [ ] **Step 1: Run the full workflows test suite**

```bash
python -m pytest tests/test_workflows.py -v
```
Expected: 14 (Plan 2a) + 4 (Task 2) + 3 (Task 3) = 21 tests pass.

- [ ] **Step 2: Run the full connection test suite**

```bash
python -m pytest tests/test_connection.py -v
```
Expected: same 20-ish tests pass that passed before Plan 2b. No regression.

- [ ] **Step 3: Smoke test MCP tool invocation via a subprocess server**

Skip this step if `test_mcp_server.py` is not currently runnable in the environment. Otherwise:

```bash
python -m pytest tests/test_mcp_server.py -v -k 'PssRender or AstSelectRender'
```

- [ ] **Step 4: Final commit (if any further changes)**

No final commit needed if the previous steps were clean. Otherwise:

```bash
git add -A && git commit -m "chore: Plan 2b complete — pss_render + ast_select_render"
```

---

## Post-completion state

- `sql/workflows.sql` has 6 macros: the 4 `*_query` briefings + `pss_render` + `ast_select_render`
- `sql/tools/workflows.sql` publishes 6 MCP tools
- `tests/test_workflows.py` has ~21 tests
- `tests/conftest.py` no longer uses `load_sql_filtered` for code.sql
- lackpy's `AstSelectInterpreter` Python-side markdown building becomes a candidate for deletion (tracked in the pluckit integration plan, not this one)

## Open questions / follow-ups

- **Format parameter** — once `webbed` + `duck_blocks_to_html` integration is validated, add `format := 'markdown' | 'html'` to both macros. Separate plan.
- **Multi-rule pss sheets** — the original pss concept was a table of (selector, show_mode) rows with `db_blocks_merge`. Deferred. Requires regex sheet parser macro.
- **Interactive HTML viewer (the "lens/umwelt" idea)** — one macro parameter away once HTML output works. Separate plan.

## Cross-references

- **Fledgling reorg design:** `/mnt/aux-data/teague/Projects/source-sextant/main/docs/superpowers/specs/2026-04-10-fledgling-reorg-design.md`
- **Plan 2a (workflow query macros, shipped):** commit `0b5e69c`
- **Plan 2c (connection API refinements, shipped):** commit `77563aa`
- **Lackpy reorg-prep (original sketch):** `/home/teague/Projects/lackpy/trees/feature/interpreter-plugins/docs/superpowers/specs/2026-04-10-sql-macro-reorg-prep.md`
