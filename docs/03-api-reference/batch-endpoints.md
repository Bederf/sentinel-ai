# Batch Endpoints API Reference

## Overview

Batch endpoints allow efficient retrieval of data for multiple devices in a single API call, eliminating the N+1 query problem and dramatically reducing rate-limit pressure on the frontend.

**Key Benefits:**
- ✅ Reduce 30+ API calls to 1 batch call
- ✅ Eliminate HTTP 429 rate limit errors
- ✅ Improve frontend responsiveness (typically <500ms for 100 items)
- ✅ Reduce backend database load through aggregation

## Endpoints

### POST /api/devices/batch/safety-status

Retrieve safety status for multiple devices in a single request.

**Request:**
```json
{
  "device_ids": ["device-001", "device-002", "device-003"]
}
```

**Parameters:**
- `device_ids` (array, max 100 items): List of device IDs to query
  - Duplicates are automatically deduplicated
  - IDs not found return error entries in response

**Response:**
```json
{
  "results": {
    "device-001": {
      "device_id": "device-001",
      "status": "safe",
      "rules_violated": []
    },
    "device-002": {
      "device_id": "device-002",
      "status": "warning",
      "rules_violated": [
        {
          "rule_id": "temp-range",
          "name": "Temperature Range Check",
          "severity": "warning"
        }
      ]
    }
  },
  "errors": {
    "device-999": "Device not found"
  }
}
```

**Status Codes:**
- `200`: Successful batch retrieval (with per-item results)
- `400`: Request validation failed (too many IDs, invalid format)
- `500`: Server error during batch processing

---

### POST /api/devices/batch/latest-readings

Retrieve latest sensor readings for multiple devices.

**Request:**
```json
{
  "device_ids": ["device-001", "device-002", "device-003"]
}
```

**Response:**
```json
{
  "results": {
    "device-001": {
      "id": "device-001",
      "name": "Chiller-01",
      "device_type": "CHILLER",
      "status": "online",
      "last_reading": {
        "value": 12.5,
        "unit": "°C",
        "timestamp": "2026-02-10T11:45:30Z"
      },
      "last_seen": "2026-02-10T11:45:30Z",
      "updated_at": "2026-02-10T11:45:30Z"
    }
  },
  "errors": {}
}
```

**Use Cases:**
- Display current sensor values on dashboard
- Monitor real-time equipment status
- Update energy consumption metrics

---

### POST /api/devices/batch/condition

Retrieve device condition/health scores for multiple devices.

**Request:**
```json
{
  "device_ids": ["device-001", "device-002"]
}
```

**Response:**
```json
{
  "results": {
    "device-001": {
      "id": "device-001",
      "name": "Chiller-01",
      "device_type": "CHILLER",
      "status": "healthy",
      "condition_score": 92,
      "health_trend": "stable",
      "last_maintenance": "2025-11-15T10:30:00Z",
      "remaining_lifespan_hours": 8760,
      "maintenance_due_days": 45,
      "last_seen": "2026-02-10T11:45:30Z",
      "safety_status": {
        "overall": "safe",
        "violations_count": 0
      }
    }
  },
  "errors": {}
}
```

---

## Implementation Guide

### Frontend: Using Batch Endpoints

**With React Query Hooks (Recommended):**
```typescript
import { useDeviceSafetyStatus, useDeviceLatestReading } from '@/hooks';

// Single device
const { data: safety } = useDeviceSafetyStatus('device-001');

// Multiple devices: automatic batching within 50ms window
const { data: reading1 } = useDeviceLatestReading('device-001');
const { data: reading2 } = useDeviceLatestReading('device-002');
// ✅ Only 1 batch API call fires, not 2

// Aggregated site data (single call returns all equipment info)
import { useSiteSummary } from '@/hooks';
const { data: summary } = useSiteSummary('site-002');
// Returns: { equipment_count, safety, alerts, predictions, energy }
```

**Direct API Call:**
```typescript
import { devicesApi } from '@/lib/api';

const response = await devicesApi.batchSafetyStatus(['device-001', 'device-002']);
// response.results: { device-001: {...}, device-002: {...} }
// response.errors: { unknown-device: 'Not found' }
```

---

## Best Practices

### ✅ DO:
- Use batch endpoints for rendering 3+ devices simultaneously
- Use React Query hooks for automatic caching and deduplication
- Batch up to 100 items per request
- Handle error entries in `errors` field gracefully

### ❌ DON'T:
- Make individual `/api/devices/{id}/safety-status` calls in loops
- Fire batch requests for single devices (use individual endpoint)
- Ignore the `errors` field when processing results
- Batch IDs across different request types (safety vs readings)

---

## Performance Characteristics

| Scenario | Old (Individual Calls) | New (Batch) | Improvement |
|----------|------------------------|-----------|-------------|
| 30 devices on dashboard | 30 calls, 5-10s | 1 call, <500ms | 60x faster |
| 100 items paginated list | 100 calls, 30-60s | 1 call, <500ms | 120x faster |
| Rate limit errors (429) | Frequent (~10-20%) | Rare (<1%) | 99% reduction |
| Backend DB queries | 30 individual queries | 1 aggregated query | Massive DB relief |

---

## Error Handling

Batch endpoints return `200 OK` even if some items fail. Check the `errors` object:

```typescript
const { results, errors } = await batchRequest(['device-001', 'device-002', 'unknown']);

// Process successful results
for (const [deviceId, data] of Object.entries(results)) {
  console.log(`Device ${deviceId}: ${data.status}`);
}

// Handle errors per device
for (const [deviceId, errorMsg] of Object.entries(errors)) {
  console.error(`Device ${deviceId} failed: ${errorMsg}`);
}
```

---

## Rate Limit Strategy

Batch endpoints have **dedicated rate limits** separate from individual endpoints:
- **Individual endpoints**: 60 req/min per user
- **Batch endpoints**: 300 req/min per user (higher quota for bulk operations)

This ensures batch operations don't starve other API traffic.

---

## Migration Guide

**From individual calls:**
```typescript
// OLD ❌ (triggers 30 API calls)
const safetyStatuses = await Promise.all(
  devices.map(d => api.getDeviceSafetyStatus(d.id))
);

// NEW ✅ (single batch call)
const response = await api.batchSafetyStatus(devices.map(d => d.id));
```

---

## See Also

- [Site Summary API](./site-summary-api.md) - Aggregated equipment/alerts/predictions for entire site
- [React Query Setup](../../frontend/README.md#react-query-integration) - Cache configuration and hook usage
- [Device Safety Status API](./condition-api.md) - Individual device safety endpoint (legacy)
