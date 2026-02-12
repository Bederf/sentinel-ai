# React + TypeScript + Vite + React Query

This is the SENTINEL BMS Intelligence frontend built with React, TypeScript, Vite, and React Query (TanStack Query) for efficient API data management.

## React Query Integration

**Version:** @tanstack/react-query v5
**Status:** Deployed (Phase 75, Feb 2026)

### Overview

React Query handles all data fetching, caching, and synchronization with the backend. This eliminates the need for manual Redux/Zustand state management for server state and provides automatic request deduplication and cache management.

### Installation

React Query and devtools are already installed:
```bash
npm install @tanstack/react-query @tanstack/react-query-devtools
```

### Configuration

**Query Client Setup** (`src/lib/queryClient.ts`):
```typescript
import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30 * 1000,           // 30 seconds
      gcTime: 5 * 60 * 1000,          // 5 minutes (formerly cacheTime)
      retry: 3,                        // Retry failed requests 3 times
      retryDelay: (attemptIndex) =>
        Math.min(1000 * 2 ** attemptIndex, 30000),  // Exponential backoff
      refetchOnWindowFocus: false,     // BMS data doesn't change that fast
    },
  },
});
```

**Provider Setup** (`src/main.tsx`):
```typescript
import { QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { queryClient } from '@/lib/queryClient';

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      {/* Your app components */}
      {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
    </QueryClientProvider>
  );
}
```

### Key Concepts

#### 1. Query Keys

Query keys are arrays that uniquely identify cached data:

```typescript
// Single site summary
queryKey: ['site-summary', 'site-002']

// Device safety status
queryKey: ['device-safety', 'device-001']

// List of buildings
queryKey: ['buildings-list']
```

#### 2. Stale Time Strategy

Data becomes "stale" after this duration and is refetched if needed:

| Data Type | Stale Time | Rationale |
|-----------|-----------|-----------|
| Site summary | 30s | Equipment status stable, hourly changes typical |
| Device readings | 15s | Sensor values change frequently for live monitoring |
| Predictions | 60s | ML model runs infrequently |
| Buildings list | 5m | Rarely changes during a session |
| Alerts | 15s | Must catch new issues quickly |

#### 3. GC Time (Garbage Collection)

Cache remains in memory for this duration after last use, then is cleared:
- Default: 5 minutes
- Balances memory usage vs cache hit rate

### Custom Hooks

All data fetching goes through custom hooks. Never fetch directly in components:

```typescript
// ✅ GOOD: Use hook
import { useSiteSummary } from '@/hooks';
const { data, isLoading, error } = useSiteSummary('site-002');

// ❌ BAD: Direct API call
const [data, setData] = useState(null);
useEffect(() => {
  api.getSiteSummary('site-002').then(setData);
}, []);
```

#### Equipment History Hooks

Specialized hooks for fetching equipment maintenance history (work orders and alerts):

```typescript
// Work orders for equipment
import { useEquipmentWorkOrders } from '@/hooks/useEquipmentHistory';
const { data: workOrders, isLoading } = useEquipmentWorkOrders('equipment-uuid', 10);

// Alerts for equipment
import { useEquipmentAlerts } from '@/hooks/useEquipmentHistory';
const { data: alerts, isLoading } = useEquipmentAlerts('equipment-uuid', 10);
```

**Configuration:**
- Work orders: 60s stale time (infrequent changes)
- Alerts: 30s stale time (frequent updates)
- Both: 5-3 minute GC time
- Automatic retry with exponential backoff

**Integration in PredictionDetail:**
The MaintenanceHistoryTabs component displays both hooks side-by-side with tab switching:
```typescript
<MaintenanceHistoryTabs equipmentId={prediction.id} />
```

This renders:
- **Work Orders tab:** List of recent maintenance/repair activities
- **Alerts & Errors tab:** History of detected issues and alarms

### Batch Aggregator Integration

React Query integrates with the batch aggregator to automatically deduplicate and batch requests:

```typescript
// Multiple components requesting same device
// Component 1
const { data: safety1 } = useDeviceSafetyStatus('device-001');

// Component 2 (mounted 20ms later)
const { data: safety2 } = useDeviceSafetyStatus('device-001');

// Result: ✅ Only 1 API call (React Query deduplication)
//         + ✅ Only 1 batch call even if 100 devices requested within 50ms window
```

### ReactQueryDevtools

Enable in development mode to inspect query state:

```bash
# Open browser DevTools (F12)
# Click "React Query" tab
# View query cache, stale/fresh status, request/response data, timing
```

### Common Patterns

**Conditional Fetching:**
```typescript
const { data } = useQuery({
  queryKey: ['device', deviceId],
  queryFn: () => api.getDevice(deviceId),
  enabled: !!deviceId,  // Only fetch if deviceId exists
});
```

**Prefetching:**
```typescript
import { useQueryClient } from '@tanstack/react-query';

const queryClient = useQueryClient();

const prefetch = () => {
  queryClient.prefetchQuery({
    queryKey: ['site-summary', 'site-002'],
    queryFn: () => api.getSiteSummary('site-002'),
  });
};
```

**Invalidation (Force Refetch):**
```typescript
// After creating/updating equipment
await api.createEquipment(data);

// Invalidate related queries
await queryClient.invalidateQueries({
  queryKey: ['site-summary'],  // Matches all site-summary queries
});
```

### Performance Tips

1. **Use hooks** - Automatic deduplication of identical queries
2. **Batch requests** - Multiple devices within 50ms window = 1 batch call
3. **Enable stale-while-revalidate** - Default behavior, no extra config needed
4. **Monitor with DevTools** - Check cache hit rate, staleness, timing
5. **Set appropriate stale times** - Balance freshness vs performance

### Troubleshooting

**Query not refetching:**
- Check if query is in cache (not stale)
- Check `refetchInterval` setting
- Use `refetchOnMount: true` to force refetch

**High API calls:**
- Check React Query DevTools for cache misses
- Verify query keys are identical across components
- Check batch window (50ms) isn't too short

**Memory usage:**
- Increase `gcTime` to keep cache longer
- Use `queryClient.clear()` to manually clear
- Check for circular references in cached data

### Migration from Old Code

```typescript
// OLD: Manual useEffect + useState
const [data, setData] = useState(null);
useEffect(() => {
  api.getSites().then(setData);
}, []);

// NEW: React Query hook
const { data } = useBuildingsList();
```

---

## Core Setup

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Babel](https://babeljs.io/) (or [oxc](https://oxc.rs) when used in [rolldown-vite](https://vite.dev/guide/rolldown)) for Fast Refresh
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/) for Fast Refresh

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...

      // Remove tseslint.configs.recommended and replace with this
      tseslint.configs.recommendedTypeChecked,
      // Alternatively, use this for stricter rules
      tseslint.configs.strictTypeChecked,
      // Optionally, add this for stylistic rules
      tseslint.configs.stylisticTypeChecked,

      // Other configs...
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```

You can also install [eslint-plugin-react-x](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from 'eslint-plugin-react-x'
import reactDom from 'eslint-plugin-react-dom'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...
      // Enable lint rules for React
      reactX.configs['recommended-typescript'],
      // Enable lint rules for React DOM
      reactDom.configs.recommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```
