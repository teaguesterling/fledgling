# Smart Defaults Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Infer project-aware default patterns at server startup so tools return useful results without explicit globs.

**Architecture:** A `ProjectDefaults` dataclass holds inferred/configured defaults. `infer_defaults()` queries the project via fledgling macros. `.fledgling-python/config.toml` overrides inferred values. `apply_defaults()` substitutes `None` params before macro execution in `server.py`.

**Tech Stack:** Python 3.10+, dataclasses, tomllib (stdlib), fledgling Connection, pytest

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `fledgling/pro/defaults.py` | Create | `ProjectDefaults` dataclass, inference logic, config loading, default application |
| `fledgling/pro/server.py` | Modify | Wire defaults into `create_server()` and `tool_fn` wrapper |
| `tests/test_pro_defaults.py` | Create | All tests for defaults inference, config, and application |

## Macro Parameter Names (verified from SQL)

These are the actual parameter names the defaults must target:

| Macro | Param(s) to default | Default field |
|-------|---------------------|---------------|
| `find_definitions` | `file_pattern` | `code_pattern` |
| `find_in_ast` | `file_pattern` | `code_pattern` |
| `code_structure` | `file_pattern` | `code_pattern` |
| `complexity_hotspots` | `file_pattern` | `code_pattern` |
| `changed_function_summary` | `file_pattern` | `code_pattern` |
| `doc_outline` | `file_pattern` | `doc_pattern` |
| `file_changes` | `from_rev`, `to_rev` | `from_rev`, `to_rev` |
| `file_diff` | `from_rev`, `to_rev` | `from_rev`, `to_rev` |
| `structural_diff` | `from_rev`, `to_rev` | `from_rev`, `to_rev` |

Note: `read_doc_section` takes `file_path` + `target_id` (both required, no
sensible default). `changed_function_summary` also has `from_rev`/`to_rev` but
`file_pattern` is the more useful default since git revs are already defaulted.

---

### Task 1: `ProjectDefaults` dataclass and `TOOL_DEFAULTS` mapping

**Files:**
- Create: `fledgling/pro/defaults.py`
- Test: `tests/test_pro_defaults.py`

- [ ] **Step 1: Write tests for ProjectDefaults and TOOL_DEFAULTS**

```python
"""Tests for fledgling.pro.defaults — smart project-aware defaults."""

from fledgling.pro.defaults import ProjectDefaults, TOOL_DEFAULTS


class TestProjectDefaults:
    """ProjectDefaults dataclass basics."""

    def test_defaults_has_expected_fields(self):
        d = ProjectDefaults(
            code_pattern="**/*.py",
            doc_pattern="docs/**/*.md",
            main_branch="main",
            languages=["python"],
        )
        assert d.code_pattern == "**/*.py"
        assert d.doc_pattern == "docs/**/*.md"
        assert d.main_branch == "main"
        assert d.languages == ["python"]

    def test_defaults_fallback_values(self):
        """Fallback defaults when nothing can be inferred."""
        d = ProjectDefaults()
        assert d.code_pattern == "**/*"
        assert d.doc_pattern == "**/*.md"
        assert d.main_branch == "main"
        assert d.languages == []


class TestToolDefaults:
    """TOOL_DEFAULTS maps tool names to (param, defaults_field) pairs."""

    def test_code_tools_mapped(self):
        code_tools = [
            "find_definitions", "find_in_ast", "code_structure",
            "complexity_hotspots", "changed_function_summary",
        ]
        for tool in code_tools:
            assert tool in TOOL_DEFAULTS
            assert "file_pattern" in TOOL_DEFAULTS[tool]
            assert TOOL_DEFAULTS[tool]["file_pattern"] == "code_pattern"

    def test_doc_tools_mapped(self):
        assert "doc_outline" in TOOL_DEFAULTS
        assert TOOL_DEFAULTS["doc_outline"]["file_pattern"] == "doc_pattern"

    def test_git_tools_mapped(self):
        git_tools = ["file_changes", "file_diff", "structural_diff"]
        for tool in git_tools:
            assert tool in TOOL_DEFAULTS
            assert TOOL_DEFAULTS[tool]["from_rev"] == "from_rev"
            assert TOOL_DEFAULTS[tool]["to_rev"] == "to_rev"
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_pro_defaults.py"])`
Expected: ImportError — `fledgling.pro.defaults` does not exist yet.

