# Security Module API Reference

## Overview

The Security API provides access to security system monitoring, access control event tracking, anomaly detection, and real-time occupancy data integrated with HVAC and lighting systems.

**Base URL:** `/api/security`

## Authentication

All endpoints require valid JWT token in `Authorization: Bearer <token>` header.

## Endpoints

### System Status

#### GET `/api/security/status`

Get overall security system status including door count, camera count, alarm zones, and occupancy.

**Rate Limit:** 30 requests/minute

**Response:**
```json
{
  "total_doors": 15,
  "doors_secure": 14,
  "cameras_online": 12,
  "cameras_total": 12,
  "alarm_zones_armed": 8,
  "alarm_zones_total": 10,
  "active_alerts": 2,
  "occupancy_total": 47
}
```

---

### C•CURE 9000 Integration Status

#### GET `/api/security/ccure/status`

Get C•CURE 9000 integration status, license information, and demo mode status.

**Rate Limit:** 30 requests/minute

**Response:**
```json
{
  "mode": "demo",
  "manufacturer": "Johnson Controls / Software House",
  "model": "C•CURE 9000 v2.90",
  "protocol": "victor Web Service API",
  "license_status": "partner_license_required",
  "message": "Demo mode active. Apply to Software House Connected Partner Program to enable live integration.",
  "demo_events_count": 5,
  "demo_doors_count": 2,
  "demo_controllers_count": 2
}
```

**Status Codes:**
- `200` — Integration working (demo or live)
- `503` — Integration unavailable

---

### Security Anomalies

#### GET `/api/security/events/anomalies`

Get security anomalies detected over the specified time window.

**Rate Limit:** 30 requests/minute

**Query Parameters:**
- `since` (string, optional) — Time window: `24h`, `7d`, `30d`. Default: `24h`
- `anomaly_type` (string, optional) — Filter by type: `after_hours_access`, `controller_offline`, `forced_door`, `door_held_open`, `anti_passback`, `tamper`

**Response:**
```json
{
  "anomalies": [
    {
      "type": "after_hours_access",
      "severity": "warning",
      "badge_event": {
        "person_name": "Johan van der Merwe",
        "department": "IT Operations",
        "timestamp": "2026-02-10T21:30:00Z"
      },
      "hvac_correlation": {
        "zone_id": "HVAC-ZN-L1",
        "activated_at": "2026-02-10T21:35:00Z",
        "setpoint_before": 28,
        "setpoint_after": 22,
        "mode": "cooling"
      },
      "lighting_correlation": {
        "zone_id": "DALI-ZN-L1",
        "activated_at": "2026-02-10T21:32:00Z",
        "brightness_before": 0,
        "brightness_after": 100
      },
      "energy_impact": "Estimated 4.25 kWh excess consumption per hour",
      "recommendation": "After-hours access by Johan van der Merwe. Consider: reduce HVAC setpoint to +2°C unoccupied mode, dim lights to 50% if low occupancy to save energy. Verify access was authorized.",
      "detected_at": "2026-02-10T21:36:00Z"
    },
    {
      "type": "controller_offline",
      "severity": "critical",
      "controller": {
        "controller_id": "CCURE-CTL-003",
        "name": "iSTAR Edge - Level 3",
        "model": "iSTAR Edge",
        "status": "offline",
        "firmware": "5.10.1"
      },
      "network_status": {
        "switch": "SW-01",
        "port": "GigabitEthernet1/0/24",
        "status": "down"
      },
      "ups_status": {
        "battery_level": 95,
        "status": "online",
        "estimated_runtime_minutes": 45
      },
      "recommendation": "Controller iSTAR Edge - Level 3 offline due to network issue. Check switch SW-01 port GigabitEthernet1/0/24. UPS battery at 95% - system stable.",
      "detected_at": "2026-02-10T03:22:00Z"
    }
  ],
  "count": 2,
  "summary": {
    "after_hours_count": 1,
    "equipment_health_count": 1
  }
}
```

**Response Fields:**
- `anomalies` — Array of detected anomalies with correlations and recommendations
- `count` — Total anomalies detected in time window
- `summary` — Breakdown by anomaly category

**Anomaly Types:**

| Type | Severity | Description |
|------|----------|-------------|
| `after_hours_access` | warning | Badge access outside business hours (18:00-06:00) with HVAC/lighting activation |
| `controller_offline` | critical | iSTAR controller lost network connection |
| `forced_door` | critical | Door opened without valid credential |
| `door_held_open` | warning | Door held open beyond threshold (typically 3 min) |
| `anti_passback` | warning | Same badge used at entry without prior exit recorded |
| `tamper` | critical | Controller enclosure tamper detected |

**Status Codes:**
- `200` — Anomalies retrieved successfully
- `400` — Invalid time window or anomaly type filter
- `503` — Anomaly detection service unavailable

---

### Real-Time Occupancy

#### GET `/api/security/occupancy/real-time`

Get real-time zone occupancy calculated from badge events, with cross-module recommendations for HVAC/lighting adjustments.

**Rate Limit:** 30 requests/minute

**Query Parameters:**
- `site_id` (string, optional) — Site identifier. Default: `site-002` (Sandton City)

