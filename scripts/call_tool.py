#!/usr/bin/env python3
"""Call a Fledgling MCP tool from the command line.

Usage:
    python scripts/call_tool.py ToolName [key=value ...]

Examples:
    python scripts/call_tool.py Help
    python scripts/call_tool.py ListFiles pattern='sql/tools/*.sql'
    python scripts/call_tool.py ReadLines file_path=CLAUDE.md lines=1-10
    python scripts/call_tool.py GitChanges count=5
    python scripts/call_tool.py CodeStructure file_pattern='tests/conftest.py'
"""

import json
import os
import sys

# Import shared test infrastructure
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))
from conftest import _create_mcp_server, mcp_request, call_tool  # noqa: E402


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        sys.exit(1)

    tool_name = sys.argv[1]

    # Parse key=value arguments
    args = {}
    for arg in sys.argv[2:]:
        if "=" not in arg:
            print(f"Error: arguments must be key=value, got: {arg}",
                  file=sys.stderr)
            sys.exit(1)
        key, value = arg.split("=", 1)
        args[key] = value

    # Create server with analyst profile, loading real conversation data
    # if available. Falls back to empty conversations on parse errors
    # (some JSONL files may be malformed).
    conv_root = os.path.expanduser("~/.claude/projects")
    conv_pattern = os.path.join(conv_root, "*/*.jsonl")
    import glob as globmod
    conv_path = conv_pattern if globmod.glob(conv_pattern) else None
    try:
        con = _create_mcp_server("profiles/analyst.sql",
                                 conv_jsonl_path=conv_path)
    except Exception:
        con = _create_mcp_server("profiles/analyst.sql")

    try:
        result = call_tool(con, tool_name, args)
        print(result)
    except AssertionError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        con.close()


if __name__ == "__main__":
    main()