- [ ] **Step 3: Implement ProjectDefaults and TOOL_DEFAULTS**

```python
"""Smart project-aware defaults for fledgling-pro tools.

Infers sensible default patterns (code globs, doc paths, git revisions)
from the project at server startup. Users can override via
.fledgling-python/config.toml. Explicit tool parameters always win.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProjectDefaults:
    """Inferred at server startup, cached for the session."""

    code_pattern: str = "**/*"
    doc_pattern: str = "**/*.md"
    main_branch: str = "main"
    from_rev: str = "HEAD~1"
    to_rev: str = "HEAD"
    languages: list[str] = field(default_factory=list)


# Tool name → {param_name: defaults_field_name}
TOOL_DEFAULTS: dict[str, dict[str, str]] = {
    "find_definitions":         {"file_pattern": "code_pattern"},
    "find_in_ast":              {"file_pattern": "code_pattern"},
    "code_structure":           {"file_pattern": "code_pattern"},
    "complexity_hotspots":      {"file_pattern": "code_pattern"},
    "changed_function_summary": {"file_pattern": "code_pattern"},
    "doc_outline":              {"file_pattern": "doc_pattern"},
    "file_changes":             {"from_rev": "from_rev", "to_rev": "to_rev"},
    "file_diff":                {"from_rev": "from_rev", "to_rev": "to_rev"},
    "structural_diff":          {"from_rev": "from_rev", "to_rev": "to_rev"},
}
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_pro_defaults.py"])`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add fledgling/pro/defaults.py tests/test_pro_defaults.py
git commit -m "feat(defaults): ProjectDefaults dataclass and TOOL_DEFAULTS mapping"
```

---

### Task 2: `apply_defaults()` function

**Files:**
- Modify: `fledgling/pro/defaults.py`
- Test: `tests/test_pro_defaults.py`

- [ ] **Step 1: Write tests for apply_defaults**

Append to `tests/test_pro_defaults.py`:

```python
from fledgling.pro.defaults import apply_defaults


class TestApplyDefaults:
    """apply_defaults substitutes None params from ProjectDefaults."""

    def setup_method(self):
        self.defaults = ProjectDefaults(
            code_pattern="**/*.py",
            doc_pattern="docs/**/*.md",
            main_branch="main",
            languages=["python"],
        )

    def test_substitutes_none_code_pattern(self):
        kwargs = {"file_pattern": None, "name_pattern": "%"}
        result = apply_defaults(self.defaults, "find_definitions", kwargs)
        assert result["file_pattern"] == "**/*.py"
        assert result["name_pattern"] == "%"

    def test_preserves_explicit_value(self):
        kwargs = {"file_pattern": "src/**/*.rs"}
        result = apply_defaults(self.defaults, "find_definitions", kwargs)
        assert result["file_pattern"] == "src/**/*.rs"

    def test_unknown_tool_passes_through(self):
        kwargs = {"file_pattern": None}
        result = apply_defaults(self.defaults, "unknown_tool", kwargs)
        assert result["file_pattern"] is None

    def test_git_tool_defaults(self):
        kwargs = {"from_rev": None, "to_rev": None, "repo": "."}
        result = apply_defaults(self.defaults, "file_changes", kwargs)
        assert result["from_rev"] == "HEAD~1"
        assert result["to_rev"] == "HEAD"
        assert result["repo"] == "."

    def test_git_tool_explicit_overrides(self):
        kwargs = {"from_rev": "abc123", "to_rev": None}
        result = apply_defaults(self.defaults, "file_changes", kwargs)
        assert result["from_rev"] == "abc123"
        assert result["to_rev"] == "HEAD"

    def test_doc_tool_defaults(self):
        kwargs = {"file_pattern": None, "max_lvl": 3}
        result = apply_defaults(self.defaults, "doc_outline", kwargs)
        assert result["file_pattern"] == "docs/**/*.md"

    def test_does_not_mutate_input(self):
        kwargs = {"file_pattern": None}
        apply_defaults(self.defaults, "find_definitions", kwargs)
        assert kwargs["file_pattern"] is None
