import os

from server import mcp


if __name__ == "__main__":
    host = os.getenv("NETWORK_MCP_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", os.getenv("NETWORK_MCP_PORT", "10000")))

    print(f"Starting network MCP on {host}:{port}/mcp")

    mcp.run(
        transport="streamable-http",
        host=host,
        port=port,
        streamable_http_path="/mcp",
    )
