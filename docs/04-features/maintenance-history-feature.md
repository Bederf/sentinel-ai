# Maintenance History Feature - Work Order & Alert Context

**Status:** Implemented and deployed (February 2026)
**Location:** Failure Prediction Details modal - Maintenance History section
**Components:** MaintenanceHistoryTabs, WorkOrderHistoryList, EquipmentAlertsList

## Overview

The Maintenance History feature provides critical operational context in the **Failure Prediction Details** modal by displaying:
1. **Work Order History** - Past maintenance and repair activities on the equipment
2. **Alert History** - Past issues and alarms detected on the equipment

This helps technicians and facility managers answer key questions:
- Has this equipment been recently serviced?
- What past issues have occurred?
- Is this a recurring problem or a new issue?

## Architecture

### Frontend Components

**Location:** `/frontend/src/components/maintenance/`

#### 1. MaintenanceHistoryTabs.tsx (Tab Container)
- Wrapper component that manages tab state
- Displays two tabs: "Work Orders" | "Alerts & Errors"
- Handles tab switching with smooth transitions
- Passes equipmentId to child components

```typescript
<MaintenanceHistoryTabs equipmentId={prediction.id} />
```

#### 2. WorkOrderHistoryList.tsx (Work Orders List)
- Displays last 10 work orders for the equipment
- Features:
  - Color-coded left border by status (green=completed, blue=in_progress, yellow=assigned, gray=scheduled)
  - Priority badges with severity colors (urgent=red, high=orange, medium=yellow, low=gray)
  - Status badges (COMPLETED, IN PROGRESS, ASSIGNED, SCHEDULED, CANCELLED)
  - Technician assignment display
  - Relative timestamps ("5 days ago", "2h ago")
  - Empty state message: "No work orders found - Equipment has clean maintenance history"
  - Loading spinner during fetch
  - Error state with retry message

#### 3. EquipmentAlertsList.tsx (Alerts List)
- Displays last 10 alerts for the equipment
- Features:
  - Severity color coding (critical=red, high=orange, warning=orange, medium=yellow, low=blue)
  - Status indicators (active/acknowledged/resolved)
  - Icon indicators with right color
  - Compact card layout
  - Empty state message: "No active alerts - Equipment is operating normally"
  - Loading spinner during fetch
  - Error state with retry message

### API & Data Layer

**Location:** `/frontend/src/lib/api/equipment_history.ts`

```typescript
export const equipmentHistoryApi = {
  getWorkOrders: (equipmentId: string, limit: number = 10) => Promise<WorkOrder[]>
  getAlerts: (equipmentId: string, limit: number = 10) => Promise<EquipmentAlert[]>
}
```

**Types:**

```typescript
interface WorkOrder {
  id: string;
  code: string;               // e.g., WO-2026-0001
  title: string;
  description?: string;
  priority: "low" | "medium" | "high" | "urgent";
  status: "scheduled" | "assigned" | "in_progress" | "completed" | "cancelled";
  assigned_to?: string;
  technician_name?: string;
  created_at: string;
  completed_at?: string;
  updated_at?: string;
}

interface EquipmentAlert {
  id: string;
  title: string;
  message: string;
  severity: "critical" | "warning" | "medium" | "low";
  status: "active" | "acknowledged" | "resolved";
  created_at: string;
  acknowledged_at?: string;
  resolved_at?: string;
}
```

### React Query Integration

**Location:** `/frontend/src/hooks/useEquipmentHistory.ts`

```typescript
export function useEquipmentWorkOrders(equipmentId: string, limit: number = 10) {
  return useQuery({
    queryKey: ['equipment-work-orders', equipmentId, limit],
    queryFn: () => equipmentHistoryApi.getWorkOrders(equipmentId, limit),
    staleTime: 60000,        // 1 minute (infrequent changes)
    gcTime: 5 * 60 * 1000,   // 5 minutes cache time
    enabled: !!equipmentId,
    retry: 2,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 10000),
  });
}

export function useEquipmentAlerts(equipmentId: string, limit: number = 10) {
  return useQuery({
    queryKey: ['equipment-alerts', equipmentId, limit],
    queryFn: () => equipmentHistoryApi.getAlerts(equipmentId, limit),
    staleTime: 30000,        // 30 seconds (frequent updates)
    gcTime: 3 * 60 * 1000,   // 3 minutes cache time
    enabled: !!equipmentId,
    retry: 2,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 10000),
  });
}
```

