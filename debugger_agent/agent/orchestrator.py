import asyncio
import operator
import sys
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from .sub_agents import create_specialist_agents


class DiagnosticState(TypedDict):
	query: str
	specialists: list[str]
	results: Annotated[dict[str, str], operator.or_]


def select_specialists(query: str) -> list[str]:
	query_lower = query.lower()
	selected = []

	if any(term in query_lower for term in ("dns", "resolve", "hostname", "domain")):
		selected.append("dns")
	if any(
		term in query_lower
		for term in ("ping", "route", "traceroute", "mtr", "latency", "connectivity", "reachable")
	):
		selected.append("connectivity")
	if any(
		term in query_lower
		for term in ("port", "tcp", "tls", "ssl", "https", "service", "connection")
	):
		selected.append("service")

	return selected or ["dns", "connectivity", "service"]


async def build_graph():
	dns_agent, connectivity_agent, service_agent = await create_specialist_agents()
	agents = {"dns": dns_agent, "connectivity": connectivity_agent, "service": service_agent}

	async def router(state: DiagnosticState) -> dict:
		return {"specialists": select_specialists(state["query"])}

	def route_edges(state: DiagnosticState) -> list[str]:
		return state["specialists"]

	def make_specialist_node(name: str):
		async def node(state: DiagnosticState) -> dict:
			agent = agents[name]
			response = await agent.ainvoke(
				{"messages": [{"role": "user", "content": state["query"]}]}
			)
			return {"results": {name: response["messages"][-1].content}}
		return node

	graph = StateGraph(DiagnosticState)
	graph.add_node("router", router)
	for name in agents:
		graph.add_node(name, make_specialist_node(name))

	graph.add_edge(START, "router")
	graph.add_conditional_edges("router", route_edges, {name: name for name in agents})
	for name in agents:
		graph.add_edge(name, END)

	return graph.compile()


_compiled_graph = None
_graph_lock = asyncio.Lock()


async def get_graph():
	global _compiled_graph
	if _compiled_graph is None:
		async with _graph_lock:
			if _compiled_graph is None:
				_compiled_graph = await build_graph()
	return _compiled_graph


def is_ready() -> bool:
	return _compiled_graph is not None


async def orchestrate(query: str) -> dict[str, str]:
	graph = await get_graph()
	final_state = await graph.ainvoke({"query": query, "specialists": [], "results": {}})
	return final_state["results"]


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