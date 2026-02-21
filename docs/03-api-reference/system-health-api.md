# System Health & Diagnostics API Reference

**Base URL:** `http://localhost:9095/api`  
**Authentication:** Bearer token (via JWT)  
**Rate Limiting:** Per-endpoint (see details below)  
**Cache:** Redis (30s default TTL)  

---

## Endpoints

### GET /api/system/health

Retrieves unified system health snapshot aggregating 15+ backend endpoints.

**Purpose:** Central monitoring endpoint for real-time system status overview.

**Method:** `GET`  
**Path:** `/api/system/health`  
**Authentication:** Optional (public by default)  
**Rate Limit:** 60 requests/minute  
**Cache:** Redis 30s TTL (key: `system:health:current`)  
**Response Time:** <2 seconds (cached), <5 seconds (fresh)

#### Request

```bash
curl -X GET http://localhost:9095/api/system/health \
  -H "Authorization: Bearer <token>" \
  -H "Accept: application/json"
```

#### Response (200 OK)

```json
{
  "timestamp": "2024-01-15T10:30:45.123456Z",
  "overall_status": "healthy",
  "overall_score": 87,
  "components": {
    "bms_connectivity": {
      "name": "BMS Connectivity",
      "status": "healthy",
      "score": 92,
      "message": "All BMS systems online",
      "details": {
        "niagara": "connected",
        "bacnet": "connected",
        "obix": "responding",
        "dali_gateway": "ready"
      }
    },
    "api_health": {
      "name": "API Health",
      "status": "healthy",
      "score": 85,
      "message": "All REST endpoints responding",
      "details": {
        "endpoint_count": 70,
        "avg_response_time_ms": 125,
        "error_rate_percent": 0.02
      }
    },
    "database_status": {
      "name": "Database Status",
      "status": "healthy",
      "score": 95,
      "message": "Supabase, InfluxDB online",
      "details": {
        "supabase": "connected",
        "influxdb": "connected",
        "redis": "connected",
        "query_time_ms": 45
      }
    },
    "service_health": {
      "name": "Service Health",
      "status": "degraded",
      "score": 72,
      "message": "ML model delayed response detected",
      "details": {
        "ml_models": "slow",
        "ai_chat": "ready",
        "device_manager": "ready",
        "workflow_engine": "ready"
      }
    },
    "data_freshness": {
      "name": "Data Freshness",
      "status": "healthy",
      "score": 88,
      "message": "Data updates within expected intervals",
      "details": {
        "last_reading_timestamp": "2024-01-15T10:30:00Z",
        "staleness_minutes": 0.75,
        "sources": {
          "niagara_points": "within 2 min",
          "bacnet_devices": "within 5 min",
          "modbus_registers": "within 10 min"
        }
      }
    }
  },
  "active_alerts": [
    {
      "component": "service_health",
      "severity": "warning",
      "message": "ML model response time elevated (2.5s avg)"
    }
  ],
  "recommendations": [
    "Review ML model performance - consider retraining",
    "Monitor service health over next 24 hours"
  ]
}
```

#### Response Schema

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | ISO 8601 | Server time when snapshot was captured |
| `overall_status` | enum | `healthy` \| `degraded` \| `critical` |
| `overall_score` | integer (0-100) | Weighted health score |
| `components` | object | Component health details (5 keys) |
| `components[*].name` | string | Human-readable component name |
| `components[*].status` | enum | `healthy` \| `degraded` \| `critical` |
| `components[*].score` | integer (0-100) | Component-specific score |
| `components[*].message` | string | Status summary |
| `components[*].details` | object | Component-specific metrics |
| `active_alerts` | array | Current system alerts |
| `recommendations` | array | Actionable recommendations |

#### Scoring Formula

