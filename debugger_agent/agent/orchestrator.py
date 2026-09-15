import asyncio
import operator
import sys
import traceback
from typing import Annotated, TypedDict
import os

from langgraph.graph import END, START, StateGraph
from langsmith import traceable

from .sub_agents import create_specialist_agents

os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
os.environ.setdefault("LANGCHAIN_PROJECT", "rag-tracing")

if not os.environ.get("LANGCHAIN_API_KEY") and not os.environ.get("LANGSMITH_API_KEY"):
    print("[WARN] LANGCHAIN_API_KEY / LANGSMITH_API_KEY not set — @traceable calls will not report to LangSmith.")

# Keep individual specialist calls below Render's request timeout. A failed or
# slow specialist must not cancel the other branches in LangGraph's fan-out.
SPECIALIST_TIMEOUT_SECONDS = float(os.getenv("SPECIALIST_TIMEOUT_SECONDS", "20"))
GRAPH_BUILD_TIMEOUT_SECONDS = float(os.getenv("GRAPH_BUILD_TIMEOUT_SECONDS", "12"))


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


def _format_exception(error: BaseException) -> str:
    """Expose nested ExceptionGroup details instead of only its top-level name."""
    if isinstance(error, BaseExceptionGroup):
        parts = []
        for nested in error.exceptions:
            parts.append(_format_exception(nested))
        return " | ".join(parts)
    return f"{type(error).__name__}: {error}" or type(error).__name__


@traceable(name="build_network_diagnostic_graph", run_type="chain")
async def build_graph():
    # MCP discovery is an external network operation. Bound it so graph
    # initialization cannot consume the entire HTTP request budget.
    dns_agent, connectivity_agent, service_agent = await asyncio.wait_for(
        create_specialist_agents(), timeout=GRAPH_BUILD_TIMEOUT_SECONDS
    )
    agents = {"dns": dns_agent, "connectivity": connectivity_agent, "service": service_agent}

    async def router(state: DiagnosticState) -> dict:
        return {"specialists": select_specialists(state["query"])}

    def route_edges(state: DiagnosticState) -> list[str]:
        return state["specialists"]

    def make_specialist_node(name: str):
        async def node(state: DiagnosticState) -> dict:
            agent = agents[name]
            try:
                response = await asyncio.wait_for(
                    agent.ainvoke(
                        {"messages": [{"role": "user", "content": state["query"]}]}
                    ),
                    timeout=SPECIALIST_TIMEOUT_SECONDS,
                )
                messages = response.get("messages", [])
                if not messages:
                    raise RuntimeError("Agent returned no messages")
                content = messages[-1].content
                if not content:
                    raise RuntimeError("Agent returned an empty response")
                return {"results": {name: content}}
            except asyncio.TimeoutError:
                message = (
                    f"{name} specialist timed out after "
                    f"{SPECIALIST_TIMEOUT_SECONDS:g}s. Other specialists were allowed to continue."
                )
                print(f"[SPECIALIST TIMEOUT] {message}")
                return {"results": {name: message}}
            except BaseException as error:
                # LangGraph fans these nodes out in an asyncio TaskGroup. Catch
                # branch failures here so one bad MCP/LLM/tool call does not
                # cancel every other specialist and surface as ExceptionGroup.
                details = _format_exception(error)
                print(f"[SPECIALIST ERROR] {name}: {details}")
                traceback.print_exception(error)
                return {
                    "results": {
                        name: f"{name} specialist failed: {details}. Other specialists were allowed to continue."
                    }
                }

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


@traceable(name="network_diagnostic", run_type="chain")
async def orchestrate(query: str) -> dict[str, str]:
    graph = await get_graph()
    final_state = await graph.ainvoke(
        {"query": query, "specialists": [], "results": {}}
    )
    results = final_state["results"]
    if not results:
        raise RuntimeError("No specialist returned a diagnostic result")
    return results


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
