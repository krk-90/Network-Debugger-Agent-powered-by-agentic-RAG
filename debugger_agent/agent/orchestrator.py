import asyncio
import sys

from .sub_agents import create_specialist_agents

def select_agents(query, agents):
	query_lower = query.lower()
	selected = []

	if any(term in query_lower for term in ("dns", "resolve", "hostname", "domain")):
		selected.append(("dns", agents[0]))
	if any(
		term in query_lower
		for term in ("ping", "route", "traceroute", "mtr", "latency", "connectivity", "reachable")
	):
		selected.append(("connectivity", agents[1]))
	if any(
		term in query_lower
		for term in ("port", "tcp", "tls", "ssl", "https", "service", "connection")
	):
		selected.append(("service", agents[2]))

	return selected or [
		("dns", agents[0]),
		("connectivity", agents[1]),
		("service", agents[2]),
	]


async def run_specialist(name, agent, query):
	response = await agent.ainvoke(
		{"messages": [{"role": "user", "content": query}]}
	)
	return name, response["messages"][-1].content


async def orchestrate(query):
	agents = await create_specialist_agents()
	selected = select_agents(query, agents)
	results = await asyncio.gather(
		*(run_specialist(name, agent, query) for name, agent in selected)
	)
	return {name: result for name, result in results}


async def main():
	query = " ".join(sys.argv[1:]).strip()
	if not query:
		query = input("Network diagnostic request: ").strip()
	if not query:
		raise SystemExit("A diagnostic request is required.")

	results = await orchestrate(query)
	for name, result in results.items():
		print(f"\n--- {name} specialist ---\n{result}")


if __name__ == "__main__":
	asyncio.run(main())
