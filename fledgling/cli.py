"""CLI entry point for fledgling.

Thin wrapper that locates the bash CLI script bundled as package data
and execs it. All the real work happens in bin/fledgling-cli (bash).
"""

import os
import sys
import subprocess


def _find_data_dir():
    """Find the package data directory containing SQL files."""
    return os.path.dirname(os.path.abspath(__file__))


def _find_cli_script():
    """Find the fledgling-cli bash script."""
    pkg_dir = _find_data_dir()
    # Check package data location
    cli = os.path.join(pkg_dir, "bin", "fledgling-cli")
    if os.path.exists(cli):
        return cli
    # Check relative to package (development install)
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


def main():
    """Main CLI entry point."""
    args = sys.argv[1:]

    # Handle 'install' subcommand specially — run the DuckDB installer
    if args and args[0] == "install":
        return _handle_install(args[1:])

    # Everything else delegates to the bash CLI
    cli = _find_cli_script()
    if cli is None:
        print("Error: fledgling-cli script not found", file=sys.stderr)
        sys.exit(1)

    os.execvp("bash", ["bash", cli] + args)


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
