from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from langchain_community.document_loaders import DirectoryLoader
from langchain_community.vectorstores import SupabaseVectorStore
from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain.tools import tool
from supabase import create_client


PROJECT_ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_BASE_PATH = Path(
    os.getenv("KNOWLEDGE_BASE_DIR", PROJECT_ROOT / "knowledge_base")
).resolve()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_TABLE = os.getenv("SUPABASE_VECTOR_TABLE", "document_chunks")
SUPABASE_QUERY = os.getenv("SUPABASE_VECTOR_QUERY", "match_document_chunks")

_retrieval_chain: Any | None = None


def _format_documents(documents: list[Document]) -> str:
    if not documents:
        return "No relevant knowledge-base documents were found."

    return "\n\n".join(
        f"Source: {Path(document.metadata.get('source', 'unknown')).name}\n"
        f"{document.page_content}"
        for document in documents
    )


def _build_retrieval_chain():
    if not KNOWLEDGE_BASE_PATH.is_dir():
        raise FileNotFoundError(
            f"Knowledge base directory does not exist: {KNOWLEDGE_BASE_PATH}"
        )

    loader = DirectoryLoader(
        str(KNOWLEDGE_BASE_PATH),
        recursive=True,
        silent_errors=True,
    )
    documents = loader.load()
    if not documents:
        raise FileNotFoundError(
            f"Knowledge base contains no readable documents: {KNOWLEDGE_BASE_PATH}"
        )
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY are required for RAG retrieval")

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = splitter.split_documents(documents)
    embeddings = GoogleGenerativeAIEmbeddings(
        model=os.getenv("GOOGLE_EMBEDDING_MODEL", "models/gemini-embedding-001"),
        output_dimensionality=int(os.getenv("GOOGLE_EMBEDDING_DIMENSIONS", "768")),
    )
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    vectorstore = SupabaseVectorStore.from_documents(
        documents=chunks,
        embedding=embeddings,
        client=supabase,
        table_name=SUPABASE_TABLE,
        query_name=SUPABASE_QUERY,
    )
    retriever = vectorstore.as_retriever(
        search_type="similarity",
        search_kwargs={"k": 5},
    )
    return retriever | RunnableLambda(_format_documents)


def get_retrieval_chain():
    global _retrieval_chain
    if _retrieval_chain is None:
        _retrieval_chain = _build_retrieval_chain()
    return _retrieval_chain


@tool
def retrieve_dns_context(query: str) -> str:
    """Retrieve DNS troubleshooting guidance only from the local knowledge base."""
    return get_retrieval_chain().invoke(query)