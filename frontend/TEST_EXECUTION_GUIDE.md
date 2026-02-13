# Frontend Test Execution Guide

Complete guide to running, debugging, and optimizing frontend tests for BMS Intelligence Platform.

## Quick Reference

```bash
# Run all tests once
npm run test:run

# Watch mode (re-run on file changes)
npm run test:watch

# Coverage report
npm run test:coverage

# Run specific test file
npm run test:run -- Dashboard.test.tsx

# Run tests matching pattern
npm run test:run -- --grep "should batch"

# Debug mode (breaks on debugger)
node --inspect-brk ./node_modules/vitest/vitest.mjs run
```

---

## Test Execution Modes

### 1. Single Run (`npm run test:run`)

**Use for:** CI/CD, pre-commit validation, performance testing

```bash
npm run test:run

# Output
PASS  src/components/__tests__/Dashboard.test.tsx
PASS  src/hooks/__tests__/useDeviceStatus.test.ts
PASS  src/lib/api/__tests__/batchAggregator.test.ts

Test Files  30 passed (30)
     Tests  641 passed (641)
  Duration  12.34s
```

**Features:**
- Runs all tests once
- Exits with code 0 (success) or 1 (failure)
- Shows summary with timing
- Ideal for CI/CD pipelines

**Performance:**
- Full suite: ~12-15 seconds
- ~50-60ms per test file
- Total 641 tests

---

### 2. Watch Mode (`npm run test:watch`)

**Use for:** Development, TDD, iterative testing

```bash
npm run test:watch

# Interactive menu
> Dashboard.test.tsx
  PASS  8 passed

› Press 'a' to run all
› Press 'p' to filter by filename
› Press 't' to filter by test name
› Press 'q' to quit
```

**Features:**
- Auto-reruns on file changes
- Interactive filtering
- Fast feedback loop
- Shows only changed tests

**Keyboard Shortcuts:**
- `a` - Run all tests
- `p` - Filter by filename pattern
- `t` - Filter by test name
- `c` - Clear filters
- `q` - Quit

**Usage Pattern:**
1. Start: `npm run test:watch`
2. Edit component/test
3. Auto-runs affected tests (~500ms)
4. See pass/fail immediately
5. Filter to specific test while fixing

---

### 3. UI Mode (`npm run test:ui`)

**Use for:** Visual test browser, exploring test structure

```bash
npm run test:ui

# Opens http://localhost:51204 in browser
# Shows interactive test tree + results
```

**Features:**
- Browser-based test runner
- Visual test tree
- Search/filter tests
- See test output in real-time
- Debug mode access

**Visual Elements:**
- Green checkmark: Passing test
- Red X: Failing test
- Yellow dash: Skipped test
- Spinner: Running test

---

### 4. Coverage Report (`npm run test:coverage`)

**Use for:** Assessing test completeness, finding untested code

```bash
npm run test:coverage

# Generates: coverage/index.html
# Shows line/branch/function coverage
```

**Output:**
```
File              Lines    Statements  Functions  Branches
Dashboard.tsx     89.2%    88.5%       90.1%      85.3%
useDeviceStatus   94.7%    93.2%       95.4%      92.1%
batchAggregator   96.8%    96.1%       97.2%      94.9%
```

**View Report:**
```bash
open coverage/index.html  # macOS
xdg-open coverage/index.html  # Linux
start coverage/index.html  # Windows
```

**Target Coverage:**
- Lines: 80%+ (critical)
- Functions: 80%+
- Branches: 75%+
- Statements: 80%+

---

## Running Specific Tests

### By File Name

```bash
# Exact match
npm run test:run -- Dashboard.test.tsx

# Partial match
npm run test:run -- Dashboard

# Multiple files
npm run test:run -- "Dashboard|Alert"
```

### By Test Pattern

```bash
# Test name contains pattern
npm run test:run -- --grep "should batch"

# Multiple patterns
npm run test:run -- --grep "should (batch|deduplicate)"
```

### By Directory

