---
title: "Testing Strategy Guide"
type: "guide"
status: "approved"
version: "1.0.0"
created: "2026-01-30"
updated: "2026-01-30"
author: "Sentinel Development Team"
tags: ["testing", "strategy", "pytest", "vitest"]
related: ["e2e-testing.md", "test-data.md", "../12-development/tool-use-best-practices.md"]
domain: "general"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 15
---

# Testing Guide for BMS Intelligence

## Overview

The BMS Intelligence system uses a comprehensive testing strategy with unit tests, integration tests, and end-to-end (E2E) tests across both frontend and backend.

## Test Structure

```
bms-intelligence/
├── frontend/
│   ├── src/
│   │   ├── __tests__/          # Unit and integration tests
│   │   ├── components/
│   │   │   └── __tests__/      # Component unit tests
│   │   └── test-utils/         # Test utilities and factories
│   └── vitest.config.ts        # Vitest configuration
├── backend/
│   ├── tests/
│   │   ├── api/                # API endpoint tests
│   │   ├── services/           # Service unit tests
│   │   ├── integration/        # Integration tests
│   │   ├── performance/        # Performance tests
│   │   └── security/          # Security tests
│   └── pytest.ini              # Pytest configuration
└── e2e/
    ├── tests/                  # E2E test scenarios
    └── playwright.config.ts    # Playwright configuration
```

## Running Tests

### Frontend Tests

```bash
cd frontend

# Run all tests
npm test

# Run tests in watch mode
npm run test:watch

# Run tests with UI
npm run test:ui

# Run tests and generate coverage
npm run test:coverage
```

### Backend Tests

```bash
cd backend

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

### E2E Tests

```bash
cd e2e

# Run all E2E tests
npm test

# Run with UI
npm run test:ui

# Run in debug mode
npm run test:debug
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

## CI/CD Integration

Tests run automatically on:
- Pull requests
- Pushes to main/develop branches

See `.github/workflows/test.yml` for configuration.

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

### Coverage not updating

- Ensure tests are actually running
- Check coverage configuration
- Verify file paths are correct

### E2E tests flaky

- Add explicit waits instead of fixed timeouts
- Check for race conditions
- Verify test data is consistent
