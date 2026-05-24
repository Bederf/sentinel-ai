---
title: "Peak Demand Management API Reference"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-02-12"
updated: "2026-02-12"
author: "SENTINEL Development Team"
tags: ["api", "peak-demand", "nmd", "demand-management", "load-shedding", "tariff", "cost-optimization"]
domain: "solar"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 15
related: ["solar-api.md", "municipal-billing.md", "optimization.md"]
---

# Peak Demand Management API Reference

REST API endpoints for real-time peak demand monitoring, NMD (Notified Maximum Demand) compliance, demand forecasting, and multi-system peak shaving coordination. Implemented in Phase 081 (Solar + BESS Peak Demand Management with Municipal Bill Integration).

**Base path:** `/api/peak-demand`

**Demo site:** `S002` (Sandton City, 6,000 kVA NMD limit)

## Overview

The Peak Demand Management system monitors real-time demand against contractual NMD limits, coordinates multi-module load reduction (Solar/BESS discharge, HVAC setpoint adjustments, load deferral), and provides cost-optimized recommendations to prevent expensive demand charge penalties.

**Key Features:**
- Real-time demand monitoring vs NMD limit
- 24-hour demand forecasting with confidence bands
- Multi-module peak shaving coordination (Solar, HVAC, Energy)
- TOU (Time-of-Use) tariff integration
- Municipal bill NMD extraction and database persistence
- Cost-benefit analysis for peak shaving actions
- Automatic multi-system approval workflow integration

## Data Sources

**Primary (Supabase):**
- `buildings.nmd_limit_kva` - Contractual NMD from municipal bill (extracted via SIMBIOT ingestion)
- `buildings.demand_charge_per_kva` - Cost per kVA exceeding NMD
- `buildings.tariff_band` - Current TOU band (off-peak, standard, peak)

**Fallback (Seeded Defaults):**
- If NMD not in database: 6,000 kVA (S002), 8,000 kVA (site-003)
- If demand data unavailable: Last known value + forecast model

**Real-Time:**
- Current building demand from energy meter or sum of major equipment
- Ambient conditions for HVAC load estimation
- BESS SOC (State of Charge) for dispatch availability

## Status Endpoint (Real-Time Monitoring)

### GET `/api/peak-demand/{site_id}/status`

Get current demand status with NMD headroom, trend analysis, and available reductions.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `site_id` | string | Yes | Building code (e.g., `S002`, `site-003`) |

**Response:**
```json
{
  "site_id": "S002",
  "timestamp": "2026-02-12T14:30:00Z",
  "current_demand_kw": 5500,
  "nmd_limit_kva": 6000,
  "headroom_kw": 500,
  "headroom_percent": 8.3,
  "headroom_level": "critical",
  "demand_trend": "rising",
  "trend_rate_kw_per_min": 15.5,
  "minutes_to_breach": 32,
  "active_modules": ["solar", "hvac"],
  "available_reductions": {
    "solar": {
      "module": "solar",
      "max_reduction_kw": 200,
      "method": "bess_discharge",
      "duration_minutes": 60,
      "cost_savings_zar_per_kwh": 3.21,
      "availability": "available"
    },
    "hvac": {
      "module": "hvac",
      "max_reduction_kw": 50,
      "method": "setpoint_increase",
      "duration_minutes": 120,
      "comfort_impact": "slight",
      "availability": "available"
    },
    "energy": {
      "module": "energy",
      "max_reduction_kw": 30,
      "method": "load_deferral",
      "duration_minutes": 45,
      "availability": "unavailable",
      "reason": "No deferrable loads currently idle"
    }
  },
  "tariff_info": {
    "current_band": "peak",
    "demand_charge_zar_per_kva": 155.50,
    "estimated_monthly_penalty_zar": 77750.00
  },
  "last_nmd_extraction": "2026-02-10T09:15:00Z",
  "nmd_source": "municipal_bill"
}
```

**Headroom Levels:**
- **healthy** (>15%): Normal operation, no action needed
- **warning** (5-15%): Monitor closely, prepare to reduce demand
- **critical** (<5%): Activate peak shaving immediately

