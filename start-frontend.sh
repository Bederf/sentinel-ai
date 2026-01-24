#!/bin/bash
# Start BMS Intelligence Frontend (local dev)

cd "$(dirname "$0")/frontend"

# Install deps if needed
if [ ! -d "node_modules" ]; then
    echo "Installing dependencies..."
    npm install
fi

echo "Starting frontend on http://localhost:9096"
npm run dev -- --host 0.0.0.0 --port 9096
