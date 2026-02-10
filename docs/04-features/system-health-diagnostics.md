# System Health & Diagnostics Dashboard

**Phase:** 74  
**Status:** ✅ Complete  
**Version:** 1.0  

## Overview

The **System Health & Diagnostics Dashboard** replaces the narrowly-focused Integration Monitoring page with a comprehensive infrastructure monitoring hub. It provides operators and support teams with real-time system health visibility, historical trend analysis, and intelligent SIMBIOT-powered diagnostics.

**Key Benefits:**
- ✅ Unified health overview (vs checking 15+ endpoints manually)
- ✅ SIMBIOT diagnostic capabilities exposed to users
- ✅ Historical trending reveals systemic issues
- ✅ Error logs provide audit trail for troubleshooting
- ✅ Actionable recommendations from diagnostic results

## Architecture

### Three-Tab Interface

#### 1. Realtime Status Tab
Displays current system health with auto-refresh every 30 seconds.

**Components:**
- **Health Overview Header** - Overall status badge (healthy/degraded/critical), score 0-100, timestamp, last refresh indicator
- **BMS Connectivity Card** - Niagara connection, BACnet network status, ObiX endpoint, DALI gateway
- **API Health Card** - Individual endpoint response times, error counts, availability percentage
- **Data Freshness Card** - Last reading timestamp by data source (Niagara, BACnet, direct integration)
- **Database Status Card** - Supabase availability, InfluxDB connectivity, Redis cache health
- **Service Health Card** - Background service status (ML models, AI chat, device manager, cache)

**Health Scoring Logic:**
```
weighted_score = (
  bms_connectivity * 0.30 +           # 30% weight
  database_status * 0.25 +             # 25% weight
  api_health * 0.20 +                  # 20% weight
  service_health * 0.15 +              # 15% weight
  data_freshness * 0.10                # 10% weight
)

Status Mapping:
- healthy:    score ≥ 80 (green)
- degraded:   60-79 (yellow)
- degrading:  40-59 (orange)
- critical:   < 40 (red)
```

#### 2. Historical Insights Tab
Analyzes trends over 24h, 7d, and 30d time ranges.

**Components:**
- **Uptime Metrics Card** - Displays uptime percentage for each time range with bar chart
- **Health Trend Chart** - Line chart showing health score progression over selected range (identifies patterns, spikes, recovery)
- **Trend Analysis** - Automatic categorization: improving/stable/degrading

**Data Source:**
- 5-minute snapshots stored in `system_health_snapshots` table
- 90-day data retention for long-term analysis
- Auto-cleanup of snapshots >90 days old

#### 3. Diagnostics Tab
Provides deep system inspection and error tracking.

**Components:**
- **Diagnostics Controls** - Trigger button, target selection (full_system, building, component), execution indicator
- **Diagnostics Results** - Display 6-tool workflow outputs:
  1. Device inventory
  2. DALI gateway detection
  3. Building configurations
  4. Active alarms
  5. Health scores
  6. Asset detail analysis
- **Error Logs Table** - Filterable error history with search, category/severity filtering, resolution tracking
- **Sync Status Card** - Current integration sync job status (from integration API)

## Health Aggregation

### 15+ Endpoints Aggregated

The service aggregates health from multiple backend systems in parallel:

1. `/api/health` - Basic system health
2. `/api/health/control` - Control system status
3. `/api/integration/health` - Integration health with alerts
4. `/api/integration/quality-metrics` - Data quality metrics
5. `/api/niagara/health` - Niagara connectivity
6. `/api/niagara/obix/connection/test` - ObiX connection validation
7. `/api/bacnet/status` - BACnet network status
8. `/api/dali/gateway/status` - DALI gateway health
9. `/api/devices/status` - Device manager status
10. `/api/cache/health` - Redis cache health
11. `/api/ml/health` - ML models status
12. `/api/chat/health` - AI service health
13. Supabase connectivity check (database query test)
14. InfluxDB connectivity check (ping test)
15. Ollama connectivity check (health endpoint)

### Error Handling

- **Graceful Degradation:** Individual endpoint errors don't break entire snapshot
- **Timeout Protection:** Each endpoint has 5-second timeout
- **Fallback Values:** Missing endpoints treated as "unknown" status, not failure
- **Exception Logging:** All errors logged to `system_error_logs` table

### Caching Strategy

- **Cache Key:** `system:health:current`
- **TTL:** 30 seconds (configurable)
- **Cache Invalidation:** On manual diagnostics trigger or error threshold exceeded
- **Backend:** Redis (configured via `REDIS_ENABLED` setting)

## SIMBIOT Diagnostics Workflow

