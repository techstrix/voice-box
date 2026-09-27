import os

# Matched to your installed model
OLLAMA_MODEL = "llama3.2:1b"
OLLAMA_CLIENT_HOST = os.getenv("OLLAMA_CLIENT_HOST", "http://127.0.0.1:11434")

SYSTEM_PROMPT = """You are a helpful, friendly phone customer service agent for {company_name}.
Answer the customer's question using ONLY the context provided below.
Keep answers short (2-3 sentences) and conversational, since this will be read aloud over a phone call.
If the context doesn't contain the answer, politely say you don't have that information
and offer to have a human follow up — do not make anything up.

Context:
{context}
"""

def generate_answer(company_name: str, context: str, question: str) -> str:
    import ollama

    ollama_client = ollama.Client(host=OLLAMA_CLIENT_HOST)
    response = ollama_client.chat(
        model=OLLAMA_MODEL,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT.format(
                    company_name=company_name, context=context
                ),
            },
            {"role": "user", "content": question},
        ],
    )
    return response.message.content