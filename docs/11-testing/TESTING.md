---
title: "Testing Strategy Guide"
type: "guide"
status: "approved"
version: "1.1.0"
created: "2026-01-30"
updated: "2026-02-26"
author: "Sentinel Development Team"
tags: ["testing", "strategy", "pytest", "vitest", "playwright", "k6"]
related: ["E2E_GUIDE.md", "TEST_DATA.md", "../../k6/README.md"]
domain: "general"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 15
---

# Testing Guide for BMS Intelligence

## Overview

The BMS Intelligence platform uses multiple test layers:
- `pytest` for backend and Python domain tests
- `vitest` for frontend unit/integration tests
- `playwright` for browser E2E flows
- `k6` for API/load testing
- module-specific test suites (for example, `runner/tests`)

## Test Structure

```
bms-intelligence/
├── frontend/
│   ├── src/**/__tests__/       # Frontend unit/integration tests
│   └── vitest.config.ts        # Vitest configuration
├── backend/
│   ├── tests/                  # Backend test suite
│   └── pytest.ini              # Pytest configuration
├── tests/                      # Repo-level Python tests
└── e2e/
    ├── tests/                  # E2E test scenarios
    └── playwright.config.ts    # Playwright configuration
├── k6/
│   ├── scenarios/              # Load test scripts
│   └── README.md               # Load test guide
└── runner/tests/               # Runner module tests
```

## Running Tests

### Frontend Tests

```bash
cd /opt/bms-intelligence/frontend

# Run all tests
npm run test:run

# Run tests in watch mode
npm run test:watch

# Run tests with UI
npm run test:ui

# Run tests and generate coverage
npm run test:coverage
```

### Backend Tests

```bash
cd /opt/bms-intelligence/backend

# Run all tests
pytest

# Run specific test file
pytest tests/services/test_device_abstraction.py

# Run with coverage
pytest --cov=app --cov-report=html

# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration
```

### Repo-level Python Tests

```bash
cd /opt/bms-intelligence

# Runs tests from root pytest.ini testpaths:
# - tests/
# - backend/tests/
pytest
```

### E2E Tests

```bash
cd /opt/bms-intelligence/e2e

# Run all E2E tests
npm test

# Run with UI
npm run test:ui

# Run in debug mode
npm run test:debug
```

### Load Tests (k6)

```bash
cd /opt/bms-intelligence/k6

# Smoke/API load test
k6 run scenarios/api-smoke-test.js

# Device control load
k6 run scenarios/device-control.js

# Hybrid chat load
k6 run scenarios/chat-load-test.js

# Mixed traffic suite
k6 run scenarios/full-suite.js
```

Optional environment variables:
- `API_URL` (default `http://localhost:9095`)
- `AUTH_TOKEN` for authenticated environments

Example:
```bash
API_URL=http://localhost:9095 AUTH_TOKEN=your_token_here k6 run scenarios/api-smoke-test.js
```

### Runner Module Tests

```bash
cd /opt/bms-intelligence/runner
pytest
```

## Writing Tests

### Frontend Component Tests

Use React Testing Library and Vitest:

```typescript
import { describe, it, expect } from 'vitest';
import { render, screen } from '../../test-utils';
import MyComponent from '../MyComponent';

describe('MyComponent', () => {
  it('should render correctly', () => {
    render(<MyComponent />);
    expect(screen.getByText('Hello')).toBeInTheDocument();
  });
});
```

### Backend Service Tests

Use pytest with async support:

```python
import pytest
from app.services.my_service import MyService

@pytest.mark.unit
class TestMyService:
    @pytest.mark.asyncio
    async def test_service_method(self):
        service = MyService()
        result = await service.do_something()
        assert result is not None
```

### Integration Tests

Test complete flows across multiple components:

```python
@pytest.mark.integration
def test_complete_flow(test_client):
    # Test full workflow
    response = test_client.get("/api/devices")
    assert response.status_code == 200
```

## Test Data Factories

Use factories to create consistent test data:

### Frontend

```typescript
import { createMockDevice } from '../../test-utils/factories';

const device = createMockDevice({
  id: 'device-001',
  name: 'Test Device',
});
```

### Backend

```python
from tests.factories import DeviceFactory

device = DeviceFactory.create(
    device_id='device-001',
    name='Test Device'
)
```

## Coverage Goals

- **Unit Tests**: 80%+ coverage
- **Integration Tests**: All critical paths covered
- **E2E Tests**: All user workflows covered
- **Load Tests**: SLA thresholds in each k6 scenario

## CI/CD Integration

Tests run automatically on:
- Pull requests
- Pushes to main/develop branches

See `.github/workflows/test.yml` for configuration.

Current CI workflow covers:
- frontend lint/typecheck/unit/coverage
- backend pytest + coverage
- Playwright E2E

`k6` is currently run manually unless added to a dedicated workflow.

## Best Practices

1. **Write tests first** (TDD) for new features
2. **Keep tests isolated** - each test should be independent
3. **Use descriptive test names** - "should do X when Y"
4. **Mock external dependencies** - API calls, file system, etc.
5. **Test edge cases** - empty states, errors, boundaries
6. **Keep tests fast** - unit tests should run in milliseconds
7. **Maintain test data** - use factories, not hardcoded data

## Troubleshooting

### Tests failing locally but passing in CI

- Check environment variables
- Verify dependencies are installed
- Check for timing issues (use `waitFor`)

### k6 scenarios failing with 401/403

- Provide `AUTH_TOKEN` if auth is enforced
- Confirm backend is reachable at `API_URL`

### k6 scenarios failing due to stale device IDs

- Current scenarios discover devices dynamically from `/api/devices`
- If `/api/devices` returns empty, seed or load demo/mock equipment first

### Coverage not updating

- Ensure tests are actually running
- Check coverage configuration
- Verify file paths are correct

### E2E tests flaky

- Add explicit waits instead of fixed timeouts
- Check for race conditions
- Verify test data is consistent
