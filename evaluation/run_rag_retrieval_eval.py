"""Evaluate the Network Debugger's real Supabase vector retrieval.

Set the same SUPABASE_* and GOOGLE_* environment variables used by the app.
Results are written locally and are safe to commit only if they contain no
secrets.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from evaluation.metrics import summarize

BASE = Path(__file__).resolve().parent
DATASET = BASE / "network_rag_eval.json"
RESULTS = BASE / "network_rag_results.json"


def build_retriever():
    from langchain_community.vectorstores import SupabaseVectorStore
    from langchain_google_genai import GoogleGenerativeAIEmbeddings
    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    key = os.environ.get("SUPABASE_KEY") or os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    embeddings = GoogleGenerativeAIEmbeddings(
        model=os.getenv("GOOGLE_EMBEDDING_MODEL", "models/gemini-embedding-001"),
        output_dimensionality=int(os.getenv("GOOGLE_EMBEDDING_DIMENSIONS", "768")),
    )
    store = SupabaseVectorStore(
        client=create_client(url, key),
        embedding=embeddings,
        table_name=os.getenv("SUPABASE_VECTOR_TABLE", "document_chunks"),
        query_name=os.getenv("SUPABASE_VECTOR_QUERY", "match_document_chunks"),
    )
    return store.as_retriever(search_kwargs={"k": int(json.loads(DATASET.read_text())["k"])})


def source_key(doc) -> str:
    metadata = getattr(doc, "metadata", {}) or {}
    return str(metadata.get("source") or metadata.get("file_path") or metadata.get("path") or "").lower()


def main() -> None:
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    retriever = build_retriever()
    k = int(data["k"])
    rows = []

    for case in data["cases"]:
        started = time.perf_counter()
        docs = retriever.invoke(case["question"])
        latency_ms = (time.perf_counter() - started) * 1000
        sources = [source_key(doc) for doc in docs]
        relevant = set(case["relevant"])
        labels = [
            expected
            for source in sources
            for expected in relevant
            if expected.lower() in source
        ]
        rows.append({
            "id": case["id"],
            "question": case["question"],
            "retrieved": labels,
            "retrieved_sources": sources,
            "relevant": sorted(relevant),
            "latency_ms": round(latency_ms, 2),
        })

    summary = summarize(rows, k=k)
    output = {"summary": summary, "cases": rows}
    RESULTS.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Results: {RESULTS}")


if __name__ == "__main__":
    main()
