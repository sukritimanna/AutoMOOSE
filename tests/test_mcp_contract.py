"""MCP tool-contract test.

Verifies that the MCP server declares exactly the ten tools documented in the
article, each with a name, description, and input schema. Importing the MCP
server pulls in the ``mcp`` and ``httpx`` packages but does not start a server
or contact any backend, so the check stays offline. If those optional
packages are not installed the test skips rather than failing.
"""
import pytest

mcp_server = pytest.importorskip(
    "automoose.mcp_server",
    reason="mcp and httpx are required for the MCP tool-contract test",
)

EXPECTED_TOOLS = {
    "health_check",
    "list_plugins",
    "generate_input",
    "run_simulation",
    "run_sweep",
    "get_run_status",
    "get_results",
    "list_runs",
    "get_log_tail",
    "stop_run",
}


def test_exactly_ten_documented_tools():
    names = {tool.name for tool in mcp_server.TOOLS}
    assert names == EXPECTED_TOOLS
    assert len(mcp_server.TOOLS) == len(EXPECTED_TOOLS)


def test_every_tool_has_a_contract():
    for tool in mcp_server.TOOLS:
        assert tool.name
        assert tool.description
        assert tool.inputSchema  # JSON schema for the tool's arguments
