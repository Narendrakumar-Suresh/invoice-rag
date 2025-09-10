import os
import logging
import hashlib
import redis
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from google import genai
from qdrant_client import QdrantClient

load_dotenv()

# --- Config ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in environment variables")

CACHE_TTL = int(os.getenv("CACHE_TTL", 86400))  # 24h default

client = genai.Client(api_key=GEMINI_API_KEY)
MODEL = "gemini-2.5-flash"
EMBEDDING_MODEL = "models/embedding-001"

qdrant = QdrantClient(host="qdrant", port=6333)
COLLECTION_NAME = "invoice_rag"

# Redis client
redis_client = redis.Redis(host='redis', port=6379)

# Logging
logging.basicConfig(level=logging.INFO)

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

# --- Embeddings + Qdrant ---
def get_embedding(text: str) -> list:
    try:
        result = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text
        )
        if result.embeddings and len(result.embeddings) > 0:
            embedding = result.embeddings[0]
            if hasattr(embedding, "values"):
                return embedding.values
            elif hasattr(embedding, "value"):
                return embedding.value
        return []
    except Exception as e:
        logging.error(f"Embedding error: {e}")
        raise HTTPException(status_code=500, detail="Error generating embedding")

def search_qdrant_context(query: str, top_k: int = 3) -> tuple[str, float]:
    try:
        query_vector = get_embedding(query)
        if not query_vector:
            return "", 0.0

        results = qdrant.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            limit=top_k
        )

        if not results:
            return "", 0.0

        chunks, total_score = [], 0.0
        for r in results:
            p = r.payload
            score = getattr(r, "score", 0.0)
            total_score += score
            chunk = f"**Source File:** {p.get('source_file', 'N/A')} (Relevance: {score:.2f})\n"
            chunk += f"**Text:** {p.get('text', '')}"
            chunks.append(chunk)

        avg_confidence = total_score / len(results)
        return "\n\n".join(chunks), avg_confidence
    except Exception as e:
        logging.error(f"Qdrant search error: {e}")
        raise HTTPException(status_code=500, detail="Error fetching context from Qdrant")

# --- Streaming with Cache ---
# --- Streaming with Cache ---
def msg_stream(prompt: str):
    # 1. Check cache
    cached = get_cached_response(prompt)
    if cached:
        logging.info("Cache hit ✅")
        # Decode bytes to string
        cached_text = cached.decode("utf-8")
        # Yield once as a plain response (not streaming chunks)
        yield cached_text
        return

    try:
        # 2. Retrieve context
        context_md, confidence = search_qdrant_context(prompt)

        system_prompt = f"""You are an expert AI invoice assistant.

Confidence Score: {confidence:.2f}

Context:
{context_md}

User Query:
{prompt}
"""

        # 3. Stream Gemini output
        full_response = ""
        for chunk in client.models.generate_content_stream(
            model=MODEL,
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
    return {"status": "Invoice Chat Service with RAG + Redis Cache is running"}

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
