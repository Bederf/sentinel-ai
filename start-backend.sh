#!/bin/bash
# Start BMS Intelligence Backend (local dev)

cd "$(dirname "$0")/backend"

# Create venv if not exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

# Install deps if needed
if [ ! -f "venv/.deps_installed" ]; then
    echo "Installing dependencies..."
    pip install -r requirements.txt
    touch venv/.deps_installed
fi

echo "Starting backend on http://localhost:9090"
uvicorn app.main:app --reload --host 0.0.0.0 --port 9090