**Status Codes:**
- `200 OK` - Successful
- `400 Bad Request` - Invalid site_id
- `503 Service Unavailable` - NMD data unavailable (using fallback)

---

## Forecast Endpoint (24-Hour Projection)

### GET `/api/peak-demand/{site_id}/forecast-24h`

Get 24-hour demand forecast with hourly granularity and confidence bands.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `site_id` | string | Yes | Building code |

**Response:**
```json
{
  "site_id": "S002",
  "generated_at": "2026-02-12T10:00:00Z",
  "nmd_limit_kva": 6000,
  "forecast_accuracy_rmse_kw": 180,
  "peak_hour": "2026-02-12T18:30:00Z",
  "peak_demand_kw": 5850,
  "peak_headroom_percent": 2.5,
  "will_breach_nmd": true,
  "hours": [
    {
      "hour": "2026-02-12T10:00:00Z",
      "demand_kw": 4200,
      "demand_high_confidence_kw": 4500,
      "demand_low_confidence_kw": 3900,
      "headroom_kw": 1800,
      "headroom_percent": 30.0,
      "headroom_level": "healthy",
      "tariff_band": "standard",
      "occupancy_pct": 60,
      "outdoor_temp_c": 24,
      "solar_available_kw": 1200
    },
    {
      "hour": "2026-02-12T18:00:00Z",
      "demand_kw": 5650,
      "demand_high_confidence_kw": 6100,
      "demand_low_confidence_kw": 5200,
      "headroom_kw": 350,
      "headroom_percent": 5.8,
      "headroom_level": "critical",
      "tariff_band": "peak",
      "occupancy_pct": 80,
      "outdoor_temp_c": 32,
      "solar_available_kw": 50
    }
  ],
  "summary": {
    "forecast_hours_critical": 3,
    "forecast_hours_warning": 5,
    "forecast_hours_healthy": 16,
    "estimated_peak_charge_zar": 77750,
    "recommended_peak_shaving_hours": ["18:00", "18:30", "19:00"]
  }
}
```

**Confidence Bands:**
- **high_confidence_kw**: 90th percentile (pessimistic forecast)
- **demand_kw**: Median estimate (most likely)
- **low_confidence_kw**: 10th percentile (optimistic forecast)

Use `high_confidence_kw` for conservative planning, `demand_kw` for typical analysis.

---

## Recommendations Endpoint (Multi-Module Shaving)

### GET `/api/peak-demand/{site_id}/recommendations`

Get AI-generated multi-module recommendations for peak shaving with cost-benefit analysis.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `site_id` | string | Yes | Building code |
| `urgency` | string | No | Filter by urgency: `critical`, `warning`, `routine` (default: all) |

