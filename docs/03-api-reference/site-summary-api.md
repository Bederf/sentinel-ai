# Site Summary API Reference

## Overview

The Site Summary API provides a comprehensive snapshot of a site's operations in a single request, including equipment inventory, safety status, active alerts, predictions, and energy consumption.

**Use Case:** Dashboard display showing complete site status without making 5+ separate API calls.

---

## Endpoints

### GET /api/sites/{site_id}/summary

Retrieve comprehensive summary for a single site.

**Parameters:**
- `site_id` (path): Site identifier (e.g., `site-002`)

**Response:**
```json
{
  "site_id": "site-002",
  "site_name": "Sandton City Office Tower",
  "last_updated": "2026-02-10T11:45:30Z",

  "equipment": {
    "total_count": 156,
    "by_type": {
      "CHILLER": 2,
      "AHU": 12,
      "FCU": 24,
      "VAV": 48,
      "DALI": 60,
      "MTR": 8,
      "GEN": 1,
      "UPS": 1
    }
  },

  "safety": {
    "total_devices": 156,
    "safe_count": 148,
    "warning_count": 6,
    "blocked_count": 2,
    "alarm_count": 0,
    "overall_status": "warning",
    "devices_with_issues": ["CHILLER-01", "AHU-02", "FCU-15", "VAV-23", "DALI-45", "MTR-07"]
  },

  "alerts": {
    "critical": 1,
    "warning": 5,
    "info": 12,
    "total_active": 18
  },

  "predictions": {
    "high_risk": 3,
    "medium_risk": 7,
    "low_risk": 12
  },

  "energy": {
    "current_kw": 245.7,
    "today_kwh": 4832.1,
    "peak_kw": 312.5,
    "average_kw": 201.3
  }
}
```

---

### GET /api/sites/{site_id}/alerts

Retrieve paginated alerts for a site.

**Parameters:**
- `site_id` (path): Site identifier
- `page` (query, optional): Page number (default: 1)
- `per_page` (query, optional): Items per page (default: 20, max: 100)
- `severity` (query, optional): Filter by severity (critical, warning, info)

**Response:**
```json
{
  "total": 18,
  "page": 1,
  "per_page": 10,
  "alerts": [
    {
      "id": "alert-001",
      "equipment_id": "CHILLER-01",
      "equipment_name": "Chiller - Building A",
      "severity": "critical",
      "title": "High Discharge Pressure",
      "description": "Chiller discharge pressure exceeded safe operating range",
      "timestamp": "2026-02-10T11:30:00Z",
      "source": "device_monitoring",
      "resolved": false
    },
    {
      "id": "alert-002",
      "equipment_id": "AHU-02",
      "equipment_name": "Air Handling Unit - Floor 2",
      "severity": "warning",
      "title": "Filter Pressure Drop High",
      "description": "Air filter requires replacement soon",
      "timestamp": "2026-02-10T10:15:00Z",
      "resolved": false
    }
  ]
}
```

---

### GET /api/sites/{site_id}/predictions

Retrieve risk predictions for a site.

**Parameters:**
- `site_id` (path): Site identifier

**Response:**
```json
{
  "site_id": "site-002",
  "timestamp": "2026-02-10T11:45:30Z",
  "predictions": [
    {
      "prediction_id": "pred-001",
      "equipment_id": "CHILLER-01",
      "equipment_name": "Chiller - Building A",
      "equipment_type": "CHILLER",
      "prediction_type": "compressor_failure",
      "risk_level": "high",
      "probability_percent": 78,
      "timeframe_days": 7,
      "confidence": "HIGH",
      "financial_impact": {
        "potential_loss_zar": 45000,
        "repair_cost_zar": 28000,
        "downtime_hours": 6
      }
    }
  ],
  "summary": {
    "high_risk_count": 3,
    "medium_risk_count": 7,
    "total_potential_loss_zar": 180000
  }
}
```

---

## Implementation Guide

### Using React Query Hooks

**Recommended: Site Summary Hook**
```typescript
import { useSiteSummary } from '@/hooks';

export function DashboardSummary({ siteId }) {
  const { data: summary, isLoading, error } = useSiteSummary(siteId);

  if (isLoading) return <div>Loading...</div>;
  if (error) return <div>Error: {error.message}</div>;

  return (
    <div>
      <h2>{summary.site_name}</h2>
      <p>Equipment: {summary.equipment.total_count}</p>
      <p>Safety Status: {summary.safety.overall_status}</p>
      <p>Active Alerts: {summary.alerts.total_active}</p>
      <p>Current Power: {summary.energy.current_kw} kW</p>
    </div>
  );
}
```

