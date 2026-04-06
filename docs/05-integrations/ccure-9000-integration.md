---
title: "C•CURE 9000 Integration Guide"
type: "spec"
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

# C•CURE 9000 Integration Guide

## Overview

**Platform:** Johnson Controls / Software House C•CURE 9000 v2.90+
**Protocol:** victor Web Service API (RESTful, IIS-hosted)
**License:** Software House Connected Partner Program (300+ existing partners)
**SENTINEL Role:** Read-only intelligence overlay on existing security infrastructure

### Integration Philosophy

SENTINEL is an **intelligence overlay** on top of existing BMS and access control systems. For C•CURE integration, this means:
- **Read-only observer** - SENTINEL reads badge events, door status, alarms
- **No direct control** - SENTINEL generates recommendations; operators execute in C•CURE UI
- **Intelligence layer** - Anomaly detection, cross-system correlation, predictive insights
- **Rapid onboarding** - 1-2 day integration for clients with existing C•CURE licenses

### Integration Phases

**Phase 58.2 (Current):** Demo mode with mock data. Demonstrates integration capability without requiring Partner Program license.

**Phase 58.3 (Future):** Live integration via victor Web Service API. Requires Software House Connected Partner Program membership.

---

## System Architecture

### Data Flow

```
C•CURE System
    ↓ (victor Web Service API)
CCureAdapter (Demo or Live mode)
    ↓ (normalized SENTINEL events)
SecurityService
    ↓
Supabase (security_badge_events, ccure_controllers, security_anomalies)
    ↓
SENTINEL Intelligence Layer
    ├─ After-Hours Anomaly Detection
    ├─ Security Equipment Health Monitoring
    └─ Occupancy-Driven Energy Optimization
    ↓
UI Dashboard + API Endpoints
```

### Integration Options

#### Option 1: Demo Mode (Phase 58.2)
- Uses `ccure_demo_data.json` with realistic sample data
- No API credentials required
- Demonstrates full intelligence pipeline
- **Enabled by default** for rapid prototyping

```python
adapter = CCureAdapter(demo_mode=True)
await adapter.connect()
```

#### Option 2: Live Mode (Phase 58.3)
- Requires Software House Connected Partner Program membership
- Implements victor Web Service API client
- OAuth authentication with C•CURE operator account
- Automatic event polling (60-second intervals in Phase 58.2, WebSocket upgrade in Phase 58.3)

```python
adapter = CCureAdapter(
    api_url="https://ccure.example.com/api",
    license_guid="SENTINEL-CCURE-GUID",
    username="sentinel_operator",
    password="<secure_password>",
    demo_mode=False
)
await adapter.connect()
```

---

## Data Entity Mapping: C•CURE ↔ SENTINEL

### Personnel

| C•CURE Field | SENTINEL Field | Purpose |
|---|---|---|
| Person ID | `person_id` | Unique identifier |
| Badge ID / Credential | `badge_id` | Physical credential number |
| First Name + Last Name | `person_name` | Display name in events |
| Department | `department` | For correlation with organizational zones |
| Clearance (e.g., IT-ADMIN) | `clearance_level` | Access privilege level |

### Doors & Readers

| C•CURE Field | SENTINEL Field | Purpose |
|---|---|---|
| Door ID | `door_id` | Unique identifier in C•CURE |
| Door Name | `name` | Human-readable (e.g., "Level 1 - Executive Suite Entry") |
| Zone | `zone_id` | Anti-passback zone in C•CURE |
| Door Status | `status` | locked, open, alarm |
| Reader Type | `reader_type` | card, biometric, pin |
| Reader Status | `reader_status` | online, offline, fault |

### Access Events

| C•CURE Field | SENTINEL Field | Purpose |
|---|---|---|
| Event Type | `event_type` | access_granted, access_denied, forced_door, etc. |
| Event ID | `event_id` | Unique event identifier |
| Badge ID | `badge_id` | Cardholder credential |
| Person Name | `person_name` | Badge holder name |
| Department | `department` | For cross-system correlation |
| Clearance | `clearance_level` | Authorization level |
| Timestamp | `timestamp` | Event time (ISO 8601) |
| Door | `door_id` | Which door accessed |
| Zone | `zone_id` | Anti-passback zone |
| Direction | `direction` | entry or exit |
| Granted | `granted` | True if access allowed, false if denied |
| Reason | `reason` | "Valid access", "Invalid credential", etc. |

