# API Client Modules

This directory contains the modularized API client for the BMS Intelligence Platform.

## Structure

```
api/
├── README.md                   # This file
├── index.ts                    # Barrel export - re-exports all modules
├── client.ts                   # Core HTTP utilities, authentication, and token management
├── auth.ts                     # Authentication APIs (login, MFA, verify token)
├── devices.ts                  # Device control and queries
├── sites.ts                    # Site and building management
├── workflow.ts                 # Inspection and maintenance workflows
├── equipment_history.ts        # Equipment work orders and alerts history
├── (future) chat.ts            # AI chat integration
├── (future) solar.ts           # Solar PV and BESS APIs
├── (future) security.ts        # Security and access control
└── (future) contracts.ts       # Contract management
```

## Usage

### Importing from Index (Recommended)

```typescript
// Import from api/index.ts (automatically picked up from api/ directory)
import { authApi, devicesApi, sitesApi } from '@/lib/api';

// Login
const response = await authApi.login('user@example.com');

// Get devices
const devices = await devicesApi.getDevices(buildingId);
```

### Importing from Original api.ts (Legacy)

For backward compatibility, all original API functions are still available:

```typescript
import api from '@/lib/api';

// All existing methods still work
const health = await api.health();
const devices = await api.getDevices(buildingId);
```

### Importing Specific Modules

```typescript
// Import specific domain module
import { devicesApi, type Device } from '@/lib/api/devices';
import { authApi, type AuthUser } from '@/lib/api/auth';
```

## Module Responsibilities

### client.ts (Core Utilities)
- `authorizedFetch()` - Fetch with auth, retry, caching, rate limiting
- `fetchApi()` - Generic fetch wrapper with JSON parsing and error handling
- `clearAuthStorage()` - Clear stored tokens
- `isExpectedApiError()` - Check for expected API errors (401, 429)
- Token management (access/refresh tokens)

**Size:** ~300 lines
**Reusability:** Used by all domain modules

### auth.ts (Authentication)
- `authApi.login()` - Email-based login
- `authApi.verify()` - Token verification
- `authApi.me()` - Get current user
- `authApi.logout()` - Logout and clear tokens

**Size:** ~80 lines
**Types:** AuthUser, LoginResponse, VerifyResponse

### devices.ts (Device Control)
- `devicesApi.getDevices()` - List devices
- `devicesApi.control()` - Send control command
- `devicesApi.checkSafety()` - Validate safety before control
- `devicesApi.getStatus()` - Device status

**Size:** ~90 lines
**Types:** Device, DevicePoint, DeviceStatus, DeviceSafetyStatus

### sites.ts (Site Management)
- `sitesApi.getSites()` - List accessible sites
- `sitesApi.getEquipment()` - List equipment
- `sitesApi.create()` - Create new site

**Size:** ~80 lines
**Types:** Site, Equipment, BuildingEquipmentResponse

### workflow.ts (Workflows & Inspections)
- `inspectionApi.getSchedule()` - Inspection schedule
- `workflowApi.getStatus()` - Workflow state
- `workflowApi.updateState()` - Update workflow

**Size:** ~100 lines
**Types:** WorkflowDashboardResponse, InspectionScheduleItem

### equipment_history.ts (Equipment Maintenance History)
- `equipmentHistoryApi.getWorkOrders()` - Fetch recent work orders for equipment
- `equipmentHistoryApi.getAlerts()` - Fetch recent alerts/errors for equipment
- Handles both response formats (array or object with data/work_orders keys)
- Graceful error handling with non-blocking fallbacks

**Size:** ~80 lines
**Types:** WorkOrder (id, code, title, priority, status, assigned_to, created_at, completed_at), EquipmentAlert (id, title, message, severity, status, created_at, acknowledged_at)
**Integration:** Used in `MaintenanceHistoryTabs` component for failure prediction details
**Stale Times:** 
- Work orders: 60 seconds (infrequent changes)
- Alerts: 30 seconds (more frequent updates)
**Use Case:** Provide maintenance context in PredictionDetail modal to show past issues and service history

## Migration Path

### Phase 1 (Complete)
- Create `api/client.ts` with shared utilities ✓
- Create `api/index.ts` barrel export ✓
- Create domain modules: `auth.ts`, `devices.ts`, `sites.ts`, `workflow.ts` ✓
- Create `equipment_history.ts` for maintenance history ✓

### Phase 2 (Planned)
- Create remaining domain modules: `chat.ts`, `solar.ts`, `security.ts`, `contracts.ts`
- Update component imports to use domain modules directly
- Deprecate re-exports from original `api.ts`

### Phase 3 (Future)
- Remove duplicate definitions from original `api.ts`
- Archive original `api.ts` for reference
- Migrate all components to use modular imports

## Design Patterns

### Service Pattern
Each domain module follows a consistent pattern:

```typescript
// 1. Import utilities
import { fetchApi } from './client';

// 2. Define types
export interface MyType { ... }

// 3. Define API methods
export const myApi = {
  get: () => fetchApi<MyType>('/api/endpoint'),
  post: (data) => fetchApi('/api/endpoint', { method: 'POST', body: JSON.stringify(data) }),
};
```

### Error Handling
All API methods throw typed `ApiError` on failure:

```typescript
try {
  const response = await authApi.login(email);
} catch (error) {
  if (isExpectedApiError(error)) {
    // Handle 401 (auth), 429 (rate limit)
  }
}
```

## Performance

- **Request deduplication:** GET requests are deduplicated in-flight
- **Response caching:** GET responses cached for 30 seconds
- **Rate limiting:** Client-side rate limit handling with exponential backoff
- **Request limiting:** Max 4 concurrent requests with queue

## Testing

Each domain module can be tested in isolation:

```typescript
// jest.mock('@/lib/api/devices');
import { devicesApi } from '@/lib/api/devices';

devicesApi.getDevices.mockResolvedValue(mockDevices);
```

## Future Enhancements

- [ ] WebSocket support for real-time updates
- [ ] Offline mode with local caching
- [ ] Request interceptors for logging
- [ ] Centralized error handling
- [ ] Request retry policies per domain