### Sequential Tool Execution

The diagnostics system orchestrates 6 MCP tools in sequence:

```
1. get_devices
   └─> Returns: Full device inventory with statuses
   
2. discover_tridonic_gateway
   └─> Returns: DALI gateway presence, network connectivity
   
3. get_buildings
   └─> Returns: Building configurations, floor mappings
   
4. search_alarms
   └─> Returns: Active alarms, severity levels, timestamps
   
5. get_health_score
   └─> Returns: Component health scores, degradation signals
   
6. get_asset_detail
   └─> Returns: Deep inspection of flagged assets, anomalies
```

### Async Polling Pattern

**Execution Flow:**
1. Client sends `POST /api/system/diagnostics` → Immediate response with `diagnostic_id`
2. Backend starts async workflow execution
3. Client polls `GET /api/system/diagnostics/{diagnostic_id}` every 5 seconds
4. Status progresses: pending → running → completed/failed
5. Results cached in `system_diagnostics` table
6. Full results returned when complete (typically 30-60 seconds)

**Result Structure:**
```json
{
  "diagnostic_id": "uuid",
  "timestamp": "2024-01-15T10:30:00Z",
  "target": "full_system",
  "status": "completed",
  "duration_seconds": 45,
  "device_inventory": {...},
  "building_config": {...},
  "alarms_found": [...],
  "health_scores": {...},
  "asset_details": [...],
  "issues_found": ["Chiller cooling inefficiency", "DALI gateway delayed response"],
  "recommendations": ["Schedule chiller maintenance", "Check DALI network cables"],
  "next_steps": ["Review fault codes", "Inspect cooling system"]
}
```

## Database Schema

### Migration 058: system_health_diagnostics

**Table 1: system_health_snapshots**
- Purpose: Historical system health data (5-minute intervals)
- Retention: 90 days
- Queries: Trend analysis, uptime calculations

```sql
CREATE TABLE system_health_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    overall_status TEXT NOT NULL CHECK (overall_status IN ('healthy', 'degraded', 'critical')),
    overall_score INTEGER NOT NULL CHECK (overall_score BETWEEN 0 AND 100),
    component_scores JSONB NOT NULL,
    details JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_health_snapshots_timestamp ON system_health_snapshots(timestamp DESC);
```

**Table 2: system_error_logs**
- Purpose: Integration/service failure audit trail
- Retention: 180 days for resolved, unlimited for unresolved
- Queries: Error filtering, trend analysis, incident investigation

```sql
CREATE TABLE system_error_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    category TEXT NOT NULL CHECK (category IN ('bms', 'api', 'database', 'service', 'other')),
    severity TEXT NOT NULL CHECK (severity IN ('warning', 'error', 'critical')),
    component TEXT NOT NULL,
    message TEXT NOT NULL,
    details JSONB,
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_error_logs_timestamp ON system_error_logs(timestamp DESC);
CREATE INDEX idx_error_logs_resolved ON system_error_logs(resolved);
CREATE INDEX idx_error_logs_category ON system_error_logs(category);
CREATE INDEX idx_error_logs_severity ON system_error_logs(severity);
```

**Table 3: system_diagnostics**
- Purpose: SIMBIOT diagnostic results cache
- Retention: 30 days
- Queries: Results retrieval by diagnostic_id, historical diagnostics

```sql
CREATE TABLE system_diagnostics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    diagnostic_id TEXT UNIQUE NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    target TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    results JSONB,
    recommendations TEXT[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_diagnostics_diagnostic_id ON system_diagnostics(diagnostic_id);
CREATE INDEX idx_diagnostics_timestamp ON system_diagnostics(timestamp DESC);
```

## Background Tasks

### Health Snapshot Task (Every 5 Minutes)
```python
@repeat_every(seconds=300)
async def store_health_snapshot_task():
    """Aggregate health from 15+ endpoints and store snapshot"""
    service = SystemHealthService()
    snapshot = await service.get_current_health()
    await service.store_health_snapshot(snapshot)
    
    # Triggers: component health evaluation, anomaly detection
```

### Error Auto-Resolution Task (Every 24 Hours)
```python
@repeat_every(seconds=86400)
async def auto_resolve_errors_task():
    """Auto-resolve errors if component recovered for 24+ hours"""
    service = SystemHealthService()
    await service.auto_resolve_stale_errors()
    
    # Triggers: error log cleanup, trend reversal detection
```

### Data Cleanup Task (Weekly)
```python
@repeat_every(seconds=604800)
async def cleanup_old_data_task():
    """Remove expired data from all health tables"""
    client = get_supabase_client()
    
    # Runs: cleanup_old_health_snapshots() PL/pgSQL function
    # Removes: snapshots >90 days, resolved errors >180 days, diagnostics >30 days
```

