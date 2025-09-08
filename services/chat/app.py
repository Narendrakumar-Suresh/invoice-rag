# import os
# import asyncio
# from dotenv import load_dotenv
# from fastapi import FastAPI
# from fastapi.responses import StreamingResponse
# from pydantic import BaseModel
# from google import genai
# from google.genai import types
# from ..ingestion.data import get_or_create_collection
#
#
#
# # Load environment variables (for the API key)
# load_dotenv()
#
# # Configure the Gemini API
# client=genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
#
#
# # --- Pydantic Model for Request Body ---
# class PromptRequest(BaseModel):
#     """Defines the structure for the incoming request."""
#     prompt: str
#
#
# # --- FastAPI App Instance ---
# app = FastAPI(title="Gemini Streaming API")
#
#
# # --- Async Generator for Streaming Gemini's Response ---
# async def gemini_stream_generator(prompt: str):
#     """
#     Yields chunks of text from Gemini's streaming response.
#     Formats each chunk as a Server-Sent Event (SSE).
#     """
#     # model = genai.GenerativeModel('gemini-1.5-flash')
#     #
#     # # Start the asynchronous streaming call
#     # async_response = await model.generate_content_async(prompt, stream=True)
#     async_response = await client.models.generate_content(
#         model="gemini-2.5-flash",
#         contents=prompt,
#         config=types.GenerateContentConfig(
#             thinking_config=types.ThinkingConfig(thinking_budget=0)  # Disables thinking
#         ),
#     )
#
#     # Iterate through chunks and yield them
#     async for chunk in async_response:
#         if chunk.text:
#             # SSE format: "data: {content}\n\n"
#             yield f"data: {chunk.text}\n\n"
#             await asyncio.sleep(0.01)  # Small delay for smoother streaming
#
#
# # --- FastAPI Endpoint ---
# @app.post("/chat/stream")
# async def stream_chat(request: PromptRequest):
#     db = load_chroma_collection("chroma_db", "rag_experiment")
#
#     # Retrieval step
#     results = db.query(query_texts=[request.prompt], n_results=3)
#     if not results or not results["documents"][0]:
#         async def no_answer():
#             yield "data: I don’t know. Escalating to agent.\n\n"
#         return StreamingResponse(no_answer(), media_type="text/event-stream")
#
#     context = "\n".join(results["documents"][0])
#     full_prompt = f"Context from invoices:\n{context}\n\nUser query:\n{request.prompt}"
#
#     return StreamingResponse(
#         gemini_stream_generator(full_prompt),
#         media_type="text/event-stream"
#     )
