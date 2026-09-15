import os
from urllib.parse import urlparse

from langchain_core.tools import StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from .server import (
    dns_lookup,
    get_dns_config,
    get_public_ip,
    mtr,
    ping,
    port_check,
    tcp_check,
    tls_check,
    traceroute,
)


_LOCAL_HOSTS = {"127.0.0.1", "localhost", "0.0.0.0", "::1"}


def _is_local_mcp_url(url: str) -> bool:
    """Return True when NETWORK_MCP_URL points back to this process."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.hostname in _LOCAL_HOSTS


def _in_process_network_tools():
    """Expose the same MCP tools directly as LangChain tools.

    The unified Render deployment hosts FastAPI and the MCP endpoint in the
    same process. FastMCP v1.x has a Starlette Route wrapper that can reject
    POSTs with 405 when self-called through localhost. Calling the underlying
    diagnostic functions directly avoids that self-HTTP loop while preserving
    the exact same tool implementations.
    """
    functions = [
        get_dns_config,
        get_public_ip,
        dns_lookup,
        ping,
        traceroute,
        tcp_check,
        port_check,
        mtr,
        tls_check,
    ]
    return [
        StructuredTool.from_function(
            func=function,
            name=function.__name__,
            description=function.__doc__ or function.__name__,
        )
        for function in functions
    ]


async def get_network_tools():
    mcp_url = os.getenv("NETWORK_MCP_URL", "").strip()

    # If a separate MCP service is configured, keep using MCP remotely.
    # In the unified Render service NETWORK_MCP_URL points to localhost;
    # use the in-process tools instead of making the app call itself over HTTP.
    if mcp_url and not _is_local_mcp_url(mcp_url):
        client = MultiServerMCPClient(
            {
                "network": {
                    "transport": "streamable_http",
                    "url": mcp_url.rstrip("/"),
                }
            }
        )
        return await client.get_tools()

    return _in_process_network_tools()
