"""Shared fixtures for fledgling macro tests.

All tests use the fledgling repo itself as test data (dog-fooding).
"""

import json
import os
import pytest
import duckdb

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQL_DIR = os.path.join(PROJECT_ROOT, "sql")
CLAUDE_PROJECTS_DIR = os.path.expanduser("~/.claude/projects")

# Test data paths (the repo itself)
SPEC_PATH = os.path.join(PROJECT_ROOT, "docs/vision/PRODUCT_SPEC.md")
ANALYSIS_PATH = os.path.join(PROJECT_ROOT, "docs/vision/CONVERSATION_ANALYSIS.md")
CONFTEST_PATH = os.path.join(PROJECT_ROOT, "tests/conftest.py")
SKILL_PATH = os.path.join(PROJECT_ROOT, "SKILL.md")
REPO_PATH = PROJECT_ROOT


def load_sql(con, filename):
    """Load a SQL macro file into a DuckDB connection.

    Strips comment-only lines before splitting on semicolons to avoid
    parsing errors from semicolons inside comments.
    """
    path = os.path.join(SQL_DIR, filename)
    with open(path) as f:
        sql = f.read()
    lines = [l for l in sql.split("\n") if not l.strip().startswith("--")]
    cleaned = "\n".join(lines)
    for stmt in cleaned.split(";"):
        stmt = stmt.strip()
        if stmt:
            con.execute(stmt + ";")


@pytest.fixture
def con():
    """Fresh in-memory DuckDB connection."""
    conn = duckdb.connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def source_macros(con):
    """Connection with read_lines extension + source macros."""
    con.execute("LOAD read_lines")
    load_sql(con, "source.sql")
    return con


@pytest.fixture
def code_macros(con):
    """Connection with sitting_duck extension + code macros."""
    con.execute("LOAD sitting_duck")
    load_sql(con, "code.sql")
    return con


@pytest.fixture
def docs_macros(con):
    """Connection with markdown extension + docs macros."""
    con.execute("LOAD markdown")
    load_sql(con, "docs.sql")
    return con


@pytest.fixture
def repo_macros(con):
    """Connection with duck_tails extension + repo macros."""
    con.execute("LOAD duck_tails")
    load_sql(con, "repo.sql")
    return con


def materialize_help(con):
    """Create the _help_sections table from SKILL.md.

    Uses absolute path so tests work regardless of CWD.
    """
    con.execute(f"""
        CREATE TABLE _help_sections AS
        SELECT section_id, section_path, level, title, content,
               start_line, end_line
        FROM read_markdown_sections('{SKILL_PATH}', content_mode := 'full',
            include_content := true, include_filepath := false)
    """)


@pytest.fixture
def help_macros(con):
    """Connection with markdown extension + help macro + materialized SKILL.md."""
    con.execute("LOAD markdown")
    materialize_help(con)
    load_sql(con, "help.sql")
    return con


@pytest.fixture
def all_macros(con):
    """Connection with ALL extensions and ALL macros loaded.

    Load order: extensions first, then SQL macro files.
    """
    con.execute("LOAD read_lines")
    con.execute("LOAD sitting_duck")
    con.execute("LOAD markdown")
    con.execute("LOAD duck_tails")
    load_sql(con, "source.sql")
    load_sql(con, "code.sql")
    load_sql(con, "docs.sql")
    load_sql(con, "repo.sql")
    materialize_help(con)
    load_sql(con, "help.sql")
    return con


# The 16 V1 custom tools that should be published in all profiles
V1_TOOLS = [
    "ListFiles",
    "ReadLines",
    "ReadAsTable",
    "FindDefinitions",
    "FindCalls",
    "FindImports",
    "CodeStructure",
    "MDOutline",
    "MDSection",
    "GitChanges",
    "GitBranches",
    "Help",
    "ChatSessions",
    "ChatSearch",
    "ChatToolUsage",
    "ChatDetail",
    "GitDiffSummary",
    "GitDiffFile",
]


# -- MCP test helpers --


def mcp_request(con, method, params=None):
    """Send a JSON-RPC request to the MCP memory transport server."""
    request = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params or {},
    })
    raw = con.execute(
        "SELECT mcp_server_send_request(?)", [request]
    ).fetchone()[0]
    return json.loads(raw)


