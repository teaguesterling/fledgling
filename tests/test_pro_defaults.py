"""Tests for fledgling.pro.defaults — smart project-aware defaults."""

from dataclasses import fields

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
