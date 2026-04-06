---
title: "Hook Testing Quick Reference Guide"
type: "guide"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-03-31"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# Hook Testing Quick Reference Guide

**Last Updated:** February 13, 2026 | Phase 68-04
**Total Hooks:** 27 | **Test Cases:** 564 | **Pass Rate:** 100%

---

## Quick Statistics

| Metric | Value |
|--------|-------|
| Total Hooks | 27 |
| Test Cases | 564 |
| Test Files | 27 |
| Lines of Test Code | 15,361 |
| Average Tests/Hook | 21 |
| Largest Test File | useSolarDashboard (924 lines, 35 tests) |
| Smallest Test File | useApprovalState (varies, 8 tests) |
| Estimated Run Time | 45-60 seconds |

---

## Hook Inventory by Category

### Core Data Fetching (7 hooks, 125 tests)

| Hook | Tests | File | Key Features |
|------|-------|------|--------------|
| useSiteAlerts | 21 | `useSiteAlerts.test.ts` | Pagination, severity filtering, 15s cache, 30s refetch |
| useSiteSummary | 20 | `useSiteSummary.test.ts` | Building aggregation, health metrics |
| useSitePredictions | 22 | `useSitePredictions.test.ts` | ML predictions, severity levels, confidence |
| useBuildingsList | 25 | `useBuildingsList.test.ts` | Building enumeration, multi-site caching |
| useServerEvents | 19 | `useServerEvents.test.ts` | SSE integration, real-time updates |
| useHealthTrends | 22 | `useHealthTrends.test.ts` | Time-series data, trend analysis |
| useMissingHooksCoverage | 36 | `useMissingHooksCoverage.test.ts` | Meta-validation, coverage checks |

### Device Management (4 hooks, 92 tests)

| Hook | Tests | File | Key Features |
|------|-------|------|--------------|
| useDeviceCondition | 30 | `useDeviceCondition.test.ts` | Status queries, real-time updates, error states |
| useDeviceControl | 17 | `useDeviceControl.test.ts` | Control operations, safety validation |
| useDeviceSafetyStatus | 26 | `useDeviceSafetyStatus.test.ts` | Safety constraints, interlock validation |
| useDeviceLatestReading | 19 | `useDeviceLatestReading.test.ts` | Sensor readings, point values |

### Equipment & Maintenance (3 hooks, 52 tests)

| Hook | Tests | File | Key Features |
|------|-------|------|--------------|
| useEquipmentWorkOrders | 15 | `useEquipmentWorkOrders.test.ts` | History, assignment, status |
| useEquipmentAlerts | 16 | `useEquipmentAlerts.test.ts` | Equipment alerts, severity tracking |
| useEquipmentByType | 21 | `useEquipmentByType.test.ts` | Type filtering, grouping, inventory |

### Alerts & Predictions (3 hooks, 55 tests)

| Hook | Tests | File | Key Features |
|------|-------|------|--------------|
| usePeakDemandStatus | 16 | `usePeakDemandStatus.test.ts` | Demand vs NMD, headroom, urgency |
| usePeakDemandForecast | 13 | `usePeakDemandForecast.test.ts` | 24h predictions, trends, thresholds |
| useDemandAwaredecision | 26 | `useDemandAwaredecision.test.ts` | AI decisions, multi-module recommendations |

### Approval & Control (1 hook, 8 tests)

| Hook | Tests | File | Key Features |
|------|-------|------|--------------|
| useApprovalState | 8 | `useApprovalState.test.ts` | Approval workflow, safety validation, device writes |

### Integrations (2 hooks, 24 tests)

| Hook | Tests | File | Key Features |
|------|-------|------|--------------|
| useIntegrationStatus | 13 | `useIntegrationStatus.test.ts` | Module health, cross-system status |
| useIntegrationScenarios | 11 | `useIntegrationScenarios.test.ts` | Use cases, capability discovery |

### Advanced Features (7 hooks, 198 tests)

| Hook | Tests | File | Key Features |
|------|-------|------|--------------|
| useSolarBESS | 39 | `useSolarBESS.test.ts` | Solar gen, battery state, arbitrage |
| useSolarDashboard | 35 | `useSolarDashboard.test.ts` | Dashboard aggregation, power curves, cost |
| useSolarGeneration | 19 | `useSolarGeneration.test.ts` | Forecasts, production, capacity |
| useDemandForecasting | 19 | `useDemandForecasting.test.ts` | Load forecasts, peak prediction, TOU |
| useOptimizationEngine | 12 | `useOptimizationEngine.test.ts` | AI optimization, recommendations |
| useMaintenanceSchedule | 17 | `useMaintenanceSchedule.test.ts` | Planning, optimization, assignment |
| useZoneBounds | 27 | `useZoneBounds.test.ts` | Boundaries, positioning, 3D support |

