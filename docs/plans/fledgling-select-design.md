# Fledgling Select: CSS Selector-Based Code Query API

**Date:** 2026-04-04
**Status:** Design
**Depends on:** sitting_duck `ast_select` (not yet in community extensions)

## Vision

One selector engine as the universal query primitive. Everything else — traversal, filtering, analysis, editing — composes on top of selection results.

Inspired by jQuery/Sizzle: selection is the primitive, methods operate on the result set.

```python
# Python
from fledgling import F

F(".func#parse_config").callers().show()
F(".func:has(.call#execute):not(:has(try_statement))").show()
F(".call#print").count()
```

```typescript
// TypeScript (same fluent API shape)
F(".func#parse_config").callers().show()
F(".func:has(.call#execute):not(:has(try_statement))").show()
F(".call#print").count()
```

```sql
-- SQL (raw power)
SELECT * FROM ast_select('**/*.py', '.func#parse_config::callers');
```

## Design Principles

1. **Selector is the primitive.** No separate APIs for "find functions,"
   "find callers," "find imports." One selector engine, composable methods.

2. **Selector string OR fluent chain — both valid.** These are equivalent:
   ```python
   F(".func::parent")           # pseudo-element in selector
   F(".func").parent()          # method on result set
   ```

3. **Language-agnostic API shape.** The fluent interface works in Python,
   TypeScript, Rust, etc. No Python-specific magic. The selector string
   is the universal format.

4. **Read and write through the same selection.** Fledgling reads,
   fledgling-edit writes — but both start with a selection:
   ```python
   F(".func#old").show()                    # read
   F(".func#old").rename("new")             # write (fledgling-edit)
   ```

5. **Lazy evaluation.** Selections build up a query plan. Execution
   happens on terminal methods (`.show()`, `.df()`, `.count()`, `.apply()`).

## The `F()` Entry Point

`F` is a short alias for "fledgling select." It creates a `Selection` object.

```python
from fledgling import F

# File pattern defaults to project defaults (from ProjectDefaults)
F(".func")                        # all functions in default code files
F(".func", "src/**/*.py")         # explicit file pattern
F(".func#main", "src/app.py")     # specific file
```

Under the hood:
```python
# F is just a convenience constructor
def F(selector: str, pattern: str = None) -> Selection:
    con = _get_default_connection()
    pattern = pattern or con._defaults.code_pattern
    return Selection(con, pattern, selector)
```

For explicit connection control:
```python
con = fledgling.connect(root="/path/to/project")
con.select(".func#main")  # same as F(".func#main") but with explicit connection
```

## Selection Object

The core abstraction. Wraps a selector string + file pattern and provides
chaining methods. Lazy — builds up a query plan, executes on terminal methods.

### Creation

```python
sel = F(".func")                    # from selector string
sel = F(".func:has(.call#execute)") # compound selector
sel = con.select(".func")           # from connection
```

### Traversal Methods

Each returns a new `Selection`:

```python
sel.parent()          # → ".func::parent"
sel.children()        # → ".func > *"
sel.descendants()     # → ".func *"
sel.siblings()        # → ".func ~ *"
sel.next()            # → ".func + *"
sel.callers()         # → ".func::callers"
sel.callees()         # → ".func::callees"
sel.scope()           # → enclosing scope (function/class/module)
```

Equivalence with selector syntax:
```python
# These pairs are equivalent:
F(".func").callers()           ↔  F(".func::callers")
F(".func").parent()            ↔  F(".func::parent")
F(".func").children()          ↔  F(".func > *")
F(".func").callers().filter(":has(try_statement)")
                               ↔  F(".func::callers:has(try_statement)")
```

### Filtering Methods

Narrow the selection:

```python
sel.filter(".async")           # add selector condition
sel.filter(":has(.call)")      # has-descendant
sel.exclude(":has(try)")       # :not wrapper
sel.named("parse%")            # name LIKE filter
sel.first()                    # :first-child
sel.last()                     # :last-child
sel.nth(3)                     # :nth-child(3)
sel.limit(10)                  # SQL LIMIT
```

### Terminal Methods (trigger execution)

```python
sel.show()                     # print formatted results
sel.df()                       # → pandas DataFrame
sel.fetchall()                 # → list of tuples
sel.count()                    # → int
sel.exists()                   # → bool
sel.one()                      # → single result or error
sel.names()                    # → list of name strings
sel.files()                    # → list of file_path strings
sel.lines()                    # → list of (file, start, end) tuples
```

### Content Methods

Read the selected code:

```python
sel.source()                   # → source text of each selected region
sel.peek()                     # → one-line preview of each
sel.context(n=5)               # → source with n lines of context
```

### Analysis Methods

```python
sel.complexity()               # → cyclomatic complexity for functions
sel.metrics()                  # → all AST metrics
sel.deps()                     # → what this code imports/depends on
sel.refs()                     # → all references to the selected names
```