**Response:**
```json
{
  "site_id": "site-002",
  "zones": [
    {
      "zone_id": "CCURE-ZN-L1-EXEC",
      "zone_name": "Level 1 - Executive Suite",
      "occupancy_count": 3,
      "badge_entries": 5,
      "badge_exits": 2,
      "last_updated": "2026-02-10T14:32:00Z",
      "source": "badge"
    },
    {
      "zone_id": "CCURE-ZN-L0-PLANT",
      "zone_name": "Ground Floor - Plant Room",
      "occupancy_count": 0,
      "badge_entries": 1,
      "badge_exits": 1,
      "last_updated": "2026-02-10T14:20:00Z",
      "source": "badge"
    }
  ],
  "building_total": 3,
  "recommendations": {
    "hvac": [
      {
        "zone_id": "CCURE-ZN-L0-PLANT",
        "zone_name": "Ground Floor - Plant Room",
        "occupancy": 0,
        "recommendation": "relax_setpoint",
        "detail": "Zone Ground Floor - Plant Room is empty. Recommend relaxing cooling setpoint by +2°C to save energy.",
        "setpoint_offset": 2,
        "module": "hvac"
      }
    ],
    "lighting": [
      {
        "zone_id": "CCURE-ZN-L0-PLANT",
        "zone_name": "Ground Floor - Plant Room",
        "occupancy": 0,
        "recommendation": "dim_to_minimum",
        "detail": "Zone Ground Floor - Plant Room is empty. Recommend dimming lights to 20%.",
        "brightness_level": 20,
        "module": "lighting"
      }
    ],
    "total_recommendations": 2,
    "dali_data_available": false
  },
  "updated_at": "2026-02-10T14:32:00Z"
}
```

**Response Fields:**
- `zones` — Per-zone occupancy derived from badge entry/exit events
- `building_total` — Total occupancy across all zones
- `recommendations` — HVAC and lighting adjustments based on occupancy
- `dali_data_available` — Whether DALI PIR sensor data is available for combined occupancy

**Status Codes:**
- `200` — Occupancy data retrieved successfully
- `400` — Invalid site ID
- `503` — Occupancy service unavailable

---

### Zone Occupancy

#### GET `/api/security/occupancy/{zone_id}`

Get occupancy for a specific zone calculated from badge events.

**Rate Limit:** 30 requests/minute

**Path Parameters:**
- `zone_id` (string, required) — Zone identifier (e.g., `CCURE-ZN-L1-EXEC`)

**Response:**
```json
{
  "zone_id": "CCURE-ZN-L1-EXEC",
  "zone_name": "Level 1 - Executive Suite",
  "occupancy_count": 3,
  "badge_entries": 5,
  "badge_exits": 2,
  "last_updated": "2026-02-10T14:32:00Z",
  "source": "badge"
}
```

**Status Codes:**
- `200` — Zone occupancy retrieved successfully
- `404` — Zone not found
- `503` — Occupancy service unavailable

---

## Error Responses

All endpoints return standardized error responses:

```json
{
  "detail": "Error description",
  "status_code": 400,
  "timestamp": "2026-02-10T14:32:00Z"
}
```

**Common Status Codes:**
- `400` — Bad request (invalid parameters)
- `401` — Unauthorized (missing or invalid token)
- `403` — Forbidden (insufficient permissions)
- `404` — Not found (resource doesn't exist)
- `429` — Rate limit exceeded (wait before retrying)
- `500` — Internal server error
- `503` — Service unavailable

---

## Rate Limiting

Security endpoints are rate-limited to prevent abuse:

- **Standard limit:** 30 requests/minute per authenticated user
- **Burst limit:** 100 requests/minute (allows short bursts)
- **Backoff:** Exponential backoff on 429 responses

**Response Headers:**
```
X-RateLimit-Limit: 30
X-RateLimit-Remaining: 29
X-RateLimit-Reset: 1707569400
```

---

## Examples

### Python

```python
import httpx

async with httpx.AsyncClient() as client:
    # Get current anomalies
    response = await client.get(
        "http://localhost:9095/api/security/events/anomalies?since=24h",
        headers={"Authorization": f"Bearer {token}"}
    )
    anomalies = response.json()

    # Get real-time occupancy
    occupancy = await client.get(
        "http://localhost:9095/api/security/occupancy/real-time",
        headers={"Authorization": f"Bearer {token}"}
    )
    zones = occupancy.json()
```

### JavaScript/TypeScript

```typescript
import { securityApi } from '@/lib/api'

// Get anomalies
const anomalies = await securityApi.getAnomalies({ since: '24h' })

// Get real-time occupancy
const occupancy = await securityApi.getRealTimeOccupancy()
```

### cURL

```bash
# Get C•CURE status
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:9095/api/security/ccure/status

# Get anomalies (last 24 hours, warning only)
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:9095/api/security/events/anomalies?since=24h&anomaly_type=after_hours_access"

# Get real-time occupancy
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:9095/api/security/occupancy/real-time
```

---

## See Also

- [C•CURE 9000 Integration Guide](../integrations/ccure-9000-integration.md)
- [Security Module Features](../04-features/58-security-module.md)
- [System Health API](./system-health-api.md)