def list_tools(con):
    """Return the list of tool descriptors from the MCP server."""
    resp = mcp_request(con, "tools/list")
    return resp["result"]["tools"]


_mcp_schemas_cache = {}


def call_tool(con, tool_name, arguments=None):
    """Call an MCP tool and return the text content.

    Automatically fills missing optional parameters with null to work
    around duckdb_mcp#19 (omitted params aren't substituted with NULL).
    Tool SQL templates use NULLIF($param, 'null') to convert back.
    """
    args = dict(arguments or {})

    # Auto-fill missing params with null using cached tool schemas.
    # Keyed on connection id so multiple connections don't cross-pollinate.
    con_id = id(con)
    if con_id not in _mcp_schemas_cache:
        _mcp_schemas_cache[con_id] = {
            t["name"]: t["inputSchema"] for t in list_tools(con)
        }
    schema = _mcp_schemas_cache[con_id].get(tool_name, {})
    for prop in schema.get("properties", {}):
        if prop not in args:
            args[prop] = None

    resp = mcp_request(con, "tools/call", {
        "name": tool_name,
        "arguments": args,
    })
    assert "error" not in resp, (
        f"Tool {tool_name} error: {resp['error']['message']}"
    )
    return resp["result"]["content"][0]["text"]


def md_row_count(text):
    """Count data rows in a markdown table (excludes header + separator)."""
    lines = [l for l in text.strip().split("\n") if l.strip().startswith("|")]
    return max(0, len(lines) - 2)


# -- MCP server fixtures --


def _write_conversation_jsonl(base_dir):
    """Write synthetic JSONL under a .claude/projects/ path.

    Returns the path to the JSONL file. The directory structure matches
    the project_dir regex in sessions() so it can extract the project name.
    """
    conv_dir = base_dir / ".claude" / "projects" / "mcp-test-project"
    conv_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = conv_dir / "conversations.jsonl"
    with open(jsonl_path, "w") as f:
        for record in CONVERSATION_RECORDS:
            f.write(json.dumps(record) + "\n")
    return jsonl_path


def _create_mcp_server(profile, conv_jsonl_path=None):
    """Create an MCP server connection with the given profile.

    Loads all extensions, macros, tool publications, then applies the
    profile SQL (which sets mcp_server_options) and starts the server.

    If conv_jsonl_path is provided, bootstraps raw_conversations from it.
    Otherwise creates an empty raw_conversations table.

    Does NOT enable filesystem lockdown (enable_external_access = false)
    because tests create tmp_path files outside the project root.
    Lockdown is tested separately and enforced in the init scripts.
    """
    con = duckdb.connect(":memory:")
    # Extensions (must load before any sandbox lockdown)
    con.execute("LOAD read_lines")
    con.execute("LOAD sitting_duck")
    con.execute("LOAD markdown")
    con.execute("LOAD duck_tails")
    # Sandbox: set root and load resolve() macro
    con.execute(f"SET VARIABLE session_root = '{PROJECT_ROOT}'")
    load_sql(con, "sandbox.sql")
    # Macros
    load_sql(con, "source.sql")
    load_sql(con, "code.sql")
    load_sql(con, "docs.sql")
    load_sql(con, "repo.sql")
    # Conversation data
    if conv_jsonl_path:
        con.execute(f"""
            CREATE TABLE raw_conversations AS
            SELECT *, filename AS _source_file
            FROM read_json_auto(
                '{conv_jsonl_path}', union_by_name=true,
                maximum_object_size=33554432, filename=true
            )
        """)
    else:
        con.execute("""
            CREATE TABLE raw_conversations AS
            SELECT NULL::VARCHAR AS uuid, NULL::VARCHAR AS sessionId,
                   NULL::VARCHAR AS type,
                   NULL::STRUCT(role VARCHAR, content JSON, model VARCHAR, id VARCHAR, stop_reason VARCHAR, usage STRUCT(input_tokens BIGINT, output_tokens BIGINT, cache_creation_input_tokens BIGINT, cache_read_input_tokens BIGINT)) AS message,
                   NULL::TIMESTAMP AS timestamp, NULL::VARCHAR AS requestId,
                   NULL::VARCHAR AS slug, NULL::VARCHAR AS version,
                   NULL::VARCHAR AS gitBranch, NULL::VARCHAR AS cwd,
                   NULL::BOOLEAN AS isSidechain, NULL::BOOLEAN AS isMeta,
                   NULL::VARCHAR AS parentUuid, NULL::VARCHAR AS _source_file
            WHERE false
        """)
    load_sql(con, "conversations.sql")
    # Help system (materialize before lockdown, same as init script)
    materialize_help(con)
    load_sql(con, "help.sql")
    # MCP tools (skip missing files so partial implementations work)
    con.execute("LOAD duckdb_mcp")
    for tool_file in ["tools/files.sql", "tools/code.sql",
                      "tools/docs.sql", "tools/git.sql",
                      "tools/conversations.sql",
                      "tools/help.sql"]:
        try:
            load_sql(con, tool_file)
        except FileNotFoundError:
            pass
    # Apply profile and start server
    load_sql(con, profile)
    con.execute(
        "SELECT mcp_server_start('memory',"
        " getvariable('mcp_server_options'))"
    )
    return con


