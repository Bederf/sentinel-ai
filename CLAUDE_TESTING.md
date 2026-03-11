# CLAUDE_TESTING.md

Testing patterns, markers, coverage requirements, and debugging.

## Backend Testing (pytest)

### Test Markers

```bash
# By category
pytest -m unit             # Unit tests (fast, isolated)
pytest -m integration      # Integration tests (with dependencies)
pytest -m security        # Security validation (REQUIRED before commit)
pytest -m slow            # Long-running tests (run separately)
pytest -m e2e             # End-to-end workflows

# By file/pattern
pytest tests/api/test_devices.py -v              # Single file
pytest tests/api/test_devices.py::test_create -v # Single test
pytest tests/ -k "not slow" -v                   # Exclude slow tests

# Performance
pytest tests/ --durations=10                     # Top 10 slowest tests
pytest tests/api/ --durations=1 -x              # Stop on first failure
```

### Test Markers (pytest.ini)

```ini
[pytest]
markers =
    unit: Unit tests (isolated, no external dependencies)
    integration: Integration tests (with DB, services)
    security: Security validation tests (REQUIRED before commit)
    slow: Long-running tests (>5 seconds)
    e2e: End-to-end workflows
```

### Async Test Pattern

```python
# ✅ CORRECT - pytest handles async
@pytest.mark.asyncio
async def test_get_devices():
    repo = EquipmentRepository()
    devices = await repo.list()
    assert len(devices) >= 0

# ✅ CORRECT - Mark if >5 seconds
@pytest.mark.slow
@pytest.mark.asyncio
async def test_long_simulation():
    # Simulation takes 30+ seconds
    result = await simulate_24_hours()
    assert result.status == "complete"
```

### Mocking Pattern

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_alert_creation():
    # Mock the Supabase response
    with patch('app.database.repositories.alert_repository.supabase') as mock_supabase:
        mock_response = AsyncMock()
        mock_response.data = {"id": "alert-123", "severity": 75}
        mock_supabase.table().insert().execute = AsyncMock(return_value=mock_response)

        repo = AlertRepository()
        alert = await repo.create(equipment_id="eq-123", severity=75)

        assert alert["id"] == "alert-123"
        assert alert["severity"] == 75
```

### Test Coverage

```bash
# Generate coverage report
pytest --cov=app tests/ --cov-report=html

# View report
open htmlcov/index.html

# Check specific file
pytest --cov=app.services.device_abstraction tests/ --cov-report=term-missing
```

**Coverage Thresholds:**
- Lines: 80%
- Functions: 80%
- Statements: 80%

## Frontend Testing (vitest)

### Test Pattern

```typescript
import { render, screen, waitFor } from '@testing-library/react'
import { MyComponent } from '../MyComponent'

describe('MyComponent', () => {
  it('displays device name', async () => {
    render(<MyComponent deviceId="123" />)

    // Wait for async data to load
    await waitFor(() => {
      expect(screen.getByText(/my device/i)).toBeInTheDocument()
    })
  })

  it('handles error state', async () => {
    // Mock API to return error
    render(<MyComponent deviceId="invalid" />)

    await waitFor(() => {
      expect(screen.getByText(/error/i)).toBeInTheDocument()
    })
  })
})
```

### Running Tests

```bash
# Single run (CI mode) - enforces 80% coverage
npm run test:run

# Watch mode (auto-rerun on changes)
npm run test:watch

# Interactive UI (recommended for development)
npm run test:ui

# Coverage report
npm run test:coverage
open coverage/index.html
```

### Coverage Thresholds

| Metric | Threshold |
|--------|-----------|
| Lines | 80% |
| Functions | 80% |
| Statements | 80% |
| Branches | 75% |

**Excluded from coverage:**
- Test files (`__tests__/`, `*.test.tsx`)
- Mocks
- Type definitions (`.d.ts`)

## Test Organization

### Backend Structure

```
backend/tests/
├── api/                    # API endpoint tests
│   ├── test_devices.py
│   ├── test_alerts.py
│   └── ...
├── services/               # Service logic tests
│   ├── test_device_abstraction.py
│   ├── test_approval_service.py
│   └── ...
├── database/               # Repository tests
│   ├── test_equipment_repository.py
│   └── ...
├── conftest.py             # Shared fixtures
└── fixtures/               # Test data
    ├── equipment.json
    └── alerts.json