```

- [ ] **Step 2: Run tests, verify new tests fail**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_pro_defaults.py::TestApplyDefaults"])`
Expected: ImportError — `apply_defaults` not yet exported.

- [ ] **Step 3: Implement apply_defaults**

Add to `fledgling/pro/defaults.py`:

```python
def apply_defaults(
    defaults: ProjectDefaults,
    tool_name: str,
    kwargs: dict[str, object],
) -> dict[str, object]:
    """Substitute None params with smart defaults for a given tool.

    Returns a new dict — does not mutate the input.
    """
    mapping = TOOL_DEFAULTS.get(tool_name)
    if not mapping:
        return kwargs
    result = dict(kwargs)
    for param, field_name in mapping.items():
        if param in result and result[param] is None:
            result[param] = getattr(defaults, field_name)
    return result
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_pro_defaults.py"])`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add fledgling/pro/defaults.py tests/test_pro_defaults.py
git commit -m "feat(defaults): apply_defaults substitutes None params from ProjectDefaults"
```

---

### Task 3: `load_config()` — read `.fledgling-python/config.toml`

**Files:**
- Modify: `fledgling/pro/defaults.py`
- Test: `tests/test_pro_defaults.py`

- [ ] **Step 1: Write tests for load_config**

Append to `tests/test_pro_defaults.py`:

```python
import os
from pathlib import Path

from fledgling.pro.defaults import load_config


class TestLoadConfig:
    """load_config reads .fledgling-python/config.toml overrides."""

    def test_missing_config_returns_empty(self, tmp_path):
        result = load_config(tmp_path)
        assert result == {}

    def test_missing_directory_returns_empty(self, tmp_path):
        result = load_config(tmp_path / "nonexistent")
        assert result == {}

    def test_reads_defaults_section(self, tmp_path):
        config_dir = tmp_path / ".fledgling-python"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text(
            '[defaults]\ncode_pattern = "src/**/*.rs"\n'
        )
        result = load_config(tmp_path)
        assert result == {"code_pattern": "src/**/*.rs"}

    def test_all_keys(self, tmp_path):
        config_dir = tmp_path / ".fledgling-python"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text(
            '[defaults]\n'
            'code_pattern = "**/*.go"\n'
            'doc_pattern = "wiki/**/*.md"\n'
            'main_branch = "develop"\n'
        )
        result = load_config(tmp_path)
        assert result == {
            "code_pattern": "**/*.go",
            "doc_pattern": "wiki/**/*.md",
            "main_branch": "develop",
        }

    def test_empty_defaults_section(self, tmp_path):
        config_dir = tmp_path / ".fledgling-python"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text("[defaults]\n")
        result = load_config(tmp_path)
        assert result == {}

    def test_no_defaults_section(self, tmp_path):
        config_dir = tmp_path / ".fledgling-python"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text('[other]\nfoo = "bar"\n')
        result = load_config(tmp_path)
        assert result == {}
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_pro_defaults.py::TestLoadConfig"])`
Expected: ImportError — `load_config` not yet exported.

- [ ] **Step 3: Implement load_config**

Add to `fledgling/pro/defaults.py`:

