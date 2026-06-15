# Sentinel AI

Smart building operations platform powered by AI. Complements existing BMS (BACnet, Modbus, Desigo, Niagara) with predictive analytics, automated fault detection, and intelligent work order generation.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        Frontend (React/Vite)                  │
│                     Cockpit dashboards + settings             │
└──────────────────────────┬───────────────────────────────────┘
                           │ REST + SSE
┌──────────────────────────▼───────────────────────────────────┐
│                      Backend (FastAPI)                        │
│                                                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐ │
│  │  Agents  │  │ Services │  │ Adapters │  │  Scheduler   │ │
│  │  (NLP,   │  │ (ML,     │  │ (BMS,    │  │  (APScheduler│ │
│  │  Graph)  │  │  Health) │  │  IoT)    │  │   tasks)     │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘ │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐  │
│  │               Database Layer (Supabase)                 │  │
│  │      PostgreSQL + Redis caching + real-time             │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
git clone git@github.com:Bederf/sentinel-ai.git
cd sentinel-ai

cp .env.example .env
# Edit .env with your Supabase credentials

./quickstart.sh
```

This starts the backend (FastAPI on `:9095`) and frontend (Vite on `:5173`).

## Project Structure

```
├── backend/          # FastAPI application
│   ├── app/
│   │   ├── agents/       # NLP, recommendation, automation agents
│   │   ├── api/          # REST endpoints + SSE real-time events
│   │   ├── services/     # ML, health monitoring, integrations
│   │   ├── adapters/     # BMS protocol adapters (BACnet, Modbus)
│   │   └── database/     # Supabase client + repositories
│   └── tests/
├── frontend/         # React + Vite + TypeScript
│   ├── src/
│   │   ├── cockpit/     # Main dashboard views
│   │   ├── settings/    # Configuration UI
│   │   └── components/  # Shared UI components
│   └── e2e/             # Playwright tests
├── supabase/         # Database migrations + config
├── docs/             # Architecture, API reference, operations
├── infrastructure/   # Docker, monitoring, deployment configs
└── .github/          # CI/CD workflows
```

## Running Tests

```bash
# Backend tests
cd backend && python -m pytest

# Frontend tests
cd frontend && npm test

# End-to-end tests
cd frontend && npx playwright test
```

## Deployment

### Docker Compose (production)

```bash
docker compose -f docker-compose.prod.yml up -d
```

### Services

- `sentinel-backend.service` — systemd unit for the FastAPI backend
- `sentinel-frontend.service` — systemd unit for the frontend (Nginx)

## Environment

See `.env.example` for all required configuration:

| Variable | Description |
|----------|-------------|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Supabase service role key |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string (caching) |

## Key Features

- **Predictive maintenance** — ML models trained on BMS telemetry detect anomalies before failure
- **Automated diagnostics** — AI agents analyze faults and recommend actions
- **Real-time monitoring** — SSE-powered live dashboard with 30s polling
- **Multi-site** — Site-isolated data model supports any number of buildings
- **Protocol agnostic** — SIMBIOT adapter layer works with BACnet, Modbus, Desigo, Niagara
- **Human-in-loop** — All automated actions require operator approval

## License

Proprietary. All rights reserved.
