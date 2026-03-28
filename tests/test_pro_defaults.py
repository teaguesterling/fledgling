"""Tests for fledgling.pro.defaults — smart project-aware defaults."""

from dataclasses import fields

from fledgling.pro.defaults import ProjectDefaults, TOOL_DEFAULTS, apply_defaults, load_config


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