```
overall_score = (
  bms_connectivity_score × 0.30 +      # 30% weight
  database_status_score × 0.25 +        # 25% weight
  api_health_score × 0.20 +             # 20% weight
  service_health_score × 0.15 +         # 15% weight
  data_freshness_score × 0.10           # 10% weight
)

Status Mapping:
- healthy:   score ≥ 80
- degraded:  score 60-79
- critical:  score < 40
```

#### Error Responses

```json
{
  "status": 503,
  "message": "Service unavailable",
  "error": "Supabase connection failed"
}
```

| Status | Message | Cause |
|--------|---------|-------|
| 503 | Service Unavailable | All critical backends unreachable (rare) |
| 429 | Too Many Requests | Rate limit exceeded (60 req/min) |

#### Cache Behavior

- **First request:** Aggregates from 15+ endpoints (3-5 seconds)
- **Subsequent requests within 30s:** Returns cached snapshot (<100ms)
- **Cache invalidation:** On diagnostics trigger, manual flush, or 30s expiry
- **Manual clear:** `POST /api/cache/flush`

---

### GET /api/system/health/history

Retrieves historical health metrics for trend analysis.

**Purpose:** Analyze system health trends over time (24h, 7d, 30d).

**Method:** `GET`  
**Path:** `/api/system/health/history`  
**Authentication:** Optional  
**Rate Limit:** 30 requests/minute  
**Query Parameters:**
- `range` (required): `24h` | `7d` | `30d`

#### Request

```bash
curl -X GET "http://localhost:9095/api/system/health/history?range=7d" \
  -H "Authorization: Bearer <token>"
```

#### Response (200 OK)

```json
{
  "range": "7d",
  "snapshots": [
    {
      "timestamp": "2024-01-08T00:00:00Z",
      "overall_score": 78,
      "overall_status": "degraded"
    },
    {
      "timestamp": "2024-01-08T05:00:00Z",
      "overall_score": 82,
      "overall_status": "healthy"
    },
    {
      "timestamp": "2024-01-15T10:30:00Z",
      "overall_score": 87,
      "overall_status": "healthy"
    }
  ],
  "uptime_percentage": 98.5,
  "avg_score": 83,
  "min_score": 72,
  "max_score": 95,
  "trend": "improving",
  "trend_change_percent": 5.2
}
```

#### Response Schema

| Field | Type | Description |
|-------|------|-------------|
| `range` | enum | `24h` \| `7d` \| `30d` |
| `snapshots` | array | Historical snapshots (5-min intervals) |
| `snapshots[*].timestamp` | ISO 8601 | Snapshot timestamp |
| `snapshots[*].overall_score` | integer (0-100) | Health score at time |
| `snapshots[*].overall_status` | enum | Status at time |
| `uptime_percentage` | float (0-100) | % time system was healthy |
| `avg_score` | integer (0-100) | Average health score |
| `min_score` | integer (0-100) | Lowest score in range |
| `max_score` | integer (0-100) | Highest score in range |
| `trend` | enum | `improving` \| `stable` \| `degrading` |
| `trend_change_percent` | float | % change from start to end |

#### Example: Trend Analysis

```bash
# Get weekly trend
curl "http://localhost:9095/api/system/health/history?range=7d" | jq '{
  uptime: .uptime_percentage,
  avg_score: .avg_score,
  trend: .trend,
  change: .trend_change_percent
}'

# Output:
# {
#   "uptime": 98.5,
#   "avg_score": 83,
#   "trend": "improving",
#   "change": 5.2
# }
```

---

### GET /api/system/monitoring

Retrieves unified monitoring snapshot for ingestion quality, control activity, commissioning readiness, and quality gate status.

**Purpose:** Single endpoint consumed by deterministic onboarding policy flows (Phase 109C/109D).

**Method:** `GET`  
**Path:** `/api/system/monitoring`  
**Authentication:** Optional  
**Rate Limit:** 60 requests/minute  
**Cache:** None (fresh snapshot)  
**Query Parameters:**
- `building_id` (optional): Building/site ID (example: `site-002`)

