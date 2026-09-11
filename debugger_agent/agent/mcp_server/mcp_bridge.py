import os

from langchain_mcp_adapters.client import MultiServerMCPClient


async def get_network_tools():
    client = MultiServerMCPClient(
        {
            "network": {
                "transport": "streamable_http",
                "url": os.getenv(
                    "NETWORK_MCP_URL",
                    "http://127.0.0.1:8000/mcp",
                ),
            }
        }
    )
    return await client.get_tools()