### Edit Methods (fledgling-edit integration)

```python
sel.rename("new_name")         # rename all selected definitions
sel.remove()                   # delete all selected nodes
sel.replace("new code")        # replace content
sel.wrap("try:", "except: pass")
sel.move_to("other_file.py")
sel.preview()                  # show diff without applying
sel.apply()                    # write changes
```

## Selector Syntax Reference

### Type Selectors (three tiers)

```
.func                          semantic (cross-language)
function_definition            bare keyword (language prefix match)
function_definition[python]    exact tree-sitter type
```

### Name Filter

```
.func#main                     exact name match
.func[name^=parse]             name starts with "parse"
.func[name$=_test]             name ends with "_test"
.func[name*=config]            name contains "config"
```

### Pseudo-classes

```
:has(selector)                 contains descendant matching selector
:not(selector)                 negation
:first-child                   first among siblings
:last-child                    last among siblings
:nth-child(n)                  nth among siblings
:named                         has a non-empty name
:definition                    is any kind of definition
:scope                         is a scope boundary
:root                          top-level (depth 0-1)
```

### Pseudo-elements

```
::parent                       parent node
::callers                      functions that call this
::callees                      functions this calls
::refs                         references to this definition
::scope                        enclosing scope
```

### Combinators

```
A B                            B is descendant of A
A > B                          B is direct child of A
A ~ B                          B is sibling after A
A + B                          B is adjacent sibling after A
```

## Implementation Sketch

### Python

```python
class Selection:
    def __init__(self, con, pattern, selector):
        self._con = con
        self._pattern = pattern
        self._selector = selector
        self._chain = []  # deferred operations

    def callers(self) -> Selection:
        return self._append_pseudo("::callers")

    def filter(self, condition) -> Selection:
        return self._append_filter(condition)

    def show(self):
        sql = self._compile()
        self._con.sql(sql).show()

    def df(self):
        sql = self._compile()
        return self._con.sql(sql).df()

    def _compile(self) -> str:
        """Build the final SQL from selector + chain."""
        selector = self._selector
        for op in self._chain:
            selector = op.apply(selector)
        return f"SELECT * FROM ast_select('{self._pattern}', '{selector}')"
```

### Key Design Decision: Chain Compiles to Selector String

The fluent chain doesn't generate SQL joins or subqueries. It modifies
the selector string. `F(".func").callers().filter(":has(try)")` compiles to
`ast_select(pattern, '.func::callers:has(try)')`.

This means:
- sitting_duck handles all the query optimization
- The Python layer is just selector string construction
- The same compiled selector works in SQL, TypeScript, CLI, etc.
- No N+1 query problems from chaining

Exception: terminal methods that need post-processing (`.source()`,
`.complexity()`) add SQL wrapping around the `ast_select` call.

## Cross-Language API

The `Selection` API is designed to work in any language:

```python
# Python
F(".func:has(.call#execute)").callers().show()
```

```typescript
// TypeScript
F(".func:has(.call#execute)").callers().show()
```

```ruby
# Ruby
F(".func:has(.call#execute)").callers.show
```

The selector string is the universal format. The fluent methods are
syntactic sugar that compile back to selector strings.

### CLI

```bash
fledgling select '.func:has(.call#execute)' --callers --show
fledgling select '.func#validate::callers:has(try_statement)' -f csv
```

## Migration Path

### Phase 1: `con.select()` wrapping `ast_select`

Add `Selection` class and `F()` entry point. Terminal methods call
`ast_select` directly. No changes to existing tools.

### Phase 2: Existing tools use `select` internally

`find_definitions` becomes `select(':definition:named:root')`.
`find_in_ast` becomes `select('.{kind}')`.
`function_callers` becomes `select('.func#name::callers')`.

Existing tools remain as convenience wrappers — they're common
selectors with good defaults.

### Phase 3: Edit integration

`fledgling-edit` operations take selections:
```python
F(".call#print").replace_each("logger.info(__ARGS__)")
```

### Phase 4: Cross-file graph

`::callers` and `::callees` gain cross-file resolution via
`ast_imports`/`ast_exports` JOIN.

## Open Questions

1. **Default file pattern** — should `F(".func")` search everything,
   or default to `ProjectDefaults.code_pattern`? jQuery defaults to
   the whole document. But "all files" is expensive for code.

2. **Result type** — should terminal methods return DuckDBPyRelation
   (composable) or plain data (list/DataFrame)? Relation is more
   powerful but leaks DuckDB abstraction.

3. **Async** — should the API be async-first for the FastMCP server?
   Or sync-first with async wrappers?

4. **Caching** — should `F(".func")` cache the AST parse? Repeated
   selectors on the same files could reuse the parsed AST.

5. **Error messages** — when a selector returns nothing, should we
   suggest corrections? ("No `.func#main` found. Did you mean
   `.func#Main` or `.func[name*=main]`?")
