import os
import re
import uuid
import docx
import pytesseract
from PIL import Image
from dotenv import load_dotenv
from google import genai
from qdrant_client import QdrantClient, models
from typing import List

# New import for handling PDF OCR
from pdf2image import convert_from_path

load_dotenv()

# --- Configuration & Client Initialization ---
DIMENSIONS = 768
DATA_FOLDER = "data"
COLLECTION_NAME = "invoice_rag"
os.makedirs(DATA_FOLDER, exist_ok=True)

try:
    # Using the Google.genai Client as you suggested
    gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    #qdrant_client = QdrantClient(url=os.getenv("QDRANT_URL"), api_key=os.getenv("QDRANT_KEY"))
    qdrant_client = QdrantClient(host = "localhost", port = 6333)

    print("Successfully connected to Gemini and Qdrant.")
except Exception as e:
    print(f"Failed to connect to services: {e}")
    exit()


# --- Core Functions ---

def embeder(text_chunk: str):
    """Generates embeddings for a given text chunk using the specified Gemini model."""
    try:
        result = gemini_client.models.embed_content(
            model="models/embedding-001",
            contents=text_chunk,
        )
        # Extract the actual vector values from the ContentEmbedding object
        if result.embeddings and len(result.embeddings) > 0:
            # Get the first embedding's values
            embedding = result.embeddings[0]
            if hasattr(embedding, 'values'):
                return embedding.values
            elif hasattr(embedding, 'value'):
                return embedding.value
        return []
    except Exception as e:
        print(f"Error during embedding: {e}")
        return []


def process_file(file_path: str) -> str:
    """
    Extracts text content from PDF, DOCX, or image files.
    Includes OCR fallback for PDFs.
    """
    _, file_extension = os.path.splitext(file_path)
    text = ""
    try:
        if file_extension.lower() == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(file_path)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"

            if not text.strip():
                print(f"No text found in {file_path}, falling back to OCR.")
                images = convert_from_path(file_path)
                for img in images:
                    text += pytesseract.image_to_string(img) + "\n"

        elif file_extension.lower() == ".docx":
            doc = docx.Document(file_path)
            for para in doc.paragraphs:
                text += para.text + "\n"
        elif file_extension.lower() in [".png", ".jpg", ".jpeg"]:
            img = Image.open(file_path)
            text = pytesseract.image_to_string(img)

    except Exception as e:
        print(f"Error processing file {file_path}: {e}")
    return text


def split_text(text: str) -> list[str]:
    """Splits text into smaller chunks based on double newlines."""
    return [chunk.strip() for chunk in re.split(r"\n\n+", text) if chunk.strip()]


def ensure_collection_exists(collection_name: str):
    """Creates the collection if it doesn't exist."""
    try:
        # Check if collection exists
        collections = qdrant_client.get_collections()
        collection_exists = any(collection.name == collection_name for collection in collections.collections)

        if not collection_exists:
            print(f"Creating collection: {collection_name}")
            qdrant_client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=DIMENSIONS,
                    distance=models.Distance.COSINE
                )
            )
            print(f"Collection '{collection_name}' created successfully.")
        else:
            print(f"Collection '{collection_name}' already exists.")
    except Exception as e:
        print(f"Error ensuring collection exists: {e}")
        raise e

def cleanup_file(file_path: str):
    """Remove file after processing."""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"Cleaned up file: {file_path}")
    except Exception as e:
        print(f"Error cleaning up file {file_path}: {e}")


def ingest_document(file_path: str, collection_name: str) -> List[models.PointStruct]:
    """Orchestrates file processing, embedding, and upserting to Qdrant."""
    try:
        print(f"Starting ingestion for: {file_path}")
        ensure_collection_exists(collection_name)

        document_text = process_file(file_path)
        if not document_text:
            return []

        chunks = split_text(document_text)
        points_to_upsert = []

        for chunk in chunks:
            vector = embeder(chunk)
            if vector and len(vector) == DIMENSIONS:
                points_to_upsert.append(
                    models.PointStruct(
                        id=str(uuid.uuid4()),
                        vector=vector,
                        payload={"text": chunk, "source_file": os.path.basename(file_path)}
                    )
                )

        if points_to_upsert:
            qdrant_client.upsert(
                collection_name=collection_name,
                points=points_to_upsert,
                wait=True
            )
            print(f"Successfully upserted {len(points_to_upsert)} points.")

        return points_to_upsert

    finally:
        # Always cleanup file, even if an error occurs
        cleanup_file(file_path)