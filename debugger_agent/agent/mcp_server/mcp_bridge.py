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


def _is_self_hosted_mcp_url(url: str) -> bool:
    """Return True when NETWORK_MCP_URL points to this unified service."""
    try:
        hostname = urlparse(url).hostname
    except ValueError:
        return False

    if not hostname:
        return False

    if hostname in _LOCAL_HOSTS:
        return True

    # In the unified Render deployment, FastAPI and MCP share one process.
    # Calling the public Render URL from that same process creates a
    # self-HTTP loop and can hit the FastMCP/Starlette 405 routing path.
    self_hosts = {
        os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip().lower(),
        os.getenv("NETWORK_MCP_ALLOWED_HOST", "").strip().lower(),
    }
    self_hosts.discard("")
    return hostname.lower() in self_hosts


def _in_process_network_tools():
    """Expose the same MCP tools directly as LangChain tools.

    The unified Render deployment hosts FastAPI and the MCP endpoint in the
    same process. Calling the underlying diagnostic functions directly avoids
    a self-HTTP loop while preserving the exact same tool implementations.
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

    # Use remote MCP only when it points to a genuinely separate MCP service.
    # If it points back to this Render service, stay in-process.
    if mcp_url and not _is_self_hosted_mcp_url(mcp_url):
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