### Controllers (iSTAR Hardware)

| C•CURE Field | SENTINEL Field | Purpose |
|---|---|---|
| Controller ID | `controller_id` | Unique identifier |
| Name | `name` | Human-readable (e.g., "iSTAR Ultra - Ground Floor") |
| Model | `model` | iSTAR Ultra, iSTAR Edge, iSTAR Standard |
| Firmware | `firmware` | Version (e.g., "5.10.2") |
| Encryption | `encryption_mode` | FIPS 197 AES-256, FIPS 140-2 |
| Tamper Status | `tamper_status` | normal, enclosure_open, back_tamper |
| Last Seen | `last_seen` | Last heartbeat timestamp |
| IP Address | `ip_address` | Network address for diagnostics |
| Reader Count | `reader_count` | Number of readers connected |
| Status | `status` | online, offline, degraded |

### Clearance / Access Level

| C•CURE Field | SENTINEL Field | Purpose |
|---|---|---|
| Clearance ID | `clearance_id` | Unique identifier |
| Name | `name` | Human-readable level (e.g., "IT-ADMIN") |
| Partition | `partition` | C•CURE partition for multi-tenant |
| Doors | `door_ids` | List of doors with access |
| Time Schedules | `time_schedules` | When access is allowed |

### Anti-Passback Zones

| C•CURE Field | SENTINEL Field | Purpose |
|---|---|---|
| Zone ID | `zone_id` | Unique identifier in C•CURE |
| Zone Name | `name` | Human-readable (e.g., "Level 1 - Executive Suite") |
| Current Count | `current_count` | Real-time occupancy |
| Max Occupancy | `max_occupancy` | Design capacity |
| Anti-Passback | `anti_passback_enabled` | True if enforcement active |

---

## Event Types & Anomaly Detection

### Standard Event Types

```
access_granted      - Person with valid credential entered zone
access_denied       - Person with invalid/revoked credential denied
forced_door         - Door opened without valid credential (ALARM!)
door_held_open      - Door held open >threshold duration (WARNING)
anti_passback       - Anti-passback rule violated (WARNING)
controller_offline  - iSTAR controller lost network (CRITICAL)
duress              - Duress button activated (CRITICAL)
tamper              - Enclosure tamper detected (CRITICAL)
```

### Anomaly Detection Patterns

#### Pattern 1: After-Hours Access + HVAC/Lighting Activation

**Detection:**
1. Badge access outside business hours (18:00-06:00)
2. Within 15 minutes: HVAC zone activated (setpoint lowered from unoccupied)
3. Within 15 minutes: Lighting zone activated (>50% brightness from off)

**Severity:** WARNING (possible after-hours work) → CRITICAL (if repeated + forced door events)

**Recommendation:**
```
"After-hours access by [Name] at [Time] in [Zone].
 Unexpected HVAC/lighting activation detected.
 Energy impact: ~2-5 kWh excess per hour.
 Action: Verify access was authorized, review occupancy schedule."
```

**Business Value:**
- Detect unauthorized after-hours facility usage
- Identify energy waste from unscheduled occupancy
- Catch insider threats (employee accessing restricted zones after hours)

#### Pattern 2: Controller Offline + Network Degradation

**Detection:**
1. iSTAR controller heartbeat lost (status: offline)
2. Network switch port down (correlated with infrastructure alerts)
3. UPS battery <30% (indicates building infrastructure issue)

**Severity:** CRITICAL (doors may revert to fail-safe)

**Recommendation:**
```
"iSTAR controller [Name] offline since [Time].
 Network status: [Switch] port [Port] DOWN
 UPS battery: [Level]%
 Action: Check physical switch connection, power supply, or firmware fault.
 Impact: Doors on this controller may be in fail-safe state."
```

**Business Value:**
- Predictive maintenance (catch network issues before they cause lockout)
- SLA compliance (track controller uptime, plan upgrades)
- Incident response (know quickly if security infrastructure degraded)

#### Pattern 3: Anti-Passback Violation

