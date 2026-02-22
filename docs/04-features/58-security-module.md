---
title: "Security Module - Access Control, Occupancy & Dashboard"
type: "spec"
status: "approved"
version: "2.0.0"
created: "2026-02-09"
updated: "2026-02-22"
author: "Sentinel Development Team"
tags: ["security", "access-control", "occupancy", "dashboard", "cameras", "module"]
domain: "security"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 15
---

# Security Module — Access Control, Occupancy & Dashboard

## Overview

The SENTINEL Security Module provides intelligent integration with access control systems (C•CURE 9000, Lenel, Gallagher, and others) as an **intelligence overlay** rather than a control system. SENTINEL reads security events and correlates them with HVAC, lighting, and infrastructure health to detect anomalies, predict maintenance, and optimize building operations.

Phase 69 added zone-level occupancy tracking, a 5-tab SecurityDashboard, CCTV camera integration with stream URLs, and registered the module as a sellable add-on ($500/month).

**Version:** Phase 69 (Dashboard + Occupancy + Sellable Module)
**Status:** Production-ready; sellable at $500/month with HVAC/Lighting cross-module integrations

---

## Phase 69: Security Dashboard & Zone Occupancy

### SecurityDashboard (5-Tab UI)

Location: `frontend/src/components/security/SecurityDashboard.tsx`

| Tab | Content |
|-----|---------|
| **Overview** | 4 KPI cards (doors, cameras, alarm zones, occupancy) + zone occupancy cards with progress bars |
| **Access Control** | AccessEventsPanel with badge event history, filtering |
| **Cameras** | CCTV status list with stream URLs, camera models, analytics badges |
| **Occupancy Analysis** | 24h AreaChart trend, peak hours summary, BarChart floor breakdown |
| **Integrations** | HVAC/Lighting automation status and cross-module integration health |

### SecurityOccupancyService (Phase 69 additions)

| Method | Purpose |
|--------|---------|
| `process_access_event(event_data)` | Handle badge events, update zone occupancy, trigger HVAC/Lighting cross-module recommendations |
| `get_occupancy_trend(zone_id, hours)` | Hourly entry/exit/net occupancy snapshots for trending and AI analysis |
| `get_floor_occupancy(floor)` | Aggregate occupancy across all zones on a floor |

### Phase 69 API Endpoints

Six zone-level endpoints added under `/api/security`:

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/occupancy/zone/{zone_id}` | Per-zone occupancy count, max capacity, percent full |
| GET | `/occupancy/floor/{floor}` | Aggregate floor occupancy across zones |
| POST | `/access-event` | Receive badge events, trigger HVAC/Lighting automations |
| GET | `/access-log/{zone_id}` | Recent badge events by zone and time range |
| GET | `/cameras/{zone_id}` | Zone cameras with stream URLs (Supabase + demo fallback) |
| GET | `/occupancy-trend/{zone_id}` | Hourly trend data for graphing (default 24h) |

See [Security API Reference](../03-api-reference/security-api.md) for full endpoint details.

### Module Registry (Sellable)

The Security module is registered as a sellable add-on in `site_modules.json`:

- **Price:** $500/month
- **Includes:** Access control monitoring, real-time occupancy tracking, CCTV integration, breach alerts, occupancy-based automation triggers
- **Cross-module integrations:**
  - Security + HVAC: Occupancy-based HVAC optimization
  - Security + Lighting: Occupancy-based lighting control

### Database Schema (Phase 69)

Migration: `supabase/migrations/security_module.sql`

**New table: `access_rules`** -- Configurable access restrictions per zone:
- `rule_type`: `time_based` | `occupancy_based` | `emergency`
- `rule_config`: JSONB (time windows, occupancy thresholds, emergency actions)
- Indexes on `zone_id` and `(active, rule_type)`

**Extended columns:**
- `security_occupancy.max_capacity` (INTEGER) -- fire code capacity per zone
- `security_occupancy.percent_full` (DECIMAL) -- computed fullness percentage
- `security_cameras.stream_url` (TEXT) -- RTSP stream URL
- `security_cameras.camera_model` (TEXT) -- hardware model string

---

## Key Features

### 1. After-Hours Anomaly Detection

**Problem:** Buildings waste energy when operators stay after-hours without notifying facilities, running full HVAC and lighting.

**Solution:** SENTINEL correlates badge access with HVAC/lighting activation to detect after-hours usage patterns.

**Example:**
- 21:30 — Badge event: "Johan van der Merwe" enters Level 1 (IT-ADMIN clearance)
- 21:35 — HVAC zone L1 setpoint changes from 28°C (unoccupied) to 22°C (occupied mode)
- 21:32 — Lighting zone L1 activates from 0% to 100% brightness

**SENTINEL Alert:**
```
⚠️ WARNING: After-hours access by Johan van der Merwe
   Unexpected HVAC/lighting activation detected
   Energy impact: 4.25 kWh excess per hour
   Recommendation: Verify access was authorized. Consider after-hours
                   setpoint policy if pattern continues.
