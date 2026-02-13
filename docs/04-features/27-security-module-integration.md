# SENTINEL Security Module Integration Guide

**Phase:** 27-Sentinel-Security
**Status:** Complete ✅
**Last Updated:** 2026-02-13

## Overview

The SENTINEL Security module integrates into the modular dashboard system and provides cross-module occupancy data for HVAC/Lighting coordination. This guide explains how to use the security module and integrate its data with other modules.

## Module Architecture

### Component Hierarchy

```
ModularDashboard
├── ModuleSelector (module activation)
├── SecurityPanel (when security module active)
│   ├── Overview Tab
│   ├── Access Events Tab
│   ├── Visitors Tab
│   ├── Alerts Tab
│   └── Access Points Tab
└── Other Module Tabs
```

### Data Flow

```
Access Control System
    ↓ (webhook)
POST /api/security/events
    ↓
SecurityRepository (Supabase + JSON fallback)
    ↓
React Query Hooks (caching + updates)
    ↓
SecurityPanel Component (display)
```

## Module Activation

### Via Frontend UI

1. Open modular dashboard
2. Click "Modules" tab
3. Toggle "Security" to ON
4. Module loads with demo data immediately

### Via API

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "site_id": "site-002",
    "module_type": "security"
  }' \
  http://localhost:9095/api/modules/activate
```

### Via Code (Component)

```typescript
import { SecurityPanel } from '@/components/modules/SecurityPanel'

<SecurityPanel siteId="site-002" />
```

## React Query Hook Usage

All hooks automatically cache and refetch based on stale time:

```typescript
import {
  useSecurityOverview,
  useAccessEvents,
  useAccessPoints,
  useVisitors,
  useSecurityAlerts,
  useOccupancy
} from '@/lib/api'

function MyComponent() {
  const siteId = 'site-002'

  // Overview (refreshes every 30 seconds)
  const { data: overview, isLoading } = useSecurityOverview(siteId)

  // Real-time events (refreshes every 15 seconds)
  const { data: events } = useAccessEvents(siteId, {
    location: 'Main Entrance',
    afterHours: false
  })

  // Access points (5 minute cache)
  const { data: points } = useAccessPoints(siteId)

  // Occupancy for HVAC/Lighting
  const { data: occupancy } = useOccupancy(siteId)

  return (
    <div>
      {isLoading && <Skeleton />}
      {overview && <Card>{overview.total_access_events_today}</Card>}
    </div>
  )
}
```

### Hook Stale Times

| Hook | Stale Time | Reason |
|------|-----------|--------|
| `useSecurityOverview` | 30s | Regular status updates |
| `useAccessEvents` | 15s | Real-time event stream |
| `useAccessPoints` | 5m | Rarely changes |
| `useVisitors` | 30s | Check-in/out updates |
| `useSecurityAlerts` | 15s | Real-time alerts |
| `useOccupancy` | 15s | Real-time occupancy |

## Cross-Module Integration Points

### Phase 28: HVAC Occupancy-Based Control

**Data Consumer:** HVAC Module
**Data Source:** Security Module occupancy endpoint

**Implementation Pattern:**

```typescript
// HVAC Module (Phase 28)
import { useOccupancy } from '@/lib/api'

function HVACOptimizer() {
  const siteId = 'site-002'
  const { data: occupancy } = useOccupancy(siteId)

  useEffect(() => {
    if (!occupancy) return

    // Adjust HVAC setpoint based on occupancy
    const { total_occupancy } = occupancy

    let targetSetpoint = 22 // default
    
    if (total_occupancy === 0) {
      targetSetpoint = 16 // empty → energy save
    } else if (total_occupancy > 50) {
      targetSetpoint = 20 // crowded → cool aggressively
    } else if (total_occupancy > 20) {
      targetSetpoint = 21 // moderate → slightly cool
    }

    hvacApi.setSetpoint(siteId, targetSetpoint)
  }, [occupancy])
}
```

### Phase 28: Lighting Occupancy-Based Dimming

**Data Consumer:** Lighting Module
**Data Source:** Security Module occupancy by zone

**Implementation Pattern:**

```typescript
// Lighting Module (Phase 28)
import { useOccupancy } from '@/lib/api'

