"""DuckDB connection for fledgling-pro.

Thin wrapper around fledgling.connect() for the FastMCP layer.
"""

import fledgling


def create_connection(**kwargs):
    """Create a fledgling-enabled DuckDB connection.

    All arguments are passed to fledgling.connect().
    See fledgling.connection.connect for full documentation.
    """
    return fledgling.connect(**kwargs)
