---
title: "Water Meter Integration & Leak Detection"
type: "feature"
status: "implemented"
version: "1.0.0"
created: "2026-02-07"
updated: "2026-02-07"
author: "SENTINEL Development Team"
tags: ["water", "leak-detection", "modbus", "consumption", "monitoring", "sustainability"]
domain: "water"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 15
phase: "35"
---

# Water Meter Integration & Leak Detection

Modbus pulse counter integration with real-time leak detection using three algorithms — continuous flow monitoring, statistical anomaly detection (Z-score), and spike detection. Includes 30-day demo dataset with 4 pre-configured leak scenarios.

**Demo Site:** Sandton City Office Tower (site-002) — Elster V100 water meter, 80mm diameter, 10L/pulse weight

## Overview

Phase 35 delivers water consumption monitoring and leak detection across 2 plans:

| Plan | Focus | Features |
|------|-------|----------|
| 35-01 (Backend) | Data ingestion, leak detection, API | Modbus adapter, 3 detection algorithms, 7 REST endpoints, 30-day demo data |
| 35-02 (Frontend) | Dashboard, visualization | WaterPanel component, KPI cards, consumption charts, alert management |

## System Architecture

### Data Flow

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Water Meter     │────▶│ Water Adapter    │────▶│ Ingestion       │
│ (Modbus Pulse   │     │ (DeviceInterface)│     │ Service         │
│  Counter)       │     │                  │     │ (60s polling)   │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                           │
                                                           ▼
                                                   ┌───────────────┐
                                                   │ Alert Service │
                                                   │ (3 Detection  │
                                                   │  Algorithms)  │
                                                   └───────┬───────┘
                                                           │
                                    ┌──────────────────────┼──────────────────┐
                                    ▼                      ▼                  ▼
                              ┌───────────┐         ┌──────────┐      ┌───────────┐
                              │ Supabase  │         │   JSON   │      │   API     │
                              │ (Primary) │         │ (Backup) │      │ Endpoints │
                              └───────────┘         └──────────┘      └───────────┘
                                                                                    │
                                                                                    ▼
                                                                            ┌───────────────┐
                                                                            │ WaterPanel   │
                                                                            │ (Dashboard)  │
                                                                            └───────────────┘
```

### Dual-Write Pattern

Water consumption data is written to both Supabase (primary) and JSON files (backup) for graceful degradation:

- **Primary:** `water_consumption` and `water_alerts` tables in Supabase
- **Backup:** `buildings/site-XXX/water_consumption.json`
- **Fallback:** JSON-only mode when Supabase unavailable

## Backend Implementation (35-01)

### Data Models

**WaterMeter** — Meter installation metadata
```python
meter_id: str              # Unique meter identifier
site: str                  # Building site code
pulse_weight: float        # Liters per pulse (default 10L)
installation_date: date    # Installation date
meter_type: MeterType      # main/submeter/irrigation/cooling/domestic/fire
```

**WaterConsumption** — Consumption readings
```python
timestamp: datetime
volume_liters: float       # Cumulative volume
flow_rate_lpm: float       # Instantaneous flow rate
pulse_count: int           # Raw pulse count
temperature: float | None   # Water temperature
pressure: float | None      # Water pressure
```

**WaterAlert** — Leak detection alerts
```python
alert_id: str
alert_type: AlertType      # continuous_flow/unusual_pattern/spike
severity: Severity         # low/medium/high/critical
timestamp: datetime
resolved: bool
resolution: str | None     # Technician notes
details: dict              # Flow rate, duration, baseline deviation
```

### Modbus Pulse Counter Integration

**WaterMeterAdapter** implements `DeviceInterface` for Modbus RTU/TCP pulse counters:

```python
# Protocol configuration
register_address: int = 30001    # 32-bit pulse count register
pulse_weight: float = 10.0       # 10 liters per pulse (default)

# Flow rate calculation
flow_rate_lpm = (delta_pulses * pulse_weight) / (delta_time_minutes)

# Wraparound handling for 32-bit counter
if delta < -MAX_INT32 / 2:  # Counter overflow detected
    delta += MAX_INT32
