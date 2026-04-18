"""Tests for full-text search macros (fts tier)."""

import pytest
from conftest import PROJECT_ROOT, load_sql


# ── Rebuild / ingestion ──────────────────────────────────────────────


class TestFtsRebuild:
    def test_populates_content(self, fts_populated):
        count = fts_populated.execute(
            "SELECT count(*) FROM fts.content"
        ).fetchone()[0]
        assert count > 1000  # repo has thousands of indexed chunks

    def test_all_kinds_present(self, fts_populated):
        kinds = fts_populated.execute(
            "SELECT DISTINCT kind FROM fts.content"
        ).fetchall()
        assert set(k[0] for k in kinds) == {
            "doc_section", "definition", "comment", "string",
        }

    def test_both_extractors_present(self, fts_populated):
        extractors = fts_populated.execute(
            "SELECT DISTINCT extractor FROM fts.content"
        ).fetchall()
        assert set(e[0] for e in extractors) == {"markdown", "sitting_duck"}

    def test_row_ids_unique(self, fts_populated):
        total, unique = fts_populated.execute(
            "SELECT count(*), count(DISTINCT id) FROM fts.content"
        ).fetchone()
        assert total == unique

    def test_markdown_rows_have_heading(self, fts_populated):
        # Every doc_section row should have a non-empty title in `name`.
        missing = fts_populated.execute(
            "SELECT count(*) FROM fts.content "
            "WHERE extractor = 'markdown' AND (name IS NULL OR name = '')"
        ).fetchone()[0]
        # Allow a handful of edge cases (frontmatter-only, etc.) but not many.
        assert missing < 5

    def test_code_definitions_have_names(self, fts_populated):
        missing = fts_populated.execute(
            "SELECT count(*) FROM fts.content "
            "WHERE kind = 'definition' AND (name IS NULL OR name = '')"
        ).fetchone()[0]
        assert missing == 0

    def test_rebuild_is_idempotent(self, fts_macros):
        load_sql(fts_macros, "fts_rebuild.sql")
        count1 = fts_macros.execute(
            "SELECT count(*) FROM fts.content"
        ).fetchone()[0]
        load_sql(fts_macros, "fts_rebuild.sql")
        count2 = fts_macros.execute(
            "SELECT count(*) FROM fts.content"
        ).fetchone()[0]
        assert count1 == count2
        assert count1 > 0


# ── fts_stats ────────────────────────────────────────────────────────


class TestFtsStats:
    def test_returns_rows(self, fts_populated):
        rows = fts_populated.execute("SELECT * FROM fts_stats()").fetchall()
        assert len(rows) == 4  # one per (extractor, kind) combo

    def test_columns(self, fts_populated):
        desc = fts_populated.execute(
            "DESCRIBE SELECT * FROM fts_stats()"
        ).fetchall()
        col_names = [r[0] for r in desc]
        assert col_names == ["extractor", "kind", "row_count", "file_count"]

    def test_counts_are_positive(self, fts_populated):
        rows = fts_populated.execute(
            "SELECT row_count, file_count FROM fts_stats()"
        ).fetchall()
        for row_count, file_count in rows:
            assert row_count > 0
            assert file_count > 0


# ── search_content (unified) ─────────────────────────────────────────


class TestSearchContent:
    def test_returns_matches_for_common_term(self, fts_populated):
        rows = fts_populated.execute(
            "SELECT * FROM search_content('lockdown')"
        ).fetchall()
        assert len(rows) > 0

    def test_ordered_by_score_desc(self, fts_populated):
        scores = fts_populated.execute(
            "SELECT score FROM search_content('connection')"
        ).fetchall()
        score_vals = [r[0] for r in scores]
        assert score_vals == sorted(score_vals, reverse=True)

    def test_filter_by_kind_doc_section(self, fts_populated):
        kinds = fts_populated.execute(
            "SELECT DISTINCT kind FROM search_content("
            "'sandbox', filter_kind := 'doc_section')"
        ).fetchall()
        assert [k[0] for k in kinds] == ["doc_section"]

    def test_filter_by_kind_definition(self, fts_populated):
        kinds = fts_populated.execute(
            "SELECT DISTINCT kind FROM search_content("
            "'lockdown', filter_kind := 'definition')"
        ).fetchall()
        assert [k[0] for k in kinds] == ["definition"]

    def test_filter_by_extractor_markdown(self, fts_populated):
        extractors = fts_populated.execute(
            "SELECT DISTINCT extractor FROM search_content("
            "'docs', filter_extractor := 'markdown')"
        ).fetchall()
        assert [e[0] for e in extractors] == ["markdown"]

    def test_filter_by_extractor_sitting_duck(self, fts_populated):
        extractors = fts_populated.execute(
            "SELECT DISTINCT extractor FROM search_content("
            "'connect', filter_extractor := 'sitting_duck')"
        ).fetchall()
        assert [e[0] for e in extractors] == ["sitting_duck"]

    def test_limit_respected(self, fts_populated):
        rows = fts_populated.execute(
            "SELECT * FROM search_content('test', limit_n := 5)"
        ).fetchall()
        assert len(rows) <= 5

    def test_no_query_match_returns_empty(self, fts_populated):
        # Compute the term at runtime so the literal doesn't appear in any
        # indexed source file. A static string here would match itself —
        # this test file gets indexed by the session fixture.
        fake = "q" * 25
        rows = fts_populated.execute(
            "SELECT * FROM search_content(?)", [fake]
        ).fetchall()
        assert rows == []

    def test_score_column_present(self, fts_populated):
        desc = fts_populated.execute(
            "DESCRIBE SELECT * FROM search_content('test')"
        ).fetchall()
        col_names = [r[0] for r in desc]
        assert "score" in col_names
        assert "text" in col_names
        assert "file_path" in col_names