**Alerts & Predictions Hooks**
```typescript
import { useSiteAlerts, useSitePredictions } from '@/hooks';

// Alerts with pagination
const { data: alertsPage } = useSiteAlerts(siteId);

// Predictions
const { data: predictions } = useSitePredictions(siteId);
```

---

## Cache Strategy

All endpoints use React Query with these configurations:

| Endpoint | Stale Time | Cache TTL | Refetch |
|----------|-----------|-----------|----------|
| `/api/sites/{id}/summary` | 30s | 5m | On window focus |
| `/api/sites/{id}/alerts` | 15s | 5m | Every 30s (auto) |
| `/api/sites/{id}/predictions` | 60s | 5m | Manual only |

**Rationale:**
- Summary: Equipment status relatively stable, hourly changes typical
- Alerts: More volatile, automatic refetch every 30s catches new issues
- Predictions: ML model runs infrequently, manual refresh sufficient

---

## Performance Impact

**Before Site Summary API:**
```
GET /api/sites/site-002/summary requires:
- GET /api/sites/site-002 (1 call)
- GET /api/sites/site-002/equipment (1 call)
- GET /api/sites/site-002/alerts (1 call)
- GET /api/sites/site-002/predictions (1 call)
- GET /api/sites/site-002/energy (1 call)

Total: 5 API calls, typically 2-5 seconds
```

**After Site Summary API:**
```
GET /api/sites/site-002/summary (1 call)
- Backend executes single Supabase RPC query
- Aggregates results in JSON

Total: 1 API call, typically <500ms
```

---

## Error Handling

### Not Found
```
GET /api/sites/unknown-site/summary
→ 404 Not Found
→ { "detail": "Site not found" }
```

### Unauthorized
```
GET /api/sites/site-002/summary (without auth)
→ 401 Unauthorized
→ Login required
```

### Server Error
```
→ 500 Internal Server Error
→ { "detail": "Database error during aggregation" }
```

---

## Data Consistency

The Site Summary API aggregates data from multiple tables:
- `equipment` - Equipment inventory and metadata
- `device_safety_status` - Current safety status per device
- `alerts` - Active and historical alerts
- `predictions` - ML-generated risk predictions
- `energy_readings` - Current and historical energy data

All data is fetched in a **single Supabase RPC call** to ensure consistency (no intermediate state changes between queries).

---

## Related APIs

- [Batch Endpoints](./batch-endpoints.md) - For device-level data (safety, readings, condition)
- [Alerts API](./alerts.md) - Detailed alert query and management
- [ML Predictions API](./ml-predictions-api.md) - Advanced prediction filtering and details
- [Energy API](./timeseries-api.md) - Time-series energy data

---

## Example: Dashboard Implementation

```typescript
import { useSiteSummary, useSiteAlerts } from '@/hooks';
import { EquipmentCard } from './EquipmentCard';

export function Dashboard({ siteId }) {
  const { data: summary } = useSiteSummary(siteId);
  const { data: alerts } = useSiteAlerts(siteId);

  if (!summary) return null;

  return (
    <div>
      {/* KPI Row */}
      <div className="grid grid-cols-4 gap-4">
        <KPICard
          label="Equipment"
          value={summary.equipment.total_count}
        />
        <KPICard
          label="Safety Status"
          value={summary.safety.overall_status}
        />
        <KPICard
          label="Active Alerts"
          value={summary.alerts.total_active}
        />
        <KPICard
          label="Power Usage"
          value={`${summary.energy.current_kw} kW`}
        />
      </div>

      {/* Equipment Grid */}
      <div className="grid grid-cols-4 gap-4 mt-6">
        {summary.safety.devices_with_issues.map(deviceName => (
          <EquipmentCard key={deviceName} name={deviceName} />
        ))}
      </div>

      {/* Recent Alerts */}
      <div className="mt-6">
        <h3>Recent Alerts ({alerts.total})</h3>
        {alerts.alerts.slice(0, 5).map(alert => (
          <AlertItem key={alert.id} alert={alert} />
        ))}
      </div>
    </div>
  );
}
```

**Result:** Single Site Summary API call instead of 5+ individual calls → Dashboard loads in <500ms.