```

**Auto-Discovery:** Scans `equipment/` directories for files matching `S*-*-W-*.json` pattern

### Leak Detection Algorithms

Three complementary algorithms detect different leak patterns:

| Algorithm | Trigger | Use Case | Severity |
|-----------|---------|----------|----------|
| **Continuous Flow** | Flow > 10 LPM for > 30 min during off-hours (22:00-06:00) | Toilet valve leak, irrigation leak, underground pipe | HIGH (same-day investigation) |
| **Z-Score Anomaly** | Current flow vs 7-day baseline, z-score > 3.0 | Underground slow leak, meter malfunction, unusual pattern | HIGH if >5.0, MEDIUM otherwise |
| **Spike Detection** | Flow increase > 200% from 15-min average | Equipment filling, pipe burst, unauthorized usage | MEDIUM |

**Configurable thresholds:**
```python
continuous_flow_threshold_lpm = 10.0
continuous_flow_duration_minutes = 30.0
continuous_flow_off_hours_start = 22
continuous_flow_off_hours_end = 6
spike_detection_threshold_percent = 200.0
spike_detection_window_minutes = 15
zscore_threshold = 3.0
zscore_baseline_days = 7
```

### API Endpoints

7 REST endpoints on the `/api/water` router:

```bash
# Consumption data
GET /api/water/consumption/{site}?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
GET /api/water/consumption/{site}/current

# Trending analysis
GET /api/water/trending/{site}?period=day|week|month

# Alert management
GET /api/water/alerts/{site}?severity=high&resolved=false
GET /api/water/alerts/{site}/active
PATCH /api/water/alerts/{alert_id}/resolve

# Ingestion status
GET /api/water/ingestion/status
```

See [Water API Reference](../03-api-reference/water-api.md) for full endpoint documentation.

### Demo Data

**Site:** Sandton City Office Tower (site-002)

**Equipment:**
- Meter: `S002-MTR-W-MAIN` (Elster V100, 80mm diameter, 10L/pulse)
- Location: Main water inlet to building

**Consumption History:**
- 8,876 records over 30 days
- 5-minute interval readings
- Date range: 2026-01-08 to 2026-02-07

**Leak Scenarios (4 pre-configured alerts):**

| Alert ID | Type | Severity | Status | Description |
|----------|------|----------|--------|-------------|
| alert-001 | continuous_flow | HIGH | RESOLVED | Toilet valve leak — 8 hours at 15 LPM |
| alert-002 | spike | MEDIUM | RESOLVED | Cooling tower makeup valve stuck — 2 hours at 80 LPM |
| alert-003 | spike | MEDIUM | ACTIVE | Afternoon spike under investigation |
| alert-004 | unusual_pattern | HIGH | ACTIVE | 50% above normal for 24 hours (possible underground leak) |

## Frontend Implementation (35-02)

### WaterPanel Component

Location: `frontend/src/components/water/WaterPanel.tsx` (440 lines)

**Features:**
- Real-time flow rate display (auto-refresh every 30 seconds)
- KPI cards: Current Flow (LPM), Today (L), This Month (L)
- Consumption trend chart (last 7 days)
- Daily comparison chart (this week vs last week)
- Active alerts panel with severity color coding
- Alert resolution workflow with API integration
- Site selector dropdown (3 demo sites)

### State Management

```typescript
const [selectedSiteId, setSelectedSiteId] = useState("site-002");
const [currentFlow, setCurrentFlow] = useState<CurrentFlowResponse | null>(null);
const [consumptionData, setConsumptionData] = useState<WaterConsumption[]>([]);
const [alerts, setAlerts] = useState<WaterAlert[]>([]);
const [trending, setTrending] = useState<WaterTrending | null>(null);
const [loading, setLoading] = useState(true);
const [error, setError] = useState<string | null>(null);
```

### API Client

Location: `frontend/src/lib/waterApi.ts` (235 lines)

**TypeScript Interfaces:**
```typescript
interface WaterMeter {
  meter_id: string;
  site: string;
  pulse_weight: number;
  installation_date: string;
}