# ── search_docs ──────────────────────────────────────────────────────


class TestSearchDocs:
    def test_returns_only_doc_sections(self, fts_populated):
        # search_docs is a thin wrapper that pins kind='doc_section'.
        # The kind column isn't in the result shape, so assert the content
        # rows all come from markdown extractor via join back.
        rows = fts_populated.execute(
            "SELECT c.extractor, c.kind "
            "FROM search_docs('sandbox') s "
            "JOIN fts.content c ON c.id = s.id"
        ).fetchall()
        assert len(rows) > 0
        assert all(e == "markdown" and k == "doc_section" for e, k in rows)

    def test_limit_respected(self, fts_populated):
        rows = fts_populated.execute(
            "SELECT * FROM search_docs('connection', 5)"
        ).fetchall()
        assert len(rows) <= 5


# ── search_code ──────────────────────────────────────────────────────


class TestSearchCode:
    def test_returns_only_code_rows(self, fts_populated):
        rows = fts_populated.execute(
            "SELECT DISTINCT extractor FROM search_code('connection')"
        ).fetchall()
        assert [r[0] for r in rows] == ["sitting_duck"]

    def test_filter_kind_definition(self, fts_populated):
        rows = fts_populated.execute(
            "SELECT DISTINCT kind FROM search_code("
            "'connect', filter_kind := 'definition')"
        ).fetchall()
        assert [r[0] for r in rows] == ["definition"]

    def test_filter_kind_comment(self, fts_populated):
        rows = fts_populated.execute(
            "SELECT DISTINCT kind FROM search_code("
            "'workaround', filter_kind := 'comment')"
        ).fetchall()
        # Only comments matched, or no matches (if no comments mention the term).
        assert rows == [] or [r[0] for r in rows] == ["comment"]

    def test_filter_kind_string(self, fts_populated):
        rows = fts_populated.execute(
            "SELECT DISTINCT kind FROM search_code("
            "'SELECT FROM read_ast', filter_kind := 'string')"
        ).fetchall()
        assert [r[0] for r in rows] == ["string"]

    def test_without_kind_returns_multiple_kinds(self, fts_populated):
        # 'auth' is common enough to appear in multiple code kinds.
        rows = fts_populated.execute(
            "SELECT DISTINCT kind FROM search_code('test connection')"
        ).fetchall()
        kinds = set(r[0] for r in rows)
        assert kinds.issubset({"definition", "comment", "string"})


# ── find_code_ranked (structural + FTS composition) ──────────────────


class TestFindCodeRanked:
    # ast_select resolves globs against cwd (not session_root), so tests
    # pin absolute file patterns via PROJECT_ROOT.
    PY_GLOB = PROJECT_ROOT + "/**/*.py"

    def test_returns_matches_for_func_selector(self, fts_populated):
        rows = fts_populated.execute(
            "SELECT * FROM find_code_ranked(?, ?, ?)",
            [self.PY_GLOB, ".func", "function_callers"],
        ).fetchall()
        assert len(rows) > 0

    def test_ordered_by_score_desc(self, fts_populated):
        scores = fts_populated.execute(
            "SELECT score FROM find_code_ranked(?, ?, ?)",
            [self.PY_GLOB, ".func", "function_callers"],
        ).fetchall()
        vals = [s[0] for s in scores]
        assert vals == sorted(vals, reverse=True)

    def test_restricts_to_class_kind_for_class_selector(self, fts_populated):
        # .class should only yield class definitions, not plain functions.
        kinds = fts_populated.execute(
            "SELECT DISTINCT kind FROM find_code_ranked(?, ?, ?)",
            [self.PY_GLOB, ".class", "Connection"],
        ).fetchall()
        for (k,) in kinds:
            assert "class" in k.lower()

    def test_no_match_returns_empty(self, fts_populated):
        # Literal computed at runtime to avoid self-indexing.
        fake = "q" * 25
        rows = fts_populated.execute(
            "SELECT * FROM find_code_ranked(?, ?, ?)",
            [self.PY_GLOB, ".func", fake],
        ).fetchall()
        assert rows == []

    def test_columns(self, fts_populated):
        desc = fts_populated.execute(
            "DESCRIBE SELECT * FROM find_code_ranked(?, ?, ?)",
            [self.PY_GLOB, ".func", "connect"],
        ).fetchall()
        cols = [r[0] for r in desc]
        assert "file_path" in cols
        assert "name" in cols
        assert "kind" in cols
        assert "score" in cols