**Detection:**
1. Same badge ID exits a zone, then attempts entry <5 minutes later
2. Entry denied by anti-passback rule

**Severity:** WARNING (could be tailgating or credential fraud)

**Recommendation:**
```
"Anti-passback violation by [Name] at [Door].
 Same credential used at entry without prior exit recorded.
 Possible: Credential lending, tailgating, system glitch.
 Action: Review video, verify with cardholder."
```

**Business Value:**
- Detect credential fraud and tailgating
- Identify zones with high violation rates (training opportunity)

---

## Cross-System Correlation Examples

### Example 1: Occupancy-Driven Energy Optimization

```
Real-Time Occupancy Feed (from C•CURE anti-passback zones):
├─ Level 1 Executive Suite: 3 people
├─ Level 2 Open Office: 8 people
└─ Level 3 Server Room: 0 people

SENTINEL Recommendations:
├─ HVAC: Maintain 22°C in occupied zones, relax to 28°C in empty zones
├─ Lighting: 100% brightness in occupied zones, dim to 20% when empty
└─ ENERGY IMPACT: Estimated 15-20% energy savings vs. 24/7 operation
```

### Example 2: Security Equipment Health Correlation

```
C•CURE Event: "iSTAR Edge - Level 3" controller OFFLINE at 03:22

SENTINEL Correlations:
├─ Network: Switch port 24 DOWN (same time)
├─ Power: UPS battery 45% (generator on standby)
├─ Infrastructure Health Score: DEGRADED
└─ Recommendation: "Check network connection at L3 switch,
                    prepare maintenance window, verify backup power"
```

### Example 3: After-Hours Security + Energy Anomaly

```
Badge Event: "Johan van der Merwe" entry at 21:30 (after-hours)
  Department: IT Operations
  Zone: Level 1 Executive Suite
  Clearance: IT-ADMIN

SENTIMENT Correlations:
├─ HVAC Zone L1: Setpoint changed 28°C→22°C at 21:35 (+5 min)
├─ Lighting Zone L1: Activated 0%→100% at 21:32 (+2 min)
├─ Energy Impact: +3.5 kWh/hour (HVAC) + 0.75 kWh/hour (Lighting)
└─ Security Status: After-hours access AUTHORIZED per IT-ADMIN clearance
    BUT: Recommend energy lockdown (after-hours setpoint + dim lighting)
```

---

## API Integration Points

### Polling Strategy (Phase 58.2)

**Interval:** 60 seconds
**Data Sources:**
- Badge events (since last poll)
- Door status (all doors)
- Controller heartbeats (all iSTAR units)
- Anti-passback zone occupancy

**Upgrade Path (Phase 58.3):**
- Switch from polling to WebSocket real-time events
- Reduce latency from 60s to <1s
- Enable real-time alerting for critical events

### Endpoint Implementation

#### Core Data Fetching (CCureAdapter)

```python
async def get_badge_events(since: datetime) -> List[Dict]
  # Returns events after timestamp with full details (person, dept, clearance)

async def get_door_status(door_id: str) -> Dict
  # Returns current status + last event time

async def get_controllers() -> List[CCureController]
  # Returns all iSTAR controllers with tamper/offline status

async def get_occupancy(zone_id: str) -> Dict
  # Returns current occupancy from anti-passback zones

async def get_personnel(badge_id: str) -> Optional[CCurePersonnel]
  # Lookup person details by badge ID
```

#### Anomaly Detection (SecurityOccupancyService)

```python
detect_after_hours_anomaly() -> List[Dict]
  # Priority 1: After-hours + HVAC/lighting correlation

detect_security_equipment_health_issues() -> List[Dict]
  # Priority 2: Controller offline + network correlation
```

#### REST API Endpoints

```
GET  /api/security/ccure/status
  → Integration mode (demo/live), license status, system health

GET  /api/security/events/anomalies?since=24h&type=after_hours_access
  → Security anomalies with severity, correlations, recommendations

GET  /api/security/occupancy/real-time
  → Per-zone occupancy + HVAC/lighting recommendations
```

---

## Implementation Checklist

