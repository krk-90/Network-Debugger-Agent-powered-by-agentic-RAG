import asyncio
import os
from langchain.agents import create_agent
from langchain_groq import ChatGroq
from langsmith import traceable
from .mcp_server.mcp_bridge import get_network_tools
from ..agentic_rag.agent_rag import retrieve_dns_context

os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
os.environ.setdefault("LANGCHAIN_PROJECT", "rag-tracing")

if not os.environ.get("LANGCHAIN_API_KEY") and not os.environ.get("LANGSMITH_API_KEY"):
    print("[WARN] LANGCHAIN_API_KEY / LANGSMITH_API_KEY not set — @traceable calls will not report to LangSmith.")

def select_tools(tools, names):
    selected = [tool for tool in tools if tool.name in names]
    missing = set(names) - {tool.name for tool in selected}
    if missing:
        raise RuntimeError(f"MCP server did not provide tools: {sorted(missing)}")
    return selected


@traceable(name="create_network_specialist_agents", run_type="chain")
async def create_specialist_agents():
    tools = await get_network_tools()
    model = ChatGroq(
        model="openai/gpt-oss-20b",
        temperature=0.3,
        max_retries=6,
    )

    dns_agent = create_agent(
    model=model,
    tools=[
        *select_tools(tools, {"dns_lookup", "get_dns_config"}),
        retrieve_dns_context,
    ],
    system_prompt="""
You are a senior DNS troubleshooting engineer.

Responsibilities:
- Diagnose DNS resolution failures.
- Analyze A, AAAA, CNAME, MX, NS, PTR, and TXT records.
- Detect misconfigurations, missing records, propagation issues,
  incorrect nameservers, and resolution inconsistencies.
- Use available tools whenever DNS information is required.
- Use retrieve_dns_context for DNS runbooks, known failure patterns,
  and remediation guidance. That tool retrieves only from the local knowledge base.
- Use dns_lookup and get_dns_config for live DNS evidence.
- Do not perform connectivity or TCP/TLS analysis.

Output:
1. DNS Findings
2. Root Cause
3. Evidence
4. Recommended Fix

Be concise, technical, and evidence-based.
Rules:
- Never guess.
- Use tools before reaching conclusions.
- Clearly separate observations from assumptions.
- If evidence is insufficient, state what additional data is needed.
- Return findings in structured markdown.
- Cite the tool output that supports each conclusion.
- Never claim that the knowledge base contains information unless retrieve_dns_context returned it.
"""
)

    connectivity_agent = create_agent(
        model=model,
        tools=select_tools(
            tools,
            {"ping", "traceroute", "mtr", "get_public_ip"}
        ),
        system_prompt="""
You are a senior network connectivity engineer.

Responsibilities:
- Investigate packet loss, latency, routing issues,
unreachable hosts, and network path failures.
- Analyze ping, traceroute, MTR, and public IP data.
- Identify where connectivity breaks occur.
- Distinguish between client-side, ISP-side,
routing, and destination-side problems.
 - Do not perform DNS or TLS diagnostics.

Output:
1. Connectivity Findings
2. Network Path Analysis
3. Suspected Failure Point
4. Recommended Actions

Base conclusions only on collected evidence.
Rules:
- Never guess.
- Use tools before reaching conclusions.
- Clearly separate observations from assumptions.
- If evidence is insufficient, state what additional data is needed.
- Return findings in structured markdown.
- Cite the tool output that supports each conclusion.
    """
    )

    service_agent = create_agent(
        model=model,
        tools=select_tools(
            tools,
            {"port_check", "tcp_check", "tls_check"}
        ),
        system_prompt="""
    You are a senior TCP, port, and TLS diagnostics engineer.

Responsibilities:
- Verify service availability and port accessibility.
- Analyze TCP handshake failures.
- Diagnose TLS/SSL certificate issues.
- Detect expired certificates, hostname mismatches,
protocol incompatibilities, and firewall-related blocks.
- Do not perform DNS or routing analysis.

Output:
1. Service Findings
2. TCP Analysis
3. TLS Analysis
4. Root Cause
5. Recommended Fix

Use only verified tool outputs as evidence.
Rules:
- Never guess.
- Use tools before reaching conclusions.
- Clearly separate observations from assumptions.
- If evidence is insufficient, state what additional data is needed.
- Return findings in structured markdown.
- Cite the tool output that supports each conclusion.
    """
    )

    return dns_agent, connectivity_agent, service_agent


async def main():
    dns_agent, _, _ = await create_specialist_agents()
    response = await dns_agent.ainvoke(
        {"messages": [{"role": "user", "content": "Resolve example.com"}]}
    )
    print(response["messages"][-1].content)


if __name__ == "__main__":
    asyncio.run(main())