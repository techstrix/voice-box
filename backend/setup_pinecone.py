from dotenv import load_dotenv
load_dotenv()

from pinecone import Pinecone, ServerlessSpec
import os

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))

pc.create_index(
    name="voice-assistant-kb",
    dimension=384,              
    metric="cosine",
    spec=ServerlessSpec(cloud="aws", region="us-east-1"),
)