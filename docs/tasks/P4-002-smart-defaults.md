# P4-002: Smart Defaults — Project-Aware Tool Configuration

## Status: Done

## Problem

Agents waste tool calls with wrong patterns: `find_definitions('**/*.py')` in a Rust project, `doc_outline('docs/**/*.md')` when docs are in `documentation/`. The tools work but return empty results, costing a round trip.

## Solution

On server startup, analyze the project and cache smart defaults:
- Dominant language → default glob pattern for code tools
- Documentation directory → default pattern for doc tools
- Git default branch → default for diff comparisons

Tools accept explicit patterns (no behavior change) but use smart defaults when called without patterns.

## Defaults to Infer

### Code tools default pattern
```python
# From project_overview(), pick top language by file count
# python → '**/*.py', rust → '**/*.rs', typescript → '**/*.{ts,tsx}'
_default_code_pattern = infer_code_pattern(project_overview)
```

Used by: `find_definitions`, `find_in_ast`, `code_structure`, `complexity_hotspots`

### Doc tools default pattern
```python
# Search for common doc directories
# Check: docs/, documentation/, doc/, wiki/, then fall back to '**/*.md'
_default_doc_pattern = find_doc_directory(list_files)
```

Used by: `doc_outline`, `read_doc_section`

### Git defaults
```python
# Default comparison: last commit vs working tree
_default_from_rev = "HEAD~1"
_default_to_rev = "HEAD"
```

Used by: `file_changes`, `file_diff`, `changed_function_summary`

## Implementation

```python
class ProjectDefaults:
    """Inferred at server startup, cached for the session."""
    code_pattern: str      # '**/*.py'
    doc_pattern: str       # 'docs/**/*.md'
    main_branch: str       # 'main'
    languages: list[str]   # ['python', 'sql']

def _infer_defaults(con: Connection) -> ProjectDefaults:
    overview = con.project_overview().fetchall()
    # Top language by file count (skip binary/config)
    ...
```

Tools check for empty/None patterns and substitute defaults:
```python
async def find_definitions(file_pattern: str = None, ...):
    if file_pattern is None:
        file_pattern = defaults.code_pattern
    ...
```

## Testing

- Default code pattern matches dominant language
- Default doc pattern finds actual docs directory
- Explicit patterns override defaults
- Empty project gets reasonable fallbacks
- Defaults cached (no repeated queries)

## Files

- Modify: `fledgling/pro/server.py`
- Add: `fledgling/pro/defaults.py`
- Add tests: `tests/test_pro_defaults.py`