interface WaterConsumption {
  timestamp: string;
  volume_liters: number;
  flow_rate_lpm: number;
  pulse_count: number;
}

interface WaterAlert {
  alert_id: string;
  alert_type: 'continuous_flow' | 'unusual_pattern' | 'spike';
  severity: 'low' | 'medium' | 'high' | 'critical';
  timestamp: string;
  resolved: boolean;
  resolution: string | null;
  details: Record<string, any>;
}
```

**Methods:**
```typescript
getCurrentFlow(site: string): Promise<CurrentFlowResponse>
getConsumption(site: string, start?: string, end?: string): Promise<WaterConsumption[]>
getAlerts(site: string, options?: AlertFilters): Promise<WaterAlert[]>
getActiveAlerts(site: string): Promise<WaterAlert[]>
resolveAlert(alertId: string, resolution: string): Promise<void>
getTrending(site: string, period: 'day' | 'week' | 'month'): Promise<WaterTrending>
getMeters(site: string): Promise<WaterMeter[]>
```

### Navigation & Routing

Water module is registered in:
- `frontend/src/lib/navigation.ts` — View definition, nav item, Droplets icon
- `frontend/src/App.tsx` — Route handling (`/water` → `<WaterPanel />`)
- `frontend/src/lib/moduleRegistry.ts` — Module registration (type: `water`, icon: `droplets`, color: `blue`)

**Sidebar Navigation:**
```typescript
{
  id: "water",
  label: "Water",
  icon: Droplets,
  description: "Water Consumption",
  category: "addon",
  requiredModule: "water",
  defaultOrder: 15  // Between solar and sustainability
}
```

### Demo Mode Fallback

All API calls include demo data fallback for offline development:

```typescript
try {
  const data = await waterApi.getCurrentFlow(site);
  setCurrentFlow(data);
} catch (error) {
  // Fallback to demo data
  setCurrentFlow({
    site: "site-002",
    flow_rate_lpm: 12.5,
    timestamp: new Date().toISOString(),
    meter_id: "meter-001"
  });
}
```

## Integration Points

### Sustainability Module

Water module links to sustainability for ESG reporting:

```json
{
  "cross_module_links": [
    {
      "from_module": "water",
      "to_module": "sustainability",
      "link_type": "data_consumer",
      "description": "ESG water tracking integration"
    }
  ]
}
```

### Sentry Telegram Bot

Water alerts can be routed via Telegram for real-time notifications (future enhancement):

```python
# Potential integration
async def notify_water_alert(alert: WaterAlert):
    await telegram_bot.send_message(
        chat_id=SITE_TELEGRAM_CHANNELS[alert.site],
        text=f"🚰 {alert.severity} WATER ALERT: {alert.details}"
    )
```

## Configuration

### Module Registration

`backend/app/data/modules/site_modules.json`

```json
{
  "instance_id": "sandton-water-001",
  "module_type": "water",
  "site_id": "site-002",
  "status": "active",
  "health": 100.0,
  "config": {
    "polling_interval_seconds": 60,
    "pulse_weight_liters": 10.0,
    "enable_continuous_flow_detection": true,
    "enable_spike_detection": true,
    "enable_zscore_detection": true
  }
}
```

### Leak Detection Thresholds

Tunable per deployment in `backend/app/services/water_alert_service.py`:

```python
# Conservative settings (default)
CONTINUOUS_FLOW_THRESHOLD_LPM = 10.0
CONTINUOUS_FLOW_DURATION_MINUTES = 30.0
SPIKE_DETECTION_THRESHOLD_PERCENT = 200.0
ZSCORE_THRESHOLD = 3.0

# Aggressive settings (high sensitivity)
# CONTINUOUS_FLOW_THRESHOLD_LPM = 5.0
# SPIKE_DETECTION_THRESHOLD_PERCENT = 150.0
# ZSCORE_THRESHOLD = 2.5
```

## Testing

### Unit Tests (Not Yet Created)

```bash
# Backend
pytest tests/services/test_water_meter_adapter.py -v
pytest tests/services/test_water_alert_service.py -v
pytest tests/services/test_water_ingestion_service.py -v

