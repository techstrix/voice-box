import os
from pathlib import Path

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone

load_dotenv(Path(__file__).with_name(".env"))

# Load the local embedding model
embedder = SentenceTransformer("all-MiniLM-L6-v2")

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("voice-assistant-kb")

def embed(text: str) -> list[float]:
    return embedder.encode(text).tolist()

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

def upsert_company_doc(company_id: str, doc_text: str, source_name: str):
    chunks = chunk_text(doc_text)
    vectors = [
        {
            "id": f"{source_name}-{i}",
            "values": embed(chunk),
            "metadata": {"text": chunk, "source": source_name},
        }
        for i, chunk in enumerate(chunks)
    ]
    index.upsert(vectors=vectors, namespace=company_id)

def retrieve_context(company_id: str, question: str, top_k: int = 3) -> str:
    query_vec = embed(question)
    results = index.query(
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