function LightingOptimizer() {
  const siteId = 'site-002'
  const { data: occupancy } = useOccupancy(siteId)

  useEffect(() => {
    if (!occupancy?.by_zone) return

    // Adjust lighting per zone based on occupancy
    Object.entries(occupancy.by_zone).forEach(([zoneId, count]) => {
      let brightness = 50 // default

      if (count === 0) {
        brightness = 0 // unoccupied → off
      } else if (count > 20) {
        brightness = 100 // crowded → full brightness
      } else if (count > 5) {
        brightness = 75 // moderate occupancy
      }

      // Account for daylight harvesting
      const daylightLevel = getDaylightLevel()
      brightness = Math.max(brightness * daylightLevel / 100, 20)

      lightingApi.setZoneBrightness(siteId, zoneId, brightness)
    })
  }, [occupancy])
}
```

## Mutation Hooks (State Changes)

### Check In/Out Visitor

```typescript
import { useCheckInVisitor, useCheckOutVisitor } from '@/lib/api'

function VisitorCard({ visitor }) {
  const { mutate: checkIn, isLoading: checkingIn } = useCheckInVisitor()
  const { mutate: checkOut, isLoading: checkingOut } = useCheckOutVisitor()

  return (
    <div>
      <button 
        onClick={() => checkIn({ visitorId: visitor.id })}
        disabled={checkingIn || visitor.status === 'checked_in'}
      >
        Check In
      </button>
      <button 
        onClick={() => checkOut({ visitorId: visitor.id })}
        disabled={checkingOut || visitor.status !== 'checked_in'}
      >
        Check Out
      </button>
    </div>
  )
}
```

### Acknowledge Alert

```typescript
import { useAcknowledgeAlert } from '@/lib/api'

function AlertCard({ alert }) {
  const { mutate: acknowledge, isLoading } = useAcknowledgeAlert()

  if (alert.status === 'acknowledged') {
    return <div>Alert acknowledged</div>
  }

  return (
    <button 
      onClick={() => acknowledge({ alertId: alert.id })}
      disabled={isLoading}
    >
      Acknowledge
    </button>
  )
}
```

## API Integration Patterns

### Direct API Calls (When Hooks Insufficient)

```typescript
import { securityApi } from '@/lib/api'

// Get overview directly
const overview = await securityApi.getOverview('site-002')

// Record event from external system
await securityApi.recordEvent({
  site: 'site-002',
  access_point: 'Main Entrance',
  person_name: 'John Smith',
  status: 'granted',
  access_type: 'badge'
})

// Get occupancy for calculations
const occupancy = await securityApi.getOccupancy('site-002')
console.log(`Building occupancy: ${occupancy.total_occupancy}`)
```

### Backend Integration (HVAC/Lighting Services)

```python
# backend/app/services/hvac_service.py
from app.database.repositories.security_repository import SecurityRepository

class HVACOptimizer:
    def __init__(self):
        self.security_repo = SecurityRepository()

    async def adjust_for_occupancy(self, site_id: str):
        # Get current occupancy
        occupancy = await self.security_repo.get_occupancy(site_id)
        
        # Adjust setpoint
        if occupancy['total_occupancy'] == 0:
            setpoint = 16  # Empty → energy save
        elif occupancy['total_occupancy'] > 50:
            setpoint = 20  # Peak occupancy → cool
        else:
            setpoint = 22  # Normal
        
        # Apply HVAC change
        await self.hvac_repo.set_setpoint(site_id, setpoint)