## Backend Integration

**Existing APIs Used:**
- `GET /api/work-orders/supabase?limit={limit}&equipment_id={id}` - List work orders
- `GET /api/alerts?equipment_id={id}&limit={limit}` - List alerts

**Repository Methods:**
- `work_order_repository.py:get_work_orders_for_equipment(equipment_id)`
- `alert_repository.py:get_active_by_equipment(equipment_id)`

## Usage

### In PredictionDetail Modal

```typescript
// At line ~810 in PredictionDetail.tsx
{prediction.id && (
  <div
    style={{
      backgroundColor: "var(--color-grafana-panel-bg)",
      padding: "1.5rem",
      borderRadius: "8px",
      border: "1px solid var(--color-grafana-border)",
      marginBottom: "1.5rem",
    }}
  >
    <h3
      style={{
        fontSize: "1.125rem",
        fontWeight: 600,
        marginBottom: "1rem",
        color: "var(--color-grafana-text-primary)",
      }}
    >
      Maintenance History
    </h3>
    <MaintenanceHistoryTabs equipmentId={prediction.id} />
  </div>
)}
```

### In Custom Components

```typescript
import { useEquipmentWorkOrders, useEquipmentAlerts } from '@/hooks/useEquipmentHistory';

function MyComponent({ equipmentId }) {
  const { data: workOrders, isLoading: woLoading } = useEquipmentWorkOrders(equipmentId, 10);
  const { data: alerts, isLoading: alertLoading } = useEquipmentAlerts(equipmentId, 10);

  return (
    <div>
      {woLoading ? <Spinner /> : <div>{workOrders.length} work orders</div>}
    </div>
  );
}
```

## Design Patterns

### Color Coding

**Work Order Status (Left Border):**
- ✅ Completed: `var(--color-status-success)` (green)
- 🔵 In Progress: `var(--color-grafana-blue)` (blue)
- 🟡 Assigned: `var(--color-grafana-yellow)` (yellow)
- ⚪ Scheduled: `var(--color-grafana-text-secondary)` (gray)
- ❌ Cancelled: `var(--color-grafana-text-disabled)` (light gray)

**Work Order Priority (Badge):**
- 🔴 Urgent: `var(--color-status-error)` (red)
- 🟠 High: `var(--color-status-warning)` (orange)
- 🟡 Medium: `var(--color-grafana-yellow)` (yellow)
- ⚪ Low: `var(--color-grafana-text-secondary)` (gray)

**Alert Severity (Left Border):**
- 🔴 Critical: `var(--color-status-error)` (red)
- 🟠 High/Warning: `var(--color-status-warning)` (orange)
- 🟡 Medium: `var(--color-grafana-yellow)` (yellow)
- 🔵 Low: `var(--color-grafana-blue)` (blue)

**Alert Status (Badge):**
- 🔴 Active: `var(--color-status-error)` (red)
- 🟡 Acknowledged: `var(--color-grafana-yellow)` (yellow)
- ✅ Resolved: `var(--color-status-success)` (green)

### Response Format Handling

The API client gracefully handles multiple response formats:

```typescript
// API may return array directly
const response1: WorkOrder[] = [...];

// Or as object with data key
const response2: { data: WorkOrder[] } = { data: [...] };

// Or with work_orders key
const response3: { work_orders: WorkOrder[] } = { work_orders: [...] };

// Client handles all formats
const workOrders = response?.data || response?.work_orders || [];
```

## Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| Stale Time (Work Orders) | 60s | Infrequent maintenance changes |
| Stale Time (Alerts) | 30s | More frequent alert generation |
| GC Time (Cache) | 5-3 min | Balanced memory vs cache hits |
| Request Retries | 2 attempts | With exponential backoff |
| Max Retry Delay | 10 seconds | After 2 failed attempts |

## Error Handling

All errors are gracefully handled:
- API fetch failures return empty arrays (non-blocking)
- UI displays error state with message
- Automatic retry with exponential backoff
- No impact on parent component rendering

