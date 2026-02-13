# Frontend Test Utilities Library

Comprehensive testing infrastructure for Phase 68-02+ component and hook testing. This document covers all available helpers, factories, and best practices.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Test Utilities](#test-utilities)
3. [Mock Factories](#mock-factories)
4. [Mocking Strategies](#mocking-strategies)
5. [Common Testing Patterns](#common-testing-patterns)
6. [Best Practices](#best-practices)
7. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Basic Component Test

```typescript
import { render, screen } from 'vitest';
import { QueryClientProvider } from '@tanstack/react-query';
import { createTestQueryClient } from '@/test-utils';
import { MyComponent } from './MyComponent';

describe('MyComponent', () => {
  it('should render', () => {
    const queryClient = createTestQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <MyComponent />
      </QueryClientProvider>
    );

    expect(screen.getByText('Expected text')).toBeInTheDocument();
  });
});
```

### Hook Test with Provider

```typescript
import { renderHook, waitFor } from '@testing-library/react';
import { createTestWrapper } from '@/test-utils';
import { useMyHook } from '@/hooks';

describe('useMyHook', () => {
  it('should fetch data', async () => {
    const wrapper = createTestWrapper();
    const { result } = renderHook(() => useMyHook(), { wrapper });

    await waitFor(() => {
      expect(result.current.data).toBeDefined();
    });
  });
});
```

---

## Test Utilities

### Render Function with Providers

**File:** `src/test-utils/test-utils.ts`

```typescript
import { render } from '@/test-utils';

// Render with default providers (QueryClient + ModuleContext)
render(<Component />, {
  moduleContext: { /* override module context if needed */ }
});

// Options
interface RenderOptions {
  moduleContext?: Partial<ModuleContextValue>;
  initialPath?: string;
  // Standard RTL render options...
}
```

**Example:**

```typescript
it('should render with custom module context', () => {
  render(<ModularDashboard />, {
    moduleContext: {
      activeModules: ['hvac', 'energy'],
      isModuleActive: (type) => ['hvac', 'energy'].includes(type),
    },
  });
});
```

### Query Client Setup

**File:** `src/test-utils/mockQueryClient.ts`

```typescript
import { createTestQueryClient, createTestWrapper } from '@/test-utils';

// Create isolated QueryClient for each test
const queryClient = createTestQueryClient();

// Wrapper component with QueryClient + ModuleContext
const wrapper = createTestWrapper({
  moduleContext: { /* optional */ }
});

// Use in renderHook
renderHook(() => useMyQuery(), { wrapper });
```

**Key Features:**
- Default stale times: 0 (immediate stale)
- Retry policy: 0 retries (fail fast in tests)
- GC time: Infinity (keep in cache during test)
- Automatic cleanup between tests

### Module Context Wrapper

**File:** `src/test-utils/mockQueryClient.ts`

```typescript
import { createModuleContextWrapper } from '@/test-utils';

// Wrapper with specific modules active
const wrapper = createModuleContextWrapper({
  activeModules: ['solar', 'energy'],
  isModuleActive: (type) => ['solar', 'energy'].includes(type),
});

renderHook(() => useModuleDashboard(), { wrapper });
```

### EventSource Mock

**File:** `src/test-utils/mockEventSource.ts`

Provides EventSource mock for SSE (Server-Sent Events) testing.

```typescript
import { getEventSource } from '@/test-utils';

it('should handle SSE messages', async () => {
  render(<IntegrationMonitoringPage />);

  const eventSource = getEventSource();
  eventSource.dispatchEvent('message', {
    data: JSON.stringify({ status: 'alert', equipment: 'chiller' }),
  });

  await waitFor(() => {
    expect(screen.getByText(/alert/i)).toBeInTheDocument();
  });
});
```

**Features:**
- `addEventListener()` / `removeEventListener()` support
- `close()` method for cleanup
- `readyState` property (0=CONNECTING, 1=OPEN, 2=CLOSED)
- `dispatchEvent(type, eventData)` for controlled event delivery

### Tremor Component Mocks

**File:** `src/test-utils/mockTremor.ts`

Provides unified mocking strategy for Tremor components.

```typescript
import { mockTremor } from '@/test-utils';
import { vi } from 'vitest';

beforeEach(() => {
  const mocks = mockTremor.createTremorMocks();
  vi.mock('@tremor/react', () => mocks);
});
```

**Mocked Components:**
- `TabGroup` - with onChange callback support
- `TabPanel` - renders children (no shadow DOM issues)
- `BarChart`, `LineChart`, `AreaChart` - empty divs (canvas untestable)
- `Metric`, `Badge`, `Gauge` - simple renders
- `Flex`, `Grid` - pass-through (no mocking needed)

---

## Mock Factories

All factories in `src/test-utils/factories.ts` support optional `overrides` parameter.

### Available Factories

- `createMockDevice(overrides?)` → Device
- `createMockAlert(overrides?)` → Alert
- `createMockPrediction(overrides?)` → Prediction
- `createMockEquipment(overrides?)` → Equipment
- `createMockWorkOrder(overrides?)` → WorkOrder
- `createMockSite(overrides?)` → Site
- `createMockModuleContext(overrides?)` → ModuleContextValue
- `createBatchResponse(endpoint, items?)` → Batch API Response

### Example Usage

```typescript
import { createMockDevice, createMockAlert } from '@/test-utils';

const device = createMockDevice({
  name: 'Custom Chiller',
  status: 'offline',
});

const alert = createMockAlert({
  severity: 'critical',
  equipment_name: 'Generator Set 5',
});
```

---

## Mocking Strategies

### Mocking API Calls

```typescript
import { vi } from 'vitest';
import * as api from '@/lib/api';

vi.mock('@/lib/api', () => ({
  devicesApi: {
    getDevice: vi.fn(),
  },
}));

// In test
api.devicesApi.getDevice.mockResolvedValue(createMockDevice());
```

### Mocking Child Components

```typescript
vi.mock('@/components/AlertFeed', () => ({
  AlertFeed: ({ alerts }: { alerts: Alert[] }) => (
    <div data-testid="alert-feed">
      {alerts.map(a => <div key={a.id}>{a.message}</div>)}
    </div>
  ),
}));
```

### User Interactions

```typescript
import { userEvent } from '@testing-library/user-event';

const user = userEvent.setup();
await user.click(screen.getByRole('button'));
```

---

## Common Testing Patterns

### Testing Data Fetching

```typescript
it('should fetch and display device status', async () => {
  const { devicesApi } = await import('@/lib/api');
  devicesApi.getDeviceStatus = vi.fn().mockResolvedValue({
    status: 'online',
    last_seen_seconds_ago: 5,
  });

  const wrapper = createTestWrapper();
  const { result } = renderHook(() => useDeviceStatus('device-1'), { wrapper });

  expect(result.current.isLoading).toBe(true);

  await waitFor(() => {
    expect(result.current.data).toBeDefined();
  });

  expect(result.current.data.status).toBe('online');
});
```

### Testing Error Handling

```typescript
it('should handle API errors gracefully', async () => {
  const { devicesApi } = await import('@/lib/api');
  devicesApi.getDeviceStatus = vi.fn().mockRejectedValue(
    new Error('Network error')
  );

  const wrapper = createTestWrapper();
  const { result } = renderHook(() => useDeviceStatus('device-1'), { wrapper });

  await waitFor(() => {
    expect(result.current.error).toBeDefined();
  });
});
```

### Testing Real-Time Updates (SSE)

```typescript
it('should update on SSE messages', async () => {
  render(<IntegrationMonitoringPage />);

  const eventSource = getEventSource();
  eventSource.dispatchEvent('message', {
    data: JSON.stringify({
      type: 'alert',
      equipment: 'chiller',
      severity: 'critical',
    }),
  });

  await waitFor(() => {
    expect(screen.getByText(/critical alert/i)).toBeInTheDocument();
  });
});
```

### Testing Approval Workflow

```typescript
it('should approve and execute recommendation', async () => {
  const user = userEvent.setup();
  const { approvalsApi } = await import('@/lib/api');

  approvalsApi.approveRecommendation = vi.fn().mockResolvedValue({
    status: 'executed',
    cov_verified: true,
  });

  render(<ApprovalDialog recommendationId="rec-001" />);

  await user.click(screen.getByRole('button', { name: /approve/i }));

  await waitFor(() => {
    expect(screen.getByText(/executed successfully/i)).toBeInTheDocument();
  });
});
```

### Testing Batch Aggregation

```typescript
it('should batch multiple requests', async () => {
  const { devicesApi } = await import('@/lib/api');
  devicesApi.listDevicesSafety = vi.fn().mockResolvedValue({
    'device-1': { status: 'safe' },
    'device-2': { status: 'warning' },
  });

  const wrapper = createTestWrapper();
  const { result: result1 } = renderHook(
    () => useDeviceSafety('device-1'),
    { wrapper }
  );
  const { result: result2 } = renderHook(
    () => useDeviceSafety('device-2'),
    { wrapper }
  );

  await waitFor(() => {
    expect(result1.current.data).toBeDefined();
  });

  // Single API call (not 2)
  expect(devicesApi.listDevicesSafety).toHaveBeenCalledTimes(1);
});
```

---

## Best Practices

### 1. Isolate Tests
```typescript
beforeEach(() => {
  vi.clearAllMocks();
  vi.clearAllTimers();
});
```

### 2. Use Semantic Queries
```typescript
screen.getByRole('button', { name: /save/i })
screen.getByLabelText(/device name/i)
```

### 3. Test User Perspective
```typescript
// Good - test visible output
expect(screen.getByText(/data loaded/i)).toBeInTheDocument();
```

### 4. Use waitFor for Async
```typescript
await waitFor(() => {
  expect(screen.getByText(/success/i)).toBeInTheDocument();
});
```

### 5. Descriptive Test Names
```typescript
it('should display error message when device API returns 500', () => {});
```

---

## Troubleshooting

### "ReferenceError: EventSource is not defined"
EventSource mock is in setup.ts. Import and use `getEventSource()`.

### "Cannot read property of undefined"
Use `createTestWrapper()` when rendering hooks:
```typescript
const wrapper = createTestWrapper();
renderHook(() => useMyQuery(), { wrapper });
```

### "Timeout: async operation did not complete"
Use `screen.debug()` to see rendered content, then adjust `waitFor` condition.

### Flaky Tests
- Use `waitFor()` instead of arbitrary delays
- Clear mocks with `vi.clearAllMocks()`
- Avoid `vi.useFakeTimers()` (causes timing issues)

---

## File Organization

```
frontend/src/test-utils/
├── README.md                 # This documentation
├── setup.ts                  # Test environment initialization
├── test-utils.ts            # Main render function
├── factories.ts             # Mock data factories
├── mockQueryClient.ts       # QueryClient + ModuleContext
├── mockEventSource.ts       # EventSource mock for SSE
└── mockTremor.ts            # Tremor component mocks
```

---

*Last Updated: 2026-02-13 | Phase 68-02-07*
