import os
import logging
import hashlib
import redis
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from google import genai

load_dotenv()

# --- Config ---
CACHE_TTL = int(os.getenv("CACHE_TTL", 86400))  # 24h default
REDIS_URL = os.getenv("REDIS_URL")
Q_URL = os.getenv("Q_URL")
Q_KEY = os.getenv("Q_KEY")
COLLECTION_NAME = "invoice_rag"
DIMENSIONS = 384  # MiniLM output dim
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("❌ GEMINI_API_KEY not found in environment variables")

# Qdrant client
qdrant = QdrantClient(url=Q_URL, api_key=Q_KEY)

# Redis client
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

# Logging
logging.basicConfig(level=logging.INFO)

# HuggingFace embedder
embed_model = SentenceTransformer("all-MiniLM-L6-v2")

# Gemini client
client = genai.Client(api_key=GEMINI_API_KEY)

# FastAPI app
app = FastAPI()

class ChatRequest(BaseModel):
    message: str

# --- Helpers ---
def normalize_query(query: str) -> str:
    return hashlib.sha256(query.strip().lower().encode()).hexdigest()

def get_cached_response(query: str):
    return redis_client.get(normalize_query(query))

def set_cached_response(query: str, response: str):
    redis_client.setex(normalize_query(query), CACHE_TTL, response)

# --- Embeddings (HuggingFace) + Qdrant ---
def get_embedding(text: str) -> list:
    try:
        vector = embed_model.encode(text)
        return vector.tolist()
    except Exception as e:
        logging.error(f"Embedding error: {e}")
        raise HTTPException(status_code=500, detail="Error generating embedding")

def search_qdrant_context(query: str, top_k: int = 3) -> str:
    try:
        query_vector = get_embedding(query)
        if not query_vector:
            return ""

        results = qdrant.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            limit=top_k
        )

        if not results:
            return ""

        chunks = []
        for r in results:
            p = r.payload
            chunk = f"Source File: {p.get('source_file', 'N/A')}\n"
            chunk += f"Text: {p.get('text', '')}"
            chunks.append(chunk)

        return "\n\n".join(chunks)
    except Exception as e:
        logging.error(f"Qdrant search error: {e}")
        raise HTTPException(status_code=500, detail="Error fetching context from Qdrant")

# --- Streaming with Cache (Gemini for LLM response) ---
def msg_stream(prompt: str):
    # 1. Check cache
    cached = get_cached_response(prompt)
    if cached:
        logging.info("Cache hit ✅")
        yield cached  # Remove .decode() since decode_responses=True is set
        return

    try:
        # 2. Retrieve context (only one return value)
        context_md = search_qdrant_context(prompt)

        system_prompt = f"""You are an expert AI invoice assistant.

Context:
{context_md}

User Query:
{prompt}
"""

        # 3. Stream Gemini output
        full_response = ""
        for chunk in client.models.generate_content_stream(
            model="gemini-2.5-flash",
            contents=system_prompt
        ):
            if chunk.text:
                full_response += chunk.text
                yield chunk.text

        # 4. Cache the complete response
        if full_response.strip():
            set_cached_response(prompt, full_response)

    except Exception as e:
        logging.error(f"Stream generation error: {e}")
        yield f"Error: {str(e)}\n\n"



# --- Routes ---
@app.get("/")
def root():
    return {"status": "Invoice Chat Service with RAG (HF Embeddings + Qdrant + Redis + Gemini LLM) is running 🚀"}

@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        return StreamingResponse(
            msg_stream(req.message),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
            }
        )
    except Exception as e:
        logging.error(f"Chat endpoint error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