@pytest.fixture(scope="session")
def mcp_server(tmp_path_factory):
    """MCP server with analyst profile (all tools) via memory transport.

    Session-scoped: all MCP tests share one connection since tools are
    read-only queries. Analyst profile matches the default init-fledgling.sql
    behavior (query, describe, list_tables enabled).
    """
    base_dir = tmp_path_factory.mktemp("mcp")
    jsonl_path = _write_conversation_jsonl(base_dir)
    con = _create_mcp_server("profiles/analyst.sql", conv_jsonl_path=jsonl_path)
    yield con
    con.close()


def _list_tools_for_profile(profile):
    """List MCP tools for a profile in a subprocess.

    duckdb_mcp uses process-global server options, so a profile's tool
    list can only be tested in isolation. This runs _create_mcp_server()
    in a forked subprocess and returns the tool names.

    Note: relies on conftest.py being importable as a regular Python module
    (not just as a pytest plugin). This works because cwd=PROJECT_ROOT
    and tests/ is on sys.path in the subprocess.
    """
    import subprocess
    import sys
    script = f"""
import sys, json
sys.path.insert(0, {os.path.join(PROJECT_ROOT, 'tests')!r})
from conftest import _create_mcp_server, list_tools
con = _create_mcp_server({profile!r})
names = sorted(t["name"] for t in list_tools(con))
print(json.dumps(names))
con.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Subprocess failed: {result.stderr}")
    return json.loads(result.stdout.strip())


# -- Synthetic conversation data for conversation macro tests --

CONVERSATION_RECORDS = [
    # Session 1, record 1: user message with string content
    {
        "uuid": "u1", "parentUuid": None, "sessionId": "sess-001",
        "type": "user",
        "message": {"role": "user", "content": "Help me fix the bug in auth"},
        "timestamp": "2025-01-15T10:00:00Z",
        "requestId": None, "slug": "fix-auth", "version": "1.0.0",
        "gitBranch": "main", "cwd": "/projects/myapp",
        "isSidechain": False, "isMeta": False,
    },
    # Session 1, record 2: assistant with text + tool_use (Bash: git status)
    {
        "uuid": "u2", "parentUuid": "u1", "sessionId": "sess-001",
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Let me look at the code"},
                {"type": "tool_use", "id": "tu_001", "name": "Bash",
                 "input": {"command": "git status"}},
            ],
            "model": "claude-sonnet-4-20250514",
            "id": "msg_001", "stop_reason": "tool_use",
            "usage": {
                "input_tokens": 1000, "output_tokens": 200,
                "cache_read_input_tokens": 500,
            },
        },
        "timestamp": "2025-01-15T10:00:05Z",
        "requestId": "req_001", "slug": "fix-auth", "version": "1.0.0",
        "gitBranch": "main", "cwd": "/projects/myapp",
        "isSidechain": False, "isMeta": False,
    },
    # Session 1, record 3: user with tool_result array content
    {
        "uuid": "u3", "parentUuid": "u2", "sessionId": "sess-001",
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "tu_001",
                 "content": "On branch main\nnothing to commit"},
            ],
        },
        "timestamp": "2025-01-15T10:00:10Z",
        "requestId": None, "slug": "fix-auth", "version": "1.0.0",
        "gitBranch": "main", "cwd": "/projects/myapp",
        "isSidechain": False, "isMeta": False,
    },
    # Session 1, record 4: assistant with text + tool_use (Read)
    {
        "uuid": "u4", "parentUuid": "u3", "sessionId": "sess-001",
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "I see the issue in the auth module"},
                {"type": "tool_use", "id": "tu_002", "name": "Read",
                 "input": {"file_path": "/src/auth.py"}},
            ],
            "model": "claude-sonnet-4-20250514",
            "id": "msg_002", "stop_reason": "tool_use",
            "usage": {
                "input_tokens": 1200, "output_tokens": 300,
                "cache_read_input_tokens": 600,
            },
        },
        "timestamp": "2025-01-15T10:00:15Z",
        "requestId": "req_002", "slug": "fix-auth", "version": "1.0.0",
        "gitBranch": "main", "cwd": "/projects/myapp",
        "isSidechain": False, "isMeta": False,
    },
    # Session 1, record 5: progress event (no message body)
    {
        "uuid": "u5", "parentUuid": "u4", "sessionId": "sess-001",
        "type": "progress",
        "timestamp": "2025-01-15T10:00:20Z",
        "requestId": None, "slug": "fix-auth", "version": "1.0.0",
        "gitBranch": "main", "cwd": "/projects/myapp",
        "isSidechain": False, "isMeta": False,
    },
    # Session 2, record 6: user message with string content
    {
        "uuid": "u6", "parentUuid": None, "sessionId": "sess-002",
        "type": "user",
        "message": {"role": "user", "content": "Show me the project files"},
        "timestamp": "2025-01-15T11:00:00Z",
        "requestId": None, "slug": "explore", "version": "1.0.0",
        "gitBranch": "dev", "cwd": "/projects/other",
        "isSidechain": False, "isMeta": False,
    },
    # Session 2, record 7: assistant with tool_use (Bash: cat README.md)
    {
        "uuid": "u7", "parentUuid": "u6", "sessionId": "sess-002",
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "tu_003", "name": "Bash",
                 "input": {"command": "cat README.md"}},
            ],
            "model": "claude-haiku-4-20250414",
            "id": "msg_003", "stop_reason": "tool_use",
            "usage": {
                "input_tokens": 500, "output_tokens": 100,
                "cache_creation_input_tokens": 200,
            },
        },
        "timestamp": "2025-01-15T11:00:05Z",
        "requestId": "req_003", "slug": "explore", "version": "1.0.0",
        "gitBranch": "dev", "cwd": "/projects/other",
        "isSidechain": False, "isMeta": False,
    },
]


@pytest.fixture
def conversation_macros(con, tmp_path):
    """Connection with conversation macros + synthetic JSONL test data.

    Writes JSONL under a .claude/projects/test-project/ directory so the
    project_dir regex in sessions() can extract "test-project".
    """
    project_dir = tmp_path / ".claude" / "projects" / "test-project"
    project_dir.mkdir(parents=True)
    jsonl_path = project_dir / "conversations.jsonl"

    with open(jsonl_path, "w") as f:
        for record in CONVERSATION_RECORDS:
            f.write(json.dumps(record) + "\n")

    # Bootstrap: define load_conversations() inline so we can create
    # raw_conversations BEFORE loading conversations.sql. DuckDB validates
    # table references at macro definition time, so raw_conversations must
    # exist when conversations.sql's other macros are parsed.
    # conversations.sql redefines load_conversations() identically.
    con.execute(f"""
        CREATE OR REPLACE MACRO load_conversations(path) AS TABLE
            SELECT *, filename AS _source_file
            FROM read_json_auto(
                path, union_by_name=true,
                maximum_object_size=33554432, filename=true
            );
        CREATE TABLE raw_conversations AS
        SELECT * FROM load_conversations('{jsonl_path}')
    """)
    load_sql(con, "conversations.sql")
    return con
