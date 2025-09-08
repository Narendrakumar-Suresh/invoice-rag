import streamlit as st
import time

# --- Page Configuration ---
st.set_page_config(
    page_title="AI Invoice Assistant",
    page_icon="🧾",
    layout="centered",
    initial_sidebar_state="auto"
)

# --- Session State Initialization ---
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'processed_files' not in st.session_state:
    st.session_state.processed_files = []
if 'recording' not in st.session_state:
    st.session_state.recording = False
if 'transcript' not in st.session_state:
    st.session_state.transcript = ""  # holds Whisper STT output

# ==================================================================================================
# SIDEBAR (File Uploads) - No changes here
# ==================================================================================================
with st.sidebar:
    st.title("📄 Invoice Processor")
    uploaded_files = st.file_uploader(
        "Upload invoice files",
        type=['pdf', 'png', 'jpg', 'jpeg'],
        accept_multiple_files=True,
        label_visibility="collapsed"
    )

    if st.button("🚀 Process Files", disabled=not uploaded_files, use_container_width=True, type="primary"):
        st.session_state.processed_files = []
        progress_bar = st.progress(0, text="Starting processing...")
        for i, file in enumerate(uploaded_files):
            time.sleep(0.5)  # Mock processing time
            st.session_state.processed_files.append({'name': file.name})
            progress_bar.progress((i + 1) / len(uploaded_files), text=f"Processing {file.name}")
        progress_bar.empty()
        st.success("Files processed successfully!")

    if st.session_state.processed_files:
        st.subheader("Processed Files:")
        for file_info in st.session_state.processed_files:
            st.markdown(f"✅ _{file_info['name']}_")

# ==================================================================================================
# MAIN CHAT INTERFACE
# ==================================================================================================

st.title("AI Invoice Assistant")
st.write("Upload your invoices on the left and ask questions below.")

# Display chat history
for message in st.session_state.chat_history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# ==================================================================================================
# AUDIO RECORDING CONTROLS
# ==================================================================================================
col1, col2 = st.columns([1, 5])
with col1:
    if not st.session_state.recording:
        if st.button("🎤 Start Recording"):
            st.session_state.recording = True
            st.toast("Recording started...")
            # Clear previous transcript when starting new recording
            st.session_state.transcript = ""
            st.rerun() # Rerun to update button state immediately
    else:
        if st.button("⏹ Stop Recording"):
            st.session_state.recording = False
            # --- MOCK STT (Whisper integration goes here) ---
            transcript = "this is a mock transcript from Whisper"

            # 1. Update session state with the new transcript
            st.session_state.transcript = transcript
            st.toast(f"Transcript ready: {transcript}")

            # 2. Force a rerun to update the text input value below
            st.rerun()

# ==================================================================================================
# CHAT INPUT BAR (Using st.text_input to allow pre-filling)
# ==================================================================================================

# Use st.form to create a submission flow for st.text_input
with st.form("chat_form", clear_on_submit=True):
    # 3. Bind st.text_input value to the transcript in session state
    prompt = st.text_input(
        "Ask a question about your invoices...",
        value=st.session_state.transcript,
        placeholder="Type here or record audio..."
    )
    submitted = st.form_submit_button("Send")

if submitted and prompt:
    # 4. Clear transcript state variable once submitted
    st.session_state.transcript = ""

    # Add user message to session state
    st.session_state.chat_history.append({"role": "user", "content": prompt})

    # Display user message (we need to re-render everything to show new message)
    # Mock assistant response
    with st.spinner("Assistant is thinking..."):
        time.sleep(1)
        response = f"Answer to your question about '{prompt[:30]}...'"
    st.session_state.chat_history.append({"role": "assistant", "content": response})

    # Rerun to display the new chat messages and clear the form's residual state
    st.rerun()