```bash
# All tests in components/
npm run test:run -- src/components/

# Specific subdirectory
npm run test:run -- src/hooks/__tests__/
```

### By Test Suite

```bash
# Single describe block
npm run test:run -- --grep "Dashboard - Data Fetching"

# Skip specific tests
npm run test:run -- --grep "should NOT batch" --invert
```

---

## Debugging Tests

### 1. Console Logs

```typescript
it('should batch requests', async () => {
  const { result } = renderHook(() => useMyHook(), { wrapper });
  
  console.log('After render:', result.current);
  console.log('API calls:', mockApi.mock.calls);
  
  await waitFor(() => {
    console.log('In waitFor:', result.current.data);
    expect(result.current.data).toBeDefined();
  });
});
```

**Run with logs:**
```bash
npm run test:run -- Dashboard.test.tsx --reporter=verbose
```

### 2. Screen Debug

```typescript
import { screen } from '@testing-library/react';

it('should render', () => {
  render(<MyComponent />);
  
  screen.debug();  // Prints DOM to console
  
  // Output:
  // <div>
  //   <button>Click me</button>
  // </div>
});
```

### 3. Debugger Breakpoint

```typescript
it('should work', async () => {
  debugger;  // ← Execution stops here
  const { result } = renderHook(() => useMyHook(), { wrapper });
  // Continue execution in DevTools
});
```

**Run with debugger:**
```bash
node --inspect-brk ./node_modules/vitest/vitest.mjs run Dashboard.test.tsx
# Open: chrome://inspect
# Click: "inspect" next to vitest process
```

### 4. Focused Tests

```typescript
// Run only this test
it.only('should batch requests', async () => {
  // ... test code
});

// Run all in this suite
describe.only('Batch Aggregator', () => {
  // ... tests
});

// Skip specific test
it.skip('should batch requests', async () => {
  // ... not run
});
```

---

## Performance Optimization

### 1. Test Timeout Issues

**Problem:** "Test timeout - async operation did not complete"

**Solution:**

```typescript
// Increase timeout for specific test
it('should do slow thing', async () => {
  // test code
}, 10000);  // 10 second timeout

// Or globally in vitest.config.ts
test: {
  testTimeout: 15000,  // 15 seconds
}
```

### 2. Memory Issues

**Problem:** "JavaScript heap out of memory"

**Solution:**

```bash
# Run with more memory
node --max-old-space-size=4096 ./node_modules/vitest/vitest.mjs run

# Or split tests
npm run test:run -- src/components/
npm run test:run -- src/hooks/
```

### 3. Slow Tests

**Identify slow tests:**

```bash
npm run test:run -- --reporter=verbose
```

**Look for tests >1000ms:**
```
SLOW  Dashboard.test.tsx > Dashboard - Data Fetching > should fetch data  1245ms
```

**Optimize:**
- Remove unnecessary mocks
- Use controlled Promises (not fakeTimers)
- Cache test data
- Skip non-critical assertions

### 4. Reduce Rebuild Time

**Watch mode too slow?**

```bash
# Skip type checking (faster)
npm run test:watch -- --no-coverage

# Run specific test file only
npm run test:watch -- Dashboard.test.tsx

# Clear cache
rm -rf node_modules/.vitest
npm run test:watch
```

---

## Common Issues & Fixes

### "Module has no exported member"

```typescript
// ❌ Wrong
import { createMockDevice } from '@/test-utils/factories';

// ✅ Right
import { createMockDevice } from '@/test-utils';
```

**Fix:** Always import from barrel export (`@/test-utils/index.tsx`)

---

### "Cannot read property 'getQueryData' of undefined"

```typescript
// ❌ Wrong
renderHook(() => useMyQuery());

// ✅ Right
const wrapper = createTestWrapper();
renderHook(() => useMyQuery(), { wrapper });
```

**Fix:** Wrap hooks with `createTestWrapper()`

---

### "ReferenceError: EventSource is not defined"

