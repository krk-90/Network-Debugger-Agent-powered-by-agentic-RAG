import platform
import shutil
import socket
import ssl
import subprocess
import urllib.request
from typing import Any

from mcp.server.fastmcp import FastMCP


mcp = FastMCP("network-debugger")


def _run_command(command: list[str], timeout: int) -> dict[str, Any]:
    """Run a diagnostic command safely without invoking a shell."""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "return_code": result.returncode,
            "output": result.stdout or result.stderr,
        }
    except FileNotFoundError:
        return {
            "return_code": None,
            "output": None,
            "error": f"{command[0]} was not found on PATH",
        }
    except subprocess.TimeoutExpired:
        return {
            "return_code": None,
            "output": None,
            "error": f"{command[0]} timed out after {timeout}s",
        }


@mcp.tool()
def get_dns_config() -> dict[str, Any]:
    """Return the host DNS configuration on Windows or Linux."""
    if platform.system().lower() == "windows":
        return _run_command(["ipconfig", "/all"], 30)

    try:
        with open("/etc/resolv.conf", "r", encoding="utf-8") as file:
            return {"return_code": 0, "output": file.read()}
    except OSError as error:
        return {"return_code": None, "output": None, "error": str(error)}


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
    try:
        addresses = sorted({item[4][0] for item in socket.getaddrinfo(host, None)})
        return {"host": host, "addresses": addresses}
    except socket.gaierror as error:
        return {"host": host, "addresses": [], "error": str(error)}


@mcp.tool()
def ping(host: str, count: int = 4) -> dict[str, Any]:
    """Send ICMP echo requests using the host operating system's ping utility."""
    count = max(1, min(count, 10))
    if platform.system().lower() == "windows":
        command = ["ping", "-n", str(count), host]
    else:
        command = ["ping", "-c", str(count), host]
    return {"host": host, **_run_command(command, 30)}


@mcp.tool()
def traceroute(host: str, max_hops: int = 12) -> dict[str, Any]:
    """Trace the route to a host on Windows or Linux."""
    max_hops = max(1, min(max_hops, 30))
    if platform.system().lower() == "windows":
        command = ["tracert", "-h", str(max_hops), host]
    else:
        executable = shutil.which("traceroute") or shutil.which("tracepath")
        if not executable:
            return {
                "host": host,
                "return_code": None,
                "output": None,
                "error": "Neither traceroute nor tracepath is installed on the server",
            }
        command = (
            [executable, "-m", str(max_hops), host]
            if executable.endswith("traceroute")
            else [executable, host]
        )
    return {"host": host, **_run_command(command, 60)}


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
    """Run MTR if it is installed on the server."""
    executable = shutil.which("mtr")
    if not executable:
        return {
            "host": host,
            "available": False,
            "error": "mtr was not found on PATH",
        }

    cycles = max(1, min(cycles, 20))
    result = _run_command(
        [executable, "--report", "--report-cycles", str(cycles), host],
        120,
    )
    return {"host": host, "available": True, **result}


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
