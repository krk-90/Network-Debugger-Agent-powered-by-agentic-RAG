from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langsmith import traceable
from pypdf import PdfReader
from supabase import create_client

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")
KNOWLEDGE_BASE_PATH = Path(
    os.getenv("KNOWLEDGE_BASE_DIR", PROJECT_ROOT / "knowledge_base.pdf")
).resolve()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
CHUNKS_TABLE = os.getenv("SUPABASE_VECTOR_TABLE", "document_chunks")
DOCUMENTS_TABLE = "documents"


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@traceable(name="load_pdfs", run_type="tool")
def _load_pdfs() -> list[Document]:
    if KNOWLEDGE_BASE_PATH.is_file():
        pdf_paths = [KNOWLEDGE_BASE_PATH]
    else:
        pdf_paths = sorted(KNOWLEDGE_BASE_PATH.rglob("*.pdf"))
    if not pdf_paths:
        raise FileNotFoundError(
            f"No PDF files found under {KNOWLEDGE_BASE_PATH}. "
            "Add PDFs there before running ingestion."
        )

    docs: list[Document] = []
    failed: list[str] = []
    for path in pdf_paths:
        try:
            reader = PdfReader(str(path))
            docs.extend(
                Document(
                    page_content=page.extract_text() or "",
                    metadata={"source": str(path), "page": page_number},
                )
                for page_number, page in enumerate(reader.pages)
            )
        except Exception:
            failed.append(path.name)

    if failed:
        print(f"Warning: failed to load PDF files: {', '.join(failed)}", file=sys.stderr)
    if not docs:
        raise RuntimeError("All knowledge-base PDFs failed to load.")
    return docs


def _get_or_create_document(supabase, source_name: str) -> str:
    result = (
        supabase.table(DOCUMENTS_TABLE)
        .upsert(
            {"title": source_name, "content": "", "user_id": None},
            on_conflict="title",
            ignore_duplicates=True,
        )
        .execute()
    )
    if result.data:
        return result.data[0]["id"]
    existing = (
        supabase.table(DOCUMENTS_TABLE)
        .select("id")
        .eq("title", source_name)
        .limit(1)
        .execute()
    )
    return existing.data[0]["id"]


def _get_existing_hashes(supabase) -> set[str]:
    existing: set[str] = set()
    page_size = 1000
    offset = 0
    while True:
        resp = (
            supabase.table(CHUNKS_TABLE)
            .select("content_hash")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            break
        existing.update(row["content_hash"] for row in rows if row.get("content_hash"))
        if len(rows) < page_size:
            break
        offset += page_size
    return existing


@traceable(name="embed_chunks", run_type="embedding")
def _embed_chunks(embeddings: GoogleGenerativeAIEmbeddings, texts: list[str]) -> list[list[float]]:
    return embeddings.embed_documents(texts)


@traceable(name="ingest_knowledge_base", run_type="chain")
def ingest() -> int:
    missing = [
        name
        for name, value in (("SUPABASE_URL", SUPABASE_URL), ("SUPABASE_KEY", SUPABASE_KEY))
        if not value
    ]
    if missing:
        raise RuntimeError(
            f"Missing {', '.join(missing)}. Copy .env.example to .env and set "
            "your Supabase project URL and key before running ingestion."
        )

    pages = _load_pdfs()

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = splitter.split_documents(pages)

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    existing_hashes = _get_existing_hashes(supabase)

    document_id_cache: dict[str, str] = {}
    to_embed: list[Document] = []
    for chunk in chunks:
        source = Path(chunk.metadata.get("source", "unknown")).name
        content_hash = _content_hash(chunk.page_content)
        if content_hash in existing_hashes:
            continue

        if source not in document_id_cache:
            document_id_cache[source] = _get_or_create_document(supabase, source)

        chunk.metadata["content_hash"] = content_hash
        chunk.metadata["document_id"] = document_id_cache[source]
        chunk.metadata["source"] = source
        to_embed.append(chunk)

    if not to_embed:
        return 0

    embeddings = GoogleGenerativeAIEmbeddings(
        model=os.getenv("GOOGLE_EMBEDDING_MODEL", "models/gemini-embedding-001"),
        output_dimensionality=int(os.getenv("GOOGLE_EMBEDDING_DIMENSIONS", "768")),
    )
    vectors = _embed_chunks(embeddings, [c.page_content for c in to_embed])

    rows = [
        {
            "document_id": chunk.metadata["document_id"],
            "content": chunk.page_content,
            "metadata": chunk.metadata,
            "embedding": vector,
            "content_hash": chunk.metadata["content_hash"],
        }
        for chunk, vector in zip(to_embed, vectors)
    ]

    batch_size = 100
    for i in range(0, len(rows), batch_size):
        supabase.table(CHUNKS_TABLE).upsert(
            rows[i : i + batch_size],
            on_conflict="content_hash",
            ignore_duplicates=True,
        ).execute()

    return len(rows)


def main() -> None:
    try:
        count = ingest()
    except Exception as exc:
        print(f"Ingestion failed: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"Done. {count} chunk(s) embedded this run.")


if __name__ == "__main__":
    main()