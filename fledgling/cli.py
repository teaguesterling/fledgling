"""CLI entry points for fledgling.

Two entry points:

  fledgling          — thin wrapper delegating to bash CLI (bin/fledgling-cli)
  fledgling-mcp      — launches DuckDB MCP server using bundled SQL
"""

import os
import re
import sys
import subprocess


def _find_data_dir():
    """Find the package data directory containing SQL files."""
    return os.path.dirname(os.path.abspath(__file__))


def _find_fledgling_home():
    """Find the directory containing init/ and sql/ subdirectories.

    In an installed package this is the package dir itself (hatch
    force-includes sql/ and init/ into fledgling/).  In a dev install
    they live at the repo root, one level above the package dir.
    """
    pkg_dir = _find_data_dir()
    if os.path.isdir(os.path.join(pkg_dir, "init")):
        return pkg_dir
    repo_root = os.path.dirname(pkg_dir)
    if os.path.isdir(os.path.join(repo_root, "init")):
        return repo_root
    return None


def _find_cli_script():
    """Find the fledgling-cli bash script."""
    pkg_dir = _find_data_dir()
    cli = os.path.join(pkg_dir, "bin", "fledgling-cli")
    if os.path.exists(cli):
        return cli
    repo_root = os.path.dirname(pkg_dir)
    cli = os.path.join(repo_root, "bin", "fledgling-cli")
    if os.path.exists(cli):
        return cli
    return None


def _find_installer():
    """Find the install-fledgling.sql script."""
    pkg_dir = _find_data_dir()
    installer = os.path.join(pkg_dir, "sql", "install-fledgling.sql")
    if os.path.exists(installer):
        return installer
    repo_root = os.path.dirname(pkg_dir)
    installer = os.path.join(repo_root, "sql", "install-fledgling.sql")
    if os.path.exists(installer):
        return installer
    return None


# ── fledgling entry point ──────────────────────────────────────────


def main():
    """Main CLI entry point (fledgling command)."""
    args = sys.argv[1:]

    if args and args[0] == "install":
        return _handle_install(args[1:])

    cli = _find_cli_script()
    if cli is None:
        print("Error: fledgling-cli script not found", file=sys.stderr)
        sys.exit(1)

    os.execvp("bash", ["bash", cli] + args)


# ── fledgling-mcp entry point ─────────────────────────────────────


_LOAD_STATEMENT = re.compile(r"^\s*LOAD\s+([A-Za-z_][A-Za-z0-9_]*)\s*;", re.M)
_READ_DIRECTIVE = re.compile(r"^\s*\.read\s+'?([^'\s]+)'?\s*$", re.M)


def _init_chain_extensions(entry_files, fledgling_home):
    """Return the extension names the init chain LOADs, in order.

    The profile init files carry no LOAD statements of their own — they
    `.read` init-fledgling-base.sql, which is where the LOADs live — so the
    chain has to be walked rather than the entry file scanned.  A relative
    path in a `.read` directive resolves against fledgling_home, because
    mcp_main() `.cd`s there before reading anything.
    """
    names = []
    seen = set()
    queue = [f for f in entry_files if f]
    while queue:
        path = os.path.realpath(queue.pop(0))
        if path in seen or not os.path.isfile(path):
            continue
        seen.add(path)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for name in _LOAD_STATEMENT.findall(text):
            if name not in names:
                names.append(name)
        for ref in _READ_DIRECTIVE.findall(text):
            queue.append(ref if os.path.isabs(ref) else os.path.join(fledgling_home, ref))
    return names


def _ensure_extensions(names):
    """INSTALL the extensions the init chain LOADs, where they are missing.

    `LOAD x` does not install x.  ~/.duckdb/extensions is keyed by DuckDB
    version, so a fresh machine — or this machine after a DuckDB upgrade —
    has an empty store for that version and the first LOAD in the init chain
    fails.  An error inside a `.read` file is fatal to the CLI, so the server
    dies there rather than serving degraded.

    The install runs through the `duckdb` binary rather than the python duckdb
    module.  The two are often different versions (measured on longbottom:
    python 2.0.0 beside a CLI v1.5.6), and each reads only its own versioned
    extension directory, so installing from python can fill a store the CLI
    never looks at.

    Only missing extensions are installed, so a warm store costs one extra
    duckdb invocation (29ms measured) and no network.
    """
    if not names:
        # The init chain always LOADs something, so an empty list means the
        # scan above broke rather than that nothing is needed.  Not fatal: a
        # hand-written init chain is allowed to load nothing.
        print(
            "Warning: found no LOAD statements in the init chain; "
            "extensions will not be installed",
            file=sys.stderr,
        )
        return

    probe = subprocess.run(
        ["duckdb", "-noheader", "-list", "-c",
         "SELECT extension_name FROM duckdb_extensions() WHERE installed"],
        capture_output=True, text=True,
    )
    # A failed probe is treated as "nothing installed": the INSTALLs below are
    # then no-ops on a warm store, so the fallback costs latency, not failure.
    present = set(probe.stdout.split()) if probe.returncode == 0 else set()

    for name in names:
        if name in present:
            continue
        # Most of what fledgling loads is a community extension; fts is core
        # and installs without FROM community.
        for statement in (f"INSTALL {name} FROM community", f"INSTALL {name}"):
            attempt = subprocess.run(["duckdb", "-c", statement], capture_output=True, text=True)
            if attempt.returncode == 0:
                break
        else:
            print(
                f"Error: cannot install DuckDB extension '{name}': "
                f"{attempt.stderr.strip() or 'unknown error'}",
                file=sys.stderr,
            )
            sys.exit(1)


