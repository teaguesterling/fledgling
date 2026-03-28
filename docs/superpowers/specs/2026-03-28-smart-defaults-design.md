# P4-002: Smart Defaults Design

## Problem

Agents waste tool calls with wrong patterns (`find_definitions('**/*.py')` in a
Rust project). Tools work but return empty results, costing a round trip.

## Solution

Infer project-aware defaults at server startup. Tools use these when called
without explicit patterns. Explicit parameters always override.

Users can override inferred defaults via `.fledgling-python/config.toml`.

## `ProjectDefaults` Dataclass

```python
@dataclass
class ProjectDefaults:
    code_pattern: str      # '**/*.py' or '**/*.{ts,tsx}'
    doc_pattern: str       # 'docs/**/*.md'
    main_branch: str       # 'main'
    languages: list[str]   # ['python', 'sql']
```

## Inference Logic

### Code pattern (`infer_code_pattern`)

1. Query `project_overview()` — returns `(language, extension, file_count)`
2. Group by language, sum file counts, take the top language
3. Collect all extensions for that language
4. Build glob: `**/*.{ext1,ext2}` (or `**/*.ext` if single extension)

A hardcoded `language → [extensions]` mapping covers common languages for now.
This will be replaced by sitting_duck's language/extension listing when
available (sitting_duck#56 or similar).

### Doc pattern (`infer_doc_pattern`)

1. Check for directories: `docs/`, `documentation/`, `doc/`, `wiki/` (in order)
2. First match: `<dir>/**/*.md`
3. No match: `**/*.md`

Detection uses `list_files()` with shallow globs to check directory existence.

### Git defaults

Static: `from_rev = "HEAD~1"`, `to_rev = "HEAD"`. No inference needed.

### Main branch

Read from `git rev-parse --abbrev-ref origin/HEAD` or fall back to `main`.
Not inferred from DuckDB — this is a git operation.

## Config File: `.fledgling-python/config.toml`

```toml
[defaults]
code_pattern = "src/**/*.rs"
doc_pattern = "documentation/**/*.md"
main_branch = "develop"
```

All keys optional. Config values override inferred values. Explicit tool
call parameters override everything.

Priority: explicit param > config file > inferred > fallback

## Tool-to-Default Mapping

```python
TOOL_DEFAULTS: dict[str, dict[str, str]] = {
    # tool_name → {param_name: defaults_field}
    "find_definitions":         {"file_pattern": "code_pattern"},
    "find_in_ast":              {"file_pattern": "code_pattern"},
    "code_structure":           {"file_pattern": "code_pattern"},
    "complexity_hotspots":      {"file_pattern": "code_pattern"},
    "doc_outline":              {"path": "doc_pattern"},
    "read_doc_section":         {"path": "doc_pattern"},
    "file_changes":             {"from_rev": "from_rev", "to_rev": "to_rev"},
    "file_diff":                {"from_rev": "from_rev", "to_rev": "to_rev"},
    "changed_function_summary": {"from_rev": "from_rev", "to_rev": "to_rev"},
}
```

Note: actual param names will be verified against the macro signatures during
implementation.

## `apply_defaults(defaults, tool_name, kwargs) -> kwargs`

- Looks up tool in `TOOL_DEFAULTS`
- For each mapped param, if the value is `None`, substitutes from `defaults`
- Returns modified kwargs (or original if no mapping exists)

## File Changes

### New: `fledgling/pro/defaults.py`

- `ProjectDefaults` dataclass
- `TOOL_DEFAULTS` mapping
- `LANGUAGE_EXTENSIONS` mapping (hardcoded for now)
- `infer_defaults(con: Connection) -> ProjectDefaults`
- `load_config(root: Path) -> dict`
- `apply_defaults(defaults, tool_name, kwargs) -> kwargs`

### Modify: `fledgling/pro/server.py`

- Import defaults module
- Call `infer_defaults(con)` + `load_config(root)` in `create_server()`
- In `_register_tool()` wrapper, call `apply_defaults()` before macro execution

### New: `tests/test_pro_defaults.py`

- Inferred code pattern matches dominant language
- Inferred doc pattern finds actual docs directory
- Config file overrides inferred values
- Explicit tool params override defaults
- Empty/missing project gets reasonable fallbacks
- Missing config file is fine (all inferred)
- `TOOL_DEFAULTS` mapping covers all expected tools

## Non-Goals

- Renaming `fledgling/pro/` to `fledgling-python/` (separate task)
- Dynamic re-inference during a session (defaults are cached at startup)
- Inferring defaults for tools not listed in the mapping
