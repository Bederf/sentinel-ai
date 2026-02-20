---
title: "Testing patterns, coverage, and debugging"
type: "guide"
status: "approved"
version: "1.0.0"
created: "2026-02-18"
updated: "2026-02-18"
tags: ["testing", "pytest", "vitest", "coverage", "debugging", "e2e"]
related: ["../01-setup/local-development-setup.md", "../02-architecture/system-overview.md"]
domain: "general"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 45
---

# Testing patterns, coverage, and debugging

Comprehensive testing guide covering unit tests, integration tests, end-to-end workflows, debugging, and coverage requirements for both backend (pytest) and frontend (vitest).

## Quick reference

**Before committing (REQUIRED):**
```bash
# Security tests (mandatory)
pytest -m security tests/api/ -v

# All tests with coverage
pytest tests/ --cov=app
npm run test:run  # 80%+ coverage required

# No timeouts >30s
pytest tests/ --durations=10

# Frontend checks
npm run lint
npm run build
```

## Backend testing (pytest)

### Test markers

Run tests by category using pytest markers:

```bash
# By type
pytest -m unit             # Fast, isolated tests (<100ms each)
pytest -m integration      # With dependencies (DB, services)
pytest -m security        # Security validation (REQUIRED before commit)
pytest -m slow            # Long-running tests (>5 seconds)
pytest -m e2e             # End-to-end workflows

# By file or pattern
pytest tests/api/test_devices.py -v                # Single file
pytest tests/api/test_devices.py::test_create -v   # Single test
pytest tests/ -k "not slow" -v                     # Exclude pattern

# Performance analysis
pytest tests/ --durations=10   # Top 10 slowest tests
pytest tests/api/ --durations=1 -x  # Stop on first failure
```

### Marker configuration

Markers are defined in `backend/pytest.ini`:

```ini
[pytest]
markers =
    unit: Unit tests (isolated, no external dependencies)
    integration: Integration tests (with DB, services)
    security: Security validation tests (REQUIRED before commit)
    slow: Long-running tests (>5 seconds)
    e2e: End-to-end workflows

asyncio_mode = auto
testpaths = tests
python_files = test_*.py
timeout = 30
```

### Async test pattern

All async functions require `@pytest.mark.asyncio`:

```python
# ✅ CORRECT - pytest handles async
@pytest.mark.asyncio
async def test_get_devices():
    repo = EquipmentRepository()
    devices = await repo.list()
    assert len(devices) >= 0

# ✅ CORRECT - Mark slow tests
@pytest.mark.slow
@pytest.mark.asyncio
async def test_24_hour_simulation():
    """Simulation takes 30+ seconds"""
    result = await simulate_24_hours()
    assert result.status == "complete"

# ❌ WRONG - Missing marker
async def test_without_marker():
    # Will fail: "RuntimeError: Event loop is closed"
    pass
```

### Mocking pattern

Mock external dependencies (Supabase, APIs, services):

```python
from unittest.mock import AsyncMock, patch
import pytest

@pytest.mark.asyncio
async def test_alert_creation():
    """Test alert creation with mocked Supabase"""

    with patch('app.database.repositories.alert_repository.supabase') as mock_supabase:
        # Setup mock response
        mock_response = AsyncMock()
        mock_response.data = {
            "id": "alert-123",
            "severity": 75,
            "equipment_id": "eq-123"
        }
        mock_supabase.table().insert().execute = AsyncMock(return_value=mock_response)

        # Test code
        repo = AlertRepository()
        alert = await repo.create(
            equipment_id="eq-123",
            severity=75,
            message="Test alert"
        )

        # Verify
        assert alert["id"] == "alert-123"
        assert alert["severity"] == 75

        # Verify mock was called
        mock_supabase.table.assert_called_once_with("alerts")
```

### Test fixtures

Shared test setup and data:

```python
# backend/tests/conftest.py

@pytest.fixture
async def mock_equipment():
    """Fixture: Mock equipment data"""
    return {
        "id": "eq-123",
        "code": "S002-VAV-101",
        "equipment_type": "VAV",
        "health_score": 85,
        "status": "healthy"
    }

@pytest.fixture
async def test_client():
    """Fixture: FastAPI test client"""
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)

@pytest.fixture
def mock_supabase():
    """Fixture: Mocked Supabase client"""
    with patch('app.database.supabase_client.get_supabase_client') as mock:
        yield mock
```

### Coverage requirements

```bash
# Generate coverage report
pytest --cov=app tests/ --cov-report=html
open htmlcov/index.html  # View in browser

# Check specific file
pytest --cov=app.services.device_abstraction tests/ --cov-report=term-missing

# Coverage thresholds
pytest --cov=app --cov-fail-under=80 tests/
```

