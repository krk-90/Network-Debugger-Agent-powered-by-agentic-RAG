import os

from langchain_mcp_adapters.client import MultiServerMCPClient


async def get_network_tools():
    mcp_url = os.getenv("NETWORK_MCP_URL")
    if not mcp_url:
        port = os.getenv("PORT", "10000")
        mcp_url = f"http://127.0.0.1:{port}/mcp"

    client = MultiServerMCPClient(
        {
            "network": {
                "transport": "streamable_http",
                "url": mcp_url.rstrip("/"),
            }
        }
    )
    return await client.get_tools()
