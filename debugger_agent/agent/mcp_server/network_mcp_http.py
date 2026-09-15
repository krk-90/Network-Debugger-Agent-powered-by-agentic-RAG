import os

from mcp.server.transport_security import TransportSecuritySettings

from server import mcp


if __name__ == "__main__":
    host = os.getenv("NETWORK_MCP_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", os.getenv("NETWORK_MCP_PORT", "10000")))
    mcp_host = os.getenv("NETWORK_MCP_ALLOWED_HOST", "network-debugger-mcp.onrender.com")
    allowed_origin = os.getenv(
        "NETWORK_MCP_ALLOWED_ORIGIN",
        "https://network-debugger-frontend.onrender.com",
    )

    # FastMCP v1.x reads HTTP settings from mcp.settings.
    # Explicitly allow the deployed hostname while keeping DNS-rebinding
    # protection enabled.
    mcp.settings.host = host
    mcp.settings.port = port
    mcp.settings.streamable_http_path = "/mcp"
    mcp.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[mcp_host, f"{mcp_host}:*"],
        allowed_origins=[allowed_origin],
    )

    print(f"Starting network MCP on {host}:{port}/mcp")
    print(f"Allowed MCP host: {mcp_host}")
    print(f"Allowed browser origin: {allowed_origin}")

    mcp.run(transport="streamable-http")