## Frontend Components

### Component Hierarchy
```
SystemHealthPage.tsx
├── HealthOverviewHeader.tsx (overall status badge, score)
├── TabGroup (Realtime | Historical | Diagnostics)
│   ├── Realtime Status Tab
│   │   ├── BMSConnectivityCard.tsx
│   │   ├── APIHealthCard.tsx
│   │   ├── DataFreshnessCard.tsx
│   │   ├── DatabaseStatusCard.tsx
│   │   └── ServiceHealthCard.tsx
│   ├── Historical Insights Tab
│   │   ├── UptimeMetricsCard.tsx (bar chart)
│   │   └── HealthTrendChart.tsx (line chart)
│   └── Diagnostics Tab
│       ├── DiagnosticsControls.tsx (trigger UI)
│       ├── DiagnosticsResults.tsx (workflow results)
│       └── ErrorLogsTable.tsx (filterable logs)
```

### Custom Hooks

**useSystemHealth()**
- Auto-fetches health snapshot every 30 seconds
- Manages error state and loading
- Returns: `{ health, loading, error }`

**useDiagnostics()**
- Orchestrates diagnostic workflow
- Handles polling until completion
- Returns: `{ result, loading, runDiagnostics() }`

**useErrorLogs()**
- Fetches paginated error logs
- Supports filtering by category, severity, resolution
- Returns: `{ logs, total, page, filters, setFilters() }`

## API Endpoints

### Public REST API

**GET /api/system/health** - Unified health snapshot
```
Response (200):
{
  "timestamp": "2024-01-15T10:30:00Z",
  "overall_status": "healthy",
  "overall_score": 87,
  "components": {
    "bms_connectivity": { "status": "healthy", "score": 92 },
    "api_health": { "status": "healthy", "score": 85 },
    "database_status": { "status": "healthy", "score": 95 },
    "service_health": { "status": "healthy", "score": 80 },
    "data_freshness": { "status": "healthy", "score": 88 }
  },
  "active_alerts": [...],
  "recommendations": [...]
}
```
- Cache: Redis 30s TTL
- Rate limit: 60 req/min

**GET /api/system/health/history?range={24h|7d|30d}** - Historical trends
```
Response (200):
{
  "range": "24h",
  "snapshots": [
    { "timestamp": "2024-01-15T00:00:00Z", "overall_score": 78, "overall_status": "degraded" },
    ...
  ],
  "uptime_percentage": 99.2,
  "avg_score": 82,
  "trend": "improving"
}
```

**POST /api/system/diagnostics** - Trigger diagnostics
```
Request:
{
  "target": "full_system|building:code|component:name",
  "building_code": "site-002" (optional)
}

Response (202):
{
  "diagnostic_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending"
}
```
- Rate limit: 10 req/min
- Async execution: 30-60 seconds typical

**GET /api/system/diagnostics/{diagnostic_id}** - Poll diagnostic results
```
Response (200):
{
  "diagnostic_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T10:30:00Z",
  "target": "full_system",
  "status": "completed",
  "duration_seconds": 45,
  "issues_found": [
    "Chiller cooling inefficiency detected",
    "DALI gateway response time degraded"
  ],
  "recommendations": [
    "Schedule chiller maintenance within 2 weeks",
    "Check DALI network connectivity"
  ],
  "next_steps": [...]
}
```

**GET /api/system/error-logs** - Query error history
```
Query Params:
- category: bms|api|database|service|other
- severity: warning|error|critical
- resolved: true|false
- limit: 1-100 (default: 20)
- offset: 0-... (default: 0)

Response (200):
{
  "total": 245,
  "logs": [
    {
      "id": "uuid",
      "timestamp": "2024-01-15T09:30:00Z",
      "category": "api",
      "severity": "warning",
      "component": "integration.sync",
      "message": "Sync job delayed 30 seconds",
      "resolved": true,
      "resolved_at": "2024-01-15T10:00:00Z"
    },
    ...
  ],
  "page": 1,
  "page_size": 20
}
```

## Usage Examples

### Check Current System Health
```bash
curl http://localhost:9095/api/system/health | jq '.overall_score'
# Output: 87
```

