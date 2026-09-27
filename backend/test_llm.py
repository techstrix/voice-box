from rag import retrieve_context
from llm import generate_answer

import os
import urllib.parse

import pytest

from rag import _get_index

try:
    _get_index()
except Exception:
    pytest.skip("Pinecone not configured (PINECONE_API_KEY)", allow_module_level=True)

OLLAMA_HOST = os.getenv("OLLAMA_CLIENT_HOST", "http://127.0.0.1:11434")
_parts = urllib.parse.urlparse(OLLAMA_HOST)
try:
    import socket

    with socket.create_connection((_parts.hostname or "127.0.0.1", _parts.port or 11434), timeout=5):
        pass
except OSError:
    pytest.skip(f"Ollama not reachable at {OLLAMA_HOST}", allow_module_level=True)

TEST_COMPANY_ID = "acme-corp-123"
COMPANY_NAME = "Acme Corp"
TEST_QUESTION = "What hours are you open during the week?"

print(f"1. Querying Pinecone for context: '{TEST_QUESTION}'...")
context = retrieve_context(company_id=TEST_COMPANY_ID, question=TEST_QUESTION)

print("\n--- Retrieved Context ---")
print(context)
print("-------------------------\n")

print("2. Generating answer with Ollama (llama3.2:1b)...")
answer = generate_answer(
    company_name=COMPANY_NAME, 
    context=context, 
    question=TEST_QUESTION
)

print("\n--- Ollama Spoken Response ---")
print(answer)
print("------------------------------")