import streamlit as st
import requests
import tempfile
import os
import re

# --- Configuration ---
API_URLS = {
    "ingestion": "http://localhost:8001/upload/",
    "chat": "http://localhost:8002/chat",
    "stt": "http://localhost:8003/stt",
    "tts": "http://localhost:8003/tts",
}

st.set_page_config(page_title="AI Invoice Assistant", page_icon="🧾", layout="centered")

# --- Session State Initialization ---
# Ensures all necessary keys are in the session state at the start.
def init_session_state():
    defaults = {
        "chat_history": [],
        "processed_files": [],
        "chat_input": "",
        "audio_cache": {},
        "playing_audio_index": None,
        "audio_input_key": 0,
        "text_input_key": 1000
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_state()


# --- Utility Functions ---

def escape_dollars(text: str) -> str:
    r"""
    Escapes dollar signs in text to prevent Streamlit's KaTeX parser error.
    Any '$' not part of a code block is replaced with '\$'.
    """
    return re.sub(r'(?<!\\)\$', r'\\$', text)


def generate_tts_audio(text: str, message_index: int):
    """
    Generate and cache Text-to-Speech audio. If already cached, return it.
    """
    audio_key = f"audio_{message_index}"
    if audio_key in st.session_state.audio_cache:
        return st.session_state.audio_cache[audio_key]

    try:
        with st.spinner("Generating audio..."):
            # Remove markdown asterisks for cleaner speech
            clean_text = re.sub(r'\*+', '', text)
            # Use `data` instead of `json` to send form-encoded data, fixing the 422 error
            tts_resp = requests.post(API_URLS["tts"], data={"text": clean_text}, timeout=60)

            if tts_resp.ok:
                st.session_state.audio_cache[audio_key] = tts_resp.content
                return tts_resp.content
            else:
                st.warning(f"TTS API failed with status: {tts_resp.status_code}")
                return None
    except requests.exceptions.RequestException as e:
        st.error(f"TTS connection error: {e}")
        return None


# --- Sidebar UI ---
with st.sidebar:
    st.title("📄 Invoice Processor")
    uploaded_files = st.file_uploader(
        "Upload invoices", type=["pdf", "png", "jpg", "jpeg", "docx"], accept_multiple_files=True
    )

    if st.button("🚀 Process Files", disabled=not uploaded_files):
        # Clear previous results before processing new files
        st.session_state.processed_files = []
        with st.spinner("Processing..."):
            for file in uploaded_files:
                files_payload = {"files": (file.name, file.getvalue(), file.type)}
                status = "failed" # Default status
                try:
                    # Attempt to send files to the ingestion API
                    resp = requests.post(API_URLS["ingestion"], files=files_payload, timeout=20)
                    if resp.ok:
                        status = "success"
                except requests.exceptions.RequestException:
                    # If the API call fails (e.g., connection error), status remains "failed"
                    pass
                st.session_state.processed_files.append({"name": file.name, "status": status})
        st.success("✅ File processing complete.")

    if st.session_state.processed_files:
        st.subheader("Processed Files Status")
        for f in st.session_state.processed_files:
            icon = "✅" if f["status"] == "success" else "⚠️"
            st.markdown(f"{icon} {f['name']}")


# --- Main Page UI ---
st.title("🧾 AI Invoice Assistant")

# Display chat history
for i, msg in enumerate(st.session_state.chat_history):
    with st.chat_message(msg["role"]):
        # Escape dollar signs to prevent KaTeX rendering errors
        safe_content = escape_dollars(msg["content"])
        st.markdown(safe_content)

        # Add a listen button only for assistant messages
        if msg["role"] == "assistant":
            if st.button("🔊 Listen", key=f"listen_{i}"):
                # Toggle the audio player's visibility
                if st.session_state.playing_audio_index == i:
                    st.session_state.playing_audio_index = None # Hide if already playing
                else:
                    st.session_state.playing_audio_index = i
                st.rerun() # Rerun to update the UI

            # If this message's audio should be playing, generate and show the player
            if st.session_state.playing_audio_index == i:
                audio_content = generate_tts_audio(msg["content"], i)
                if audio_content:
                    st.audio(audio_content, format="audio/mpeg")


# --- Speech-to-Text Section ---
st.subheader("🎤 Record a voice question")
# Use st.audio_input to allow recording directly in the app
audio_bytes = st.audio_input(
    "Record your voice message here",
    key=f"audio_recorder_{st.session_state.audio_input_key}"
)

if audio_bytes:
    with st.spinner("Transcribing audio..."):
        transcript_to_add = ""
        try:
            # Prepare the audio bytes for the STT API
            files = {"file": ("recorded_audio.wav", audio_bytes, "audio/wav")}
            resp = requests.post(API_URLS["stt"], files=files, timeout=30)
            if resp.ok:
                transcript_to_add = resp.json().get("text", "")
            else:
                st.warning("STT service failed. Using mock transcript.")
                transcript_to_add = "Mock transcript: What is the total on invoice INV-123?"
        except requests.exceptions.RequestException as e:
            st.error(f"STT connection error: {e}")
            transcript_to_add = "Mock transcript: What is the total on invoice INV-123?"

        # Replace the chat input text with the new transcript
        st.session_state.chat_input = transcript_to_add

        # Reset the recorder and rerun to update the text box
        st.session_state.audio_input_key += 1
        st.rerun()


# --- Chat Input Section ---
with st.form(key="chat_form", clear_on_submit=True):
    # The text input's initial value is set from session state, but the widget
    # itself is not bound to the key, preventing the API error.
    prompt = st.text_input(
        "Ask a question...",
        value=st.session_state.chat_input,
        placeholder="Record audio to transcribe, or type here and press Send.",
        label_visibility="collapsed"
    )
    submitted = st.form_submit_button("Send")

if submitted and prompt:
    # Append user message to history and display it
    st.session_state.chat_history.append({"role": "user", "content": prompt})

    # Clear the session state for the input, so it's empty on the next run
    st.session_state.chat_input = ""

    with st.chat_message("user"):
        st.markdown(escape_dollars(prompt))

    # Stream assistant's response
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        response_text = ""
        try:
            with requests.post(API_URLS["chat"], json={"message": prompt}, stream=True, timeout=120) as resp:
                resp.raise_for_status() # Raise an exception for bad status codes
                for chunk in resp.iter_content(chunk_size=512, decode_unicode=True):
                    if chunk:
                        response_text += chunk
                        # Display the streamed response safely
                        message_placeholder.markdown(escape_dollars(response_text) + "▌")

            message_placeholder.markdown(escape_dollars(response_text)) # Final clean text
        except requests.exceptions.RequestException as e:
            response_text = f"**Error:** Could not connect to the chat service. {e}"
            message_placeholder.markdown(response_text)

    # Append the final assistant response to history
    st.session_state.chat_history.append({"role": "assistant", "content": response_text})

    # Rerun to show the new messages. The form's clear_on_submit will handle the UI.
    st.rerun()

# --- System Status Expander ---
with st.expander("🔧 System Status"):
    st.metric("Uploaded & Processed Files", len(st.session_state.processed_files))
    st.metric("Total Chat Messages", len(st.session_state.chat_history))
    st.metric("Cached Audio Files", len(st.session_state.audio_cache))

    if st.button("🗑️ Clear Audio Cache"):
        st.session_state.audio_cache = {}
        st.session_state.playing_audio_index = None
        st.rerun()