```

### Frontend Structure

```
frontend/src/
├── components/
│   ├── __tests__/
│   │   ├── Dashboard.test.tsx
│   │   ├── Recommendations.test.tsx
│   │   └── ...
│   └── ...
├── hooks/
│   ├── __tests__/
│   │   ├── useDevices.test.tsx
│   │   └── ...
│   └── ...
└── test-utils/
    ├── setup.ts           # Auto-loaded by vitest
    └── mocks.ts
```

## BOLA (Object-Level Authorization) Tests

Location: `tests/api/test_bola_authorization.py` — **57 tests**

Validates that `require_site_access()` and `require_equipment_access()` block cross-site access.
Uses two mock users: an owner (admin, site-002) and an attacker (operator, site-003 only).
Covers GET/POST/PATCH/DELETE across 17 API files (~158 protected endpoints).

```bash
# Run BOLA tests only
pytest tests/api/test_bola_authorization.py -v

# All security tests (includes BOLA + compliance)
pytest -m security tests/api/ -v
```

See `docs/09-security/bola-scanner-and-object-level-authorization.md` for full details.

## Pre-Commit Tests (REQUIRED)

```bash
# Run these BEFORE git push:

# 1. Security tests (REQUIRED — includes 57 BOLA + 2 compliance tests)
pytest -m security tests/api/ -v

# 2. Unit tests
pytest -m unit tests/ -v

# 3. Check for timeouts (>30s)
pytest tests/ --durations=10

# 4. Frontend checks
npm run lint
npm run test:run              # Must pass 80% coverage
npm run build                 # Must compile without errors
```

## Common Test Fixtures

### Backend Fixtures

```python
# backend/tests/conftest.py

@pytest.fixture
async def mock_equipment():
    """Mock equipment for testing"""
    return {
        "id": "eq-123",
        "code": "S002-VAV-101",
        "equipment_type": "VAV",
        "health_score": 85,
        "status": "healthy"
    }

@pytest.fixture
async def test_client():
    """FastAPI test client"""
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)

@pytest.fixture
async def mock_supabase():
    """Mock Supabase instance"""
    with patch('app.database.supabase') as mock:
        yield mock
```

### Frontend Test Utilities

```typescript
// frontend/src/test-utils/setup.ts

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'

export function renderWithProviders(component: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      {component}
    </QueryClientProvider>
  )
}
```

## Debugging Tests

### Backend

```bash
# Run single test with output
pytest tests/api/test_devices.py::test_create -v -s

# Stop on first failure
pytest tests/ -x

# Show print statements
pytest tests/ -s

# Verbose output with full tracebacks
pytest tests/ -vv

# Drop to debugger on failure
pytest tests/ --pdb

# Show slowest N tests
pytest tests/ --durations=10
```

### Frontend

```bash
# Run tests with debugging
npm run test:watch -- --inspect-brk

# Run in UI (easiest for visual debugging)
npm run test:ui

# Show coverage gaps
npm run test:coverage

# Watch specific file
npm run test:watch -- MyComponent.test.tsx
```

## Performance Baselines

| Test Type | Typical Time | Timeout |
|-----------|-------------|---------|
| Unit | <100ms | 5s |
| Integration | 100ms-1s | 30s |
| API endpoint | 50-200ms | 10s |
| Database query | 20-100ms | 5s |
| Simulation (24h) | 5-60s | 300s |

**Enforce timeout: 30 seconds per test** (configured in pytest.ini)

## Test Checklist

Before committing:

- [ ] `pytest -m security tests/api/ -v` passes
- [ ] `pytest tests/ --durations=10` shows no tests >30s
- [ ] `npm run lint` passes
- [ ] `npm run test:run` passes with 80%+ coverage
- [ ] `npm run build` compiles without errors
- [ ] No `@pytest.mark.skip` or `.skip()` in frontend tests
- [ ] All mocked API calls verified
- [ ] Error cases tested (not just happy path)

---

See `CLAUDE_QUICK_START.md` for quick test commands.
