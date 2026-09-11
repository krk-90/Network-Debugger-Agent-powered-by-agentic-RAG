import socket
import ssl
import subprocess
import urllib.request
from typing import Any

from mcp.server.fastmcp import FastMCP


mcp = FastMCP("network-debugger")


@mcp.tool()
def get_dns_config() -> dict[str, Any]:
    """Return the host DNS configuration on Windows."""
    result = subprocess.run(
        ["ipconfig", "/all"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return {
        "return_code": result.returncode,
        "output": result.stdout or result.stderr,
    }


@mcp.tool()
def get_public_ip() -> dict[str, Any]:
    """Return the public IPv4 address visible to an external service."""
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=10) as response:
            return {"public_ip": response.read().decode("utf-8").strip()}
    except (OSError, ValueError) as error:
        return {"public_ip": None, "error": str(error)}


@mcp.tool()
def dns_lookup(host: str) -> dict[str, Any]:
    """Resolve a hostname to IPv4 and IPv6 addresses."""
    addresses = sorted({item[4][0] for item in socket.getaddrinfo(host, None)})
    return {"host": host, "addresses": addresses}


@mcp.tool()
def ping(host: str, count: int = 4) -> dict[str, Any]:
    """Send ICMP echo requests to a host."""
    result = subprocess.run(
        ["ping", "-n", str(max(1, count)), host],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return {
        "host": host,
        "return_code": result.returncode,
        "output": result.stdout or result.stderr,
    }


@mcp.tool()
def traceroute(host: str, max_hops: int = 12) -> dict[str, Any]:
    """Trace the route to a host on Windows."""
    result = subprocess.run(
        ["tracert", "-h", str(max(1, max_hops)), host],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return {
        "host": host,
        "return_code": result.returncode,
        "output": result.stdout or result.stderr,
    }


@mcp.tool()
def tcp_check(host: str, port: int, timeout: float = 5.0) -> dict[str, Any]:
    """Check whether a TCP connection can be established."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"host": host, "port": port, "reachable": True}
    except OSError as error:
        return {
            "host": host,
            "port": port,
            "reachable": False,
            "error": str(error),
        }


@mcp.tool()
def port_check(host: str, port: int, timeout: float = 5.0) -> dict[str, Any]:
    """Check whether a TCP port is accepting connections."""
    return tcp_check(host, port, timeout)


@mcp.tool()
def mtr(host: str, cycles: int = 10) -> dict[str, Any]:
    """Run MTR to a host; install MTR separately on Windows."""
    try:
        result = subprocess.run(
            ["mtr", "--report", "--report-cycles", str(max(1, cycles)), host],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except FileNotFoundError:
        return {
            "host": host,
            "available": False,
            "error": "mtr was not found on PATH. Install mtr and try again.",
        }
    except subprocess.TimeoutExpired:
        return {"host": host, "available": True, "error": "mtr timed out"}

    return {
        "host": host,
        "available": True,
        "return_code": result.returncode,
        "output": result.stdout or result.stderr,
    }


@mcp.tool()
def tls_check(host: str, port: int = 443, timeout: float = 5.0) -> dict[str, Any]:
    """Perform a TLS handshake and return certificate details."""
    context = ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=timeout) as connection:
            with context.wrap_socket(connection, server_hostname=host) as tls_socket:
                certificate = tls_socket.getpeercert()
                return {
                    "host": host,
                    "port": port,
                    "valid": True,
                    "tls_version": tls_socket.version(),
                    "subject": certificate.get("subject"),
                    "issuer": certificate.get("issuer"),
                }
    except (OSError, ssl.SSLError) as error:
        return {
            "host": host,
            "port": port,
            "valid": False,
            "error": str(error),
        }