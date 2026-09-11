import os

from server import mcp

if __name__ == "__main__":
    mcp.settings.host = os.getenv("NETWORK_MCP_HOST", "127.0.0.1")
    mcp.settings.port = int(os.getenv("NETWORK_MCP_PORT", "8000"))
    mcp.run(transport="streamable-http")