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

class UploadResponse(BaseModel):
    """Defines the structure of the entire JSON response for the /upload endpoint."""
    filename: str
    message: str
    data: List[IngestedPoint]

# --- API Endpoints ---
@app.post("/upload/", response_model=UploadResponse)
async def upload_invoice(file: UploadFile = File(...)):
    """
    Endpoint to upload a file (PDF, DOCX, JPG, etc.).
    The file is saved, ingested, and the generated data is returned.
    """
    file_path = os.path.join(DATA_FOLDER, file.filename)

    try:
        # Save the uploaded file to disk
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())

        # Process the file and get the list of generated points
        ingested_data = ingest_document(file_path, COLLECTION_NAME)

        # Convert the list of PointStruct objects into a list of dictionaries
        # so it can be properly returned as JSON.
        response_data = [point.model_dump() for point in ingested_data]

        return {
            "filename": file.filename,
            "message": "File uploaded and ingested successfully.",
            "data": response_data
        }
    except Exception as e:
        # Return a detailed error if something goes wrong
        raise HTTPException(status_code=500, detail=f"An error occurred during file ingestion: {str(e)}")

@app.get("/")
def read_root():
    """Root endpoint to check if the service is running."""
    return {"status": "Ingestion Service is running"}