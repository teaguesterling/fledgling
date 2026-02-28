"""Tests for security profile enforcement.

Verifies that core and analyst profiles correctly control which built-in
tools are available while all custom tools remain present in both.

Note: duckdb_mcp uses process-global server options. The first call to
mcp_server_start() in a process sets built-in tool visibility for all
subsequent calls. Core profile tests use subprocess isolation to avoid
contaminating the analyst fixture used by other tests.
"""

import json
import os

import duckdb
import pytest

from conftest import (
    PROJECT_ROOT, SQL_DIR, V1_TOOLS,
    call_tool, list_tools, load_sql,
    _list_tools_for_profile,
)

# Built-in duckdb_mcp tools controlled by profile options
ANALYST_BUILTINS = {"query", "describe", "list_tables"}


class TestCoreProfile:
    """Core profile: all custom tools, no built-in query tools."""

    def test_options_variable_set(self):
        """Profile SQL sets mcp_server_options with query disabled."""
        con = duckdb.connect(":memory:")
        con.execute("LOAD duckdb_mcp")
        load_sql(con, "profiles/core.sql")
        opts = json.loads(
            con.execute("SELECT getvariable('mcp_server_options')").fetchone()[0]
        )
        assert opts["enable_query_tool"] is False
        assert opts["enable_describe_tool"] is False
        assert opts["enable_list_tables_tool"] is False
        con.close()

    def test_memory_limit_set(self):
        """Core profile sets 2GB memory limit."""
        con = duckdb.connect(":memory:")
        load_sql(con, "profiles/core.sql")
        limit = con.execute("SELECT current_setting('memory_limit')").fetchone()[0]
        # DuckDB displays 2GB (decimal) as 1.8 GiB (binary)
        assert limit == "1.8 GiB"
        con.close()

    def test_tool_list_in_isolation(self):
        """Core server only has custom tools (subprocess-isolated)."""
        names = _list_tools_for_profile("profiles/core.sql")
        assert set(names) == set(V1_TOOLS)

    def test_no_builtin_tools_in_isolation(self):
        """Core server has no query/describe/list_tables (subprocess-isolated)."""
        names = set(_list_tools_for_profile("profiles/core.sql"))
        for builtin in ANALYST_BUILTINS:
            assert builtin not in names, f"Core should not have {builtin}"


class TestAnalystProfile:
    """Analyst profile: all custom tools plus built-in query tools."""

    def test_options_variable_set(self):
        """Profile SQL sets mcp_server_options with query enabled."""
        con = duckdb.connect(":memory:")
        con.execute("LOAD duckdb_mcp")
        load_sql(con, "profiles/analyst.sql")
        opts = json.loads(
            con.execute("SELECT getvariable('mcp_server_options')").fetchone()[0]
        )
        assert opts["enable_query_tool"] is True
        assert opts["enable_describe_tool"] is True
        assert opts["enable_list_tables_tool"] is True
        con.close()

    def test_memory_limit_set(self):
        """Analyst profile sets 4GB memory limit."""
        con = duckdb.connect(":memory:")
        load_sql(con, "profiles/analyst.sql")
        limit = con.execute("SELECT current_setting('memory_limit')").fetchone()[0]
        # DuckDB displays 4GB (decimal) as 3.7 GiB (binary)
        assert limit == "3.7 GiB"
        con.close()

    def test_all_custom_tools_present(self, mcp_server):
        names = {t["name"] for t in list_tools(mcp_server)}
        for tool in V1_TOOLS:
            assert tool in names, f"Missing custom tool: {tool}"

    def test_query_tool_present(self, mcp_server):
        names = {t["name"] for t in list_tools(mcp_server)}
        assert "query" in names

    def test_describe_tool_present(self, mcp_server):
        names = {t["name"] for t in list_tools(mcp_server)}
        assert "describe" in names

    def test_list_tables_tool_present(self, mcp_server):
        names = {t["name"] for t in list_tools(mcp_server)}
        assert "list_tables" in names

    def test_query_tool_executes(self, mcp_server):
        """The query tool actually runs SQL and returns results."""
        text = call_tool(mcp_server, "query", {"sql": "SELECT 42 AS answer"})
        assert "42" in text


class TestProfileIsolation:
    """Cross-profile assertions: analyst has tools that core does not."""

    def test_analyst_has_more_tools(self, mcp_server):
        analyst_names = set(_list_tools_for_profile("profiles/analyst.sql"))
        core_names = set(_list_tools_for_profile("profiles/core.sql"))
        extra = analyst_names - core_names
        assert extra == ANALYST_BUILTINS, (
            f"Expected analyst extras {ANALYST_BUILTINS}, got {extra}"
        )

    def test_both_have_all_custom_tools(self, mcp_server):
        analyst_names = set(_list_tools_for_profile("profiles/analyst.sql"))
        core_names = set(_list_tools_for_profile("profiles/core.sql"))
        for tool in V1_TOOLS:
            assert tool in analyst_names, f"Analyst missing: {tool}"
            assert tool in core_names, f"Core missing: {tool}"

    def test_exact_custom_tool_count(self):
        """Core should have exactly the custom tools (no builtins)."""
        names = _list_tools_for_profile("profiles/core.sql")
        assert len(names) == len(V1_TOOLS), (
            f"Expected {len(V1_TOOLS)} tools, got {len(names)}: {names}"
        )