```python
import tomllib
from pathlib import Path


def load_config(root: str | Path) -> dict[str, str]:
    """Read defaults overrides from .fledgling-python/config.toml.

    Returns the [defaults] section as a flat dict, or {} if the file
    doesn't exist or has no [defaults] section.
    """
    config_path = Path(root) / ".fledgling-python" / "config.toml"
    if not config_path.is_file():
        return {}
    with open(config_path, "rb") as f:
        data = tomllib.load(f)
    return dict(data.get("defaults", {}))
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_pro_defaults.py"])`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add fledgling/pro/defaults.py tests/test_pro_defaults.py
git commit -m "feat(defaults): load_config reads .fledgling-python/config.toml"
```

---

### Task 4: `infer_defaults()` — project analysis

**Files:**
- Modify: `fledgling/pro/defaults.py`
- Test: `tests/test_pro_defaults.py`

This task uses the fledgling `Connection` to query `project_overview()` and
`list_files()`. Tests use the existing `all_macros` fixture from conftest.py.

- [ ] **Step 1: Write tests for infer_defaults**

Append to `tests/test_pro_defaults.py`:

```python
from conftest import PROJECT_ROOT

import fledgling
from fledgling.pro.defaults import infer_defaults


class TestInferDefaults:
    """infer_defaults queries the project and builds ProjectDefaults."""

    @pytest.fixture
    def con(self):
        return fledgling.connect(root=str(PROJECT_ROOT))

    def test_code_pattern_is_python(self, con):
        """This repo is primarily Python, so code_pattern should be **/*.py."""
        defaults = infer_defaults(con)
        assert "py" in defaults.code_pattern

    def test_languages_includes_python(self, con):
        defaults = infer_defaults(con)
        assert "Python" in defaults.languages

    def test_doc_pattern_finds_docs_dir(self, con):
        """This repo has a docs/ directory."""
        defaults = infer_defaults(con)
        assert defaults.doc_pattern.startswith("docs/")

    def test_main_branch_is_string(self, con):
        defaults = infer_defaults(con)
        assert isinstance(defaults.main_branch, str)
        assert len(defaults.main_branch) > 0

    def test_config_overrides_inferred(self, con, tmp_path):
        """load_config values override inferred values."""
        overrides = {"code_pattern": "custom/**/*.rs", "main_branch": "develop"}
        defaults = infer_defaults(con, overrides=overrides)
        assert defaults.code_pattern == "custom/**/*.rs"
        assert defaults.main_branch == "develop"
        # Non-overridden values still inferred
        assert "py" not in defaults.code_pattern

    def test_empty_overrides_no_effect(self, con):
        d1 = infer_defaults(con)
        d2 = infer_defaults(con, overrides={})
        assert d1 == d2
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_pro_defaults.py::TestInferDefaults"])`
Expected: ImportError — `infer_defaults` not yet exported.

- [ ] **Step 3: Implement LANGUAGE_EXTENSIONS and infer_defaults**

Add to `fledgling/pro/defaults.py`:

```python
from fledgling.connection import Connection


# Language name (as returned by project_overview) → file extensions.
# Hardcoded for now; will be replaced by sitting_duck's extension listing
# when available.
LANGUAGE_EXTENSIONS: dict[str, list[str]] = {
    "Python": ["py", "pyi"],
    "JavaScript": ["js", "jsx", "mjs"],
    "TypeScript": ["ts", "tsx"],
    "Rust": ["rs"],
    "Go": ["go"],
    "Java": ["java"],
    "Ruby": ["rb"],
    "C": ["c"],
    "C++": ["cpp", "cc"],
    "C/C++": ["h", "hpp"],
    "SQL": ["sql"],
    "Shell": ["sh", "bash", "zsh"],
    "Kotlin": ["kt", "kts"],
    "Swift": ["swift"],
    "Dart": ["dart"],
    "PHP": ["php"],
    "Lua": ["lua"],
    "Zig": ["zig"],
    "R": ["r", "R"],
    "C#": ["cs"],
    "HCL": ["hcl", "tf"],
}

# Directories to check for docs, in priority order.
_DOC_DIRS = ["docs", "documentation", "doc", "wiki"]


def _code_glob(extensions: list[str]) -> str:
    """Build a glob pattern from a list of extensions."""
    if len(extensions) == 1:
        return f"**/*.{extensions[0]}"
    joined = ",".join(extensions)
    return f"**/*.{{{joined}}}"


def _find_doc_dir(con: Connection) -> str | None:
    """Check for common doc directories using list_files."""
    for d in _DOC_DIRS:
        try:
            rows = con.list_files(f"{d}/*").fetchall()
            if rows:
                return d
        except Exception:
            continue
    return None


def infer_defaults(
    con: Connection,
    overrides: dict[str, str] | None = None,
) -> ProjectDefaults:
    """Analyze the project and build smart defaults.

    Args:
        con: A fledgling Connection to the project.
        overrides: Values from config file that override inference.

    Returns:
        ProjectDefaults with inferred + overridden values.
    """
    overrides = overrides or {}

    # ── Code pattern ────────────────────────────────────────────
    code_pattern = "**/*"
    languages = []
    try:
        rows = con.project_overview().fetchall()
        # rows are (language, extension, file_count) ordered by count DESC
        if rows:
            # Group by language, sum file counts
            lang_counts: dict[str, int] = {}
            for lang, _ext, count in rows:
                lang_counts[lang] = lang_counts.get(lang, 0) + count
            # Top language
            top_lang = max(lang_counts, key=lang_counts.get)
            languages = list(lang_counts.keys())
            # Build glob from known extensions
            if top_lang in LANGUAGE_EXTENSIONS:
                code_pattern = _code_glob(LANGUAGE_EXTENSIONS[top_lang])
    except Exception:
        pass

    # ── Doc pattern ─────────────────────────────────────────────
    doc_dir = _find_doc_dir(con)
    doc_pattern = f"{doc_dir}/**/*.md" if doc_dir else "**/*.md"

    # ── Build defaults, apply overrides ─────────────────────────
    defaults = ProjectDefaults(
        code_pattern=code_pattern,
        doc_pattern=doc_pattern,
        languages=languages,
    )

    for key, value in overrides.items():
        if hasattr(defaults, key):
            setattr(defaults, key, value)

    return defaults
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_pro_defaults.py"])`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add fledgling/pro/defaults.py tests/test_pro_defaults.py
git commit -m "feat(defaults): infer_defaults analyzes project for smart code/doc patterns"
```

---

### Task 5: Wire defaults into `server.py`

**Files:**
- Modify: `fledgling/pro/server.py`
- Test: `tests/test_pro_defaults.py`

- [ ] **Step 1: Write integration test**

Append to `tests/test_pro_defaults.py`:

```python
from fledgling.pro.server import create_server


class TestServerIntegration:
    """Defaults are wired into the FastMCP server."""

    @pytest.fixture
    def server(self):
        return create_server(root=str(PROJECT_ROOT))

    def test_server_has_defaults(self, server):
        """create_server stores ProjectDefaults on the server context."""
        assert hasattr(server, "_defaults")
        assert isinstance(server._defaults, ProjectDefaults)

    def test_server_defaults_inferred(self, server):
        """Defaults reflect this project (Python, docs/)."""
        assert "py" in server._defaults.code_pattern
        assert server._defaults.doc_pattern.startswith("docs/")
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_pro_defaults.py::TestServerIntegration"])`
Expected: FAIL — `_defaults` not on server yet.

- [ ] **Step 3: Modify create_server to infer and store defaults**

In `fledgling/pro/server.py`, add import at top:

```python
from fledgling.pro.defaults import (
    ProjectDefaults, apply_defaults, infer_defaults, load_config,
)
```

Modify `create_server()` — after creating `con`, before the tool loop:

```python
    con = fledgling.connect(init=init, root=root, modules=modules, profile=profile)
    mcp = FastMCP(name)

    # Infer smart defaults, merge with config file overrides
    project_root = root or os.getcwd()
    overrides = load_config(project_root)
    defaults = infer_defaults(con, overrides=overrides)
    mcp._defaults = defaults

    # Register each macro as an MCP tool
    for macro_info in con._tools.list():
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_pro_defaults.py::TestServerIntegration"])`
Expected: All pass.