```

## Demo Data Overview

**Location:** `backend/app/data/demo_security_data.json`

### Sample Scenarios

**Scenario 1: Normal Business Day**
- Morning arrival (6:30-8:00): 8 badge access events
- Working hours (9:00-17:00): 7 access events
- 2 visitors checked in from 9:00-11:30
- No alerts

**Scenario 2: After-Hours Activity**
- Server room access at 22:30 (after-hours alert generated)
- Late night maintenance override access
- Alert status: Acknowledged

**Scenario 3: Security Incident Simulation**
- Tailgating detection at main entrance
- Multiple persons with single badge
- Alert severity: Info (informational logging)

### Access Points

1. **Main Entrance (L0)** - Badge reader
   - 12 events today
   - Status: Active
   - Last access: 16:45

2. **Server Room (B1)** - Card reader
   - 3 events today
   - Status: Active
   - Last access: 15:30

3. **Parking Gate (L1)** - Sensor
4. **Roof Access (R)** - Override panel
5. **Emergency Exit (L2)** - Emergency sensor

## Troubleshooting

### Module Not Showing in Dashboard

**Issue:** SecurityPanel not appearing in tab list

**Solutions:**
1. Check module is activated: `GET /api/modules/available`
2. Verify ModularDashboard imported in App.tsx
3. Check SecurityPanel component path is correct

### Occupancy Always Zero

**Issue:** Building occupancy shows 0 even when people present

**Cause:** No recent badge access in last 30 minutes OR no checked-in visitors

**Solutions:**
1. Create test event: `POST /api/security/events`
2. Manually check in visitor: `POST /api/security/visitors/{id}/checkin`
3. Verify recent access events: `GET /api/security/events?after_hours=false`

### Stale Occupancy Data

**Issue:** Occupancy not updating in real-time

**Cause:** React Query cache still valid (15s stale time)

**Solutions:**
1. Wait 15 seconds for automatic refetch
2. Create new access event to trigger refetch
3. Force refetch: Component's `queryClient.invalidateQueries()`

## Testing

### Component Testing

```typescript
import { render, screen, waitFor } from '@testing-library/react'
import { SecurityPanel } from '@/components/modules/SecurityPanel'

it('renders overview tab with stats', async () => {
  render(<SecurityPanel siteId="site-002" />)
  
  await waitFor(() => {
    expect(screen.getByText(/15 access events/)).toBeInTheDocument()
    expect(screen.getByText(/2 active visitors/)).toBeInTheDocument()
  })
})
```

### API Testing

```bash
# Test overview endpoint
curl "http://localhost:9095/api/security/overview?site=site-002"

# Test occupancy for HVAC integration
curl "http://localhost:9095/api/security/occupancy?site=site-002"

# Test event recording
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "site": "site-002",
    "access_point": "Main Entrance",
    "person_name": "Test User",
    "status": "granted",
    "access_type": "badge"
  }' \
  http://localhost:9095/api/security/events
```

## Performance Considerations

### Caching Strategy

- Security module uses 15-30 second stale times for real-time data
- Access points use 5 minute cache (rarely change)
- Batch aggregation: Multiple hook calls within 50ms window = 1 API call

### Optimization Tips

1. **Use React Query hooks** instead of direct API calls (automatic caching)
2. **Batch event queries** when possible (combine multiple filters)
3. **Use occupancy endpoint** for HVAC/Lighting decisions (not polling events)
4. **Avoid repeated alerts** - cache alert list, poll only for new ones

### Monitoring

```bash
# Monitor query performance (React DevTools)
F12 → React Query → View cache status
# Shows: stale time, last fetch, cache size, hit rate

# Monitor network (Network tab)
# Look for: /api/security/* endpoints, batch calls, no duplicates
```

## Security Considerations

### Authentication

- All endpoints require valid JWT token in `Authorization` header
- Read-only operations: `AUTHENTICATED` role sufficient
- Write operations (create alerts, record events): `OPERATOR` role required

### Data Privacy

- Visitor data: Contains personal info (name, company, host)
- Access events: Personal movement logs
- See SECURITY.md for privacy policies and data handling

### Rate Limiting

- Prevent API abuse through rate limiting
- Batch endpoints have higher quota (encourage efficient usage)
- Implement exponential backoff for retries

## Future Enhancements (Phase 28+)

1. **Real Access Control Integration**
   - Connect to actual BACnet card readers
   - Receive events from access control system webhooks

2. **HVAC/Lighting Cross-Module Integration**
   - HVAC uses occupancy for setpoint optimization
   - Lighting uses occupancy for zone-based dimming

3. **Advanced Security Features**
   - CCTV camera feed integration
   - Biometric access (fingerprint, facial recognition)
   - Pattern recognition for suspicious activity

4. **Compliance & Reporting**
   - Access logs for audit trails
   - Visitor history reports
   - Security incident statistics

## Related Documentation

- **API Reference:** `docs/03-api-reference/security-api.md`
- **Feature Overview:** `docs/04-features/27-sentinel-security.md`
- **Modular Architecture:** `docs/06-module-architecture/module-patterns.md`
- **Phase 28 Planning:** `.planning/phases/28-sentinel-compliance/`

---

**Documentation Version:** 1.0
**Last Updated:** 2026-02-13
**Maintained by:** BMS Intelligence Development Team
