# Full-Text Search

**Extension**: [`fts`](https://duckdb.org/docs/current/core_extensions/full_text_search) (bundled)

BM25-based lexical search across markdown documentation and code (definitions, comments, and string literals). Extracted chunks live in a single `fts.content` table and are scored via DuckDB's built-in inverted-index implementation.

Complementary to existing grep-style and AST-structural macros — this is the "find things containing these words" axis, where `find_definitions` answers "find the `parse_config` function" and `search_code` answers "find any code mentioning authentication".

## At a glance

Timings from this repo (~70 files, 6,000 indexed chunks, DuckDB 1.5.1):

| Operation | Time |
|---|---|
| `fledgling.connect()` (cold, loads all modules) | ~6.3 s |
| `rebuild_fts()` (full corpus re-index) | ~2.7 s |
| `search_content('lockdown')` | ~25 ms |
| `search_code('function_callers', filter_kind := 'definition')` | ~23 ms |

Rebuild is a **manual** operation. The FTS index doesn't track source changes — call `rebuild_fts()` after files change. This is a known DuckDB FTS limitation, not an oversight.

## Data shape: `fts.content`

One row per indexed chunk. Deliberately under-specified so new extractors can be added without schema churn.

| Column | Type | Description |
|---|---|---|
| `id` | `BIGINT` | Primary key, assigned at rebuild time |
| `file_path` | `VARCHAR` | Absolute path to the source file |
| `start_line` / `end_line` | `INTEGER` | Location within the source file |
| `extractor` | `VARCHAR` | `'markdown'` or `'sitting_duck'` |
| `kind` | `VARCHAR` | `'doc_section'`, `'definition'`, `'comment'`, `'string'` |
| `name` | `VARCHAR` | Displayable identifier (symbol name or heading title; `NULL` for comments/strings) |
| `ordinal` | `INTEGER` | Extractor-defined opaque int (heading level for markdown, AST `node_id` for sitting_duck) |
| `attrs` | `JSON` | Per-extractor extras (`semantic_type`, `heading_path`, etc.) |
| `text` | `VARCHAR` | The searchable content — BM25 index target |

Storage location follows the current connection. An in-memory DuckDB gives an ephemeral index; a file-backed DuckDB persists it (though you still need to rebuild after source changes).

## Rebuild

### SQL script

```sql
-- Defaults: '**/*.md' and '**/*.py'
.read sql/fts_rebuild.sql

-- Or narrow the scope
SET VARIABLE fts_code_glob = 'src/**/*.py';
SET VARIABLE fts_docs_glob = 'docs/**/*.md';
.read sql/fts_rebuild.sql
```

### Python API

```python
import fledgling
con = fledgling.connect(root='.')
con.rebuild_fts()                              # defaults
con.rebuild_fts(code_glob='src/**/*.py')       # narrow code scope
con.rebuild_fts(docs_glob='README.md')         # single doc file
```

The rebuild:
1. `DELETE FROM fts.content`
2. Inserts fresh rows from markdown sections (via `read_markdown_sections`), AST definitions / comments / strings (via `read_ast`)
3. Dedupes tree-sitter's nested string nodes (outer vs. `string_content`) using `QUALIFY`
4. Rebuilds the BM25 index with `PRAGMA create_fts_index(..., overwrite = 1)`

## Search macros

### `search_content`

Unified BM25 search across all indexed content. Optional filters narrow by kind or extractor.

```sql
search_content(query, filter_kind := NULL, filter_extractor := NULL, limit_n := 20)
```

**Returns**: all columns from `fts.content`, plus `score` (BM25, higher = better match). Ordered by score descending.

```sql
-- Ranked hits across docs and code
SELECT file_path, kind, name, score
FROM search_content('session_root sandbox');

-- Only docs
SELECT * FROM search_content('authentication', filter_kind := 'doc_section');

-- Only code, limit to 5
SELECT * FROM search_content('retry', filter_extractor := 'sitting_duck', limit_n := 5);
```

### `search_docs`

Thin wrapper that pins `filter_kind := 'doc_section'`. Example:

```sql
SELECT file_path, name AS heading, score
FROM search_docs('session_root sandbox', 5);
```

Output on this repo:

```
file                              lines    score  text
P2-005-init-and-config.md         40-71     3.56  sql/sandbox.sql … Optional: override
P2-005-init-and-config.md         91-98     3.20  What's sandboxed … All `read_lines`…
P2-005-init-and-config.md         14-22     2.94  Files … | File | Action | …
```

### `search_code`

BM25 over code chunks. Filter by `kind` (`'definition'`, `'comment'`, `'string'`).

```sql
SELECT file_path, start_line, name, score
FROM search_code('function_callers', filter_kind := 'definition');
```

Output:

```
file                              line  name                              score
test_code.py                       317  test_caller_is_enclosing_function  5.18
test_connection.py                 320  test_find_definitions_and_callers  3.20
test_code.py                       300  test_finds_callers                 3.20
test_e2e_integration.py            188  test_find_functions                2.34
```

Kind examples:

```sql
-- Only docstrings and string constants (includes Python triple-quoted strings)
SELECT * FROM search_code('SELECT FROM read_ast', filter_kind := 'string');

-- Only line comments
SELECT * FROM search_code('workaround', filter_kind := 'comment');
```

### `find_code_ranked`

Composition of `ast_select` (structural) with FTS (lexical ranking). Pass a structural selector AND a BM25 query; results are all the nodes matching the selector that also appear in `fts.content`, ordered by relevance.

```sql
find_code_ranked(file_pattern, selector, fts_query, lang := NULL)
```

**Returns**: `file_path`, `start_line`, `end_line`, `name`, `kind`, `node_type`, `peek`, `score`

This is the "fuzzy front door for structural navigation" — where `find_definitions` demands a name prefix and `search_code` has no structural constraint, `find_code_ranked` gives you "all functions, ranked by how well they match this concept":

```sql
-- Functions most relevant to 'function_callers'
SELECT name, score
FROM find_code_ranked('**/*.py', '.func', 'function_callers')
LIMIT 5;
```

```
file                       line  name                               score
test_code.py                317  test_caller_is_enclosing_function   5.11
test_code.py                300  test_finds_callers                  3.14
test_connection.py          320  test_find_definitions_and_callers   3.14
test_e2e_integration.py     188  test_find_functions                 2.32
test_e2e_integration.py     211  test_view_functions                 2.32
```

**How it works**: `ast_select` returns rows with `node_id`. Each code row in `fts.content` has `ordinal = node_id`. A JOIN on `(file_path, ordinal = node_id)` bridges the two, then `match_bm25()` scores each match.

**Coverage**: only rows that also exist in `fts.content` are returned. Selectors that match kinds we don't index (`.loop`, `.if`, `.call`) will yield zero rows regardless of the query.

**Cost**: `ast_select` re-parses the matched files, so `find_code_ranked` is slower than `search_code` (~500ms vs. ~25ms on this repo). If you already know you want a lexical answer, prefer `search_code`. Use this when the structural constraint matters.

### `fts_stats`

Diagnostic macro — row and file counts per extractor/kind. No index required.

```sql
SELECT * FROM fts_stats();
```

```
 extractor     | kind        | row_count | file_count
---------------+-------------+-----------+-----------
 markdown      | doc_section |       989 |         72
 sitting_duck  | comment     |       589 |         56
 sitting_duck  | definition  |      1408 |         60
 sitting_duck  | string      |      3225 |         64
```

## MCP tools

Four tools are published in all profiles:

| Tool | Purpose |
|---|---|
| **SearchContent** | Unified BM25 search with kind/extractor filters |
| **SearchDocs** | BM25 over markdown sections |
| **SearchCode** | BM25 over code (definition/comment/string) |
| **FtsStats** | Counts of what's currently indexed — check before searching |

All four require a populated index. If agents call `SearchContent` before `rebuild_fts()` has run, they'll get a clear "function does not exist" error directing them to rebuild.

## Caveats

- **Manual rebuild.** The FTS index doesn't update when `fts.content` changes. Call `rebuild_fts()` after source file edits or re-run the SQL script. See [duckdb/duckdb#3543](https://github.com/duckdb/duckdb/issues/3543) for the upstream limitation.
- **Tokenization.** BM25 uses the default FTS tokenizer (Porter stemmer, English stopwords, lowercase, strips accents). Queries like `'zzzzzzzz_xyzzy'` get split on non-alphanumerics. A literal multi-word phrase won't require all words unless you pass `conjunctive := 1` (DuckDB feature — not yet exposed in our macros; easy to add).
- **Self-matching on dogfooded test data.** Test files that mention search terms as string literals will match themselves. Mostly harmless; use computed terms in assertions about "no matches".
- **String dedup.** Tree-sitter reports nested string nodes (outer literal + `string_content`). The rebuild keeps only the longest per `(file, line span)`, which is the outer quoted form. You'll see `"template"` in results, not a separate `template` row.
- **Extension stub index.** `sql/fts.sql` creates an empty index at load time so the search macros can reference `fts_fts_content.match_bm25` without errors. Running on a persistent DB with an already-populated index: the stub replaces the real index, so rebuild after reconnect. (If this becomes painful we can add a "skip if already built" Python guard.)

## Design notes

- **One table, many extractors.** Rather than a separate table per kind, one `fts.content` table with a discriminator (`extractor`, `kind`) and opaque extensibility (`name`, `ordinal`, `attrs`). Adding a new extractor (e.g. conversation messages, SQL macro definitions) is an INSERT path change, not a schema change.
- **Storage is caller-controlled.** Fledgling doesn't pick `.fledgling/index.db` — whatever database you've opened or ATTACHed holds the index.
- **Complement to AST and grep, not a replacement.** `find_definitions` answers "where is this symbol defined" (structural); `search_code` answers "what mentions these words" (lexical). Use both.
