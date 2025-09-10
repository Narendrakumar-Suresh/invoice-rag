import os
import re
import uuid
import docx
import pytesseract
from PIL import Image
from dotenv import load_dotenv
from qdrant_client import QdrantClient, models
from typing import List
import hashlib

# New imports for PDF OCR and embeddings
from pdf2image import convert_from_path
from sentence_transformers import SentenceTransformer

load_dotenv()
Q_URL=os.getenv("Q_URL")
Q_KEY=os.getenv("Q_KEY")
# --- Configuration & Client Initialization ---
DATA_FOLDER = "data"
COLLECTION_NAME = "invoice_rag"
os.makedirs(DATA_FOLDER, exist_ok=True)

DIMENSIONS = 384  # Matches the embedding model output

# Initialize Hugging Face embedder
embed_model = SentenceTransformer("all-MiniLM-L6-v2")

try:
    qdrant_client = QdrantClient(url=Q_URL,api_key=Q_KEY)
    print("Successfully connected to Qdrant.")
except Exception as e:
    print(f"Failed to connect to Qdrant: {e}")
    exit()


# --- Core Functions ---

def embeder(text_chunk: str):
    """Generates embeddings using Hugging Face SentenceTransformer."""
    try:
        vector = embed_model.encode(text_chunk)
        return vector.tolist()  # Convert numpy array to list
    except Exception as e:
        print(f"Error during embedding: {e}")
        return []


def process_file(file_path: str) -> str:
    """Extracts text from PDF, DOCX, or image files. Uses OCR fallback for PDFs."""
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
    """Splits text into chunks based on double newlines."""
    return [chunk.strip() for chunk in re.split(r"\n\n+", text) if chunk.strip()]


def compute_file_hash(file_path: str) -> str:
    """Compute SHA256 hash of file contents."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def file_already_ingested(collection_name: str, file_hash: str) -> bool:
    """Check if a file with the same hash already exists in Qdrant."""
    try:
        results = qdrant_client.scroll(
            collection_name=collection_name,
            scroll_filter=models.Filter(
                must=[models.FieldCondition(key="file_hash", match=models.MatchValue(value=file_hash))]
            ),
            limit=1
        )
        return len(results[0]) > 0
    except Exception as e:
        print(f"Error checking for duplicate file: {e}")
        return False


def ensure_collection_exists(collection_name: str):
    """Creates the collection if it doesn't exist."""
    try:
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
    """
    Orchestrates file processing, embedding, and upserting to Qdrant with deduplication.
    """
    try:
        print(f"Starting ingestion for: {file_path}")
        ensure_collection_exists(collection_name)

        file_hash = compute_file_hash(file_path)
        if file_already_ingested(collection_name, file_hash):
            print(f"Duplicate detected: {file_path} already ingested. Skipping.")
            return []

        document_text = process_file(file_path)
        if not document_text:
            print(f"No text extracted from {file_path}. Skipping.")
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
                        payload={
                            "text": chunk,
                            "source_file": os.path.basename(file_path),
                            "file_hash": file_hash
                        }
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
        cleanup_file(file_path)
