# Network Debugger Agent (powered by Agentic RAG)

An AI-powered network debugging agent that routes natural-language diagnostic requests (e.g. *"ping google.com"*, *"resolve github.com"*, *"check if port 443 is open on cloudflare.com"*) to specialized LLM agents, each backed by live network tools exposed over MCP (Model Context Protocol).

## How it works

```
Client
  │  POST /diagnostics
  ▼
FastAPI (app/backend)
  │
  ▼
Orchestrator ──▶ keyword-routes the query to one or more specialist agents
  │
  ├─▶ DNS Agent            (dns_lookup, get_dns_config)
  ├─▶ Connectivity Agent   (ping, traceroute, mtr, get_public_ip)
  └─▶ Service/TLS Agent    (tcp_check, port_check, tls_check)
        │
        ▼
   MCP Bridge (LangChain MCP client)
        │
        ▼
   Network Debugger MCP Server (FastMCP, streamable-http)
        │
        ▼
   Real system calls (ping, tracert, socket, ssl, urllib)
```

Each specialist is a LangChain agent (Groq-hosted LLM, `openai/gpt-oss-20b`) restricted to a specific subset of tools. The orchestrator selects relevant specialists by keyword match, runs them concurrently, and merges their responses.

## Project structure

```
.
├── LICENSE                     # Apache-2.0
├── .env.example                # Environment variable template (fill in and rename to .env)
├── app/
│   └── backend/
│       ├── __init__.py
│       ├── main.py             # FastAPI app entry point (exposes `fastapi_app`)
│       └── route.py            # /diagnostics route definition
└── debugger_agent/
    ├── __init__.py
    └── agent/
        ├── __init__.py
        ├── orchestrator.py     # Keyword-based agent routing + concurrent execution
        ├── sub_agents.py       # DNS / connectivity / service specialist agents
        └── mcp_server/
            ├── __init__.py
            ├── server.py             # FastMCP server exposing network tools
            ├── network_mcp_http.py   # Entry point to run the MCP server (streamable-http)
            └── mcp_bridge.py         # LangChain MCP client bridge
```

## Prerequisites

- Python 3.11+
- A [Groq API key](https://console.groq.com/)
- `pip` / a virtual environment

> **Platform note:** `server.py`'s `get_dns_config`, `ping`, and `traceroute` tools currently shell out to **Windows-specific commands** (`ipconfig`, `ping -n`, `tracert`). On Linux/macOS these will need to be adapted (`ip addr`/`ifconfig`, `ping -c`, `traceroute`).

## Installation

```bash
git clone https://github.com/krk-90/Network-Debugger-Agent-powered-by-agentic-RAG.git
cd Network-Debugger-Agent-powered-by-agentic-RAG

python -m venv .venv

# Windows
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate
```

## Environment variables

Copy `.env.example` to `.env` and fill in:

```bash
GROQ_API_KEY=your_groq_api_key_here

# Optional overrides (defaults shown)
NETWORK_MCP_HOST=127.0.0.1
NETWORK_MCP_PORT=8000
NETWORK_MCP_URL=http://127.0.0.1:8000/mcp
```

## Running the project

This project requires **two processes** running at the same time.

### 1. Start the MCP server (network tools)

`network_mcp_http.py` imports its FastMCP instance with a bare `from server import mcp`, so it must be run **from inside its own folder**:

```bash
cd debugger_agent/agent/mcp_server
python network_mcp_http.py
```

This starts a FastMCP server on `http://127.0.0.1:8000/mcp` exposing the tools:
`dns_lookup`, `get_dns_config`, `get_public_ip`, `ping`, `traceroute`, `mtr`, `tcp_check`, `port_check`, `tls_check`.

### 2. Start the FastAPI backend

In a **separate terminal**, from the **project root**:

```bash
uvicorn app.backend.main:fastapi_app --reload --port 8080
```

Interactive API docs will be available at `http://127.0.0.1:8080/docs`.

## Usage

### Via Swagger UI
Open `http://127.0.0.1:8080/docs`, expand `POST /diagnostics/`, and try it with a body like:

```json
{
  "query": "ping google.com"
}
```

### Via curl

```bash
curl -X POST http://127.0.0.1:8080/diagnostics/ \
  -H "Content-Type: application/json" \
  -d '{"query": "resolve github.com"}'
```

### Example queries

| Query | Routed to |
|---|---|
| `resolve github.com` | DNS specialist |
| `ping google.com` | Connectivity specialist |
| `traceroute to cloudflare.com` | Connectivity specialist |
| `check if port 443 is open on google.com` | Service/TLS specialist |
| `resolve and ping openai.com, then check its tls certificate` | All three, concurrently |
| *(no matching keywords)* | Falls back to running all three specialists |

### Example response

```json
{
  "results": {
    "dns": "DNS resolution for `github.com`:\n- IPv4: 140.82.113.4\n- IPv6: 2606:50c0:8000::1"
  }
}
```

## Command-line usage (without the API)

The orchestrator can also be run directly:

```bash
cd debugger_agent/agent
python orchestrator.py ping google.com
```

or interactively:

```bash
python orchestrator.py
Network diagnostic request: check dns for example.com
```

## Routing logic

`orchestrator.py` routes queries by keyword match:

- **DNS**: `dns`, `resolve`, `hostname`, `domain`
- **Connectivity**: `ping`, `route`, `traceroute`, `mtr`, `latency`, `connectivity`, `reachable`
- **Service**: `port`, `tcp`, `tls`, `ssl`, `https`, `service`, `connection`

If no keywords match, all three specialists run and their results are merged.

## Known limitations / roadmap

- **No `requirements.txt` yet** — dependencies must currently be installed manually (see Installation).
- **OS-specific tool commands** in `server.py` assume Windows; cross-platform support needs branching on `platform.system()`.
- **Agents are rebuilt on every API request** — `create_specialist_agents()` re-creates the MCP client and all three LangChain agents per call. Caching them at FastAPI startup (e.g. via a `lifespan` handler) would reduce latency.
- **No authentication** is enforced on `/diagnostics` — add auth before exposing this publicly, since it lets arbitrary hosts be pinged/scanned from your server.
- **RAG over incident history / runbooks / architecture docs** (referenced in the repo description) is not yet implemented in the current codebase — this is a planned extension beyond the live-diagnostics agents that exist today.

## License

Apache License 2.0 — see [LICENSE](./LICENSE).