```

**Business Value:**
- Detect unauthorized after-hours facility usage
- Identify energy waste from unscheduled occupancy
- Catch insider threats (employee accessing restricted zones after hours)
- Estimated savings: 2-5% energy reduction through occupancy-driven control

---

### 2. Security Equipment Health Monitoring

**Problem:** Controller offline events go unnoticed until access is completely denied.

**Solution:** SENTINEL correlates controller heartbeats with network infrastructure health (switch status, UPS battery) to predict failures before they occur.

**Example:**
- 03:22 — iSTAR Edge controller (Level 3) goes offline
- 03:22 — Network switch port 24 shows DOWN status
- UPS battery at 95% — generator on standby (system stable)

**SENTINEL Alert:**
```
🔴 CRITICAL: iSTAR Edge - Level 3 offline since 03:22
   Network: Switch SW-01 port GigabitEthernet1/0/24 DOWN
   UPS: 95% battery, ~45 min runtime if mains lost
   Recommendation: Check physical switch connection at L3.
                   May indicate port failure or cable damage.
                   Doors on this controller may be in fail-safe state.
```

**Business Value:**
- Predictive maintenance (catch network issues before lockout)
- SLA compliance tracking (uptime reporting)
- Incident response (know immediately if security infrastructure degraded)

---

### 3. Real-Time Occupancy Integration

**Problem:** HVAC/lighting systems don't know actual occupancy; they run on schedule regardless of zone usage.

**Solution:** Badge entry/exit counting provides real-time occupancy per zone.

**Example Occupancy Calculation:**
```
Zone: Level 1 - Executive Suite
  Entries: 5 badge swipes in
  Exits:   2 badge swipes out
  Current Occupancy: 5 - 2 = 3 people

Recommendation:
  ✓ HVAC: Maintain 22°C cooling
  ✓ Lighting: Keep at 100% brightness
  ✓ Energy: Setpoint aligned with actual occupancy
```

**Cross-Module Recommendations:**
- Empty zones → HVAC relaxed to +2°C, lighting dimmed to 20%
- Low occupancy (1-3 people) → HVAC relaxed by 1°C, lighting at 50%
- Full occupancy → Standard setpoint 22°C, lighting 100%

**Business Value:**
- 15-20% energy savings vs. scheduled operation
- Improved comfort (heating/cooling follows actual usage)
- Automated occupancy-driven recommendations

---

### 4. Governance Layer for Access Control Integration

**Critical Requirement:** When integrating any access control system, SENTINEL validates configuration to prevent security incidents like the Fairlands breach.

**Validation During Onboarding:**

1. **Operator Scoping Audit**
   - Verify operators scoped to assigned sites/campuses
   - Flag enterprise-wide visibility by default
   - Prevent scope creep in multi-site deployments

2. **Alarm Partition Validation**
   - Controllers only receive events from designated partition
   - No broadcast alarms leaking across boundaries
   - Validate routing rules before go-live

3. **Cross-Region Data Exposure Check**
   - Camera feeds isolated by site/campus
   - Badge events scoped to authorized zones
   - Personnel records not exposed across unauthorized boundaries

4. **Alarm Volume & Fatigue Assessment**
   - Calculate expected alarm volume per operator
   - Flag if >10 alarms/minute (fatigue risk)
   - Recommend filtering rules or staffing adjustments

**Why This Matters:** Fairlands incident occurred because operator scoping was misconfigured and accepted without governance validation. SENTINEL catches this DURING onboarding, not after production deployment.

---

## Architecture

### Data Flow

```
Access Control System (C•CURE 9000)
    ↓ victor Web Service API