---

## Test Patterns

### 1. Basic Data Fetching Pattern

```typescript
it('should fetch data successfully', async () => {
  // Setup
  vi.mocked(apiFetch).mockResolvedValueOnce(mockData);

  // Act
  const { result } = renderHook(() => useMyHook(params), {
    wrapper: createWrapper(queryClient),
  });

  // Assert - Wait for success
  await waitFor(() => {
    expect(result.current.isSuccess).toBe(true);
  });

  // Verify data
  expect(result.current.data).toEqual(mockData);
});
```

### 2. Pagination Pattern

```typescript
it('should handle pagination correctly', async () => {
  const page1 = { items: [...], offset: 0, limit: 25 };
  const page2 = { items: [...], offset: 25, limit: 25 };

  vi.mocked(apiFetch)
    .mockResolvedValueOnce(page1)
    .mockResolvedValueOnce(page2);

  // First page
  const { result: result1 } = renderHook(
    () => useMyHook({ offset: 0, limit: 25 }),
    { wrapper: createWrapper(queryClient) }
  );

  // Second page
  const { result: result2 } = renderHook(
    () => useMyHook({ offset: 25, limit: 25 }),
    { wrapper: createWrapper(queryClient) }
  );

  await waitFor(() => {
    expect(result1.current.isSuccess).toBe(true);
    expect(result2.current.isSuccess).toBe(true);
  });

  // Verify separate caches
  expect(apiFetch).toHaveBeenCalledTimes(2);
});
```

### 3. Caching Pattern

```typescript
it('should cache data with correct staleTime', async () => {
  vi.mocked(apiFetch).mockResolvedValueOnce(mockData);

  const { result } = renderHook(() => useMyHook('id'), {
    wrapper: createWrapper(queryClient),
  });

  await waitFor(() => {
    expect(result.current.isSuccess).toBe(true);
  });

  // Verify cache entry
  const cacheEntry = queryClient.getQueryData(['query-key', 'id']);
  expect(cacheEntry).toEqual(mockData);
});
```

### 4. Real-Time Updates Pattern

```typescript
it('should refetch on demand', async () => {
  const initialData = { count: 1 };
  const updatedData = { count: 2 };

  vi.mocked(apiFetch)
    .mockResolvedValueOnce(initialData)
    .mockResolvedValueOnce(updatedData);

  const { result } = renderHook(() => useMyHook('id'), {
    wrapper: createWrapper(queryClient),
  });

  await waitFor(() => {
    expect(result.current.data?.count).toBe(1);
  });

  // Trigger refetch
  const refetchPromise = result.current.refetch();

  await waitFor(() => {
    expect(result.current.data?.count).toBe(2);
  });

  await refetchPromise;
});
```

### 5. Error Handling Pattern

```typescript
it('should handle network errors', async () => {
  const error = new Error('Network failed');
  vi.mocked(apiFetch).mockRejectedValueOnce(error);

  const { result } = renderHook(() => useMyHook('id'), {
    wrapper: createWrapper(queryClient),
  });

  await waitFor(() => {
    expect(result.current.isError).toBe(true);
  });

  expect(result.current.error).toEqual(error);
});
```

### 6. Filter/Search Pattern

```typescript
it('should apply filters correctly', async () => {
  const allItems = [
    { id: 1, severity: 'critical' },
    { id: 2, severity: 'warning' },
  ];

  vi.mocked(apiFetch).mockResolvedValueOnce(allItems);

  const { result } = renderHook(
    () => useMyHook({ severity: 'critical' }),
    { wrapper: createWrapper(queryClient) }
  );

  await waitFor(() => {
    expect(result.current.isSuccess).toBe(true);
  });

  // Verify API called with filter
  expect(apiFetch).toHaveBeenCalledWith(
    expect.stringContaining('severity=critical')
  );
});
```

---

## Running Tests

### Quick Commands

```bash
# Run all tests
npm run test:run

# Run specific hook tests
npm run test:run -- useSiteAlerts.test.ts

# Run tests matching pattern
npm run test:run -- --grep "Caching"

# Watch mode (auto-rerun on changes)
npm run test:watch

# Interactive UI
npm run test:ui

# Coverage report
npm run test:coverage

# Debug specific test
npm run test:run -- useSiteAlerts.test.ts -t "should fetch site alerts"
```