- [ ] **Step 5: Wire apply_defaults into tool_fn wrapper**

In `_register_tool()`, pass `defaults` and apply before macro call. Update
the `_register_tool` signature to accept defaults:

```python
def _register_tool(
    mcp: FastMCP,
    con: Connection,
    macro_name: str,
    params: list[str],
    defaults: ProjectDefaults,
):
```

In the `tool_fn` body, replace the existing filtering with:

```python
    async def tool_fn(**kwargs) -> str:
        # Apply smart defaults for None params
        kwargs = apply_defaults(defaults, macro_name, kwargs)
        # Remove remaining None values (optional params not provided)
        filtered = {k: v for k, v in kwargs.items() if v is not None}
```

Update the call site in `create_server()`:

```python
        _register_tool(mcp, con, macro_name, params, defaults)
```

- [ ] **Step 6: Run full test suite**

Run: `mcp__blq_mcp__run(command="test")`
Expected: All tests pass (existing + new).

- [ ] **Step 7: Commit**

```bash
git add fledgling/pro/server.py tests/test_pro_defaults.py
git commit -m "feat(defaults): wire smart defaults into FastMCP server and tool wrappers"
```

---

### Task 6: End-to-end tool call test

**Files:**
- Test: `tests/test_pro_defaults.py`

- [ ] **Step 1: Write end-to-end test calling a tool without a pattern**

Append to `tests/test_pro_defaults.py`:

```python
import asyncio


class TestToolCallDefaults:
    """Tools use defaults when called without explicit patterns."""

    @pytest.fixture
    def server(self):
        return create_server(root=str(PROJECT_ROOT))

    def _call(self, server, tool_name, kwargs):
        """Call a tool function registered on the server."""
        # FastMCP stores tools by name
        tool = server._tool_manager.get_tool(tool_name)
        return asyncio.get_event_loop().run_until_complete(
            tool.run(kwargs)
        )

    def test_find_definitions_uses_default_pattern(self, server):
        """find_definitions with no file_pattern uses inferred default."""
        result = self._call(server, "find_definitions", {})
        # Should return Python definitions (this is a Python project)
        assert result != "(no results)"

    def test_find_definitions_explicit_overrides(self, server):
        """Explicit pattern overrides the default."""
        result = self._call(
            server, "find_definitions", {"file_pattern": "nonexistent/**/*.xyz"}
        )
        assert result == "(no results)"

    def test_doc_outline_uses_default_pattern(self, server):
        """doc_outline with no file_pattern uses inferred doc pattern."""
        result = self._call(server, "doc_outline", {})
        assert result != "(no results)"
```

Note: The exact `_call` helper depends on FastMCP's internal API. The
implementer should check how FastMCP exposes registered tools and adjust.
The key behavior to test: calling a tool with `{}` uses defaults, calling
with an explicit pattern uses that instead.

- [ ] **Step 2: Run tests, verify they pass**

Run: `mcp__blq_mcp__run(command="test", extra=["tests/test_pro_defaults.py::TestToolCallDefaults"])`
Expected: All pass (defaults already wired in Task 5).

- [ ] **Step 3: Run full test suite**

Run: `mcp__blq_mcp__run(command="test")`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_pro_defaults.py
git commit -m "test(defaults): end-to-end tool call tests for smart defaults"
```

---

## Summary

| Task | What it delivers |
|------|-----------------|
| 1 | `ProjectDefaults` dataclass + `TOOL_DEFAULTS` mapping |
| 2 | `apply_defaults()` function |
| 3 | `load_config()` for `.fledgling-python/config.toml` |
| 4 | `infer_defaults()` with project analysis |
| 5 | Server wiring — defaults in `create_server()` + `tool_fn` |
| 6 | End-to-end tool call tests |