#### Request

```bash
# Global snapshot (no building filter)
curl -X GET http://localhost:9095/api/system/monitoring

# Building-specific snapshot
curl -X GET "http://localhost:9095/api/system/monitoring?building_id=site-002"
```

#### Response (200 OK)

```json
{
  "ingestion_mode": "shadow_live",
  "is_live": true,
  "building_id": "site-002",
  "ingestion": {
    "freshness_hours": 0.4,
    "error_rate": 0.2,
    "unmatched_points": 8,
    "total_points": 420,
    "match_coverage": 98.1,
    "provenance_summary": {
      "live_protocol": 4,
      "file_manual": 0
    }
  },
  "control": {
    "shadow_writes_24h": 12,
    "blocked_writes_24h": 1,
    "approved_writes_24h": 44,
    "safety_violations_24h": 0
  },
  "commissioning": {
    "gates_passed": 8,
    "gates_total": 8,
    "all_gates_passed": true,
    "consecutive_pass_days": 2,
    "can_promote": true,
    "blocking_gates": []
  },
  "alerts": [],
  "trend_24h": [
    {
      "hour": "2026-02-21T08:00:00",
      "freshness_hours": 0.0,
      "error_rate": 0.0,
      "shadow_writes": 1,
      "derived": true
    }
  ],
  "checked_at": "2026-02-21T10:15:00.000000",
  "quality_gate": {
    "overall_status": "pass",
    "enforcement_action": "normal",
    "mode": "shadow_live",
    "failed_rules": [],
    "warn_rules": [],
    "reason_codes": [],
    "evaluated_at": "2026-02-21T10:15:00.000000"
  }
}
```

#### Response Schema

| Field | Type | Description |
|-------|------|-------------|
| `ingestion_mode` | enum | `simulation` \| `shadow_live` \| `live_control` |
| `is_live` | boolean | True when mode is `shadow_live` or `live_control` |
| `building_id` | string \| null | Filtered building ID if provided |
| `ingestion` | object | Ingestion health KPIs |
| `ingestion.freshness_hours` | float | Data age in hours |
| `ingestion.error_rate` | float | Ingestion error rate percentage (example: `0.2` means `0.2%`) |
| `ingestion.unmatched_points` | int | Unmatched points count |
| `ingestion.total_points` | int | Total mapped points |
| `ingestion.match_coverage` | float | Match coverage percentage (0-100) |
| `ingestion.provenance_summary` | object | Source counts by provenance class |
| `control` | object | 24h control KPIs from audit logs |
| `commissioning` | object \| null | Commissioning summary (null in simulation or when unavailable) |
| `alerts` | array | Monitoring rule alerts |
| `trend_24h` | array | 24 hourly buckets |
| `trend_24h[*].derived` | boolean | True when values are synthetic/derived from current snapshot |
| `checked_at` | ISO 8601 | Snapshot generation time |
| `quality_gate` | object \| null | Quality gate outcome and reason codes |

#### Error responses

```json
{
  "status": 500,
  "message": "Monitoring snapshot failed",
  "error": "Failed to collect monitoring data"
}
```

| Status | Message | Cause |
|--------|---------|-------|
| 500 | Monitoring snapshot failed | Aggregation or downstream source failure |

#### Notes for deterministic policy flows

- `ingestion.provenance_summary.file_manual` is used to detect provenance breach in live stages.
- `control.blocked_writes_24h + control.safety_violations_24h` is used as conflict signal.
- `commissioning.*` fields gate stage promotions.
- `quality_gate.overall_status` is used for mode-specific promotion/fail-closed decisions.

---

### POST /api/system/diagnostics

Triggers SIMBIOT diagnostic workflow for deep system inspection.

**Purpose:** Run comprehensive system diagnostics (asynchronous, polling-based).

