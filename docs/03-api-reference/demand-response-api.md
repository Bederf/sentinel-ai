# Demand Response API

Real-time curtailable HVAC load signal for BESS controllers and demand response aggregators.

**Base URL:** `/api/demand-response`  
**Authentication:** Required (JWT Bearer or API Key)  
**Version:** 1.0.0

---

## Overview

The Demand Response API provides a single endpoint that tells external systems exactly how much HVAC load can be safely curtailed at a site right now, for how long, and with what confidence.

**Primary consumers:**
- IES (BESS hardware manufacturer) — for safe discharge window calculation
- LTM Energy / eSUMS — for DDMP bid preparation

**Compatible with:** Eskom Demand Response Market Programme (DDMP)

---

## Endpoints

### Health Check

```http
GET /api/demand-response/health
```

Returns service status and compatibility information.

**Response:**
```json
{
  "status": "ok",
  "endpoint": "/api/demand-response/curtailable-load",
  "version": "1.0.0",
  "ddmp_compatible": true
}
```

---

### Get Curtailable Load

```http
GET /api/demand-response/curtailable-load?site_id={site_id}&min_priority={min_priority}&include_zones={include_zones}
```

Returns real-time curtailable load signal for a site.

#### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `site_id` | string | Yes | — | Sentinel site ID (e.g., `site-002`) |
| `min_priority` | integer | No | `3` | Minimum zone priority to include (1=critical, 5=lowest). Default P3+ means P3, P4, P5 zones only — never shed P1/P2 (executive/server rooms) |
| `include_zones` | boolean | No | `true` | Include per-zone breakdown in response |

#### Response

**Success (200):**

```json
{
  "site_id": "site-002",
  "timestamp": "2026-05-18T17:45:00Z",
  "curtailable_load_kw": 142.0,
  "safe_duration_minutes": 95,
  "confidence": 0.82,
  "limiting_factor": "chiller_thermal_mass",
  "eskom_stage": 2,
  "is_load_shedding_active": false,
  "ddmp_eligible": true,
  "bess_soc_pct": 78.4,
  "zone_breakdown": [
    {
      "zone_id": "L0-A",
      "zone_name": "Ground Floor Zone A",
      "priority": 3,
      "curtailable_kw": 28.4,
      "current_temp_c": 21.8,
      "setpoint_c": 22.0,
      "headroom_c": 2.2,
      "equipment_count": 4
    }
  ],
  "data_freshness_seconds": 45,
  "calculation_method": "thermal_runway_zone_priority"
}
```

**Field Descriptions:**

| Field | Type | Description |
|-------|------|-------------|
| `site_id` | string | Sentinel site identifier |
| `timestamp` | ISO8601 | UTC timestamp of calculation |
| `curtailable_load_kw` | float | Total HVAC load that can be safely curtailed (kW) |
| `safe_duration_minutes` | integer | Minutes until comfort breach if curtailed |
| `confidence` | float | Prediction confidence (0.0-0.95) |
| `limiting_factor` | string | Primary constraint: `chiller_thermal_mass`, `comfort_boundary`, `bess_low_soc`, `zone_temperature_limit`, `thermal_runway_short`, `none` |
| `eskom_stage` | integer | Current Eskom load shedding stage (0-8) |
| `is_load_shedding_active` | boolean | Whether load shedding is currently active |
| `ddmp_eligible` | boolean | Whether site meets DDMP minimum requirements |
| `bess_soc_pct` | float | BESS state of charge (0-100%), null if no BESS |
| `zone_breakdown` | array | Per-zone details (if include_zones=true) |
| `data_freshness_seconds` | integer | Seconds since last sensor reading |
| `calculation_method` | string | Algorithm used: `thermal_runway_zone_priority` |

#### Zone Breakdown Object

| Field | Type | Description |
|-------|------|-------------|
| `zone_id` | string | Zone identifier |
| `zone_name` | string | Human-readable zone name |
| `priority` | integer | Zone priority (1-5) |
| `curtailable_kw` | float | Estimated curtailable load for this zone |
| `current_temp_c` | float | Current zone temperature |
| `setpoint_c` | float | Zone temperature setpoint |
| `headroom_c` | float | Temperature headroom before comfort boundary |
| `equipment_count` | integer | Number of HVAC equipment in zone |

#### Error Responses

**404 — Site Not Found:**
```json
{
  "detail": "Site site-002 not found"
}
```

**422 — Invalid Parameters:**
```json
{
  "detail": "min_priority must be between 1 and 5"
}
```

**503 — Insufficient Live Data:**
```json
{
  "detail": "Insufficient live sensor data for site site-002. Last reading: 312 seconds ago."
}
```

**401 — Authentication Required:**
```json
{
  "detail": "Authentication required"
}
```

---

## Algorithm

### Curtailable Load Calculation

