# CLAUDE_SETUP.md

First-time setup for the SENTINEL BMS platform. **One-time only.**

## Prerequisites

```bash
# Check versions (must have at least):
python --version          # Python 3.11+
node --version            # Node.js 20+
docker --version          # Docker (for Supabase local)
```

**Optional (for local development):**
- Ollama 0.3.0+ (for LLM inference)
- Redis (for query caching)

## Backend Setup

```bash
# Navigate to backend
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate    # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env:
#   DEMO_MODE=true          (for fastest local dev)
#   SUPABASE_URL=...        (if using cloud DB)
#   JWT_SECRET_KEY=...      (run: openssl rand -hex 32)
```

## Frontend Setup

```bash
# Navigate to frontend
cd frontend

# Install dependencies
npm install

# Verify installation
npm run build     # Should compile without errors
```

## Supabase Setup (Local)

```bash
# Start local Supabase (includes PostgreSQL, API, Studio)
supabase start

# Verify it's running:
supabase status   # Should show API:55321, DB:55322

# Apply migrations
supabase db push

# Verify schema synced
supabase db pull

# Access database UI (opens browser)
# Studio should be at http://localhost:54323
```

**Ports:**
- API: `http://localhost:55321`
- DB: `localhost:55322`
- Studio: `http://localhost:54323`

## Verify Setup

Run these checks in order:

```bash
# 1. Backend imports
cd backend && python -c "import fastapi; print('✓ FastAPI')"

# 2. Frontend packages
cd frontend && npm list react > /dev/null && echo "✓ React"

# 3. Supabase API
curl http://localhost:55321/rest/v1/ && echo "✓ Supabase API"

# 4. Backend health check
curl http://localhost:9095/health && echo "✓ Backend"
# (Start backend first: ./start-backend.sh)

# 5. Database connection
curl http://localhost:9095/api/sites | grep '"sites"' && echo "✓ DB connected"
```

## Start Services

**Terminal 1: Backend**
```bash
./start-backend.sh
# Logs: http://localhost:9095/health
```

**Terminal 2: Frontend**
```bash
./start-frontend.sh
# Opens: http://localhost:9096
```

**Terminal 3: Monitor (optional)**
```bash
tail -f backend.log
```

## Configuration Reference

### Backend `.env`

```bash
# Core
DEMO_MODE=true                              # Skip auth, mock data
ENVIRONMENT=development                     # development|production
DEBUG=true                                  # Verbose logging

# Database
SUPABASE_URL=https://xxx.supabase.co        # Cloud or http://localhost:55321 for local
SUPABASE_SERVICE_ROLE_KEY=eyJ...            # From Supabase project settings
USE_JSON_STORAGE=false                      # Fallback when Supabase down

# Authentication
JWT_SECRET_KEY=<32-char hex>                # Generate: openssl rand -hex 32
ANTHROPIC_API_KEY=sk-...                    # Claude API (only if DEMO_MODE=false)

# Caching
REDIS_ENABLED=true                          # Query caching
REDIS_URL=redis://localhost:6379

# Voice Chat (optional)
ELEVENLABS_API_KEY=...                      # ElevenLabs TTS
ELEVENLABS_TTS_ENABLED=true                 # Enable voice output

# Integrations (optional for local dev)
SENTRY_WEBHOOK_SECRET=...                    # Telegram bot
ESKOMSEPush_API_TOKEN=...                   # South African load shedding
SIMBIOT_*=...                               # MRI Evolution
```

### Frontend `.env.development`

```bash
VITE_API_URL=http://localhost:9095
VITE_DEBUG=true                             # Verbose logging
```

## Troubleshooting Setup

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: No module named 'fastapi'` | Run `pip install -r requirements.txt` in venv |
| `EACCES: permission denied` (npm) | Run `npm cache clean --force` then `npm install` |
| Supabase won't start | Check ports 55321-55323 are free; run `docker ps` |
| Backend won't connect to DB | Check `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in `.env` |
| `localhost:9095` refuses connection | Make sure `./start-backend.sh` is running in Terminal 1 |
| TypeScript errors in frontend | Run `npm ci` to get exact dependency versions |
| "Can't find python venv" | Recreate: `rm -rf backend/venv && python -m venv backend/venv` |

## Development vs Production

**Development (.env):**
```bash
DEMO_MODE=true              # Mock data, no Claude API needed
USE_JSON_STORAGE=false      # Use local Supabase
DEBUG=true
```

**Production (.env):**
```bash
DEMO_MODE=false             # Real data, Claude API required
SUPABASE_URL=https://prod.supabase.co
DEBUG=false
```

## Session Memory

After setup, project memories are auto-loaded from:
- `/home/bederf/.claude/projects/-opt-bms-intelligence/memory/MEMORY.md`

This contains phase status, equipment registry, and lessons learned from past sessions.

## Next Steps

1. ✅ Backend setup complete
2. ✅ Frontend setup complete
3. ✅ Supabase setup complete
4. → **Daily work:** See `CLAUDE_QUICK_START.md`
5. → **Learning architecture:** See `CLAUDE_ARCHITECTURE.md`
