# Frontend Testing Guide

This guide documents established patterns and best practices for testing the BMS Intelligence Platform frontend.

## Table of Contents

1. [Test Infrastructure](#test-infrastructure)
2. [Common Patterns](#common-patterns)
3. [Testing React Query Hooks](#testing-react-query-hooks)
4. [Testing Components](#testing-components)
5. [Testing API Clients](#testing-api-clients)
6. [Mocking Strategies](#mocking-strategies)
7. [Async & Timer Testing](#async--timer-testing)
8. [Accessibility Testing](#accessibility-testing)
9. [File Organization](#file-organization)
10. [Running Tests](#running-tests)

---

## Test Infrastructure

### Vitest Configuration

Tests are configured in `frontend/vitest.config.ts` with:

- **Environment:** jsdom (browser-like environment)
- **Coverage thresholds:** 80% lines, 80% functions, 75% branches, 80% statements
- **Setup file:** `src/test-utils/setup.ts` (runs before all tests)
- **Test timeout:** 10 seconds per test

### Setup File (`src/test-utils/setup.ts`)

The setup file initializes test environment with:

- React Testing Library's jest-dom matchers
- Global cleanup after each test
- Mocked `window.matchMedia` (required for responsive components)
- Mocked `ResizeObserver` (required for @dnd-kit/core)
- Mocked `IntersectionObserver` (required for lazy-loading components)

---

## Common Patterns

### Test Structure

All tests follow a consistent structure:

```typescript
describe('ComponentName', () => {
  // Setup
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

### Test Data Factories

Use factories from `src/test-utils/factories.ts` to create consistent mock data:

```typescript
import {
  createMockDevice,
  createMockSite,
  createMockAlert,
  createMockPrediction,
} from '@/test-utils';

// Use defaults
const device = createMockDevice();

// Override specific fields
const device = createMockDevice({
  name: 'Custom Device',
  status: 'offline',
});

// Create multiple items
const devices = createMockDevices(5);
```

Available factories:

- `createMockDevice(overrides?)` → `Device`
- `createMockSite(overrides?)` → `Site`
- `createMockAlert(overrides?)` → `Alert`
- `createMockPrediction(overrides?)` → `Prediction`
- `createMockEquipment(overrides?)` → `Equipment`
- `createMockAuditLog(overrides?)` → `AuditLogEntryResponse`
- `createMockDashboardStats(overrides?)` → `DashboardStats`
- `createMockDeviceStatus(overrides?)` → `DeviceStatus`
- `createMockDeviceSafetyStatus(overrides?)` → `DeviceSafetyStatus`
- `createMockDevices(count)` → `Device[]`
- `createMockSites(count)` → `Site[]`
- `createMockAlerts(count)` → `Alert[]`
- `createMockPredictions(count)` → `Prediction[]`

---

## Testing React Query Hooks

React Query hooks require special setup because they depend on `QueryClientProvider`.

### Basic Hook Test

```typescript
import { renderHook, waitFor } from '@testing-library/react';
import { createQueryWrapper } from '@/test-utils/mockQueryClient';
import { useSiteSummary } from '@/hooks/useSiteSummary';

vi.mock('@/lib/api/client', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/lib/api/client';

describe('useSiteSummary', () => {
  it('should fetch site summary successfully', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      json: () => Promise.resolve({ site_id: 'site-002', status: 'normal' }),
    });

    const wrapper = createQueryWrapper();
    const { result } = renderHook(() => useSiteSummary('site-002'), { wrapper });

    // Hook starts in loading state
    expect(result.current.isLoading).toBe(true);

    // Wait for success
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // Verify data
    expect(result.current.data).toEqual({ site_id: 'site-002', status: 'normal' });
  });
});
```

### Cache Testing

```typescript
it('should use cached data on second call', async () => {
  vi.mocked(apiFetch).mockResolvedValue({
    json: () => Promise.resolve({ site_id: 'site-002' }),
  });

  const wrapper = createQueryWrapper();

  // First hook instance
  const { result: result1 } = renderHook(
    () => useSiteSummary('site-002'),
    { wrapper }
  );

  await waitFor(() => expect(result1.current.isSuccess).toBe(true));

  // API called once
  expect(apiFetch).toHaveBeenCalledTimes(1);

  // Second hook instance (within 30s stale time)
  const { result: result2 } = renderHook(
    () => useSiteSummary('site-002'),
    { wrapper }
  );

  // Should use cache, not call API again
  expect(result2.current.data).toEqual(result1.current.data);
  expect(apiFetch).toHaveBeenCalledTimes(1); // Still 1, not 2
});
```

### Error Testing

```typescript
it('should handle fetch errors', async () => {
  vi.mocked(apiFetch).mockRejectedValue(new Error('Network error'));

  const wrapper = createQueryWrapper();
  const { result } = renderHook(() => useSiteSummary('site-002'), { wrapper });

  await waitFor(() => {
    expect(result.current.isError).toBe(true);
  });

  expect(result.current.error).toEqual(new Error('Network error'));
});
```

### Refetch Testing

```typescript
it('should refetch when refetch is called', async () => {
  vi.mocked(apiFetch).mockResolvedValue({
    json: () => Promise.resolve({ site_id: 'site-002' }),
  });

  const wrapper = createQueryWrapper();
  const { result } = renderHook(() => useSiteSummary('site-002'), { wrapper });

  await waitFor(() => expect(result.current.isSuccess).toBe(true));

  // Call refetch
  result.current.refetch();

  // Should call API again
  await waitFor(() => {
    expect(apiFetch).toHaveBeenCalledTimes(2);
  });
});
```

---

## Testing Components

### Component with Props

```typescript
import { render, screen } from '@/test-utils';

describe('MyComponent', () => {
  it('should render with props', () => {
    render(
      <MyComponent
        title="Test"
        onClick={vi.fn()}
      />
    );

    expect(screen.getByText('Test')).toBeInTheDocument();
  });
});
```

### User Interactions

```typescript
import { render, screen, fireEvent } from '@/test-utils';
import userEvent from '@testing-library/user-event';

describe('MyComponent', () => {
  it('should handle click', async () => {
    const onClick = vi.fn();
    render(<MyComponent onClick={onClick} />);

    const button = screen.getByRole('button');
    fireEvent.click(button);

    expect(onClick).toHaveBeenCalled();
  });

  it('should handle user input', async () => {
    const user = userEvent.setup();
    render(<MyComponent />);

    const input = screen.getByRole('textbox');
    await user.type(input, 'test value');

    expect(input).toHaveValue('test value');
  });
});
```

### Component with Query Hook

```typescript
import { createQueryWrapper } from '@/test-utils/mockQueryClient';

vi.mock('@/lib/api/client');
import { apiFetch } from '@/lib/api/client';

describe('ComponentWithHook', () => {
  it('should display fetched data', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      json: () => Promise.resolve({ name: 'Test Site' }),
    });

    const wrapper = createQueryWrapper();
    const { container } = render(
      <wrapper.type>
        <ComponentWithHook />
      </wrapper.type>
    );

    await waitFor(() => {
      expect(screen.getByText('Test Site')).toBeInTheDocument();
    });
  });
});
```

### Testing Conditional Rendering

```typescript
describe('MyComponent', () => {
  it('should show loading state', () => {
    render(<MyComponent isLoading={true} />);
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it('should show error state', () => {
    render(<MyComponent error="Something went wrong" />);
    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
  });

  it('should show success state', () => {
    render(<MyComponent data={{ id: 1, name: 'Test' }} />);
    expect(screen.getByText('Test')).toBeInTheDocument();
  });
});
```

---

## Testing API Clients

### HTTP Fetch Mocking

```typescript
vi.stubGlobal('fetch', vi.fn());

describe('myApiFunction', () => {
  it('should make correct request', async () => {
    const mockFetch = vi.mocked(fetch);
    mockFetch.mockResolvedValue({
      status: 200,
      json: () => Promise.resolve({ success: true }),
    } as any);

    const result = await myApiFunction('param');

    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:9095/api/endpoint',
      expect.objectContaining({
        method: 'GET',
        headers: expect.objectContaining({
          Authorization: 'Bearer token',
        }),
      })
    );

    expect(result).toEqual({ success: true });
  });
});
```

### Error Responses

```typescript
it('should handle 401 errors', async () => {
  const mockFetch = vi.mocked(fetch);
  mockFetch.mockResolvedValue({
    status: 401,
    json: () => Promise.resolve({ message: 'Unauthorized' }),
  } as any);

  await expect(myApiFunction()).rejects.toThrow('401');
});

it('should handle 429 rate limit errors', async () => {
  const mockFetch = vi.mocked(fetch);
  mockFetch.mockResolvedValue({
    status: 429,
    json: () => Promise.resolve({ message: 'Too Many Requests' }),
  } as any);

  await expect(myApiFunction()).rejects.toThrow('429');
});
```

---

## Mocking Strategies

### API Mocking with vi.mock()

```typescript
// At top of test file
vi.mock('@/lib/api/client', () => ({
  authorizedFetch: vi.fn(),
  fetchApi: vi.fn(),
}));

import { authorizedFetch } from '@/lib/api/client';

describe('MyComponent', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should call API', async () => {
    vi.mocked(authorizedFetch).mockResolvedValue({
      json: () => Promise.resolve({ data: 'test' }),
    });

    render(<MyComponent />);

    await waitFor(() => {
      expect(authorizedFetch).toHaveBeenCalledWith('/api/endpoint');
    });
  });
});
```

### Global Fetch Mocking

```typescript
beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

it('should use global fetch', async () => {
  const mockFetch = vi.mocked(fetch);
  mockFetch.mockResolvedValue({
    ok: true,
    json: () => Promise.resolve({ data: 'test' }),
  } as Response);

  const result = await fetch('/api/endpoint');
  expect(mockFetch).toHaveBeenCalled();
});
```

### Module Mocking

```typescript
// Mock entire module
vi.mock('@/hooks/useSiteSummary', () => ({
  useSiteSummary: vi.fn(() => ({
    data: { site_id: 'site-002' },
    isLoading: false,
    isError: false,
  })),
}));

import { useSiteSummary } from '@/hooks/useSiteSummary';

it('should use mocked hook', () => {
  render(<ComponentUsingHook />);
  expect(useSiteSummary).toHaveBeenCalled();
});
```

---

## Async & Timer Testing

### Async Operations

```typescript
it('should handle async operations', async () => {
  render(<AsyncComponent />);

  // Wait for specific element
  await waitFor(() => {
    expect(screen.getByText('Loaded')).toBeInTheDocument();
  }, { timeout: 3000 });
});
```

### Timer-Based Behavior

```typescript
import { vi } from 'vitest';

describe('AutoRefresh', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('should refresh every 30 seconds', async () => {
    const fetchFn = vi.fn().mockResolvedValue({ data: 'test' });
    render(<ComponentWithRefresh fetchFn={fetchFn} />);

    // Initial fetch
    await waitFor(() => expect(fetchFn).toHaveBeenCalled());
    const initialCallCount = fetchFn.mock.calls.length;

    // Advance time by 30 seconds
    vi.advanceTimersByTime(30000);

    // Should have fetched again
    expect(fetchFn.mock.calls.length).toBeGreaterThan(initialCallCount);
  });

  it('should cancel timers on unmount', () => {
    const fetchFn = vi.fn();
    const { unmount } = render(<ComponentWithRefresh fetchFn={fetchFn} />);

    unmount();

    // Clear all pending timers
    vi.runAllTimers();

    // fetchFn should not be called additional times
    expect(fetchFn).not.toHaveBeenCalledAfter(unmount);
  });
});
```

### Batch Window Testing

```typescript
it('should batch requests within 50ms window', async () => {
  vi.useFakeTimers();
  const apiCall = vi.fn().mockResolvedValue({ data: 'test' });

  render(
    <div>
      <HookComponent1 onData={apiCall} />
      <HookComponent2 onData={apiCall} />
      <HookComponent3 onData={apiCall} />
    </div>
  );

  // All 3 requests should be batched
  vi.advanceTimersByTime(50);

  await waitFor(() => {
    expect(apiCall).toHaveBeenCalledTimes(1); // Single batch call
  });

  vi.useRealTimers();
});
```

---

## Accessibility Testing

### ARIA Attributes

```typescript
it('should have proper ARIA labels', () => {
  render(<Button>Click Me</Button>);

  const button = screen.getByRole('button', { name: /click me/i });
  expect(button).toHaveAttribute('aria-label', 'Click button');
});
```

### Semantic HTML

```typescript
it('should use semantic HTML', () => {
  render(<Form />);

  expect(screen.getByRole('form')).toBeInTheDocument();
  expect(screen.getByRole('textbox')).toBeInTheDocument();
  expect(screen.getByRole('button')).toBeInTheDocument();
});
```

### Keyboard Navigation

```typescript
it('should support keyboard navigation', async () => {
  const user = userEvent.setup();
  render(<Dialog />);

  // Tab to button
  await user.tab();
  expect(screen.getByRole('button')).toHaveFocus();

  // Press Enter
  await user.keyboard('{Enter}');
  expect(screen.getByText(/dialog closed/i)).toBeInTheDocument();
});
```

---

## File Organization

### Test File Naming

- Component tests: `ComponentName.test.tsx` or `__tests__/ComponentName.test.tsx`
- Hook tests: `__tests__/hookName.test.ts`
- Utility tests: `__tests__/utilityName.test.ts`
- Integration tests: `__tests__/integration/scenario-name.test.tsx`

### Directory Structure

```
frontend/src/
├── components/
│   ├── MyComponent.tsx
│   └── __tests__/
│       ├── MyComponent.test.tsx
│       └── integration/
│           └── workflow.test.tsx
├── hooks/
│   ├── useMyHook.ts
│   └── __tests__/
│       └── useMyHook.test.ts
├── lib/
│   ├── api/
│   │   ├── client.ts
│   │   └── __tests__/
│   │       └── client.test.ts
│   └── utils.ts
└── test-utils/
    ├── setup.ts
    ├── index.tsx
    ├── factories.ts
    ├── mockQueryClient.ts
    └── TESTING_GUIDE.md
```

---

## Running Tests

### Run All Tests

```bash
npm run test:run
```

### Watch Mode

```bash
npm run test:watch
```

### Run Specific File

```bash
npm run test:run src/components/__tests__/MyComponent.test.tsx
```

### Run Matching Pattern

```bash
npm run test:run -- -t "should render"
```

### Run with Coverage

```bash
npm run test:coverage
```

### Run Single Test

```bash
npm run test:run -- -t "MyComponent should render"
```

### UI Test Runner

```bash
npm run test:ui
```

---

## Tips & Best Practices

### 1. Don't Test Implementation Details

❌ **BAD:** Testing internal state or component internals

```typescript
// Don't do this
const { getByTestId } = render(<MyComponent />);
const innerDiv = getByTestId('internal-div');
```

✅ **GOOD:** Test user-facing behavior

```typescript
// Do this
render(<MyComponent title="Hello" />);
expect(screen.getByText('Hello')).toBeInTheDocument();
```

### 2. Use User-Centric Queries

❌ **BAD:** DOM structure queries

```typescript
screen.getByDisplayValue('value');
```

✅ **GOOD:** Semantic role queries

```typescript
screen.getByRole('button', { name: /click/i });
screen.getByLabelText(/email/i);
```

### 3. Keep Tests Independent

```typescript
// ✅ GOOD: Each test is self-contained
describe('MyComponent', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.clearAllTimers();
  });

  it('should do X', () => { /* ... */ });
  it('should do Y', () => { /* ... */ });
  // Each test doesn't depend on others
});
```

### 4. Mock External Dependencies

```typescript
// ✅ GOOD: Mock external API
vi.mock('@/lib/api/client');

