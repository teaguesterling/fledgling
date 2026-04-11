"""Fledgling: MCP tools for AI coding agents, powered by DuckDB."""

try:
    from importlib.metadata import version as _version
    __version__ = _version("fledgling-mcp")
except Exception:
    __version__ = "0.7.0"  # fallback for editable installs / dev

from fledgling.connection import (
    connect,
    attach,
    configure,
    lockdown,
    load_extensions,
    set_session_root,
    load_macros,
    apply_local_init,
    Connection,
)

__all__ = [
    "connect",
    "attach",
    "configure",
    "lockdown",
    "load_extensions",
    "set_session_root",
    "load_macros",
    "apply_local_init",
    "Connection",
    "__version__",
]
