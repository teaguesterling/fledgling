"""Fledgling: MCP tools for AI coding agents, powered by DuckDB."""

try:
    from importlib.metadata import version as _version
    __version__ = _version("fledgling-mcp")
except Exception:
    __version__ = "0.6.2"  # fallback for editable installs / dev

from fledgling.connection import connect

__all__ = ["connect", "__version__"]
