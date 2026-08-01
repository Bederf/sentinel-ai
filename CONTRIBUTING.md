# Contributing

Thanks for your interest in SENTINEL. This document covers the practical steps for making a change.

## Development setup

See [`docs/01-getting-started/quick-start.md`](docs/01-getting-started/quick-start.md) and
[`docs/01-getting-started/development-environment.md`](docs/01-getting-started/development-environment.md)
for full environment setup. Short version:

```bash
cp .env.example .env      # fill in Supabase/Redis credentials
./quickstart.sh           # starts backend (:9095) and frontend (:5173)
```

## Before opening a pull request

Run the same checks CI runs:

```bash
# Backend
cd backend
ruff format --check .
ruff check .
python -m pytest tests/ -m "not integration and not performance and not slow"

# Frontend
cd frontend
npm run lint
npx tsc --noEmit
npm run test:run
```

A pull request is expected to pass linting, type checking, and unit tests. Integration tests (needing a live
Supabase instance) and E2E tests run separately and don't block merges.

## Commit messages

This repo follows [Conventional Commits](https://www.conventionalcommits.org/):
`type(scope): summary`, e.g. `fix(onboarding): save site details on next`. Common types: `feat`, `fix`, `docs`,
`chore`, `refactor`, `test`.

## Code size and structure

Backend and frontend files are expected to stay decomposable — as a rough guide, a single file exceeding ~800
lines is a signal to split it rather than keep growing it. Prefer extending existing modules/services over
creating parallel implementations of the same concept.

## Security-sensitive changes

Never commit secrets, credentials, or `.env*` files. See [`SECURITY.md`](SECURITY.md) for how to report a
vulnerability and what the automated security gates check.

## Where things live

- Backend: `backend/app/` (FastAPI) — see [`docs/02-architecture/`](docs/02-architecture/)
- Frontend: `frontend/src/` (React + Vite + TypeScript)
- Database: `supabase/migrations/`
- Docs: [`docs/README.md`](docs/README.md) is the documentation index