CCureAdapter (demo mode or live)
    ↓ normalized badge events
SecurityService + OccupancyService
    ↓
Intelligence Layer
    ├─ After-Hours Anomaly Detection
    ├─ Equipment Health Monitoring
    └─ Occupancy-Driven Recommendations
    ↓
REST API Endpoints
    ├─ /api/security/ccure/status
    ├─ /api/security/events/anomalies
    └─ /api/security/occupancy/real-time
    ↓
Dashboard UI + Alerts
```

### Integration Modes

**Phase 58.2: Demo Mode** (Current)
- Uses `ccure_demo_data.json` with realistic sample data
- No API credentials required
- Full intelligence pipeline visible
- Perfect for demonstrations and training

**Phase 58.3: Live Mode** (Q2 2026)
- Requires Software House Connected Partner Program license
- victor Web Service API integration
- Real badge events from customer C•CURE instance
- WebSocket upgrade for real-time events

---

## API Endpoints

All endpoints require JWT authentication and are rate-limited to 30 requests/minute.

### System Status
- `GET /api/security/status` — Overall security system health

### C•CURE Integration
- `GET /api/security/ccure/status` — Integration mode and license status

### Anomaly Detection
- `GET /api/security/events/anomalies?since=24h&type=after_hours_access` — Security anomalies with correlations

### Real-Time Occupancy
- `GET /api/security/occupancy/real-time` — Zone occupancy with HVAC/lighting recommendations
- `GET /api/security/occupancy/{zone_id}` — Per-zone occupancy

**See:** [Security API Reference](../03-api-reference/security-api.md)

---

## Database Schema

### security_anomalies
Tracks detected security anomalies (after-hours access, controller offline, etc.)

```sql
CREATE TABLE security_anomalies (
    id UUID PRIMARY KEY,
    anomaly_type TEXT,  -- after_hours_access, controller_offline, forced_door
    severity TEXT,      -- warning, critical, info
    badge_event_id TEXT,
    zone_id TEXT,
    description TEXT,
    hvac_correlation JSONB,     -- Correlated HVAC events
    lighting_correlation JSONB, -- Correlated lighting events
    energy_impact TEXT,         -- e.g., "Estimated 2-5 kWh excess"
    resolved BOOLEAN DEFAULT FALSE,
    detected_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    notes TEXT
);
```

### ccure_controllers
Tracks iSTAR controller health and status

```sql
CREATE TABLE ccure_controllers (
    controller_id TEXT PRIMARY KEY,
    site_id TEXT,
    name TEXT,
    model TEXT,              -- iSTAR Ultra, iSTAR Edge
    firmware TEXT,
    encryption_mode TEXT,    -- FIPS 197 AES-256
    tamper_status TEXT,      -- normal, enclosure_open, back_tamper
    last_seen TIMESTAMPTZ,
    ip_address TEXT,
    reader_count INT,
    status TEXT              -- online, offline, degraded
);
```

### security_badge_events (extended)
Added C•CURE-specific fields:
- `event_type` — access_granted, forced_door, controller_offline, etc.
- `clearance_level` — Badge holder's access level (e.g., IT-ADMIN)
- `department` — For cross-system correlation
- `after_hours` — Boolean flag for post-hours access

---

## Dashboard

Two dashboard layouts are available:

### Original Dashboard (`components/SecurityDashboard.tsx`)

Flat layout with KPI cards, C•CURE status, anomalies panel, access events, camera/alarm status.

### Phase 69 Tabbed Dashboard (`components/security/SecurityDashboard.tsx`)

5-tab Tremor TabGroup dashboard:

1. **Overview** -- 4 KPI cards (doors, cameras, alarm zones, occupancy) + zone occupancy cards with progress bars showing percent_full against max_capacity
2. **Access Control** -- AccessEventsPanel with badge event history, person name, location, status badges, time
3. **Cameras** -- CCTV camera list with stream URLs, camera model, resolution, analytics capability badges
4. **Occupancy Analysis** -- 24h AreaChart (hourly entries/exits/net occupancy), peak hours summary, BarChart floor breakdown
5. **Integrations** -- HVAC/Lighting automation status showing cross-module integration health and triggered recommendations

---

## Client Onboarding (1-2 Days)

### Prerequisites
- Client has C•CURE 9000 v2.90+ deployed
- Valid Software House Connected Partner Program license (or licensing applied for)
- C•CURE administrator access to configure Operator account

### Onboarding Steps

1. **Day 1 (Morning):** SENTINEL Deployment (1 hour)
   - Deploy SENTINEL stack with C•CURE module enabled
   - Verify demo mode shows realistic sample data

2. **Day 1 (Mid-morning):** Operator Account Setup (30 min)
   - Client creates "sentinel_operator" account in C•CURE
   - Assigns "SYSTEM ALL" permission
   - Generates API credentials

3. **Day 1 (Afternoon):** Live Integration Configuration (30 min)
   - Input C•CURE API endpoint in SENTINEL settings
   - Configure operator credentials (encrypted storage)
   - Enable live mode in CCureAdapter
   - Test badge event polling

4. **Day 1 (Late afternoon):** Intelligence Validation (1 hour)
   - Trigger test after-hours access
   - Verify anomaly detection working
   - Confirm HVAC/lighting correlation visible
   - Show real-time occupancy feed

5. **Day 2 (Morning):** Dashboard Training (30 min)
   - Show C•CURE status card
   - Explain anomaly severity levels
   - Walk through cross-system recommendations
   - Show ROI (energy savings, security improvements)

6. **Day 2 (Afternoon):** Go-Live
   - Enable production badges
   - Configure alert thresholds
   - Set up notification rules
   - Handoff to client operations team

---

## Future Phases

### Phase 58.3: Live C•CURE Integration
- Obtain Software House Connected Partner Program license
- Implement victor Web Service API client
- Replace demo mode with live badge event polling
- Add WebSocket support for real-time events

### Phase 58.4: Multi-Platform Support
- Abstract CCureAdapter patterns for Lenel OnGuard
- Add Gallagher Security adapter
- Add Paxton Net2 adapter
- Apply governance framework to all platforms

### Phase 58.5: Bi-Directional Control (Future)
- Door unlock/lock commands via victor API
- Safety validation for security commands
- Emergency override capabilities
- Requires FSR Domain 4 compliance

---

## Phase 58.6: Video Intelligence Integration (Camera/LPR → SENTINEL)

**Status:** 🔮 Future | **Priority:** Post-58.5 | **Timeline:** Phase B roadmap

**Objective:** Integrate vehicle counting and license plate recognition into facility security monitoring and work order pipeline.

**Integration Points:**
- **LPR Camera Systems** → Vehicle counts, unauthorized vehicles, parking violations
- **Alert Pipeline**: Generate work orders for security team (e.g., "Unauthorized vehicle in loading bay")
- **Equipment Abstraction**: Security cameras become equipment type `CAMERA` with `LPR` specialty
- **Work Order Routing**: Security alerts auto-routed based on location (parking, entrance, loading dock)
- **Schema Compatibility**: Existing `alerts` + `work_orders` tables handle camera events without modification
- **Notification System**: Phase 102 multi-channel notifications deliver camera alerts to security technicians

**Examples:**
- ✅ "High-speed vehicle detected in parking area" → Security work order (safety concern)
- ✅ "Unknown license plate detected 3x in 1 hour" → Security alert (suspicious pattern)
- ✅ "Loading bay capacity exceeded" → Operational alert

**Why This Works:**
- Uses same alert and work order pipeline as badge events
- Camera equipment maps to existing equipment abstraction layer
- Security roles inherit view permissions via RLS policies
- Audit trail captures all camera-based alerts and resolutions

---

## Phase 58.7: Facial Recognition Integration (Unwanted Persons → SENTINEL)

**Status:** 🔮 Future | **Priority:** Post-58.6 | **Timeline:** Phase B+ roadmap

**Objective:** Detect and alert on flagged individuals, feeding into security and access control workflows.

**Integration Points:**
- **Facial Recognition System** → Person identification + confidence scores
- **Watchlist Matching**: Detect known threats, missing persons, flagged employees
- **Alert Generation**: Instant work order to security team with location, confidence, recommended action
- **Cascade Actions**: Can trigger access control lock-down, escalate to law enforcement
- **Schema Compatibility**: Existing `alerts` + `work_orders` tables handle facial recognition events without modification
- **Notification System**: Phase 102 multi-channel notifications deliver urgent alerts to security team

**Examples:**
- ✅ "Flagged individual detected in Zone-A (91% confidence)" → High-priority security work order
- ✅ "Missing person recognized in Building 2" → Alert to authorities
- ✅ "Employee flagged for investigation entering after-hours" → Access log alert + escalation

**Governance Requirements:**
- Privacy compliance (POPIA, GDPR)
- Watchlist management and audit trail
- Confidence threshold configuration per watchlist category
- Opt-out mechanisms for employees
- Data retention policies (24-72 hours typical)

**Why This Works:**
- Same alert and work order pipeline as C•CURE badge events
- Facial recognition equipment maps to existing equipment abstraction
- Security roles inherit view permissions via RLS policies
- No schema changes required — uses existing alert severity/type system

---

## Architectural Advantage: Unified Security Pipeline

All security integrations (C•CURE badge events, Camera/LPR, Facial recognition) leverage the **same** SENTINEL infrastructure without schema modification:

1. **Alert Pipeline**: All security events use `alerts` table (severity, equipment_id, message, status)
2. **Work Order System**: Security work orders route identically to maintenance/operations
3. **Notification Infrastructure**: Phase 102 multi-channel notifications (Telegram, WhatsApp, SMS) deliver alerts
4. **Equipment Abstraction**: Controllers, cameras, facial recognition systems map to existing equipment types
5. **Authorization**: Existing role-based access control (ADMIN, OPERATOR, TECHNICIAN + SECURITY) gates visibility
6. **Audit Trail**: Existing audit logs capture all security events, changes, and resolutions

**Key Insight:** The notification system being built (Phase 102.1 multi-channel technician notifications) was designed to be integration-agnostic. Security systems hook into the same pipelines as HVAC, electrical, and occupancy systems—no special-casing required for new security data sources.

---

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/services/ccure/ccure_adapter.py` | C•CURE API integration adapter |
| `backend/app/services/security_occupancy_service.py` | Occupancy tracking, cross-module coordination, anomaly detection |
| `backend/app/api/security.py` | REST endpoints (/api/security/*) including Phase 69 zone-level endpoints |
| `backend/app/models/security.py` | Security data models (CCureEventType, SecurityOccupancy, etc.) |
| `backend/app/data/ccure_demo_data.json` | Demo badge events, controllers, zones |
| `backend/app/data/modules/site_modules.json` | Module registry with sellable metadata |
| `frontend/src/components/SecurityDashboard.tsx` | Original security dashboard (flat layout) |
| `frontend/src/components/security/SecurityDashboard.tsx` | Phase 69 tabbed security dashboard (5 tabs) |
| `frontend/src/components/SecurityAnomaliesPanel.tsx` | Anomalies display component |
| `supabase/migrations/060_ccure_integration.sql` | Original C•CURE database schema |
| `supabase/migrations/security_module.sql` | Phase 69 schema: access_rules, occupancy extensions |

---

## Troubleshooting

### Demo Mode Not Showing Events
**Check:** ccure_demo_data.json loaded correctly
```bash
python3 -c "import json; json.load(open('backend/app/data/ccure_demo_data.json'))"
```

### API Endpoints Returning 404
**Check:** Security router registered in startup/routes.py
```python
# backend/app/api/registrars/operations.py should include:
from app.api import security
app.include_router(security.router)
```

### Anomalies Not Detected
**Check:** CCureAdapter connected and returning events
```bash
curl http://localhost:9095/api/security/ccure/status
curl http://localhost:9095/api/security/events/anomalies?since=24h
```

---

## See Also

- [C•CURE 9000 Integration Guide](../integrations/ccure-9000-integration.md)
- [Partner Program Roadmap](../integrations/ccure-partner-program-roadmap.md)
- [Security API Reference](../03-api-reference/security-api.md)
- [System Health Dashboard](./74-system-health-diagnostics.md)
