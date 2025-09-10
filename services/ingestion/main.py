import os
from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

# Imports from the data.py file
from data import ingest_document, DATA_FOLDER, COLLECTION_NAME

# --- FastAPI App Initialization ---
app = FastAPI(
    title="Ingestion Service",
    description="API for uploading and processing invoices.",
    version="1.0.0"
)

# --- Pydantic Models ---

class IngestedPoint(BaseModel):
    """Defines the structure for a single data point in the response."""
    id: str
    payload: Dict[str, Any]
    vector: Optional[List[float]] = None

class FileResult(BaseModel):
    """Defines the structure for a single file ingestion result."""
    filename: str
    message: str
    data: List[IngestedPoint]

class UploadResponse(BaseModel):
    """Defines the structure of the JSON response when multiple files are uploaded."""
    results: List[FileResult]

# --- API Endpoints ---
@app.post("/upload/", response_model=UploadResponse)
async def upload_invoices(files: List[UploadFile] = File(...)):
    """
    Endpoint to upload multiple files (PDF, DOCX, JPG, etc.).
    Each file is saved, ingested, and the generated data is returned.
    """
    results: List[FileResult] = []

    try:
        for file in files:
            file_path = os.path.join(DATA_FOLDER, file.filename)

            # Save file
            with open(file_path, "wb") as buffer:
                buffer.write(await file.read())

            # Ingest file
            ingested_data = ingest_document(file_path, COLLECTION_NAME)

            # Convert to dicts
            response_data = [point.model_dump() for point in ingested_data]

            # Append result
            results.append(FileResult(
                filename=file.filename,
                message="File uploaded and ingested successfully.",
                data=response_data
            ))

        return {"results": results}

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred during file ingestion: {str(e)}"
        )

@app.get("/")
def read_root():
    """Root endpoint to check if the service is running."""
    return {"status": "Ingestion Service is running"}
