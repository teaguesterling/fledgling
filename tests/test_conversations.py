"""Tests for conversation analysis macros (conversations.sql)."""

import pytest


class TestLoadConversations:
    def test_loads_jsonl(self, conversation_macros):
        rows = conversation_macros.execute(
            "SELECT count(*) FROM raw_conversations"
        ).fetchone()
        assert rows[0] == 7

    def test_source_file_populated(self, conversation_macros):
        rows = conversation_macros.execute(
            "SELECT DISTINCT _source_file FROM raw_conversations"
        ).fetchall()
        assert len(rows) == 1
        assert ".claude/projects/test-project/" in rows[0][0]


class TestSessions:
    def test_session_count(self, conversation_macros):
        rows = conversation_macros.execute(
            "SELECT * FROM sessions()"
        ).fetchall()
        assert len(rows) == 2

    def test_project_dir_extracted(self, conversation_macros):
        rows = conversation_macros.execute(
            "SELECT DISTINCT project_dir FROM sessions()"
        ).fetchall()
        dirs = [r[0] for r in rows]
        assert "test-project" in dirs

    def test_message_counts(self, conversation_macros):
        row = conversation_macros.execute(
            "SELECT user_messages, assistant_messages, progress_events, "
            "total_records FROM sessions() WHERE session_id = 'sess-001'"
        ).fetchone()
        assert row[0] == 2  # user messages (u1, u3)
        assert row[1] == 2  # assistant messages (u2, u4)
        assert row[2] == 1  # progress events (u5)
        assert row[3] == 5  # total records

    def test_duration_calculated(self, conversation_macros):
        row = conversation_macros.execute(
            "SELECT duration FROM sessions() WHERE session_id = 'sess-001'"
        ).fetchone()
        assert row[0] is not None


class TestMessages:
    def test_filters_user_assistant_only(self, conversation_macros):
        rows = conversation_macros.execute(
            "SELECT DISTINCT record_type FROM messages()"
        ).fetchall()
        types = {r[0] for r in rows}
        assert types == {"user", "assistant"}

    def test_total_message_count(self, conversation_macros):
        rows = conversation_macros.execute(
            "SELECT count(*) FROM messages()"
        ).fetchone()
        # 3 user + 3 assistant = 6 (progress excluded)
        assert rows[0] == 6

    def test_flattens_message_struct(self, conversation_macros):
        desc = conversation_macros.execute(
            "DESCRIBE SELECT * FROM messages()"
        ).fetchall()
        col_names = [r[0] for r in desc]
        for col in ["message_id", "session_id", "role", "content",
                     "model", "input_tokens", "output_tokens"]:
            assert col in col_names


class TestContentBlocks:
    def test_unnests_blocks(self, conversation_macros):
        rows = conversation_macros.execute(
            "SELECT count(*) FROM content_blocks()"
        ).fetchone()
        # u2: 2 blocks (text, tool_use), u4: 2 blocks, u7: 1 block = 5
        assert rows[0] == 5

    def test_block_types_present(self, conversation_macros):
        rows = conversation_macros.execute(
            "SELECT DISTINCT block_type FROM content_blocks()"
        ).fetchall()
        types = {r[0] for r in rows}
        assert "text" in types
        assert "tool_use" in types

    def test_guards_non_array_content(self, conversation_macros):
        """String user content should not appear in content_blocks."""
        rows = conversation_macros.execute(
            "SELECT count(*) FROM content_blocks() "
            "WHERE message_id IN ('u1', 'u6')"
        ).fetchone()
        assert rows[0] == 0


class TestToolCalls:
    def test_extracts_tool_use(self, conversation_macros):
        rows = conversation_macros.execute(
            "SELECT count(*) FROM tool_calls()"
        ).fetchone()
        # tu_001 (Bash), tu_002 (Read), tu_003 (Bash) = 3
        assert rows[0] == 3

    def test_bash_command_extracted(self, conversation_macros):
        row = conversation_macros.execute(
            "SELECT bash_command FROM tool_calls() "
            "WHERE tool_use_id = 'tu_001'"
        ).fetchone()
        assert row[0] == "git status"

    def test_file_path_extracted(self, conversation_macros):
        row = conversation_macros.execute(
            "SELECT file_path FROM tool_calls() "
            "WHERE tool_use_id = 'tu_002'"
        ).fetchone()
        assert row[0] == "/src/auth.py"


class TestToolResults:
    def test_extracts_tool_results(self, conversation_macros):
        rows = conversation_macros.execute(
            "SELECT count(*) FROM tool_results()"
        ).fetchone()
        assert rows[0] == 1

    def test_tool_use_id_present(self, conversation_macros):
        row = conversation_macros.execute(
            "SELECT tool_use_id, result_content FROM tool_results()"
        ).fetchone()
        assert row[0] == "tu_001"
        assert "branch main" in row[1]


