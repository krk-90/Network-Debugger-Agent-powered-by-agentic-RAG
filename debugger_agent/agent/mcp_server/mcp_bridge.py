import os

from langchain_mcp_adapters.client import MultiServerMCPClient


async def get_network_tools():
    # Local development can override this with localhost. Production uses the
    # dedicated Render MCP service so the API never tries to call itself.
    mcp_url = os.getenv(
        "NETWORK_MCP_URL",
        "https://network-debugger-mcp.onrender.com/mcp",
    ).rstrip("/")

    client = MultiServerMCPClient(
        {
            "network": {
                "transport": "streamable_http",
                "url": mcp_url,
            }
        }
    )
    return await client.get_tools()