**Method:** `POST`  
**Path:** `/api/system/diagnostics`  
**Authentication:** Optional  
**Rate Limit:** 10 requests/minute  
**Response Time:** Immediate (returns diagnostic_id)  
**Execution Time:** 30-60 seconds (async)

#### Request Body

```json
{
  "target": "full_system",
  "building_code": "site-002"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `target` | enum | Yes | `full_system` \| `building:{code}` \| `component:{name}` |
| `building_code` | string | No | Supabase building code (e.g., "site-002") |

#### Request Examples

```bash
# Full system diagnostics
curl -X POST http://localhost:9095/api/system/diagnostics \
  -H "Content-Type: application/json" \
  -d '{"target": "full_system"}'

# Building-specific diagnostics
curl -X POST http://localhost:9095/api/system/diagnostics \
  -H "Content-Type: application/json" \
  -d '{
    "target": "building:site-002",
    "building_code": "site-002"
  }'

# Component-specific diagnostics
curl -X POST http://localhost:9095/api/system/diagnostics \
  -H "Content-Type: application/json" \
  -d '{
    "target": "component:dali_gateway"
  }'
```

#### Response (202 Accepted)

```json
{
  "diagnostic_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "Diagnostics workflow started. Poll GET /api/system/diagnostics/{diagnostic_id} for results."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `diagnostic_id` | UUID | Unique identifier for polling results |
| `status` | enum | `pending` (workflow queued) |
| `message` | string | Human-readable status message |

#### Polling Pattern

Client must poll `GET /api/system/diagnostics/{diagnostic_id}` every 5 seconds:

```bash
DIAGNOSTIC_ID="550e8400-e29b-41d4-a716-446655440000"

while true; do
  RESULT=$(curl -s http://localhost:9095/api/system/diagnostics/$DIAGNOSTIC_ID)
  STATUS=$(echo $RESULT | jq -r '.status')

  echo "Status: $STATUS"

  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
    echo $RESULT | jq '.'
    break
  fi

  sleep 5
done
```

#### Error Responses

```json
{
  "status": 429,
  "message": "Rate limit exceeded",
  "error": "Maximum 10 diagnostics per minute. Try again in 30 seconds."
}
```

| Status | Message | Cause |
|--------|---------|-------|
| 429 | Rate Limit Exceeded | >10 diagnostics/minute |
| 400 | Invalid Request | Missing/invalid target parameter |
| 503 | Service Unavailable | SIMBIOT server unreachable |

---

### GET /api/system/diagnostics/{diagnostic_id}

Polls diagnostic workflow results.

**Purpose:** Retrieve results from async diagnostic workflow.

**Method:** `GET`  
**Path:** `/api/system/diagnostics/{diagnostic_id}`  
**Authentication:** Optional  
**Rate Limit:** Unlimited (polling)  
**Response Time:** <100ms (from cache)

#### Request

```bash
curl -X GET http://localhost:9095/api/system/diagnostics/550e8400-e29b-41d4-a716-446655440000
```

#### Response - Running (200 OK)

```json
{
  "diagnostic_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T10:30:00Z",
  "target": "full_system",
  "status": "running",
  "message": "Executing diagnostic tool 3 of 6: get_buildings",
  "elapsed_seconds": 15,
  "estimated_remaining_seconds": 30
}
```

#### Response - Completed (200 OK)

```json
{
  "diagnostic_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T10:30:00Z",
  "target": "full_system",
  "status": "completed",
  "duration_seconds": 47,
  "device_inventory": {
    "total_devices": 156,
    "by_type": {
      "hvac": 32,
      "lighting": 45,
      "power": 28,
      "security": 18,
      "other": 33
    },
    "offline_devices": [
      {
        "device_id": "BMS-CHILLER-001",
        "type": "hvac",
        "status": "offline",
        "last_seen": "2024-01-15T09:30:00Z"
      }
    ]
  },
  "building_config": {
    "name": "Sandton Office Tower",
    "code": "site-002",
    "floors": 3,
    "zones_per_floor": [12, 14, 10]
  },
  "alarms_found": [
    {
      "id": "alarm-001",
      "component": "S002-CHILLER-B1-001",
      "severity": "warning",
      "message": "Chiller cooling efficiency below 85%",
      "timestamp": "2024-01-15T10:15:00Z"
    }
  ],
  "health_scores": {
    "hvac_system": 82,
    "lighting_system": 91,
    "power_system": 88,
    "security_system": 92,
    "overall": 88
  },
  "asset_details": [
    {
      "asset_id": "S002-CHILLER-B1-001",
      "type": "chiller",
      "status": "operating",
      "efficiency": 84,
      "age_years": 5,
      "maintenance_due": false,
      "anomalies": [
        {
          "type": "efficiency_degradation",
          "severity": "warning",
          "details": "Cooling capacity 15% below baseline"
        }
      ]
    }
  ],
  "issues_found": [
    "Chiller cooling efficiency below target (84% vs 95% baseline)",
    "One HVAC device offline (BMS-FCU-L1-005)",
    "DALI gateway response time elevated (250ms vs 100ms baseline)"
  ],
  "recommendations": [
    "Schedule chiller maintenance within 2 weeks - cooling performance degradation detected",
    "Investigate offline FCU device - check power supply and network connectivity",
    "Review DALI network cables for potential interference"
  ],
  "next_steps": [
    "1. Review detailed chiller diagnostics in Technical Chat",
    "2. Create maintenance work order for chiller cleaning",
    "3. Check DALI gateway network logs for timing issues"
  ]
}
```

#### Response Schema

| Field | Type | Description |
|-------|------|-------------|
| `diagnostic_id` | UUID | Diagnostic workflow ID |
| `timestamp` | ISO 8601 | When workflow started |
| `target` | string | Diagnostic target scope |
| `status` | enum | `pending` \| `running` \| `completed` \| `failed` |
| `duration_seconds` | integer | Total execution time |
| `device_inventory` | object | Full device inventory |
| `building_config` | object | Building structure and zones |
| `alarms_found` | array | Active system alarms |
| `health_scores` | object | Component health scores |
| `asset_details` | array | Deep asset inspection results |
| `issues_found` | array | Identified problems |
| `recommendations` | array | Actionable recommendations |
| `next_steps` | array | Steps operators should take |

#### Response - Failed (200 OK)

```json
{
  "diagnostic_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T10:30:00Z",
  "target": "full_system",
  "status": "failed",
  "duration_seconds": 5,
  "error": "SIMBIOT server unreachable - diagnostic workflow interrupted",
  "partial_results": {
    "device_inventory": { "total_devices": 156 },
    "building_config": null,
    "alarms_found": null
  }
}
```

---

### GET /api/system/error-logs

Queries integration error history with filtering.

**Purpose:** Audit trail for troubleshooting integration failures.

**Method:** `GET`  
**Path:** `/api/system/error-logs`  
**Authentication:** Optional  
**Rate Limit:** 60 requests/minute  
**Query Parameters:**
- `category` (optional): `bms` | `api` | `database` | `service` | `other`
- `severity` (optional): `warning` | `error` | `critical`
- `resolved` (optional): `true` | `false`
- `limit` (optional): 1-100 (default: 20)
- `offset` (optional): 0-... (default: 0)

#### Request Examples

```bash
# All critical errors (unresolved)
curl "http://localhost:9095/api/system/error-logs?severity=critical&resolved=false"

# BMS integration errors (last 50)
curl "http://localhost:9095/api/system/error-logs?category=bms&limit=50"

# Database errors from 24 hours ago
curl "http://localhost:9095/api/system/error-logs?category=database&offset=0&limit=100"
```

#### Response (200 OK)

```json
{
  "total": 245,
  "logs": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "timestamp": "2024-01-15T09:30:00Z",
      "category": "bms",
      "severity": "critical",
      "component": "niagara.obix",
      "message": "ObiX connection timeout - Niagara server unresponsive",
      "details": {
        "host": "192.168.1.100",
        "port": 8080,
        "timeout_seconds": 5,
        "retry_count": 3
      },
      "resolved": false,
      "resolved_at": null
    },
    {
      "id": "550e8400-e29b-41d4-a716-446655440001",
      "timestamp": "2024-01-15T08:15:00Z",
      "category": "api",
      "severity": "warning",
      "component": "integration.sync",
      "message": "Sync job delayed - high database load detected",
      "details": {
        "job_id": "sync-2024-01-15-08",
        "delay_seconds": 45,
        "queue_depth": 8
      },
      "resolved": true,
      "resolved_at": "2024-01-15T09:00:00Z"
    }
  ],
  "page": 1,
  "page_size": 20,
  "has_more": true
}
```

#### Response Schema

| Field | Type | Description |
|-------|------|-------------|
| `total` | integer | Total error count (across all pages) |
| `logs` | array | Error log entries |
| `logs[*].id` | UUID | Unique error identifier |
| `logs[*].timestamp` | ISO 8601 | When error occurred |
| `logs[*].category` | enum | `bms` \| `api` \| `database` \| `service` \| `other` |
| `logs[*].severity` | enum | `warning` \| `error` \| `critical` |
| `logs[*].component` | string | System component that failed |
| `logs[*].message` | string | Human-readable error description |
| `logs[*].details` | object | Error-specific diagnostic data |
| `logs[*].resolved` | boolean | Whether error was resolved |
| `logs[*].resolved_at` | ISO 8601 \| null | When error was resolved |
| `page` | integer | Current page (1-indexed) |
| `page_size` | integer | Entries per page |
| `has_more` | boolean | More entries on next page |

#### Pagination Example

```bash
# Page 1 (default)
curl "http://localhost:9095/api/system/error-logs?limit=20&offset=0"

# Page 2
curl "http://localhost:9095/api/system/error-logs?limit=20&offset=20"

# Page 3
curl "http://localhost:9095/api/system/error-logs?limit=20&offset=40"
```

---

## Authentication

All endpoints support optional Bearer token authentication:

```bash
curl -X GET http://localhost:9095/api/system/health \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

Public access enabled by default. To require authentication, set `REQUIRE_AUTH=true` in `.env`.

---

## Rate Limiting

| Endpoint | Limit | Window |
|----------|-------|--------|
| GET /api/system/health | 60 req/min | Per IP |
| GET /api/system/health/history | 30 req/min | Per IP |
| GET /api/system/monitoring | 60 req/min | Per IP |
| POST /api/system/diagnostics | 10 req/min | Per IP |
| GET /api/system/diagnostics/{id} | Unlimited | (Polling) |
| GET /api/system/error-logs | 60 req/min | Per IP |

**Rate Limit Headers:**
```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 47
X-RateLimit-Reset: 1705322445
```

---

## Error Handling

All endpoints return standardized error responses:

```json
{
  "status": 429,
  "message": "Rate limit exceeded",
  "error": "Maximum 60 requests per minute",
  "details": {
    "limit": 60,
    "window_seconds": 60,
    "reset_at": "2024-01-15T10:31:45Z"
  }
}
```

### Common HTTP Status Codes

| Code | Meaning | Action |
|------|---------|--------|
| 200 | OK | Request succeeded |
| 202 | Accepted | Async operation started (diagnostics) |
| 400 | Bad Request | Invalid parameters - check request |
| 429 | Rate Limited | Wait before retrying |
| 503 | Service Unavailable | Backend error - retry after 30s |

---

## Examples

### Health Dashboard Update Loop (JavaScript/Node)

```typescript
import axios from 'axios';

async function updateHealthDashboard() {
  try {
    // Fetch current health
    const response = await axios.get('http://localhost:9095/api/system/health');
    const health = response.data;

    // Update UI with health status
    console.log(`Overall Status: ${health.overall_status} (${health.overall_score}%)`);

    // Show component scores
    Object.entries(health.components).forEach(([key, component]) => {
      console.log(`  ${component.name}: ${component.status} (${component.score}%)`);
    });

    // Display alerts
    if (health.active_alerts.length > 0) {
      console.log('\nActive Alerts:');
      health.active_alerts.forEach(alert => {
        console.log(`  ⚠️  ${alert.message}`);
      });
    }
  } catch (error) {
    console.error('Failed to fetch health:', error.message);
  }
}

// Auto-refresh every 30 seconds
setInterval(updateHealthDashboard, 30000);
```

### Diagnostic Workflow (Bash)

```bash
#!/bin/bash

# 1. Trigger diagnostics
echo "🔍 Starting diagnostics..."
RESPONSE=$(curl -s -X POST http://localhost:9095/api/system/diagnostics \
  -H "Content-Type: application/json" \
  -d '{"target": "full_system"}')

DIAGNOSTIC_ID=$(echo $RESPONSE | jq -r '.diagnostic_id')
echo "Diagnostic ID: $DIAGNOSTIC_ID"

# 2. Poll until complete
COMPLETE=false
while [ "$COMPLETE" = false ]; do
  sleep 5

  RESULT=$(curl -s http://localhost:9095/api/system/diagnostics/$DIAGNOSTIC_ID)
  STATUS=$(echo $RESULT | jq -r '.status')

  case $STATUS in
    pending|running)
      MESSAGE=$(echo $RESULT | jq -r '.message // "Running..."')
      echo "⏳ $MESSAGE"
      ;;
    completed)
      echo "✅ Diagnostics completed in $(echo $RESULT | jq '.duration_seconds')s"

      # Display findings
      echo "\n📋 Issues Found:"
      echo $RESULT | jq -r '.issues_found[]' | sed 's/^/  - /'

      echo "\n💡 Recommendations:"
      echo $RESULT | jq -r '.recommendations[]' | sed 's/^/  - /'

      COMPLETE=true
      ;;
    failed)
      echo "❌ Diagnostics failed: $(echo $RESULT | jq -r '.error')"
      COMPLETE=true
      ;;
  esac