# Frontend
npm test -- src/components/water/WaterPanel.test.tsx
npm test -- src/lib/waterApi.test.ts
```

### Integration Tests

```bash
# API endpoint tests
pytest tests/api/test_water_api.py -v

# Leak detection verification
curl localhost:9095/api/water/alerts/site-002/active
curl localhost:9095/api/water/trending/site-002?period=week
```

### Manual Verification

1. **Flow Rate Calculation:** Verify pulse count → volume → flow rate conversion
2. **Wraparound Handling:** Test 32-bit counter overflow (0xFFFFFFFF → 0x00000000)
3. **Leak Detection:** Inject leak scenarios, verify alert generation
4. **Alert Resolution:** Resolve alert via API, confirm status change
5. **Dashboard Rendering:** Verify KPI cards, charts, alerts display correctly

## Known Limitations

1. **Backend API:** Water endpoints use demo data only (real Modbus integration pending)
2. **Charts:** Custom placeholder implementation (not full Tremor LineChart/BarChart)
3. **Alert Details:** Details button is placeholder (no modal)
4. **Cost Tracking:** No ZAR calculation (requires tariff data)
5. **Historical Data:** Limited to last 7 days (expandable via date range picker)
6. **Multi-Meter Sites:** Demo data assumes single meter per site

## Future Enhancements

### Phase 35-03: Advanced Water Features

- Real-time Tremor LineChart for consumption trend
- BarChart for daily comparison (this week vs last week)
- Alert details modal with full history
- Water cost calculations (ZAR per kiloliter)
- Leak severity scoring algorithm
- Consumption forecasting (ML-based)
- Date range picker for historical data
- Alert filtering by severity and date range

### Production Readiness

- Replace mock Modbus adapter with real ModbusClient for production meters
- Configure Supabase `water_consumption` and `water_alerts` tables
- Set up alert notifications via Telegram/Sentry bot integration
- Implement alert escalation rules (unresolved HIGH → 1 hour, CRITICAL → 15 min)
- Add data validation and quality checks
- Implement retry logic for failed Modbus reads

### Cross-Module Integration

- **Sustainability:** Water consumption → Carbon footprint (water treatment emissions)
- **Contracts:** Water cost tracking → FM contract profitability
- **Security:** Water shut-off valve integration for leak containment

## Troubleshooting

### Common Issues

**Issue:** Flow rate shows negative values
- **Cause:** 32-bit counter wraparound not handled
- **Fix:** Check `delta < -MAX_INT32/2` logic in `WaterMeterAdapter`

**Issue:** No alerts generated despite high flow
- **Cause:** Detection thresholds too high or off-hours window mismatch
- **Fix:** Adjust `CONTINUOUS_FLOW_THRESHOLD_LPM` or verify timezone settings

**Issue:** Dashboard shows demo data instead of API data
- **Cause:** Backend not running or API endpoint returning errors
- **Fix:** Start backend server (`uvicorn app.main:app --reload`) and check `/api/water` endpoints

**Issue:** TypeScript compilation errors in frontend
- **Cause:** Duplicate type exports or missing props
- **Fix:** Check `frontend/src/lib/api.ts` for duplicate exports, verify component props

## References

- **Phase 35-01 Plan:** `.planning/phases/35-water-meter-integration/35-01-PLAN.md`
- **Phase 35-01 Summary:** `.planning/phases/35-water-meter-integration/35-01-SUMMARY.md`
- **Phase 35-02 Plan:** `.planning/phases/35-water-meter-integration/35-02-PLAN.md`
- **Phase 35-02 Summary:** `.planning/phases/35-water-meter-integration/35-02-SUMMARY.md`
- **Water API Reference:** `docs/03-api-reference/water-api.md`
- **Solar Module (Pattern Reference):** `docs/04-features/34-solar-bess-module.md`

---

**Implementation Date:** 2026-02-07
**Status:** ✅ Complete (Backend API + Frontend Dashboard)
**Demo Data:** 30 days (8,876 consumption records, 4 leak scenarios)
**Next Phase:** 35-03 (Advanced Features) or 36 (Blinds/Shading Integration)
