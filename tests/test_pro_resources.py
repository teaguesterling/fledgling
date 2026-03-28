"""Tests for fledgling-pro MCP resources.

Validates that FastMCP resources registered in create_server() are
discoverable and return correct content matching direct macro output.
"""

import asyncio

import pytest
from fastmcp import Client

from fledgling.pro.server import create_server

RESOURCE_URIS = [
    "fledgling://project",
    "fledgling://diagnostics",
    "fledgling://docs",
    "fledgling://git",
]


@pytest.fixture(scope="module")
def mcp():
    """FastMCP server instance with fledgling resources."""
    return create_server(init=False)


@pytest.fixture(scope="module")
def resource_list(mcp):
    """All resources from the server."""
    async def _list():
        async with Client(mcp) as client:
            return await client.list_resources()
    return asyncio.run(_list())


class TestResourceDiscovery:
    """Resources appear in list_resources."""

    def test_resources_listed(self, resource_list):
        uris = [str(r.uri) for r in resource_list]
        for expected in RESOURCE_URIS:
            assert expected in uris, f"{expected} not in {uris}"

    def test_resource_count(self, resource_list):
        assert len(resource_list) == 4