// ❌ BAD: Don't make real API calls
// Remove comments like: // await fetch('/api/...')
```

### 5. Test User Workflows

```typescript
// ✅ GOOD: Test complete flow
it('should complete device control workflow', async () => {
  const user = userEvent.setup();
  render(<ControlDashboard />);

  // Select device
  await user.click(screen.getByText('Chiller'));

  // Adjust temperature
  const slider = screen.getByRole('slider');
  await user.click(slider, { clientX: 300 });

  // Confirm
  await user.click(screen.getByRole('button', { name: /confirm/i }));

  // Verify success
  await waitFor(() => {
    expect(screen.getByText(/control successful/i)).toBeInTheDocument();
  });
});
```

---

## Common Issues & Solutions

### Issue: "Warning: useLayoutEffect does nothing on the server"

**Solution:** This is expected in jsdom tests. Add to setup.ts if needed:

```typescript
vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
  return setTimeout(cb, 0);
});
```

### Issue: "Cannot find module" errors

**Solution:** Clear node_modules and reinstall:

```bash
rm -rf node_modules/.vite node_modules/.tsc*
npm ci
```

### Issue: Tests timeout

**Solution:** Use `{ timeout: 5000 }` in waitFor:

```typescript
await waitFor(
  () => expect(element).toBeInTheDocument(),
  { timeout: 5000 }
);
```

### Issue: ReferenceError: fetch is not defined

**Solution:** Mock fetch globally in setup or test:

```typescript
vi.stubGlobal('fetch', vi.fn());
```

---

## Resources

- [Vitest Documentation](https://vitest.dev/)
- [React Testing Library Docs](https://testing-library.com/react)
- [Testing Library Queries](https://testing-library.com/queries)
- [TanStack Query Testing](https://tanstack.com/query/latest/docs/react/testing)
- [Jest DOM Matchers](https://github.com/testing-library/jest-dom)

