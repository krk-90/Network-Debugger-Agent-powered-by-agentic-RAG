import asyncio

from langchain.agents import create_agent
from langchain_groq import ChatGroq
from .mcp_server.mcp_bridge import get_network_tools
def select_tools(tools, names):
    selected = [tool for tool in tools if tool.name in names]
    missing = set(names) - {tool.name for tool in selected}
    if missing:
        raise RuntimeError(f"MCP server did not provide tools: {sorted(missing)}")
    return selected


async def create_specialist_agents():
    tools = await get_network_tools()
    model = ChatGroq(
        model="openai/gpt-oss-20b",
        temperature=0.3,
        max_retries=6,
    )

    dns_agent = create_agent(
        model=model,
        tools=select_tools(tools, {"dns_lookup", "get_dns_config"}),
        system_prompt="You are a DNS specialist. Only handle DNS-related tasks.",
    )

    connectivity_agent = create_agent(
        model=model,
        tools=select_tools(tools, {"ping", "traceroute", "mtr", "get_public_ip"}),
        system_prompt="You are a network connectivity specialist.",
    )

    service_agent = create_agent(
        model=model,
        tools=select_tools(tools, {"port_check", "tcp_check", "tls_check"}),
        system_prompt="You are a TCP and TLS specialist.",
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