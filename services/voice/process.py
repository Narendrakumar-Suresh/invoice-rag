import os
from groq import Groq
from elevenlabs.client import ElevenLabs
from dotenv import load_dotenv

load_dotenv()

# STT client
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# TTS client
elevenlabs = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

def generate_transcription(audio_file_path):
    with open(audio_file_path, "rb") as file:
        transcription = client.audio.transcriptions.create(
            file=("test.mp3", file, "audio/mpeg"),
            model="whisper-large-v3",
            response_format="verbose_json",
        )
        return transcription.text

# Generate speech
def generate_speech(msg: str) -> bytes:
    audio_stream = elevenlabs.text_to_speech.convert(
        text=msg,
        voice_id="JBFqnCBsd6RMkjVDRZzb",
        model_id="eleven_multilingual_v2",
        output_format="mp3_44100_128",
    )

    audio_bytes = b"".join(chunk for chunk in audio_stream)
    return audio_bytes
