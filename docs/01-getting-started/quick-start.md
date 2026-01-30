---
title: "Quick Start Guide"
type: "tutorial"
status: "approved"
version: "1.0.0"
created: "2026-01-30"
updated: "2026-01-30"
author: "Sentinel Development Team"
tags: ["getting-started", "setup", "installation"]
related: ["development-environment.md", "../02-architecture/system-overview.md"]
domain: "general"
audience: "all"
complexity: "beginner"
estimated_read_time: 10
---

# Quick Start Guide

Get SENTINEL BMS Intelligence Platform running in 5 minutes.

## Prerequisites

- **Python:** 3.11+
- **Node.js:** 18+
- **Git:** Latest version
- **API Keys:** Anthropic API key (for AI features)

## Start the Platform

### Terminal 1 - Backend API

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 9095
```

### Terminal 2 - Frontend UI

```bash
cd frontend
npm install
npm run dev
```

## Access the Platform

- **Frontend:** http://localhost:9096
- **Backend API:** http://localhost:9095
- **API Documentation:** http://localhost:9095/docs
- **Health Check:** http://localhost:9095/api/health

## Verify Installation

```bash
# Check backend health
curl http://localhost:9095/api/health

# Expected response:
# {"status":"healthy","version":"1.0.0"}
```

## First Steps

1. **Open the frontend** at http://localhost:9096
2. **View the dashboard** with demo sites and devices
3. **Try device control** on the Control page
4. **Chat with AI** on the Chat page
5. **Explore API docs** at http://localhost:9095/docs

## Environment Setup

### Backend `.env` File

Create `backend/.env`:

```bash
# Required for AI features
ANTHROPIC_API_KEY=your_api_key_here

# Optional database (defaults to JSON files)
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
USE_JSON_STORAGE=true

# Optional Ollama for hybrid AI
OLLAMA_BASE_URL=http://localhost:11434
```

### Frontend `.env.development` File

Create `frontend/.env.development`:

```bash
VITE_API_URL=http://localhost:9095
```

## Demo Mode

The platform starts in **demo mode** with:
- Pre-configured building sites
- Mock devices simulating real BMS equipment
- Sample alerts and predictions
- Pre-seeded AI chat responses

Demo mode requires no database or external BMS systems.

## Next Steps

- [**Development Environment**](development-environment.md) - Full setup guide
- [**System Overview**](../02-architecture/system-overview.md) - Architecture deep dive
- [**API Reference**](../03-api-reference/rest-api-endpoints.md) - API documentation

## Troubleshooting

### Backend fails to start

**Problem:** `ModuleNotFoundError: No module named 'app'`

**Solution:** Ensure you're in the `backend/` directory and venv is activated:

```bash
cd backend
source venv/bin/activate
pip install -r requirements.txt
```

### Frontend fails to start

**Problem:** `Cannot find module 'vite'`

**Solution:** Install dependencies:

```bash
cd frontend
npm install
```

### API returns 404 errors

**Problem:** Frontend can't connect to backend

**Solution:** Check backend is running on port 9095:

```bash
curl http://localhost:9095/api/health
```

If failing, restart backend and check for port conflicts:

```bash
# Check if port 9095 is in use
lsof -i :9095
```

### AI chat returns errors

**Problem:** `anthropic.AuthenticationError`

**Solution:** Verify ANTHROPIC_API_KEY in `backend/.env`:

```bash
# Test API key
export ANTHROPIC_API_KEY=sk-ant-...
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01"
```

## Common Tasks

### Run Tests

```bash
# Backend tests
cd backend
pytest

# Frontend tests
cd frontend
npm run test
```

### View Logs

```bash
# Backend logs (stdout from uvicorn)
# Check terminal where backend is running

# Frontend logs (browser console)
# Open browser DevTools (F12) → Console
```

### Reset Demo Data

```bash
# Delete mock device state
rm backend/app/data/mock_device_state.json

# Restart backend to regenerate
```

## Support

- **Documentation:** See `docs/` directory
- **Issues:** Report bugs in GitHub Issues
- **Chat:** Join the community Discord (link in README)
