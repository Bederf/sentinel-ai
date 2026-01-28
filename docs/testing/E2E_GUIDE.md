# E2E Testing Guide

## Overview

End-to-end (E2E) tests verify complete user workflows using Playwright.

## Setup

```bash
cd e2e
npm install
npx playwright install chromium
```

## Running E2E Tests

```bash
# Run all tests
npm test

# Run with UI
npm run test:ui

# Run in debug mode
npm run test:debug

# Run specific test file
npx playwright test tests/dashboard.spec.ts
```

## Writing E2E Tests

### Basic Test Structure

```typescript
import { test, expect } from '@playwright/test';

test.describe('Feature Name', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should do something', async ({ page }) => {
    // Test steps
    await expect(page.locator('text=Hello')).toBeVisible();
  });
});
```

## Test Scenarios

### Dashboard Flow

```typescript
test('should load dashboard and display sites', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('text=Risk Dashboard')).toBeVisible();
  await expect(page.locator('[class*="SiteCard"]').first()).toBeVisible();
});
```

### Device Control Flow

```typescript
test('should control device', async ({ page }) => {
  await page.goto('/control');
  await page.click('[data-testid="device-select"]');
  await page.fill('[data-testid="setpoint-input"]', '22');
  await page.click('[data-testid="apply-button"]');
  await expect(page.locator('text=Success')).toBeVisible();
});
```

## Best Practices

1. **Use data-testid** - More reliable than CSS selectors
2. **Wait for elements** - Use `waitFor` instead of fixed timeouts
3. **Test user workflows** - Not implementation details
4. **Keep tests independent** - Each test should work standalone
5. **Use page objects** - For complex pages (future improvement)

## Debugging

### Visual Debugging

```bash
npm run test:ui
```

### Debug Mode

```bash
npm run test:debug
```

### Screenshots

Screenshots are automatically captured on failure in `test-results/`.

## CI/CD Integration

E2E tests run automatically on:
- Pull requests (if backend/frontend tests pass)
- Merges to main branch

See `.github/workflows/test.yml` for configuration.