```typescript
// In api client
catch (error) {
  console.error('Failed to fetch work orders:', error);
  return [];  // Non-blocking fallback
}

// In UI
if (error) {
  return (
    <div style={{ color: 'var(--color-status-error)' }}>
      Failed to load work orders
    </div>
  );
}
```

## Testing

### Manual Testing
1. Open dashboard and select at-risk equipment with failure prediction
2. Click on prediction card to open PredictionDetail modal
3. Scroll to "Maintenance History" section (before "Recommended Action")
4. Click "Work Orders" tab - should show last 10 work orders
5. Click "Alerts & Errors" tab - should show last 10 alerts
6. Verify color coding matches severity/status
7. Verify timestamps are relative ("5 days ago")
8. Verify empty states show helpful messages

### Unit Tests
Located: `frontend/src/components/maintenance/__tests__/`

```bash
npm run test:run -- maintenance/
```

Key test cases:
- Component renders correctly
- Tab switching works
- Hooks fetch data correctly
- Loading/error states display
- Empty states show appropriate messages
- Color coding applies correctly

## Future Enhancements (Out of Scope)

1. **Pagination** - "View all" links for larger datasets
2. **Filtering** - Status, severity, date range dropdowns
3. **Inline Details** - Click work order to see full details
4. **Real-time Updates** - WebSocket subscription for live alerts
5. **Export** - Download history as PDF/CSV
6. **Analytics** - Charts showing maintenance trends
7. **Comparison** - Compare history across similar equipment

## Troubleshooting

### Work orders/alerts not appearing

**Checklist:**
1. ✅ Equipment has equipment ID (prediction.id exists)
2. ✅ Backend APIs are running (`/api/work-orders/supabase`, `/api/alerts`)
3. ✅ Network tab shows requests (F12 → Network)
4. ✅ React Query DevTools shows queries (F12 → React Query tab)
5. ✅ Database has data for the equipment

**Debug steps:**
```bash
# 1. Check API directly
curl http://localhost:9095/api/work-orders/supabase?equipment_id={id}&limit=10

# 2. Check database
psql postgresql://postgres:postgres@localhost:55322/postgres \
  -c "SELECT * FROM work_orders WHERE equipment_id = '{id}' LIMIT 10;"

# 3. Check React Query cache
# Open F12 → React Query tab → search for "equipment-work-orders"
```

### Slow load times

**Optimization:**
1. Check stale times in `useEquipmentHistory.ts` (60s/30s is optimal)
2. Verify network isn't throttled (F12 → Network → disable throttling)
3. Check if multiple requests are happening (React Query should deduplicate)
4. Profile with React Query DevTools

### Color coding looks wrong

**Fix:**
1. Verify CSS variables are defined in theme
2. Check browser DevTools → Computed Styles
3. Clear cache: `rm -rf node_modules/.vite node_modules/.tsc*`
4. Restart dev server

## Files Modified/Created

### New Files
- `/frontend/src/lib/api/equipment_history.ts` - API client
- `/frontend/src/hooks/useEquipmentHistory.ts` - React Query hooks
- `/frontend/src/components/maintenance/MaintenanceHistoryTabs.tsx` - Tab container
- `/frontend/src/components/maintenance/WorkOrderHistoryList.tsx` - Work orders component
- `/frontend/src/components/maintenance/EquipmentAlertsList.tsx` - Alerts component

### Modified Files
- `/frontend/src/lib/api/index.ts` - Added equipment_history exports
- `/frontend/src/components/PredictionDetail.tsx` - Added import and section
- `/opt/bms-intelligence/CLAUDE.md` - Added feature documentation
- `/frontend/README.md` - Added hooks and integration docs
- `/frontend/src/lib/api/README.md` - Added module documentation

## Related Documentation

- **API Reference:** `/docs/03-api-reference/work_orders.md`
- **Alert System:** `/docs/03-api-reference/alerts.md`
- **React Query:** `/frontend/README.md` - React Query Integration section
- **Components:** `/frontend/src/components/maintenance/` - Component files
- **Hooks:** `/frontend/src/hooks/useEquipmentHistory.ts` - Hook documentation

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | Feb 2026 | Initial implementation - work orders and alerts history |

---

**Last Updated:** February 12, 2026
**Maintainers:** Claude Code
**Status:** Production Ready
