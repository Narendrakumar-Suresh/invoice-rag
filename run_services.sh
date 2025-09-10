#!/bin/bash
# run_services.sh
# Fully robust script to run all services

# --- Set up project root ---
PROJECT_ROOT=$(pwd)
export PYTHONPATH=$PYTHONPATH:$PROJECT_ROOT

# --- Activate virtual environment ---
if [ -f ".venv/bin/activate" ]; then
    echo "Activating virtual environment..."
    source .venv/bin/activate
else
    echo "Virtual environment not found. Creating .venv..."
    python3 -m venv .venv
    source .venv/bin/activate
fi

# --- Install dependencies ---
if [ -f "requirements.txt" ]; then
    echo "Installing dependencies from requirements.txt..."
    pip install --upgrade pip
    pip install -r requirements.txt
else
    echo "requirements.txt not found! Exiting..."
    exit 1
fi

# --- Define service ports and URLs ---
declare -A API_URLS
API_URLS=(
    ["ingestion"]="http://localhost:8001/upload/"
    ["chat"]="http://localhost:8002/chat"
    ["stt"]="http://localhost:8003/stt"
    ["tts"]="http://localhost:8003/tts"
    ["frontend"]="http://localhost:8501"
)

# --- Check if a port is free ---
function check_port {
    PORT=$1
    if lsof -i:$PORT >/dev/null; then
        echo "Error: Port $PORT is already in use."
        exit 1
    fi
}

# --- Check all ports ---
for port in 8001 8002 8003 8501; do
    check_port $port
done

# --- Start services ---
echo "Starting Ingestion service..."
cd services/ingestion || exit
uvicorn main:app --host 0.0.0.0 --port 8001 --reload &
cd "$PROJECT_ROOT" || exit

echo "Starting Chat service..."
cd services/chat || exit
uvicorn main:app --host 0.0.0.0 --port 8002 --reload &
cd "$PROJECT_ROOT" || exit

echo "Starting Voice service (STT & TTS)..."
cd services/voice || exit
uvicorn main:app --host 0.0.0.0 --port 8003 --reload &
cd "$PROJECT_ROOT" || exit

echo "Starting Frontend (Streamlit)..."
streamlit run services/frontend/main.py --server.port 8501 &

# --- Print service URLs ---
echo ""
echo "All services started. Access them at:"
for key in "${!API_URLS[@]}"; do
    printf "%-10s -> %s\n" "$key" "${API_URLS[$key]}"
done
echo ""

# --- Wait for all background processes ---
wait