class TestTokenUsage:
    def test_token_fields_present(self, conversation_macros):
        desc = conversation_macros.execute(
            "DESCRIBE SELECT * FROM token_usage()"
        ).fetchall()
        col_names = [r[0] for r in desc]
        for col in ["input_tokens", "output_tokens", "cache_read_tokens",
                     "total_input_tokens", "total_tokens", "cache_hit_rate"]:
            assert col in col_names

    def test_cache_hit_rate_calculation(self, conversation_macros):
        row = conversation_macros.execute(
            "SELECT cache_hit_rate FROM token_usage() "
            "WHERE request_id = 'req_001'"
        ).fetchone()
        # input=1000, cache_read=500, cache_creation=null(0)
        # rate = 500 / (1000 + 0 + 500) = 1/3
        assert abs(row[0] - (500.0 / 1500.0)) < 0.001

    def test_only_assistant_with_tokens(self, conversation_macros):
        rows = conversation_macros.execute(
            "SELECT count(*) FROM token_usage()"
        ).fetchone()
        # 3 assistant messages, all have usage data
        assert rows[0] == 3


class TestBashCommands:
    def test_category_git_read(self, conversation_macros):
        row = conversation_macros.execute(
            "SELECT category FROM bash_commands() "
            "WHERE command = 'git status'"
        ).fetchone()
        assert row[0] == "git_read"

    def test_category_file_read(self, conversation_macros):
        row = conversation_macros.execute(
            "SELECT category FROM bash_commands() "
            "WHERE command = 'cat README.md'"
        ).fetchone()
        assert row[0] == "file_read"

    def test_replaceable_by(self, conversation_macros):
        rows = conversation_macros.execute(
            "SELECT command, replaceable_by FROM bash_commands() "
            "ORDER BY command"
        ).fetchall()
        by_cmd = {r[0]: r[1] for r in rows}
        assert by_cmd["cat README.md"] == "read_lines"
        assert by_cmd["git status"] == "duck_tails"

    def test_leading_command(self, conversation_macros):
        rows = conversation_macros.execute(
            "SELECT command, leading_command FROM bash_commands() "
            "ORDER BY command"
        ).fetchall()
        by_cmd = {r[0]: r[1] for r in rows}
        assert by_cmd["git status"] == "git"
        assert by_cmd["cat README.md"] == "cat"


class TestToolFrequency:
    def test_counts_by_tool(self, conversation_macros):
        rows = conversation_macros.execute(
            "SELECT tool_name, sum(call_count) AS total "
            "FROM tool_frequency() GROUP BY tool_name ORDER BY tool_name"
        ).fetchall()
        by_name = {r[0]: r[1] for r in rows}
        assert by_name["Bash"] == 2
        assert by_name["Read"] == 1


class TestSearchMessages:
    def test_finds_user_text(self, conversation_macros):
        rows = conversation_macros.execute(
            "SELECT * FROM search_messages('fix the bug')"
        ).fetchall()
        assert len(rows) >= 1
        assert any(r[3] == "user" for r in rows)  # role column

    def test_finds_assistant_text_blocks(self, conversation_macros):
        rows = conversation_macros.execute(
            "SELECT * FROM search_messages('auth module')"
        ).fetchall()
        assert len(rows) >= 1
        assert any(r[3] == "assistant" for r in rows)


class TestSearchToolInputs:
    def test_finds_tool_input(self, conversation_macros):
        rows = conversation_macros.execute(
            "SELECT * FROM search_tool_inputs('git status')"
        ).fetchall()
        assert len(rows) >= 1
        assert any("Bash" in str(r) for r in rows)


class TestSessionSummary:
    def test_returns_rows(self, conversation_macros):
        rows = conversation_macros.execute(
            "SELECT * FROM session_summary()"
        ).fetchall()
        assert len(rows) == 2

    def test_aggregated_counts(self, conversation_macros):
        row = conversation_macros.execute(
            "SELECT total_tool_calls, distinct_tools_used, "
            "total_input_tokens, total_output_tokens, "
            "bash_calls, bash_replaceable_calls "
            "FROM session_summary() WHERE session_id = 'sess-001'"
        ).fetchone()
        assert row[0] == 2  # tool_calls: Bash + Read
        assert row[1] == 2  # distinct tools: Bash, Read
        assert row[2] > 0   # total_input_tokens
        assert row[3] > 0   # total_output_tokens
        assert row[4] == 1  # bash_calls (only git status)
        assert row[5] == 1  # bash_replaceable_calls (git status → duck_tails)


class TestModelUsage:
    def test_groups_by_model(self, conversation_macros):
        rows = conversation_macros.execute(
            "SELECT model, sessions, api_calls FROM model_usage()"
        ).fetchall()
        assert len(rows) == 2
        models = {r[0] for r in rows}
        assert "claude-sonnet-4-20250514" in models
        assert "claude-haiku-4-20250414" in models
