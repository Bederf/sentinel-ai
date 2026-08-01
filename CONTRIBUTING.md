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

## Known CI limitations

CI's `backend-tests` job runs the full non-integration test suite against placeholder credentials
(`SUPABASE_SERVICE_ROLE_KEY=test-key-not-real`, a local `DATABASE_URL`) and no Ollama instance. In a
generic checkout with no local services running, a substantial number of tests are expected to fail —
this is a known gap, not a secret, and not evidence the sanitized/public history is broken. As of this
writing the suite runs ~6,400 tests with a ~91% pass rate; almost all remaining failures fall into:

- **Auth/API tests expecting a real Supabase instance** (`assert 401 == ...`, `postgrest.exceptions.APIError:
  JWSError`) — these hit `SUPABASE_URL`/`DATABASE_URL` for real and get rejected by whatever is actually
  listening on `127.0.0.1:55321`/`55322` (or time out if nothing is). Reproduce locally with the
  [Supabase CLI](https://supabase.com/docs/guides/cli): `supabase start` in the repo root picks up the
  committed `supabase/config.toml`, which pins those exact ports.
- **Tests exercising local LLM fallback** (`app/services/ollama_client.py`, `hybrid_ai_service.py`,
  `model_gateway.py`) — need a running [Ollama](https://ollama.com) instance; fail with attribute/connection
  errors otherwise.
- **`pytest-asyncio` version drift** — the CI install step doesn't pin `pytest-asyncio`'s version, so a small
  cluster of `RuntimeError: no current event loop` / `coroutine is not subscriptable` failures can appear or
  disappear depending on which release `pip`/`uv` resolves at install time.
- A long tail of pre-existing, single-test assertion failures across unrelated subsystems (equipment-code
  mapping, health scoring, notification counters) that predate any given change and are tracked as ordinary
  backlog, not release blockers.

If you're touching one of these areas, run the affected test file directly with the real local services up
rather than relying on the full-suite CI signal, and don't assume a red `backend-tests` run means your change
broke something until you've checked which category the failures fall into.

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
