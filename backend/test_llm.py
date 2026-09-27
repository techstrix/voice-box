from rag import retrieve_context
from llm import generate_answer

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