### Output Interpretation

```
✓ useSiteAlerts.test.ts (21)
  ✓ Alert Fetching (7)
    ✓ should fetch site alerts successfully
    ✓ should include alert details
    ...
  ✓ Caching Behavior (3)
    ✓ should use 15s staleTime
    ...

Test Files  27 passed (27)
     Tests  564 passed (564)
  Duration  52.34s
```

---

## Common Test Issues & Solutions

### Timeout (>10s per test)

**Problem:** Test hangs or times out

**Solution:**
```typescript
// Option 1: Increase timeout
it('should complete', async () => { /* ... */ }, { timeout: 10000 });

// Option 2: Debug async
await waitFor(() => {
  // Add debug output
  console.log('Current state:', result.current);
  expect(result.current.isSuccess).toBe(true);
}, { timeout: 5000 });
```

### "Cannot read property 'data' of undefined"

**Problem:** Data accessed before hook loads

**Solution:**
```typescript
// WRONG: Data might not be loaded
expect(result.current.data.id).toBe('123');

// RIGHT: Wait first, then use optional chaining
await waitFor(() => {
  expect(result.current.isSuccess).toBe(true);
});
expect(result.current.data?.id).toBe('123');
```

### Mock Not Called

**Problem:** `apiFetch` not called, hook returns undefined

**Solution:**
```typescript
// Verify mock setup BEFORE hook renders
vi.mocked(apiFetch).mockResolvedValueOnce(mockData);

const { result } = renderHook(() => useMyHook(), {
  wrapper: createWrapper(queryClient),
});

// Debug: Check if mock was actually called
console.log('Mock calls:', vi.mocked(apiFetch).mock.calls);
```

### "Cannot find module '@/lib/api'"

**Problem:** Path alias not resolved

**Solution:** Check `vitest.config.ts` has:
```typescript
resolve: {
  alias: {
    '@': fileURLToPath(new URL('./src', import.meta.url)),
  },
}
```

---

## React Query Configuration Reference

### Stale Times in SENTINEL

| Data Type | Stale Time | Refetch Interval | Reason |
|-----------|-----------|------------------|--------|
| Alerts | 15s | 30s | Frequent changes, real-time |
| Device readings | 15s | 30s | Real-time sensor data |
| Buildings list | 5m | None | Rarely changes |
| Predictions | 60s | None | Models run infrequently |
| Site summary | 30s | None | Aggregated data |

### Mock Setup Template

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

vi.mock('@/lib/api/fetchClient', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/lib/api/fetchClient';

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: 0,
        gcTime: 0,
      },
    },
  });
}

function createWrapper(queryClient: QueryClient) {
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

describe('useMyHook', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  // Your tests here
});
```

---

## Test File Locations

All hook tests located at:
```
/opt/bms-intelligence/frontend/src/hooks/__tests__/
```

Directory structure:
```
hooks/
├── __tests__/
│   ├── useSiteAlerts.test.ts
│   ├── useDeviceCondition.test.ts
│   ├── useSolarDashboard.test.ts
│   └── ... (27 test files total)
├── useSiteAlerts.ts
├── useDeviceCondition.ts
└── ... (27 hook files total)
```

---

## Performance Expectations

| Metric | Value |
|--------|-------|
| Full test suite | 45-60s |
| Single hook test | 1-5s |
| Single test case | 100-500ms |
| Memory peak | 120-150 MB |
| Parallel execution | 8+ threads |

---

## Integration with CI/CD

### Pre-commit

```bash
#!/bin/bash
npm run lint
npm run build
npm run test:run
```

### GitHub Actions

```yaml
- name: Run Tests
  run: npm run test:run

- name: Upload Coverage
  uses: codecov/codecov-action@v3
```

### Pre-deployment

```bash
# All must pass before deployment
npm run lint
npm run build
npm run test:run
npm run test:coverage
```

---

## Documentation Links

- **Full Guide:** `docs/PHASE_68_TESTING_COMPLETE.md`
- **Approval Workflow:** `docs/APPROVAL_WORKFLOW.md`
- **Architecture:** `CLAUDE.md`
- **React Query:** https://tanstack.com/query/latest/docs/react/testing
- **Vitest:** https://vitest.dev/

---

**Last Updated:** 2026-02-13 | Phase 68-04 Complete ✅