def mcp_main():
    """MCP server entry point (fledgling-mcp command).

    Locates the bundled init SQL, sets up DuckDB with the correct
    session variables, and execs duckdb.  Works globally — no
    project-specific .fledgling-init.sql required.  If one exists
    in the project root it is applied as an overlay.
    """
    import shutil

    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        print("Usage: fledgling-mcp serve [--profile analyst] [--transport stdio|sse] [--root DIR]", file=sys.stderr)
        sys.exit(0 if args else 1)

    if args[0] != "serve":
        print(f"Unknown command: {args[0]}", file=sys.stderr)
        print("Usage: fledgling-mcp serve [--profile analyst] [--transport stdio|sse] [--root DIR]", file=sys.stderr)
        sys.exit(1)

    profile = "analyst"
    transport = "stdio"
    root = os.path.abspath(os.getcwd())
    i = 1
    while i < len(args):
        if args[i] == "--profile" and i + 1 < len(args):
            profile = args[i + 1]
            i += 2
        elif args[i] == "--transport" and i + 1 < len(args):
            transport = args[i + 1]
            i += 2
        elif args[i] == "--root" and i + 1 < len(args):
            root = os.path.abspath(args[i + 1])
            i += 2
        else:
            print(f"Unknown flag: {args[i]}", file=sys.stderr)
            sys.exit(1)

    if not shutil.which("duckdb"):
        print("Error: duckdb CLI not found in PATH", file=sys.stderr)
        sys.exit(1)

    fledgling_home = _find_fledgling_home()
    if fledgling_home is None:
        print("Error: fledgling SQL files not found", file=sys.stderr)
        sys.exit(1)

    init_file = os.path.join(fledgling_home, "init", f"init-fledgling-{profile}.sql")
    if not os.path.exists(init_file):
        print(f"Error: init file for profile '{profile}' not found: {init_file}", file=sys.stderr)
        sys.exit(1)

    # .cd to fledgling home so the init file's relative .read
    # directives (e.g. ".read sql/profiles/analyst.sql") resolve
    # against the bundled SQL tree.
    cmd = [
        "duckdb",
        "-cmd", f".cd '{fledgling_home}'",
        "-cmd", f"SET VARIABLE session_root = '{root}'",
        "-cmd", f"SET VARIABLE transport = '{transport}'",
        "-cmd", f"CREATE OR REPLACE MACRO _resolve(p) AS CASE WHEN p IS NULL THEN NULL WHEN p[1] = '/' THEN p ELSE '{root}/' || p END",
        "-cmd", f"CREATE OR REPLACE MACRO _session_root() AS '{root}'",
        "-cmd", f".read {init_file}",
    ]

    # Apply project-local overlay if present
    local_init = os.path.join(root, ".fledgling-init.sql")
    if os.path.exists(local_init):
        cmd.extend(["-cmd", f".read '{local_init}'"])

    # The extensions have to be on disk before the exec: LOAD does not install,
    # and a failed LOAD inside the init is fatal to the CLI.
    _ensure_extensions(_init_chain_extensions([init_file, local_init], fledgling_home))

    os.execvp("duckdb", cmd)


def _handle_install(args):
    """Run the fledgling installer.

    Usage:
        fledgling install                    # default config
        fledgling install --modules source,code,repo
        fledgling install --profile core
        fledgling install --cli
    """
    import shutil

    if not shutil.which("duckdb"):
        print("Error: duckdb CLI not found in PATH", file=sys.stderr)
        print("Install: brew install duckdb  (or see https://duckdb.org/docs/installation/)", file=sys.stderr)
        sys.exit(1)

    installer = _find_installer()
    if installer is None:
        # Fall back to curl from GitHub
        print("Using remote installer...")
        cmd = ["bash", "-c",
               "curl -sL https://teaguesterling.github.io/fledgling/install.sql | duckdb"]
    else:
        # Use local installer
        cmd = ["bash", "-c", f"duckdb < {installer}"]

    # Parse --modules, --profile, --cli flags
    config_parts = []
    i = 0
    while i < len(args):
        if args[i] == "--modules" and i + 1 < len(args):
            modules = args[i + 1].split(",")
            quoted = ", ".join(f"'{m.strip()}'" for m in modules)
            config_parts.append(f"modules: [{quoted}]")
            i += 2
        elif args[i] == "--profile" and i + 1 < len(args):
            config_parts.append(f"profile: '{args[i + 1]}'")
            i += 2
        elif args[i] == "--cli":
            config_parts.append("cli: true")
            i += 1
        else:
            print(f"Unknown flag: {args[i]}", file=sys.stderr)
            sys.exit(1)

    if config_parts:
        config = ", ".join(config_parts)
        if installer:
            cmd = ["bash", "-c",
                   f'duckdb -cmd "SET VARIABLE fledgling_config = {{{config}}}" < {installer}']
        else:
            cmd = ["bash", "-c",
                   f'curl -sL https://teaguesterling.github.io/fledgling/install.sql '
                   f'| duckdb -cmd "SET VARIABLE fledgling_config = {{{config}}}"']

    sys.exit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
