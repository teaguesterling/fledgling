"""CLI entry point for fledgling-edit.

Usage:
    python -m fledgling.edit.cli rename "**/*.py" old_name new_name
    python -m fledgling.edit.cli remove "**/*.py" MyClass --apply
    python -m fledgling.edit.cli match-replace "**/*.py" "pattern" "template" --lang python
    python -m fledgling.edit.cli move "src/main.py" helper "src/utils.py" --apply
"""

from __future__ import annotations

import argparse
import os
import sys

import duckdb


def _make_connection():
    """Create a DuckDB connection with sitting_duck + macros loaded."""
    con = duckdb.connect(":memory:")
    con.execute("LOAD sitting_duck")
    con.execute("LOAD read_lines")
    # Load SQL macros from the fledgling sql/ directory
    sql_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "sql",
    )
    for f in ["source.sql", "code.sql"]:
        path = os.path.join(sql_dir, f)
        if os.path.exists(path):
            _load_sql(con, path)
    return con


def _load_sql(con, path):
    with open(path) as f:
        sql = f.read()
    lines = [l for l in sql.split("\n") if not l.strip().startswith("--")]
    cleaned = "\n".join(lines)
    for stmt in cleaned.split(";"):
        stmt = stmt.strip()
        if stmt:
            con.execute(stmt + ";")


def _make_editor(con):
    from fledgling.edit.builder import Editor
    return Editor(con)


def cmd_rename(args):
    con = _make_connection()
    ed = _make_editor(con)
    cs = ed.definitions(args.file_pattern, args.name).rename(args.new_name)
    if args.apply:
        paths = cs.apply()
        print(f"Applied to: {', '.join(paths)}")
    else:
        print(cs.diff())


def cmd_remove(args):
    con = _make_connection()
    ed = _make_editor(con)
    cs = ed.definitions(args.file_pattern, args.name).remove()
    if args.apply:
        paths = cs.apply()
        print(f"Applied to: {', '.join(paths)}")
    else:
        print(cs.diff())


def cmd_move(args):
    con = _make_connection()
    ed = _make_editor(con)
    cs = ed.definitions(args.file_pattern, args.name).move_to(args.destination)
    if args.apply:
        paths = cs.apply()
        print(f"Applied to: {', '.join(paths)}")
    else:
        print(cs.diff())


def cmd_match_replace(args):
    con = _make_connection()
    from fledgling.edit.locate import match_replace
    cs = match_replace(con, args.file_pattern, args.pattern, args.template,
                       args.lang)
    if args.apply:
        paths = cs.apply()
        print(f"Applied to: {', '.join(paths)}")
    else:
        print(cs.diff())


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="fledgling-edit",
        description="AST-aware code editing tools",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # rename
    p = sub.add_parser("rename", help="Rename a definition")
    p.add_argument("file_pattern", help="Glob pattern for files")
    p.add_argument("name", help="Current name")
    p.add_argument("new_name", help="New name")
    p.add_argument("--apply", action="store_true", help="Write changes")
    p.set_defaults(func=cmd_rename)

    # remove
    p = sub.add_parser("remove", help="Remove a definition")
    p.add_argument("file_pattern", help="Glob pattern for files")
    p.add_argument("name", help="Name to remove")
    p.add_argument("--apply", action="store_true", help="Write changes")
    p.set_defaults(func=cmd_remove)

    # move
    p = sub.add_parser("move", help="Move a definition to another file")
    p.add_argument("file_pattern", help="Source glob pattern")
    p.add_argument("name", help="Definition name")
    p.add_argument("destination", help="Destination file path")
    p.add_argument("--apply", action="store_true", help="Write changes")
    p.set_defaults(func=cmd_move)

    # match-replace
    p = sub.add_parser("match-replace", help="Pattern match/replace")
    p.add_argument("file_pattern", help="Glob pattern for files")
    p.add_argument("pattern", help="Code pattern with __NAME__ wildcards")
    p.add_argument("template", help="Replacement template (empty to remove)")
    p.add_argument("--lang", required=True, help="Language (e.g., python)")
    p.add_argument("--apply", action="store_true", help="Write changes")
    p.set_defaults(func=cmd_match_replace)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