**Response:**
```json
{
  "site_id": "S002",
  "generated_at": "2026-02-12T14:35:00Z",
  "current_demand_kw": 5500,
  "nmd_limit_kva": 6000,
  "headroom_percent": 8.3,
  "recommendations": [
    {
      "id": "rec-20260212-001",
      "type": "multi_module_shaving",
      "urgency": "critical",
      "reason": "NMD breach imminent (95% of limit, approaching peak tariff window)",
      "created_at": "2026-02-12T14:35:00Z",
      "expires_at": "2026-02-12T14:50:00Z",
      "modules_involved": ["solar", "hvac"],
      "module_actions": [
        {
          "module": "solar",
          "action": "bess_discharge_200kw",
          "description": "Discharge BESS at 200 kW for 60 minutes",
          "duration_minutes": 60,
          "estimated_reduction_kw": 200,
          "estimated_cost_savings_zar": 31100,
          "constraints": {
            "min_final_soc_pct": 20,
            "max_discharge_rate_kw": 250
          }
        },
        {
          "module": "hvac",
          "action": "setpoint_increase_2c",
          "description": "Increase chilled water setpoint from 7°C to 9°C",
          "duration_minutes": 120,
          "estimated_reduction_kw": 50,
          "comfort_impact": "slight",
          "estimated_cost_savings_zar": 7775
        }
      ],
      "estimated_total_reduction_kw": 250,
      "estimated_total_savings_zar": 38875,
      "estimated_payback_minutes": 15,
      "safety_constraints_met": true,
      "requires_operator_approval": true,
      "approval_workflow": "tier_2",
      "status": "pending_approval"
    },
    {
      "id": "rec-20260212-002",
      "type": "multi_module_shaving",
      "urgency": "warning",
      "reason": "Peak tariff window starting in 2 hours, forecast predicts 5.8% headroom",
      "created_at": "2026-02-12T14:35:00Z",
      "expires_at": "2026-02-12T16:35:00Z",
      "modules_involved": ["solar", "energy"],
      "module_actions": [
        {
          "module": "solar",
          "action": "bess_discharge_150kw",
          "description": "Discharge BESS at 150 kW starting at 16:00",
          "duration_minutes": 90,
          "estimated_reduction_kw": 150,
          "estimated_cost_savings_zar": 23325
        },
        {
          "module": "energy",
          "action": "pump_defer_30min",
          "description": "Defer chilled water pump operation by 30 minutes",
          "duration_minutes": 30,
          "estimated_reduction_kw": 40,
          "estimated_cost_savings_zar": 6200
        }
      ],
      "estimated_total_reduction_kw": 190,
      "estimated_total_savings_zar": 29525,
      "estimated_payback_minutes": 25,
      "status": "pending_approval"
    }
  ]
}
```

**Status Enum:**
- `pending_approval` - Awaiting operator action
- `approved` - Operator approved, executing
- `executed` - Changes successfully applied
- `rejected` - Operator rejected recommendation
- `expired` - Recommendation validity window closed

---

## Approval Endpoint (Operator Sign-Off)

### POST `/api/peak-demand/{site_id}/approve-recommendation`

Approve a peak shaving recommendation and execute all coordinated module actions.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `site_id` | string | Yes | Building code |

**Request Body:**
```json
{
  "recommendation_id": "rec-20260212-001",
  "approved_by": "technician@site-002",
  "approval_notes": "Peak demand response approved - load deferral available"
}
```

**Response:**
```json
{
  "recommendation_id": "rec-20260212-001",
  "status": "executing",
  "approval_timestamp": "2026-02-12T14:36:00Z",
  "executed_actions": [
    {
      "module": "solar",
      "action": "bess_discharge_200kw",
      "status": "executing",
      "equipment_id": "S002-BESS-B1-001",
      "power_output_kw": 200,
      "start_time": "2026-02-12T14:36:05Z",
      "expected_completion": "2026-02-12T15:36:05Z"
    },
    {
      "module": "hvac",
      "action": "setpoint_increase_2c",
      "status": "executing",
      "equipment_id": "S002-VAV-101",
      "setpoint_previous": 7,
      "setpoint_target": 9,
      "setpoint_current": 7.5,
      "change_rate_c_per_min": 0.25,
      "start_time": "2026-02-12T14:36:05Z",
      "expected_completion": "2026-02-12T14:44:05Z"
    }
  ],
  "estimated_time_to_reduction_sec": 5,
  "estimated_demand_reduction_kw": 250,
  "monitoring_interval_sec": 30,
  "auto_rollback_on_failure": true
}
```

**Status Codes:**
- `200 OK` - Recommendation approved, actions executing
- `400 Bad Request` - Invalid recommendation_id or site_id
- `409 Conflict` - Recommendation already processed or expired
- `503 Service Unavailable` - One or more module actions failed

---

## Summary Endpoint (Building Overview)

### GET `/api/peak-demand/{site_id}/summary`

Get concise demand summary for dashboard cards.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `site_id` | string | Yes | Building code |

**Response:**
```json
{
  "site_id": "S002",
  "timestamp": "2026-02-12T14:30:00Z",
  "demand_kw": 5500,
  "nmd_limit_kva": 6000,
  "headroom_percent": 8.3,
  "status": "critical",
  "peak_forecast_kw": 5850,
  "peak_forecast_hour": "18:30",
  "will_breach": true,
  "pending_recommendations": 2,
  "active_shaving": false,
  "estimated_monthly_demand_charge_zar": 930000
}
```

