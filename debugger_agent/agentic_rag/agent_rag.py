from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_community.vectorstores import SupabaseVectorStore
from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain.tools import tool
from langsmith import traceable
from supabase import create_client


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")
os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
os.environ.setdefault("LANGCHAIN_PROJECT", "rag-tracing")

if not os.environ.get("LANGCHAIN_API_KEY") and not os.environ.get("LANGSMITH_API_KEY"):
    print("[WARN] LANGCHAIN_API_KEY / LANGSMITH_API_KEY not set — @traceable calls will not report to LangSmith.")


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_TABLE = os.getenv("SUPABASE_VECTOR_TABLE", "document_chunks")
SUPABASE_QUERY = os.getenv("SUPABASE_VECTOR_QUERY", "match_document_chunks")
RETRIEVAL_K = int(os.getenv("RETRIEVAL_K", "5"))

_retrieval_chain: Any | None = None
_lock = threading.Lock()


def _format_documents(documents: list[Document]) -> str:
    if not documents:
        return "No relevant knowledge-base documents were found."

    formatted = []
    for document in documents:
        source = document.metadata.get("source", "unknown")
        try:
            source_name = Path(source).name
        except (TypeError, ValueError):
            source_name = str(source)
        formatted.append(f"Source: {source_name}\n{document.page_content}")

    return "\n\n".join(formatted)


def _build_retrieval_chain():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY are required for RAG retrieval")

    embeddings = GoogleGenerativeAIEmbeddings(
        model=os.getenv("GOOGLE_EMBEDDING_MODEL", "models/gemini-embedding-001"),
        output_dimensionality=int(os.getenv("GOOGLE_EMBEDDING_DIMENSIONS", "768")),
    )
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    vectorstore = SupabaseVectorStore(
        client=supabase,
        embedding=embeddings,
        table_name=SUPABASE_TABLE,
        query_name=SUPABASE_QUERY,
    )
    retriever = vectorstore.as_retriever(
        search_type="similarity",
        search_kwargs={"k": RETRIEVAL_K},
    )
    return retriever | RunnableLambda(_format_documents)


def get_retrieval_chain():
    global _retrieval_chain
    if _retrieval_chain is None:
        with _lock:
            if _retrieval_chain is None:
                _retrieval_chain = _build_retrieval_chain()
    return _retrieval_chain


def refresh_retrieval_chain() -> None:
    global _retrieval_chain
    with _lock:
        _retrieval_chain = None


@tool(description="Retrieve DNS troubleshooting guidance from the configured knowledge base.")
@traceable(name="retrieve_dns_context", run_type="tool")
def retrieve_dns_context(query: str) -> str:
    try:
        return get_retrieval_chain().invoke(query)
    except Exception as exc:
        return f"Knowledge-base retrieval is currently unavailable ({type(exc).__name__})."