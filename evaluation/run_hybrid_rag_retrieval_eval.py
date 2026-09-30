"""Evaluate the Network Debugger's hybrid (vector + keyword) retrieval.

Mirrors run_rag_retrieval_eval.py exactly but uses the hybrid retriever so
results from both scripts are directly comparable.

Set the same SUPABASE_* and GOOGLE_* environment variables used by the app.
Results are written to network_hybrid_rag_results.json.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from evaluation.metrics import summarize

BASE = Path(__file__).resolve().parent
DATASET = BASE / "network_rag_eval.json"
RESULTS = BASE / "network_hybrid_rag_results.json"
BASELINE_RESULTS = BASE / "network_rag_results.json"


def build_hybrid_retriever():
    from langchain_community.vectorstores import SupabaseVectorStore
    from langchain_google_genai import GoogleGenerativeAIEmbeddings
    from langchain_core.documents import Document
    from langchain_core.runnables import RunnableLambda
    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    key = os.environ.get("SUPABASE_KEY") or os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    k = int(json.loads(DATASET.read_text())["k"])
    fetch_k = max(k * 3, 15)

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
    base_retriever = store.as_retriever(search_kwargs={"k": fetch_k})

    def _keyword_score(query: str, content: str) -> int:
        tokens = [t.lower() for t in query.split() if len(t) > 2]
        return sum(1 for t in tokens if t in content.lower())

    def _hybrid_rerank(query: str, docs: list[Document]) -> list[Document]:
        scored = []
        for rank, doc in enumerate(docs, 1):
            score = 1.0 / rank + 0.1 * _keyword_score(query, doc.page_content)
            scored.append((score, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scored[:k]]

    def _invoke(query: str) -> list[Document]:
        return _hybrid_rerank(query, base_retriever.invoke(query))

    return RunnableLambda(_invoke)


def source_key(doc) -> str:
    metadata = getattr(doc, "metadata", {}) or {}
    return str(metadata.get("source") or metadata.get("file_path") or metadata.get("path") or "").lower()


def main() -> None:
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    retriever = build_hybrid_retriever()
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

    print("=== Hybrid RAG Retrieval Results ===")
    print(json.dumps(summary, indent=2))

    # Side-by-side comparison if baseline exists
    if BASELINE_RESULTS.exists():
        baseline = json.loads(BASELINE_RESULTS.read_text(encoding="utf-8"))
        b_summary = baseline.get("summary", {})
        print("\n=== Comparison: Hybrid vs Similarity-only ===")
        print(f"  {'Metric':<22} {'Similarity':>12} {'Hybrid':>10} {'Delta':>8}")
        print(f"  {'-'*54}")
        for key, hybrid_val in summary.items():
            base_val = b_summary.get(key, 0.0)
            delta = hybrid_val - base_val
            sign = "+" if delta >= 0 else ""
            print(f"  {key:<22} {base_val:>12.4f} {hybrid_val:>10.4f} {sign}{delta:>7.4f}")

    print(f"\nResults saved to: {RESULTS}")


if __name__ == "__main__":
    main()