---

## Background Coordinator Service

The Demand-Aware Coordinator (`backend/app/services/demand_aware_coordinator.py`) runs automatically every 5 minutes to monitor NMD headroom and generate recommendations without manual triggers.

**Workflow:**
```
Every 5 minutes:
  1. Query building.nmd_limit_kva from Supabase (with fallback)
  2. Get current demand from meter/equipment
  3. Calculate headroom vs NMD limit
  4. Query active modules (Solar, HVAC, Energy, etc.)
  5. Call module-specific optimization methods
  6. If headroom < 15%:
     → Generate AI recommendation with module actions
     → Store in recommendations table
     → Return to API endpoint (user sees on dashboard)
  7. If recommendation approved:
     → Execute approval workflow (Tier 2)
     → Write changes to devices via device_manager
     → Verify COV feedback from devices
     → Create audit log entry
```

**Performance:**
- Coordinator cycle time: 2-5 seconds (fast enough for 5-minute interval)
- API response time: <1 second (recommendations pre-calculated)
- Database queries cached (5-minute TTL on NMD lookups)

**Full algorithm documentation:** [Demand-Aware Coordinator Feature Guide](../04-features/13-demand-aware-coordinator.md)

---

## BESS Real-Time Shaving Thresholds

**Source:** `backend/app/services/solar_demand_service.py:793`

The BESS shaving engine runs independently (event-driven, not part of the 5-min coordinator cycle). It monitors demand continuously and triggers discharge at NMD thresholds:

| Condition | Action | Priority |
|-----------|--------|----------|
| `demand > 95% NMD` | Max discharge: `min(BESS_RATED_POWER, demand - (NMD × 0.85))` | **critical** |
| `demand > 85% NMD` | Discharge: `min(BESS_RATED_POWER, demand - (NMD × 0.85))` | **high** |
| `demand > 85% × 0.9` and rising | BESS on standby | **medium** |
| Below threshold | No action | **low** |

BESS peak shaving **always preempts TOU arbitrage** — when demand approaches NMD, the battery prioritises shaving over energy trading.

Example for site-002 (NMD = 1,820 kVA):
- 85% threshold = **1,547 kW**
- 95% threshold = **1,729 kW**
- At 1,730 kW demand: discharge `min(200, 1730 - 1547)` = **183 kW**

---

## Demand Ratchet (12-Month Rolling Peak)

**Source:** `backend/app/services/demand_ratchet.py`

City Power bills the higher of current month peak or the highest peak in the previous 11 months. The ratchet algorithm calculates:

```
ratchet_kva       = max(trailing 11 month peaks)
billing_kva       = max(current_peak, ratchet_kva)
shaving_target    = ratchet_kva (or NMD × 0.85 if no ratchet yet)
spike_cost_r      = (current_peak - shaving_target) × demand_charge_rate
```

Full algorithm documentation: [Demand Ratchet Algorithm](../04-features/12-demand-ratchet-algorithm.md)

---

## NMD Data Sources & Persistence

### Municipal Bill Integration

NMD limit is extracted from municipal electricity bills via SIMBIOT ingestion and stored in `buildings.nmd_limit_kva`.

**PDF Upload Flow:**
1. Site manager uploads electricity bill PDF → `/api/municipal-billing/invoices/upload`
2. SIMBIOT invoice service processes PDF
3. AI extracts NMD value from bill metadata (e.g., "Notified Maximum Demand: 6,000 kVA")
4. Updates `buildings` table:
   - `nmd_limit_kva` = extracted value
   - `demand_charge_per_kva` = extracted rate
   - `nmd_extracted_from_bill` = true
   - `bill_last_uploaded_at` = timestamp
   - `electricity_provider` = extracted municipality
   - `billing_cycle_start_date` = extracted period

**See also:** [Municipal Billing API](municipal-billing.md)

### Manual NMD Update (Admin)

Update NMD via admin panel or direct API (not recommended):
```bash
curl -X PATCH http://localhost:9095/api/buildings/S002 \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"nmd_limit_kva": 6000}'
```