```typescript
// EventSource mock should be auto-loaded from setup.ts
// If not working, check:
// 1. setup.ts is in vitest.config.ts setupFiles
// 2. EventSource is global (not just in test)
// 3. Clear test cache: rm -rf node_modules/.vitest
```

---

### Test Fails in Watch Mode, Passes in Single Run

**Cause:** State leaking between tests

**Fix:**

```typescript
beforeEach(() => {
  vi.clearAllMocks();      // Clear all mocks
  vi.clearAllTimers();     // Clear timers
  vi.restoreAllMocks();    // Restore originals
});

afterEach(() => {
  vi.clearAllMocks();
});
```

---

### Flaky Tests (Pass sometimes, fail other times)

**Causes:**
- Race conditions (setTimeout vs waitFor)
- Timing dependencies (fakeTimers issues)
- Shared state between tests
- Random data in test IDs

**Fixes:**

```typescript
// ❌ Bad - timing dependent
await new Promise(r => setTimeout(r, 100));

// ✅ Good - condition-based
await waitFor(() => {
  expect(element).toBeInTheDocument();
}, { timeout: 3000 });

// ❌ Bad - random data
const id = Math.random();

// ✅ Good - deterministic data
const id = 'test-device-1';
```

---

## Pre-Commit Checklist

Before committing test changes:

```bash
# 1. Run full suite
npm run test:run

# 2. Check coverage
npm run test:coverage
# Verify coverage targets met

# 3. Run linting
npm run lint

# 4. Commit only if passing
git add frontend/src/__tests__/
git commit -m "test: fix Dashboard SSE integration"

# 5. Pre-push verification
npm run test:run -- --reporter=verbose
```

---

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Frontend Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: '20'
      
      - run: cd frontend && npm ci
      - run: npm run test:run
      - run: npm run test:coverage
      
      - uses: codecov/codecov-action@v3
        with:
          files: ./coverage/coverage-final.json
```

### Local Pre-Commit Hook

```bash
#!/bin/bash
# .git/hooks/pre-commit

npm run test:run
if [ $? -ne 0 ]; then
  echo "Tests failed - commit aborted"
  exit 1
fi
```

---

## Test Organization

### File Structure

```
frontend/src/
├── components/
│   ├── __tests__/
│   │   ├── Dashboard.test.tsx
│   │   ├── AlertFeed.test.tsx
│   │   └── ...
│   ├── Dashboard.tsx
│   └── ...
├── hooks/
│   ├── __tests__/
│   │   ├── useDeviceStatus.test.ts
│   │   └── ...
│   └── ...
└── test-utils/
    ├── README.md
    ├── factories.ts
    ├── patterns.ts
    └── ...
```

### Test File Naming

```typescript
// Component test
Dashboard.test.tsx

// Hook test
useDeviceStatus.test.ts

// API test
devicesApi.test.ts

// Utility test
batchAggregator.test.ts
```

### Test Structure

```typescript
describe('ComponentName', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Feature Group', () => {
    it('should do specific thing', () => {
      // Arrange
      const props = { /* ... */ };

      // Act
      render(<Component {...props} />);

      // Assert
      expect(something).toBe(expected);
    });
  });
});
```

---

## Documentation References

- `frontend/src/test-utils/README.md` - Utilities library guide
- `.planning/PHASE_68_02_LEARNINGS.md` - Patterns and best practices
- `frontend/src/test-utils/patterns.ts` - Reusable test patterns
- `CLAUDE.md` - TypeScript/React patterns

---

## Helpful Commands

```bash
# Quick commands
npm run test:run          # All tests once
npm run test:watch       # Watch mode
npm run test:ui          # Visual browser
npm run test:coverage    # Coverage report

# Specific tests
npm run test:run -- Dashboard.test.tsx
npm run test:run -- --grep "should batch"

# Debugging
npm run test:run -- --reporter=verbose
node --inspect-brk ./node_modules/vitest/vitest.mjs run

# Cleanup
rm -rf node_modules/.vitest
npm ci
```

---

*Last Updated: 2026-02-13 | Phase 68-02-07*
