---
title: "Development Environment Setup"
type: "guide"
status: "approved"
version: "1.0.0"
created: "2026-01-30"
updated: "2026-01-30"
author: "Sentinel Development Team"
tags: ["development", "setup", "environment"]
related: ["quick-start.md", "../12-development/tool-use-best-practices.md"]
domain: "general"
audience: "developers"
complexity: "beginner"
estimated_read_time: 15
---

# Development Environment Setup

Complete guide to setting up a SENTINEL development environment.

## Prerequisites

### Required Software

- **Python:** 3.11+ ([Download](https://www.python.org/downloads/))
- **Node.js:** 18+ ([Download](https://nodejs.org/))
- **Git:** Latest ([Download](https://git-scm.com/downloads))
- **Code Editor:** VS Code recommended ([Download](https://code.visualstudio.com/))

### Optional Software

- **Ollama:** For local AI testing ([Download](https://ollama.ai/))
- **Docker:** For containerized deployment ([Download](https://www.docker.com/))
- **Postgres Client:** For Supabase direct access

## Clone Repository

```bash
git clone https://github.com/your-org/bms-intelligence.git
cd bms-intelligence
```

## Backend Setup

### 1. Create Python Virtual Environment

```bash
cd backend
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configure Environment

Create `backend/.env`:

```bash
# Required for AI features
ANTHROPIC_API_KEY=sk-ant-your-key-here

# Optional database (defaults to JSON files)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-anon-key
USE_JSON_STORAGE=true

# Claude model configuration
CLAUDE_MODEL=claude-sonnet-4-20250514

# Optional Ollama for hybrid AI
OLLAMA_BASE_URL=http://localhost:11434

# Demo mode (uses pre-seeded responses)
DEMO_MODE=true
```

### 4. Verify Installation

```bash
# Check Python version
python --version  # Should be 3.11+

# Check dependencies
pip list | grep -E "fastapi|anthropic|pydantic"

# Run health check (after starting server)
uvicorn app.main:app --port 9095 &
sleep 3
curl http://localhost:9095/api/health
```

## Frontend Setup

### 1. Install Dependencies

```bash
cd frontend
npm install
```

### 2. Configure Environment

Create `frontend/.env.development`:

```bash
VITE_API_URL=http://localhost:9095
```

### 3. Verify Installation

```bash
# Check Node version
node --version  # Should be 18+

# Check npm version
npm --version

# Run dev server
npm run dev
```

Access at http://localhost:9096

## IDE Setup (VS Code)

### Recommended Extensions

Install these VS Code extensions:

```bash
code --install-extension ms-python.python
code --install-extension ms-python.vscode-pylance
code --install-extension dbaeumer.vscode-eslint
code --install-extension esbenp.prettier-vscode
code --install-extension bradlc.vscode-tailwindcss
```

### VS Code Settings

Create `.vscode/settings.json`:

```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/backend/venv/bin/python",
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": true,
  "python.formatting.provider": "black",
  "eslint.workingDirectories": ["frontend"],
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "source.fixAll.eslint": true
  }
}
```

## Development Workflow

### Start Development Servers

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

**Terminal 3 - Optional Ollama:**
```bash
ollama serve
```

### Run Tests

**Backend:**
```bash
cd backend
pytest                          # All tests
pytest tests/api/               # Specific directory
pytest -k "device"              # Filter by name
pytest -v --tb=short            # Verbose with short traceback
pytest -m unit                  # Run only unit tests
pytest tests/ -m "not slow"     # Exclude slow tests
```

**Frontend:**
```bash
cd frontend
npm run test                   # Vitest watch mode
npm run test:run              # Single run
npm run test:coverage         # With coverage
npm run test:ui               # Vitest UI
```

### Linting

**Backend:**
```bash
cd backend
pylint app/
black app/
isort app/
```

**Frontend:**
```bash
cd frontend
npm run lint                   # ESLint
npm run lint:fix              # Auto-fix issues
```

## Database Setup (Optional)

### Supabase Setup

1. **Create project** at https://supabase.com
2. **Run migrations**:

```bash
cd backend
export SUPABASE_URL=https://your-project.supabase.co
export SUPABASE_KEY=your-service-role-key

# Apply migrations
psql $SUPABASE_URL -f supabase/migrations/001_*.sql
psql $SUPABASE_URL -f supabase/migrations/002_*.sql
# ... etc
```

3. **Update `.env`**:

```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
USE_JSON_STORAGE=false
```

### JSON Fallback (Default)

No database setup required. Data stored in `backend/app/data/`:

- `mock_devices.json` - Device catalog
- `sites.json` - Building sites
- `safety_rules.json` - Safety validation rules
- `audit_log.json` - Audit trail

## Ollama Setup (Optional)

For local AI testing (40% cost savings):

### 1. Install Ollama

```bash
curl https://ollama.ai/install.sh | sh
```

### 2. Pull Models

```bash
ollama pull llama2
ollama pull mistral
```

### 3. Configure Backend

```bash
# backend/.env
OLLAMA_BASE_URL=http://localhost:11434
```

### 4. Test Hybrid Routing

```bash
curl -X POST http://localhost:9095/api/hybrid-chat \
  -H "Content-Type: application/json" \
  -d '{"message":"What is the temperature of chiller S001-CHILLER-B1-001?"}'
```

## Troubleshooting

### Python Version Issues

**Problem:** Python version too old

**Solution:** Install Python 3.11+ using pyenv:

```bash
# Install pyenv
curl https://pyenv.run | bash

# Install Python 3.11
pyenv install 3.11.7
pyenv local 3.11.7
```

### Dependency Conflicts

**Problem:** `pip install` fails with conflicts

**Solution:** Create fresh venv:

```bash
cd backend
rm -rf venv
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Port Already in Use

**Problem:** `Address already in use :9095`

**Solution:** Find and kill process:

```bash
# Find process
lsof -i :9095

# Kill process
kill -9 <PID>

# Or use different port
uvicorn app.main:app --port 9096
```

### CORS Errors

**Problem:** Frontend can't connect to backend

**Solution:** Verify backend CORS config:

```python
# backend/app/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:9096"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Ollama Connection Failed

**Problem:** `Connection refused` to Ollama

**Solution:** Start Ollama service:

```bash
ollama serve

# Verify
curl http://localhost:11434/api/tags
```

## Development Tips

### Hot Reload

- **Backend:** Auto-reloads on file changes (uvicorn --reload)
- **Frontend:** Auto-refreshes on file changes (Vite HMR)

### Debugging

**Backend (Python):**
```python
# Add breakpoint
import pdb; pdb.set_trace()

# Or use ipdb (better)
import ipdb; ipdb.set_trace()
```

**Frontend (TypeScript):**
```typescript
// Add debugger statement
debugger;

// Or use console.log
console.log('Value:', value);
```

### Logging

**Backend:**
```python
import logging
logger = logging.getLogger(__name__)
logger.info("Info message")
logger.error("Error message", exc_info=True)
```

**Frontend:**
```typescript
console.log('Log message');
console.error('Error:', error);
console.warn('Warning:', warning);
```

## Next Steps

- [**Tool Use Best Practices**](../12-development/tool-use-best-practices.md) - Development workflow
- [**Testing Strategy**](../11-testing/testing-strategy.md) - Test architecture
- [**System Overview**](../02-architecture/system-overview.md) - Architecture deep dive

## Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [React Documentation](https://react.dev/)
- [Vite Documentation](https://vitejs.dev/)
- [Anthropic Claude API](https://docs.anthropic.com/)
