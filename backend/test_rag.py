from rag import upsert_company_doc, retrieve_context
import time

import pytest

from rag import _get_index

try:
    _get_index()
except Exception:
    pytest.skip("Pinecone not configured (PINECONE_API_KEY)", allow_module_level=True)

# 1. Define dummy data for a test company
TEST_COMPANY_ID = "acme-corp-123"
DUMMY_DOC = """
Welcome to Acme Corp. Our business hours are Monday through Friday, 9 AM to 5 PM. 
We are closed on weekends. Our return policy allows returns within 30 days of purchase 
with a valid receipt. To check your order status, please have your 8-digit order number ready.
"""

print(f"Upserting document for namespace: {TEST_COMPANY_ID}...")
# 2. Upsert the document
upsert_company_doc(
    company_id=TEST_COMPANY_ID, 
    doc_text=DUMMY_DOC, 
    source_name="acme_faq.txt"
)

print("Waiting a few seconds for Pinecone to index the vectors...")
time.sleep(3) # Give Pinecone a moment to make the vectors searchable

# 3. Test the retrieval with a relevant question
TEST_QUESTION = "What is your return policy?"
print(f"\nQuerying: '{TEST_QUESTION}'")

# 4. Fetch the context using the company namespace
retrieved_text = retrieve_context(company_id=TEST_COMPANY_ID, question=TEST_QUESTION)

print("\n--- Retrieved Context ---")
print(retrieved_text)
print("-------------------------")

# Quick sanity check
if "30 days" in retrieved_text:
    print("\n✅ Success! Pinecone retrieved the correct chunk based on the question.")
else:
    raise AssertionError("The expected answer wasn't in the retrieved text.")