# Repository Guidelines

## Project Structure & Module Organization
- `frontend/`: React + TypeScript + Vite UI. Main code is in `frontend/src` (`components/`, `pages/`, `hooks/`, `lib/api/`, `__tests__/`).
- `backend/`: FastAPI services and ML/domain logic. API and core services are under `backend/app`; Python tests are under `backend/tests`.
- `e2e/`: Playwright end-to-end tests.
- `simbiot_concept/`, `docs/`, `infrastructure/`, `supabase/`: integration module, documentation, deployment/ops config, and database assets.
- Keep generated output (`frontend/dist`, caches, logs) out of commits unless explicitly needed.

## Build, Test, and Development Commands
- Start local stack (recommended):
  - `./start-backend.sh` (FastAPI on `:9095`)
  - `./start-frontend.sh` (Vite on `:9096`)
- Frontend (`frontend/`):
  - `npm run dev` (dev server), `npm run build` (type-check + production build)
  - `npm run lint` (ESLint), `npm run test:run`, `npm run test:coverage` (Vitest)
- Backend (`backend/`):
  - `source venv/bin/activate && pytest` (test suite)
- Full Python tests from repo root:
  - `pytest` (uses root `pytest.ini`, includes `tests` and `backend/tests`)
- Containerized run:
  - `docker compose up --build`

## Coding Style & Naming Conventions
- Python: 4-space indentation, Ruff linting (`backend/pyproject.toml`), max line length 120.
- TypeScript/React: ESLint with `typescript-eslint` and React Hooks rules (`frontend/eslint.config.js`). Prefix intentionally unused variables with `_`.
- Naming: React components in PascalCase (e.g., `SiteDetail.tsx`); Python modules/data files in `snake_case`.
- Domain IDs and key fields must follow `docs/02-architecture/NAMING_CONVENTIONS.md` (e.g., equipment IDs like `S002-CHILLER-B1-001`).

## Testing Guidelines
- Frameworks: `pytest` (Python), `vitest` + Testing Library (frontend), `playwright` (`e2e/`).
- Test file patterns: Python `test_*.py` / `*_test.py`; frontend tests under `src/**/__tests__`.
- Use pytest markers (`unit`, `integration`, `slow`, `performance`, `security`, `e2e`) and keep marker usage accurate.

## Commit & Pull Request Guidelines
- Follow the existing Conventional Commit style from history: `feat(scope): ...`, `docs(scope): ...`, `fix(scope): ...`.
- Keep commits focused and atomic; include tests with functional changes.
- PRs should include:
  - clear summary and impacted paths
  - linked issue/task ID
  - test evidence (commands run + results)
  - UI screenshots/video for frontend behavior changes
- Run `pre-commit run --all-files` before opening a PR; secret and `.env` checks are enforced.

## Markdown Document Placement Rules
- Do not create new ad-hoc `.md` files in repo root unless they are canonical entry docs.
- Root is reserved for: `README.md`, `AGENTS.md`, `CLAUDE*.md`, `FEATURES.md`, `INVESTOR.md`, `TODO.md`, `TODOdone.md`, and approved top-level compliance/sign-off docs.
- Place phase execution artifacts (`PLAN`, `SUMMARY`, status snapshots, debug logs, rollout notes) in `.planning/phases/<phase>/` or `.planning/archive/`.
- Place durable product/system documentation in `docs/` under the correct domain folder (architecture, api, features, integrations, security, operations, testing, development).
- Place one-off validation/test run notes in `.planning/archive/` unless explicitly requested as durable docs.
- If unsure where a new document belongs, default to `.planning/archive/` and add links from the relevant `docs/README.md` or phase README.
