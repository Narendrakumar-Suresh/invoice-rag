from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse
import process
import os
import uuid

app = FastAPI(
    title="Voice Service",
    description="Speech-to-Text (STT) with Groq + Text-to-Speech (TTS) with ElevenLabs",
    version="1.0.0"
)

# --- STT Endpoint ---
@app.post("/stt")
async def stt(file: UploadFile = File(...)):
    """
    Upload an audio file (e.g., mp3/wav).
    Returns the transcribed text using Groq Whisper.
    """
    temp_filename = f"/tmp/{uuid.uuid4()}_{file.filename}"
    with open(temp_filename, "wb") as buffer:
        buffer.write(await file.read())

    try:
        transcription = process.generate_transcription(temp_filename)
        return {"text": transcription}
    finally:
        os.remove(temp_filename)

# --- TTS Endpoint ---
@app.post("/tts")
async def tts(text: str = Form(...)):
    output_path = f"/tmp/{uuid.uuid4()}.mp3"
    audio_bytes = process.generate_speech(text)

    with open(output_path, "wb") as f:
        f.write(audio_bytes)

    return FileResponse(output_path, media_type="audio/mpeg", filename="speech.mp3")