### Run Full System Diagnostics
```bash
DIAG_ID=$(curl -s -X POST http://localhost:9095/api/system/diagnostics \
  -H "Content-Type: application/json" \
  -d '{"target": "full_system"}' | jq -r '.diagnostic_id')

echo "Diagnostic ID: $DIAG_ID"

# Poll for results (every 5 seconds)
for i in {1..20}; do
  STATUS=$(curl -s http://localhost:9095/api/system/diagnostics/$DIAG_ID | jq -r '.status')
  echo "Status: $STATUS"
  
  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
    curl -s http://localhost:9095/api/system/diagnostics/$DIAG_ID | jq '.'
    break
  fi
  
  sleep 5
done
```

### Query Critical Errors
```bash
curl "http://localhost:9095/api/system/error-logs?severity=critical&resolved=false" \
  | jq '.logs[] | {component, message, timestamp}'
```

### Get 7-Day Uptime Trend
```bash
curl "http://localhost:9095/api/system/health/history?range=7d" \
  | jq '{uptime: .uptime_percentage, trend: .trend, avg_score: .avg_score}'
```

## Deployment & Operations

### Configuration

**Backend Settings** (`backend/app/config/settings.py`):
```python
SYSTEM_HEALTH_ENABLED = True
SYSTEM_HEALTH_SNAPSHOT_INTERVAL_SECONDS = 300  # 5 minutes
SYSTEM_HEALTH_SNAPSHOT_RETENTION_DAYS = 90
SYSTEM_HEALTH_ENDPOINT_TIMEOUT_SECONDS = 5
SYSTEM_HEALTH_CACHE_TTL_SECONDS = 30
```

**Environment Variables**:
```bash
# Enable/disable health dashboard
SYSTEM_HEALTH_ENABLED=true

# Redis caching
REDIS_ENABLED=true
REDIS_URL=redis://localhost:6379

# Supabase (for health snapshots)
DATABASE_URL=postgresql://...
```

### Monitoring

**Health Endpoint SLA:**
- Response time: <2 seconds (cached)
- Uptime: 99.9%+
- Error rate: <0.1%

**Database Performance:**
- `system_health_snapshots` query: <100ms for 7-day range
- `system_error_logs` query: <200ms with category filter
- Snapshot storage: ~5KB per record, ~360/day = ~1.8MB/month

### Troubleshooting

**Dashboard loads slowly (>2s)**
1. Check Redis connectivity: `curl http://localhost:6379 PING`
2. Check endpoint latencies: `/api/system/health` debug logs
3. Clear cache: `curl -X POST http://localhost:9095/api/cache/flush`

**Diagnostics workflow times out (>120s)**
1. Check SIMBIOT server availability: `telnet localhost:9500`
2. Review MCP tool logs for individual tool failures
3. Increase timeout: `SYSTEM_HEALTH_ENDPOINT_TIMEOUT_SECONDS=10`

**Error logs not appearing**
1. Verify migration applied: Check Supabase Studio for `system_error_logs` table
2. Check log level: `python -c "import logging; logging.basicConfig(level=logging.DEBUG)"`
3. Manually log error: See backend service for `log_system_error()` method

## Success Metrics

✅ **Performance:**
- Dashboard loads in <2s (Redis cached)
- Aggregation of 15+ endpoints completes in <5s
- Diagnostics workflow completes in 30-60 seconds
- Historical queries return in <200ms

✅ **Reliability:**
- 99.9% uptime for `/api/system/health` endpoint
- Zero single points of failure (parallel endpoint aggregation)
- Graceful degradation when individual endpoints fail
- Automatic error recovery and resolution

✅ **Data Quality:**
- 5-minute snapshot intervals maintained consistently
- 90-day historical retention without data loss
- Error logs capture 100% of integration/service failures
- Diagnostic results stored for 30-day audit trail

✅ **User Experience:**
- One-click diagnostics trigger with visual progress
- Clear status indicators (healthy/degraded/critical)
- Actionable error filtering and search
- Trend visualization shows patterns over time

## Migration from Integration Monitoring

**Old Page:** `/integration-monitoring` (archived)
**New Page:** `/system-health` (active)

**Migration Path:**
1. `/integration-monitoring` redirects to `/system-health`
2. Old page archived at `frontend/src/components/_archived/IntegrationMonitoringPage.tsx`
3. Integration API endpoints remain active for backward compatibility
4. User-facing URL changed in navigation/bookmarks

**What's New:**
- Unified health score vs separate sync metrics
- Historical trending vs point-in-time snapshots
- SIMBIOT diagnostics vs manual tool execution
- Error log audit trail vs transient logs
- Responsive mobile design with Tremor v3

## Future Enhancements

- [ ] Email alerts for critical health events
- [ ] Predictive anomaly detection using ML
- [ ] Custom health dashboards per role
- [ ] Health API webhooks for external integrations
- [ ] SLA tracking and breach notifications
- [ ] Cost attribution by component