done
```

### Error Log Analysis (Python)

```python
import requests
import json

API_BASE = "http://localhost:9095/api"

def analyze_errors():
    """Analyze recent critical errors"""

    # Fetch critical errors
    response = requests.get(
        f"{API_BASE}/system/error-logs",
        params={
            "severity": "critical",
            "resolved": False,
            "limit": 50
        }
    )

    errors = response.json()
    print(f"Found {errors['total']} unresolved critical errors\n")

    # Group by component
    by_component = {}
    for log in errors['logs']:
        component = log['component']
        if component not in by_component:
            by_component[component] = []
        by_component[component].append(log)

    # Display summary
    for component, logs in sorted(by_component.items()):
        print(f"🔴 {component}: {len(logs)} critical errors")
        for log in logs[:3]:  # Show first 3
            print(f"   - {log['message']}")
        if len(logs) > 3:
            print(f"   ... and {len(logs) - 3} more")
```

---

## WebSocket Streaming (Future)

```javascript
// Planned feature: Real-time health updates via WebSocket
const ws = new WebSocket('ws://localhost:9095/api/system/health/stream');

ws.onmessage = (event) => {
  const health = JSON.parse(event.data);
  console.log(`Health updated: ${health.overall_score}%`);
};
```

---

## See Also

- [System Health & Diagnostics Feature Docs](../04-features/system-health-diagnostics.md)
- [Integration Monitoring (Legacy)](./integration.md)
- [SIMBIOT MCP Tools](./mcp-tools-reference.md)
- [Main API Docs](./README.md)
