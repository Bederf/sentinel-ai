# SENTINEL BMS Intelligence - Setup Guide

**Last Updated:** 2026-02-09
**Status:** Production Ready

## Quick Start (5 minutes)

### Prerequisites
- Python 3.11+
- Node.js 20+
- **⚠️ IMPORTANT: Tesseract-OCR system binary** (see [OCR Setup](#ocr-setup))

### 1. Backend Setup
```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env from template
cp .env.example .env
# Edit .env with your settings

# Start backend
uvicorn app.main:app --reload --port 9095
```

**Backend running at:** `http://localhost:9095`
**API docs:** `http://localhost:9095/docs`

### 2. Frontend Setup
```bash
cd frontend

# Install dependencies
npm install

# Start dev server
npm run dev
```

**Frontend running at:** `http://localhost:9096`

### 3. Verify Installation
```bash
# Health check
curl http://localhost:9095/health

# Expected response:
{
  "status": "healthy",
  "ocr_available": true,
  "components": {
    "ocr": "available"
  }
}
```

---

## ⚠️ Critical: OCR Setup

OCR (Optical Character Recognition) is **required infrastructure** used across multiple modules:
- Floor plan sanitization (Phase A: Digital Twin)
- Work order technician pipeline (Phase 41)
- Equipment vision processing
- Service sheet data entry

### Installing Tesseract-OCR

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr libtesseract-dev

# Verify
tesseract --version
```

**macOS:**
```bash
brew install tesseract

# Verify
tesseract --version
```

**Windows (WSL or Native):**
```bash
# WSL
wsl
sudo apt-get install -y tesseract-ocr libtesseract-dev

# Native: Download from
# https://github.com/UB-Mannheim/tesseract/wiki
# Or: choco install tesseract
```

**Docker:**
```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libtesseract-dev \
    && rm -rf /var/lib/apt/lists/*
```

**Verify Installation:**
```bash
# In backend directory
source venv/bin/activate
python3 << 'EOF'
from app.services.floor_plan_sanitizer import get_floor_plan_sanitizer
sanitizer = get_floor_plan_sanitizer()
print(f"✅ OCR Ready: {sanitizer.ocr_installed}")
EOF
```

**⚠️ If OCR installation fails:**
- Some features will degrade gracefully
- Floor plan extraction will still work (without text removal)
- See `docs/01-setup/ocr-setup-guide.md` for troubleshooting

---

## Full Setup Steps

### 1. Clone Repository
```bash
git clone <repo-url>
cd bms-intelligence
```

### 2. Backend Configuration

#### Create Virtual Environment
```bash
cd backend
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# OR
venv\Scripts\activate  # Windows
```

#### Install Python Dependencies
```bash
pip install -r requirements.txt
```

#### Configure Environment
```bash
# Copy template
cp .env.example .env

# Edit .env with:
# - JWT_SECRET_KEY (generate: openssl rand -hex 32)
# - ANTHROPIC_API_KEY (if using Claude API)
# - DATABASE_URL (Supabase or PostgreSQL)
# - DEMO_MODE (true/false)
```

#### Key Environment Variables
| Variable | Purpose | Example |
|----------|---------|---------|
| `DEMO_MODE` | Use demo responses | `true` |
| `ANTHROPIC_API_KEY` | Claude API key | (your key) |
| `DATABASE_URL` | Supabase/PostgreSQL | `postgresql://...` |
| `REDIS_ENABLED` | Cache layer | `true` |
| `TESSERACT_CMD` | (optional) Tesseract path | `/usr/bin/tesseract` |

### 3. Frontend Configuration

#### Install Node Modules
```bash
cd frontend
npm install
```

#### Environment Setup
```bash
# Create .env.development
cat > .env.development << EOF
VITE_API_URL=http://localhost:9095
VITE_DEMO_MODE=true
EOF
```

### 4. Start Services

**Terminal 1 - Backend:**
```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 9095
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```

**Optional Terminal 3 - Local Supabase:**
```bash
supabase start
# Runs local database on :55322, API on :55321
```

### 5. Run Tests

```bash
# Backend unit tests
cd backend
pytest tests/ -v

# Backend with coverage
pytest tests/ --cov=app --cov-report=html

# Frontend tests
cd frontend
npm run test:run

# E2E tests
cd e2e
npx playwright test
```

---

## System Architecture

### Backend (`/backend`)
- **Framework:** FastAPI (Python 3.11)
- **Database:** Supabase (PostgreSQL) with JSON fallback
- **ML:** TensorFlow (LSTM + Autoencoder models)
- **APIs:** 70+ REST endpoints, 31 MCP tools
- **Key Services:**
  - Device abstraction (BACnet, Modbus, DALI, mock)
  - AI optimizer (equipment recommendations)
  - Safety engine (temperature/pressure validation)
  - Hybrid AI (Ollama Tier 1 + Claude Tier 2)

### Frontend (`/frontend`)
- **Framework:** React 18 + TypeScript + Vite
- **UI:** Tremor v3 components + Tailwind CSS
- **Key Pages:**
  - Dashboard (building overview)
  - Device control (manual + optimization)
  - Tech chat (AI conversational interface)
  - SIMBIOT wizard (BMS onboarding)
  - Recommendations (health profiles)

### Infrastructure
```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│   Frontend  │◄───────►│  Backend API │◄───────►│  Supabase   │
│ :9096       │ HTTP    │  :9095       │ SQL     │  PostgreSQL │
└─────────────┘         └──────────────┘         └─────────────┘
                               │
                        ┌──────┴──────┬─────────┐
                        ▼             ▼         ▼
                    [Claude API] [Ollama] [Redis]
                    (Tier 2 AI)  (Tier 1) (Cache)
```

---

## Demo Mode vs Production

### Demo Mode (`DEMO_MODE=true`)
- ✅ No API keys required
- ✅ Pre-seeded equipment and buildings
- ✅ Simulated BMS responses
- ✅ Local-only (no cloud dependencies)
- ⚠️ Cannot connect to real BMS hardware

```bash
# .env
DEMO_MODE=true
USE_JSON_STORAGE=true
```

### Production Mode (`DEMO_MODE=false`)
- ✅ Real BMS integration (BACnet, Modbus, OPC-UA)
- ✅ Claude API for advanced AI
- ✅ Supabase for production database
- ✅ Redis caching
- ⚠️ Requires API keys and infrastructure

```bash
# .env
DEMO_MODE=false
ANTHROPIC_API_KEY=sk-ant-...
DATABASE_URL=postgresql://...
```

---

## Optional: Local Supabase Setup

For development without cloud Supabase:

```bash
# Install Supabase CLI
# (https://supabase.com/docs/guides/cli)

# Start local stack
supabase start

# This provides:
# - API: http://localhost:55321
# - DB: localhost:55322
# - Studio: http://localhost:55323

# Update .env
DATABASE_URL=postgresql://postgres:postgres@localhost:55322/postgres
```

---

## Optional: Redis Caching

For performance optimization:

```bash
# Install Redis
# Ubuntu: sudo apt-get install redis-server
# macOS: brew install redis
# Or Docker: docker run -d -p 6379:6379 redis:latest

# Update .env
REDIS_ENABLED=true
REDIS_URL=redis://localhost:6379
```

---

## Docker Deployment

### Build Image
```bash
docker build -f backend/Dockerfile -t bms-backend:latest .
```

### Run Container
```bash
docker run -d \
  -p 9095:9095 \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -e DATABASE_URL=postgresql://... \
  -e DEMO_MODE=false \
  bms-backend:latest
```

### Docker Compose
```bash
docker-compose up -d

# Logs
docker-compose logs -f backend
```

---

## Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'app'"
**Solution:** Ensure you're in `/backend` directory and venv is activated
```bash
cd backend
source venv/bin/activate
```

### Issue: "tesseract is not installed"
**Solution:** Install tesseract-ocr system binary (see [OCR Setup](#ocr-setup) above)

### Issue: "ANTHROPIC_API_KEY not found"
**Solution:**
1. For demo: Set `DEMO_MODE=true` in .env
2. For production: Add key to .env:
   ```
   ANTHROPIC_API_KEY=sk-ant-your-actual-key-here
   ```

### Issue: Frontend shows "Cannot reach API"
**Solution:** Check backend is running
```bash
curl http://localhost:9095/health
# Should return 200 with health status
```

### Issue: Tests timeout or fail
**Solution:** Increase timeout in `backend/pytest.ini`:
```ini
[pytest]
timeout = 60  # seconds per test
```

### Issue: Database connection errors
**Solution:**
1. If using Supabase: Verify `DATABASE_URL` in .env
2. If using local: Run `supabase start`
3. If using PostgreSQL: Verify connection string

---

## Quick Commands Reference

| Task | Command |
|------|---------|
| **Start backend** | `cd backend && source venv/bin/activate && uvicorn app.main:app --reload --port 9095` |
| **Start frontend** | `cd frontend && npm run dev` |
| **Run tests** | `cd backend && pytest tests/ -v` |
| **Check health** | `curl http://localhost:9095/health` |
| **View API docs** | Open `http://localhost:9095/docs` in browser |
| **Check OCR** | `source venv/bin/activate && python -m pytest tests/services/test_floor_plan_sanitizer.py -v` |
| **View logs** | `docker-compose logs -f backend` (if Docker) |

---

## Documentation Structure

- **`docs/01-setup/ocr-setup-guide.md`** - OCR installation and troubleshooting
- **`docs/02-architecture/`** - System architecture, naming conventions, ML models
- **`docs/03-api-reference/`** - REST API endpoints, OpenAPI specs
- **`docs/04-features/`** - Feature guides (Digital Twin, SIMBIOT, Technician Mobile)
- **`docs/05-troubleshooting/`** - Debugging guides, common issues

---

## Next Steps

1. ✅ Backend and frontend running locally
2. ✅ Tests passing
3. Next: Explore SIMBIOT wizard in UI (`http://localhost:9096`)
4. Next: Connect to local demo building (site-002)
5. Next: Test AI optimizer recommendations

---

## Support & Questions

For issues or questions:
1. Check `docs/05-troubleshooting/` directory
2. Review test output: `pytest tests/ -v`
3. Check health endpoint: `curl http://localhost:9095/health`
4. Review logs for errors

---

**Status:** ✅ Production Ready
**Last Verified:** 2026-02-09
**Maintained By:** SENTINEL Development Team