- [ ] **Phase 58.2 (Current)**
  - [x] Documentation (this file + partner roadmap)
  - [x] Extended security models (CCureEventType, CCurePersonnel, CCureController)
  - [x] Database migration (anomaly tracking, controller tables)
  - [x] CCureAdapter class (demo mode)
  - [x] Demo data JSON (5 events, 2 controllers, 2 doors, 2 zones)
  - [x] SecurityOccupancyService intelligence methods
  - [x] API endpoints (/ccure/status, /events/anomalies, /occupancy/real-time)
  - [x] Frontend dashboard updates (C•CURE status card, anomalies panel)

- [ ] **Phase 58.3 (Future)**
  - [ ] Software House Connected Partner Program membership
  - [ ] victor Web Service API client implementation
  - [ ] OAuth authentication with C•CURE operators
  - [ ] WebSocket upgrade for real-time events
  - [ ] Live testing with customer C•CURE instance
  - [ ] Certification through Software House

- [ ] **Phase 58.4 (Future)**
  - [ ] Multi-platform adapter abstraction (Lenel, Gallagher, Paxton)
  - [ ] Bi-directional control (door unlock/lock with safety validation)
  - [ ] FSR Domain 4 compliance

---

## Client Onboarding (1-2 Days)

### Prerequisites
- Client has C•CURE 9000 v2.90+ deployed
- Client has valid Software House Connected Partner Program license (or licensing applied for)
- C•CURE administrator access to configure Operator account
- Operator account with "SYSTEM ALL" permission

### Onboarding Steps

1. **SENTINEL Deployment** (Day 1, 1 hour)
   - Deploy SENTINEL stack with C•CURE module enabled
   - Verify demo mode shows realistic sample data

2. **C•CURE Operator Account Setup** (Day 1, 30 min)
   - Client creates "sentinel_operator" account in C•CURE
   - Assigns "SYSTEM ALL" permission
   - Generates API credentials (Phase 58.3 only)

3. **Live Integration Configuration** (Day 1, 30 min - Phase 58.3+)
   - Input C•CURE API endpoint in SENTINEL settings
   - Configure operator credentials (encrypted storage)
   - Enable live mode in CCureAdapter
   - Test badge event polling

4. **Intelligence Validation** (Day 1, 1 hour)
   - Trigger test after-hours access
   - Verify anomaly detection working
   - Confirm HVAC/lighting correlation visible
   - Show real-time occupancy feed

5. **Dashboard Training** (Day 2, 30 min)
   - Show C•CURE status card (demo vs. live)
   - Explain anomaly severity levels
   - Walk through cross-system recommendations
   - Show ROI (energy savings, security improvements)

6. **Go-Live** (Day 2)
   - Enable production badges
   - Configure alert thresholds
   - Set up notification rules
   - Handoff to client operations team

---

## Troubleshooting

### Demo Mode Not Showing Events
**Check:** `ccure_demo_data.json` loaded correctly
```bash
python -c "import json; json.load(open('backend/app/data/ccure_demo_data.json'))"
```

### API Endpoints Returning 404
**Check:** Registrar includes security routes
```python
# backend/app/api/registrars/operations.py should include:
from app.api import security
app.include_router(security.router)
```

### Anomalies Not Detected
**Check:** CCureAdapter connected and returning events
```bash
# Test adapter directly
cd backend
python -c "
import asyncio
from app.services.ccure.ccure_adapter import CCureAdapter
async def test():
    adapter = CCureAdapter(demo_mode=True)
    await adapter.connect()
    events = await adapter.get_badge_events()
    print(f'Events: {len(events)}')
asyncio.run(test())
"
```

### Controllers Showing as Offline
**Check:** Controller status calculation
```bash
# Verify ccure_controllers table has correct data
psql $DATABASE_URL -c "SELECT controller_id, name, status, last_seen FROM ccure_controllers LIMIT 5;"
```

---

## References

- **Software House:** https://softwarehouse.com/products/ccure-9000/
- **Partner Program:** https://softwarehouse.com/partner-network/
- **victor API Docs:** https://softwarehouse.com/developers/ (requires partnership)
- **Existing Partners:** Envoy, Milestone, HID, Oloid, 300+ others
- **SENTINEL Security Module:** Phase 58 - Access Control, CCTV, Alarms

---

*Last Updated: Phase 58.2*
*Next Review: Phase 58.3 (Live API Implementation)*
