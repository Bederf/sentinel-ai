---
title: "Devices API Reference (Legacy)"
type: "reference"
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

# Devices API Reference (Legacy)

## ⚠️ DEPRECATION NOTICE

**Status:** DEPRECATED in favor of batch endpoints (Phase 75, Feb 2026)

This API remains for backward compatibility but is **no longer recommended** for new development. Individual device endpoints cause the N+1 query problem and contribute to rate limiting issues.

**Migration:** Use batch endpoints instead:
- Individual endpoint → `POST /api/devices/batch/safety-status`
- Use React Query hooks for automatic caching and deduplication

---

## Deprecated Endpoints

### GET /api/devices/{device_id}/safety-status

**Status:** DEPRECATED - Use `POST /api/devices/batch/safety-status` instead

Retrieve safety status for a single device.

**Parameters:**
- `device_id` (path): Device identifier

**Response:**
```json
{
  "device_id": "device-001",
  "status": "safe",
  "rules_violated": []
}
```

**Why it's deprecated:**
- Making individual calls for multiple devices causes N+1 problem (30 devices = 30 API calls)
- Batch endpoint reduces 30 calls to 1 → 60x faster
- Increased rate limiting due to high request volume

**Migration:**
```typescript
// OLD ❌ (triggers 30 API calls)
const safetyStatus = await fetch(`/api/devices/${deviceId}/safety-status`);

// NEW ✅ (single batch call)
const response = await fetch('/api/devices/batch/safety-status', {
  method: 'POST',
  body: JSON.stringify({ device_ids: [deviceId] })
});
```

---

### GET /api/devices/{device_id}/readings

**Status:** DEPRECATED - Use `POST /api/devices/batch/latest-readings` instead

Retrieve latest readings for a single device.

**Why it's deprecated:** Same N+1 problem as safety-status endpoint.

**Migration:** Use `POST /api/devices/batch/latest-readings` with device ID array.

---

### GET /api/devices/{device_id}/condition

**Status:** DEPRECATED - Use `POST /api/devices/batch/condition` instead

Retrieve condition/health score for a single device.

**Why it's deprecated:** Same N+1 problem as other individual endpoints.

**Migration:** Use `POST /api/devices/batch/condition` with device ID array.

---

## Migration Path

### Step 1: Identify Usage
Search your code for calls to individual device endpoints:
```bash
grep -r "GET /api/devices/" src/
grep -r "/api/devices/.*/safety-status" src/
grep -r "/api/devices/.**/readings" src/
grep -r "/api/devices/.**/condition" src/
```

### Step 2: Replace with Batch Calls
If fetching multiple devices, replace with batch:
```typescript
// OLD ❌
async function getSafetyStatuses(deviceIds) {
  return Promise.all(
    deviceIds.map(id =>
      fetch(`/api/devices/${id}/safety-status`)
    )
  );
}

// NEW ✅
async function getSafetyStatuses(deviceIds) {
  const response = await fetch('/api/devices/batch/safety-status', {
    method: 'POST',
    body: JSON.stringify({ device_ids: deviceIds })
  });
  return response.json();
}
```

### Step 3: Use React Query Hooks
Instead of manual fetching, use the provided hooks (automatically batches within 50ms window):
```typescript
import { useDeviceSafetyStatus } from '@/hooks';

// Automatically batches multiple calls within 50ms
const { data: status1 } = useDeviceSafetyStatus('device-001');
const { data: status2 } = useDeviceSafetyStatus('device-002');
const { data: status3 } = useDeviceSafetyStatus('device-003');
// Only 1 batch API call fires!
```

---

## Performance Comparison

| Metric | Individual Endpoint | Batch Endpoint | Improvement |
|--------|-------------------|-----------------|-------------|
| API calls for 30 devices | 30 | 1 | 30x reduction |
| Response time | 5-10 seconds | <500ms | 20x faster |
| Rate limiting errors | Frequent | Rare | 99% reduction |
| Backend database load | 30 queries | 1 query | Massive relief |
| Frontend code complexity | High | Low | Cleaner with hooks |

---

## When Individual Endpoints Are OK

Individual device endpoints are acceptable ONLY when:
- Fetching a single device in isolation (not in a list)
- User specifically navigated to a device detail page
- No other concurrent device requests

**Example:** Device detail modal for one specific device → OK to use individual endpoint

**Counter-example:** Rendering a list of 10 devices → MUST use batch endpoint

---

## See Also

- [Batch Endpoints API](./batch-endpoints.md) - Modern replacement for individual calls
- [Site Summary API](./site-summary-api.md) - Aggregated site data in single call
- [Frontend README - React Query](../../frontend/README.md) - Hook-based data fetching strategy