### Fallback Values (No Bill Uploaded)

If NMD not in database, coordinator uses seeded defaults:
- S002 (Sandton Office): 6,000 kVA
- site-003 (Hospital): 8,000 kVA
- Other sites: 6,000 kVA (default)

---

## Caching Strategy

**NMD Limit Cache (5-minute TTL):**
- Coordinator caches building NMD values in memory
- Prevents N+1 database queries during 5-minute evaluation cycle
- Cache invalidated on bill upload or manual update

**Demand Data Cache (1-minute TTL):**
- Current demand cached to avoid re-querying meter
- Forecast cache refreshed hourly

**Recommendation Cache (15-minute TTL):**
- Pending recommendations kept in memory
- Cleared on approval/rejection or expiry

---

## Error Handling

**NMD Data Unavailable:**
```json
{
  "status": "503 Service Unavailable",
  "message": "NMD limit not available, using fallback value",
  "nmd_limit_kva": 6000,
  "nmd_source": "fallback",
  "fallback_reason": "No municipal bill uploaded, using default"
}
```

**Module Unavailable During Approval:**
```json
{
  "status": "503 Service Unavailable",
  "message": "One or more modules unavailable for peak shaving",
  "failed_modules": ["hvac"],
  "failed_reason": "HVAC setpoint adjustment blocked by safety engine",
  "executed_modules": ["solar"],
  "partial_reduction_kw": 200
}
```

---

## Integration with Other Systems

### Solar Module Integration
- Peak demand status displayed on Solar dashboard
- BESS dispatch coordinated with demand limits
- Cost savings from demand reduction tracked separately

**See also:** [Solar API](solar-api.md)

### HVAC Module Integration
- Setpoint adjustments coordinated with thermal comfort
- Occupancy and weather integrated into impact analysis
- Chilled water loop demand estimated from occupancy + outdoor temp

**See also:** [HVAC API](hvac.md)

### Approval Workflow Integration
- Multi-module recommendations routed through Tier 2 approval
- COV feedback verifies device changes
- Rollback available if issues detected post-execution

**See also:** [Recommendations API](recommendations-api.md)

---

## Examples

### Example 1: Monitor Current Demand
```bash
curl http://localhost:9095/api/peak-demand/S002/status \
  -H "Authorization: Bearer <token>"
```

**Response (Healthy):**
```json
{
  "site_id": "S002",
  "current_demand_kw": 4200,
  "nmd_limit_kva": 6000,
  "headroom_percent": 30.0,
  "headroom_level": "healthy",
  "demand_trend": "stable"
}
```

### Example 2: Check Peak Forecast
```bash
curl http://localhost:9095/api/peak-demand/S002/forecast-24h \
  -H "Authorization: Bearer <token>"
```

**Response:** Shows peak demand at 18:30 = 5,850 kW (97.5% of NMD).

### Example 3: Approve Peak Shaving
```bash
curl -X POST http://localhost:9095/api/peak-demand/S002/approve-recommendation \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "recommendation_id": "rec-20260212-001",
    "approved_by": "technician@site-002",
    "approval_notes": "Approved for 1 hour BESS discharge"
  }'
```

**Response:** Actions executing, reduction estimate: 250 kW over 60 minutes.

---

## MCP Tools

1 tool registered in SIMBIOT MCP server:

| Tool | Description |
|------|-------------|
| `get_peak_demand_status` | Current demand, NMD headroom, available modules for peak shaving |

**Example use in Claude chat:**
```
"What's our peak demand status?"
→ Tool: get_peak_demand_status(site_id="S002")
→ Response: 5,500 kW current demand, 8.3% headroom, critical status
```

---

## Related Documentation

- [Solar & BESS API](solar-api.md) - BESS dispatch coordination
- [Municipal Billing API](municipal-billing.md) - NMD bill extraction
- [Recommendations API](recommendations-api.md) - Approval workflow
- [Optimization API](optimization.md) - Load shedding integration
- [System Architecture](../02-architecture/system-overview.md) - Demand-aware coordinator component
