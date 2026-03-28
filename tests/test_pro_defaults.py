"""Tests for fledgling.pro.defaults — smart project-aware defaults."""

import asyncio
import pytest
from dataclasses import fields

import fledgling
from fledgling.pro.defaults import ProjectDefaults, TOOL_DEFAULTS, apply_defaults, load_config, infer_defaults
from conftest import PROJECT_ROOT


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
        assert d.from_rev == "HEAD~1"
        assert d.to_rev == "HEAD"
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

    def test_all_field_names_are_valid(self):
        """Every value in TOOL_DEFAULTS must name a real ProjectDefaults field."""
        valid_fields = {f.name for f in fields(ProjectDefaults)}
        for tool, mapping in TOOL_DEFAULTS.items():
            for _param, field_name in mapping.items():
                assert field_name in valid_fields, (
                    f"{tool}: '{field_name}' is not a ProjectDefaults field"
                )


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

    def test_substitutes_absent_param(self):
        """Absent params (not just None) get defaults injected."""
        kwargs = {"name_pattern": "%"}
        result = apply_defaults(self.defaults, "find_definitions", kwargs)
        assert result["file_pattern"] == "**/*.py"
        assert result["name_pattern"] == "%"

    def test_does_not_mutate_input(self):
        kwargs = {"file_pattern": None}
        apply_defaults(self.defaults, "find_definitions", kwargs)
        assert kwargs["file_pattern"] is None


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

    def test_config_overrides_inferred(self, con):
        """load_config values override inferred values."""
        overrides = {"code_pattern": "custom/**/*.rs", "main_branch": "develop"}
        defaults = infer_defaults(con, overrides=overrides)
        assert defaults.code_pattern == "custom/**/*.rs"
        assert defaults.main_branch == "develop"

    def test_empty_overrides_no_effect(self, con):
        d1 = infer_defaults(con)
        d2 = infer_defaults(con, overrides={})
        assert d1 == d2


# ── Server integration tests ───────────────────────────────────────

try:
    from fledgling.pro.server import create_server
    _has_fastmcp = True
except ImportError:
    _has_fastmcp = False


@pytest.mark.skipif(not _has_fastmcp, reason="fastmcp not installed")
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


@pytest.mark.skipif(not _has_fastmcp, reason="fastmcp not installed")
class TestToolCallDefaults:
    """Tools use defaults when called without explicit patterns."""

    @pytest.fixture(scope="class")
    def server(self):
        return create_server(root=str(PROJECT_ROOT))

    @staticmethod
    def _call(server, tool_name, arguments):
        """Call a tool on the FastMCP server and return the text result."""
        result = asyncio.run(server.call_tool(tool_name, arguments))
        # ToolResult.content is a list of TextContent
        return result.content[0].text

    def test_find_definitions_uses_default_pattern(self, server):
        """find_definitions with no file_pattern uses inferred default."""
        result = self._call(server, "find_definitions", {})
        assert result != "(no results)"
        # Should find Python definitions (this is a Python project)
        assert "def" in result.lower() or "class" in result.lower() or "|" in result

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

    def test_doc_outline_explicit_overrides(self, server):
        """Explicit doc pattern overrides the default."""
        result = self._call(
            server, "doc_outline", {"file_pattern": "nonexistent/**/*.xyz"}
        )
        assert result == "(no results)"

    def test_code_structure_uses_default_pattern(self, server):
        """code_structure with no file_pattern uses inferred default."""
        result = self._call(server, "code_structure", {})
        assert result != "(no results)"

    def test_code_structure_explicit_overrides(self, server):
        """Explicit pattern overrides the default for code_structure."""
        result = self._call(
            server, "code_structure", {"file_pattern": "nonexistent/**/*.xyz"}
        )
        assert result == "(no results)"

    def test_complexity_hotspots_uses_default_pattern(self, server):
        """complexity_hotspots with no file_pattern uses inferred default."""
        result = self._call(server, "complexity_hotspots", {})
        assert result != "(no results)"