**Coverage thresholds (enforced in CI):**
- Lines: 80% minimum
- Functions: 80% minimum
- Statements: 80% minimum

**Excluded from coverage:**
- Type definitions (`.d.ts`, type stubs)
- Migrations and fixtures
- Generated code

## Frontend testing (vitest)

### Test pattern

Use React Testing Library for UI testing:

```typescript
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MyComponent } from '../MyComponent'

describe('MyComponent', () => {
  it('displays device name', async () => {
    render(<MyComponent deviceId="123" />)

    // Wait for async data to load
    await waitFor(() => {
      expect(screen.getByText(/my device/i)).toBeInTheDocument()
    })
  })

  it('handles click events', async () => {
    const handleClick = vi.fn()
    render(<MyComponent onClick={handleClick} />)

    // Simulate user interaction
    await userEvent.click(screen.getByRole('button'))

    // Verify callback was called
    expect(handleClick).toHaveBeenCalledOnce()
  })

  it('displays error state', async () => {
    render(<MyComponent deviceId="invalid" />)

    await waitFor(() => {
      expect(screen.getByText(/error/i)).toBeInTheDocument()
    })
  })
})
```

### Running tests

```bash
# Single run (CI mode) - enforces 80% coverage
npm run test:run

# Watch mode (auto-rerun on file changes)
npm run test:watch

# Interactive UI (recommended for development)
npm run test:ui

# Coverage report
npm run test:coverage
open coverage/index.html
```

### Coverage thresholds

| Metric | Threshold |
|--------|-----------|
| Lines | 80% |
| Functions | 80% |
| Statements | 80% |
| Branches | 75% |

**Excluded:**
- Test files (`__tests__/`, `*.test.tsx`)
- Mock files
- Type definitions

## Test organization

### Backend structure

```
backend/tests/
├── api/                      # API endpoint tests
│   ├── test_devices.py
│   ├── test_alerts.py
│   ├── test_approvals.py
│   └── test_recommendations.py
├── services/                 # Business logic tests
│   ├── test_device_abstraction.py
│   ├── test_approval_service.py
│   ├── test_energy_cost_service.py
│   └── test_thermal_simulation_engine.py
├── database/                 # Repository tests
│   ├── test_equipment_repository.py
│   ├── test_alert_repository.py
│   └── test_work_order_repository.py
├── ml/                       # ML/AI tests
│   ├── test_model_inference.py
│   └── test_explanations.py
├── conftest.py               # Shared fixtures
└── fixtures/                 # Test data
    ├── equipment.json
    ├── alerts.json
    └── recommendations.json
```

### Frontend structure

```
frontend/src/
├── components/
│   ├── __tests__/
│   │   ├── Dashboard.test.tsx
│   │   ├── DeviceCard.test.tsx
│   │   ├── AlertPanel.test.tsx
│   │   └── ...
│   └── ...
├── hooks/
│   ├── __tests__/
│   │   ├── useDevices.test.tsx
│   │   ├── useAlerts.test.tsx
│   │   └── ...
│   └── ...
├── pages/
│   ├── __tests__/
│   │   ├── DashboardPage.test.tsx
│   │   └── ...
│   └── ...
└── test-utils/
    ├── setup.ts              # Auto-loaded by vitest
    ├── mocks.ts              # Common mocks
    └── fixtures.ts           # Test data
```

## End-to-end workflows

### Setting up E2E tests

Verify complete workflows across frontend → backend → database:

```bash
# Terminal 1: Backend
./start-backend.sh

# Terminal 2: Frontend
./start-frontend.sh

# Terminal 3: Run E2E tests
npm run test:e2e
```

### E2E test pattern

```typescript
import { test, expect } from '@playwright/test'

test('complete device control workflow', async ({ page }) => {
  // Navigate to application
  await page.goto('http://localhost:9096')

  // Login
  await page.fill('input[name="email"]', 'test@example.com')
  await page.click('button:has-text("Login")')

  // Wait for dashboard
  await page.waitForSelector('[data-testid="device-card"]')

  // Select device
  const deviceCard = page.locator('[data-testid="device-card"]').first()
  await deviceCard.click()

  // Verify device details loaded
  await expect(page.locator('h1')).toContainText('Device Details')

  // Perform control action
  await page.click('button:has-text("Set Setpoint")')
  await page.fill('input[type="number"]', '22')
  await page.click('button:has-text("Confirm")')

  // Verify success message
  await expect(page.locator('[role="alert"]')).toContainText('Setpoint updated')

  // Verify in backend via API
  const response = await page.evaluate(() =>
    fetch('/api/devices/device-123')
      .then(r => r.json())
  )
  expect(response.setpoint).toBe(22)
})
```

