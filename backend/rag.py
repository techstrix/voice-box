"""Pinecone RAG helpers, namespaced per company.

Heavy third-party clients (embedding model, Pinecone) are created lazily so
that importing this module -- and the FastAPI app -- never pays model-load
cost or requires credentials until an embedding/index call actually runs.
Public function signatures are unchanged.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _get_embedder():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer("all-MiniLM-L6-v2")


@lru_cache(maxsize=1)
def _get_index():
    import os

    from dotenv import load_dotenv
    from pinecone import Pinecone

    load_dotenv(Path(__file__).with_name(".env"))
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "PINECONE_API_KEY is not set. Copy backend/.env.example to backend/.env."
        )
    pc = Pinecone(api_key=api_key)
    return pc.Index(os.getenv("PINECONE_INDEX_NAME", "voice-assistant-kb"))


def embed(text: str) -> list[float]:
    return _get_embedder().encode(text).tolist()


def chunk_text(text: str, max_chars: int = 500) -> list[str]:
    words = text.split()
    chunks, current = [], []
    length = 0
    for w in words:
        current.append(w)
        length += len(w) + 1
        if length >= max_chars:
            chunks.append(" ".join(current))
            current, length = [], 0
    if current:
        chunks.append(" ".join(current))
    return chunks


def upsert_company_doc(company_id: str, doc_text: str, source_name: str) -> int:
    chunks = chunk_text(doc_text)
    vectors = [
        {
            "id": f"{source_name}-{i}",
            "values": embed(chunk),
            "metadata": {"text": chunk, "source": source_name},
        }
        for i, chunk in enumerate(chunks)
    ]
    _get_index().upsert(vectors=vectors, namespace=company_id)
    return len(vectors)


def retrieve_context(company_id: str, question: str, top_k: int = 3) -> str:
    query_vec = embed(question)
    results = _get_index().query(
        vector=query_vec,
        top_k=top_k,
        namespace=company_id,
        include_metadata=True,
    )
    chunks = [
        match.metadata["text"]
        for match in results.matches
        if match.metadata and "text" in match.metadata
    ]
    return "\n---\n".join(chunks)