1. **Validate site exists** — return 404 if not found
2. **Get thermal runway** — minutes until comfort breach using thermal model
3. **Get current HVAC load** — from energy centre power summary
4. **Get zones** — filter by min_priority (P1-P5 system)
5. **Per-zone calculation:**
   - Calculate headroom: `abs(setpoint - current_temp)`
   - If headroom ≥ 2.0°C: 85% of load curtailable
   - If 1.0 ≤ headroom < 2.0°C: proportional curtailment
   - If headroom < 1.0°C: 0 curtailment (at boundary)
   - Apply priority multiplier:
     - P1 (critical): 0% (never curtail)
     - P2 (important): 50% (partial only)
     - P3-P5: 100% (full curtailment eligible)
6. **Sum zone loads** → total `curtailable_load_kw`
7. **Calculate confidence** — weighted average:
   - Data freshness: 30% weight
   - Zone coverage: 40% weight
   - Thermal model confidence: 30% weight
8. **Identify limiting factor** — first match:
   - Thermal runway < 30 min → `chiller_thermal_mass`
   - Headroom < 1.0°C → `comfort_boundary`
   - BESS SOC < 20% → `bess_low_soc`
   - Zones at boundary → `zone_temperature_limit`
   - Thermal runway < 60 min → `thermal_runway_short`
   - Else → `none`
9. **Get BESS SOC** — from `solar_hourly_snapshots` table
10. **Apply DDMP eligibility rules**

### DDMP Eligibility (Eskom Distribution Demand Management Programme)

Site qualifies for **Industrial/Commercial Load Management** stream if ALL conditions met:

- `curtailable_load_kw` ≥ **200 kW** (0.2 MW minimum)
- `safe_duration_minutes` ≥ 60 (must sustain through evening peak)
- If BESS present: `bess_soc_pct` ≥ 20% (backup power available)

**Official Programme Details:**
- **Incentive:** R3 Million per MW of achieved reduction
- **Payment:** Quarterly over 24-month sustainability period
- **Aggregation:** Up to 4 sites (same entity) can be combined
- **Implementation:** 6 months from approval
- **Target:** Evening peak period load clipping/shifting
- **Important:** Does NOT grant exemption from load shedding

**Reference:** [Eskom DDMP Official Page](https://www.eskom.co.za/distribution/demand-management-programme/)

**Example Portfolio:**
```
Building A (Sandton):     85 kW  ← our endpoint measures this
Building B (Rosebank):    92 kW  ← our endpoint measures this
Building C (Midrand):     78 kW  ← our endpoint measures this
                         ----
Portfolio Total:         255 kW  ← exceeds 200 kW minimum ✅

Incentive: 0.255 MW × R3M = R765,000 over 24 months
```

**Note:** Single buildings may not hit 200 kW, but portfolios easily do through aggregation.

### Data Freshness Guard

If the most recent sensor reading is older than **300 seconds (5 minutes)**, the endpoint returns **503 Service Unavailable**.

This is a safety requirement — BESS controllers and DR aggregators should not act on stale data.

---

## Examples

### Example 1: Basic Request

```bash
curl -H "Authorization: Bearer $JWT_TOKEN" \
  "https://bms.sentinel-ai.co.za/api/demand-response/curtailable-load?site_id=site-002"
```

### Example 2: Exclude Zone Breakdown (Faster)

```bash
curl -H "Authorization: Bearer $JWT_TOKEN" \
  "https://bms.sentinel-ai.co.za/api/demand-response/curtailable-load?site_id=site-002&include_zones=false"
```

### Example 3: Include Lower Priority Zones

```bash
curl -H "Authorization: Bearer $JWT_TOKEN" \
  "https://bms.sentinel-ai.co.za/api/demand-response/curtailable-load?site_id=site-002&min_priority=4"
```

---

## Dependencies

The endpoint assembles data from existing Sentinel components:

| Component | Source |
|-----------|--------|
| Thermal runway | `thermal_model.calculate_thermal_runway()` |
| Zone priority | `DeviceLocation.zone_priority` / `ZoneType` enum |
| Eskom schedule | `eskomsepush_service` |
| HVAC load | `energy_centre_service.get_power_summary()` |
| BESS SOC | `solar_hourly_snapshots.bess_soc_pct` |
| Zone definitions | Supabase `zones` table |
| Equipment data | Supabase `equipment` table |
| Sensor readings | Supabase `equipment_sensor_readings` table |

---

## Testing

Run the test suite:

```bash
cd /opt/bms-intelligence/backend
python3 -m pytest tests/services/test_demand_response.py -v
```

**Test coverage:**
- Happy path with full response
- Zone at comfort boundary (zero curtailment)
- BESS not present (null SOC)
- BESS low SOC (limiting factor)
- Stale data (503 error)
- Site not found (404 error)
- All zones P1/P2 (reduced curtailment)
- Confidence calculation formula
- DDMP eligibility rules
- min_priority filtering

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-05-18 | Initial release — Phase 211 |

---

## See Also

- [Phase 211 Document](../../vault/00-GSD-Phases/Phase-211-Demand-Response-Endpoint.md)
- [Thermal Model](../02-architecture/thermal-model.md)
- [Zone Priority System](../02-architecture/zone-priorities.md)
- [DDMP Requirements](https://www.eskom.co.za/demand-response/)