## Pre-commit requirements

**MUST pass before committing:**

```bash
# 1. Security tests (mandatory - gates all commits)
cd backend && pytest -m security tests/api/ -v

# 2. Unit tests
pytest -m unit tests/ -v

# 3. Performance check (no tests >30s)
pytest tests/ --durations=10
# Last item should show time <30s

# 4. Frontend checks
cd ../frontend
npm run lint         # ESLint
npm run test:run     # vitest (80%+ coverage)
npm run build        # TypeScript + bundler

# 5. Git pre-commit hook
git commit -m "description"
# Hook runs automatically
```

**If pre-commit hook fails:**
```bash
# View details
pre-commit run --all-files -v

# Fix issues (hooks auto-fix some)
# Then commit again
git add .
git commit -m "description"
```

## Debugging tests

### Backend debugging

```bash
# Run single test with full output
pytest tests/api/test_devices.py::test_create -v -s

# Stop on first failure
pytest tests/ -x

# Show print statements
pytest tests/ -s

# Verbose with full tracebacks
pytest tests/ -vv

# Drop to debugger on failure
pytest tests/ --pdb

# Show slowest 10 tests
pytest tests/ --durations=10

# Run with verbose logging
pytest tests/ -v --log-cli-level=DEBUG
```

### Frontend debugging

```bash
# Run tests in UI (visual debugging)
npm run test:ui

# Watch specific file
npm run test:watch -- MyComponent.test.tsx

# Show coverage gaps
npm run test:coverage

# Run with debugging
npm run test:watch -- --inspect-brk

# Browser DevTools
npm run test:watch
# DevTools opens in browser, set breakpoints
```

## Performance baselines

**Expected test duration:**

| Test Type | Typical Time | Timeout |
|-----------|-------------|---------|
| Unit test | <100ms | 5s |
| Integration test | 100ms-1s | 30s |
| API endpoint | 50-200ms | 10s |
| Database query | 20-100ms | 5s |
| Simulation (24h) | 5-60s | 300s |
| E2E test | 5-30s | 60s |

**Enforced: 30 seconds per test** (configured in pytest.ini)

Tests exceeding timeout will fail and block commits.

## Test checklist

**Before committing, verify:**

- [ ] `pytest -m security tests/api/ -v` passes (gates all commits)
- [ ] `pytest tests/ --durations=10` shows no tests >30s
- [ ] `pytest tests/ --cov=app --cov-fail-under=80` passes
- [ ] `npm run lint` passes with no errors
- [ ] `npm run test:run` passes with 80%+ coverage
- [ ] `npm run build` compiles without errors
- [ ] No `.skip()` or `@pytest.mark.skip` in tests (use `@pytest.mark.xfail` for known failures)
- [ ] All mocked API calls verified with `.assert_called()`
- [ ] Error cases tested (not just happy path)
- [ ] Async tests properly marked with `@pytest.mark.asyncio`

## Common issues and fixes

### Backend

**"Event loop is closed" error:**
- Add `@pytest.mark.asyncio` to async test functions
- Ensure `asyncio_mode = auto` in pytest.ini

**"Timeout after 30s":**
- Test is too slow or has infinite loop
- Add `@pytest.mark.slow` if legitimately >5s
- Consider breaking into smaller tests
- Increase timeout only if necessary (discuss with team)

**"Mock not being called":**
- Verify patch path is correct (use full module path)
- Ensure test actually triggers the mock
- Use `print()` or `.assert_called()` to debug

### Frontend

**"Module not found" errors:**
- Clear TypeScript cache: `rm -rf node_modules/.tsc*`
- Clear Vite cache: `rm -rf node_modules/.vite`
- Run `npm ci && npm run build`

**"Cannot find element" in test:**
- Add `waitFor()` for async component renders
- Verify selector is correct (use `data-testid` attributes)
- Check component actually renders (add debug output)

**Coverage below 80%:**
- Run `npm run test:coverage` and view report
- Add tests for uncovered lines
- Focus on logic branches, not just happy path

## Resources

- **Jest/Vitest documentation**: https://vitest.dev/
- **React Testing Library**: https://testing-library.com/react
- **pytest documentation**: https://docs.pytest.org/
- **Playwright**: https://playwright.dev/

## Related documentation

- [Local development setup](../01-setup/local-development-setup.md)
- [System overview and architecture](../02-architecture/system-overview.md)
- [API reference](../03-api-reference/rest-api-endpoints.md)
