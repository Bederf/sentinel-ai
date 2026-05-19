---
title: "Energy API Reference"
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

# Energy API Reference

**Status:** ✅ Available | **Version:** 1.0 | **Phase:** 084

---

## Overview

The Energy API provides endpoints for energy consumption analysis, optimization predictions, and rules-based energy savings calculations. All endpoints use rules-based optimization by default with fallback to hardcoded method.

**Base URL:** `http://localhost:9095/api`

**Related Docs:**
- [Phase 084: Energy Rules Engine](../04-features/PHASE_084_ENERGY_RULES_ENGINE.md) - Rules implementation details
- [Phase 083: Energy Comparison API](../04-features/PHASE_083_ENERGY_COMPARISON_API.md) - Card visualization
- [Demand Response API](./demand-response-api.md) - Real-time curtailable load for BESS/DR aggregators (Phase 211)

---

## Quick Start

### Get Energy Comparison (Most Common)

```bash
curl "http://localhost:9095/api/energy/comparison-summary?site_id=site-002&method=rules_based"
```

**Returns:** Actual vs SENTINEL energy comparison with dynamic savings and confidence

### Test Learning Curve Progression

```bash
# Rules-based (dynamic confidence 78-92%)
curl "http://localhost:9095/api/energy/comparison-summary?site_id=site-002" | jq '.ai_confidence_percent'

# Hardcoded (fixed confidence 85%)
curl "http://localhost:9095/api/energy/comparison-summary?site_id=site-002&method=hardcoded" | jq '.ai_confidence_percent'
```

### Activate DALI Module (Tests Rule 4)

```bash
curl -X POST "http://localhost:9095/api/modules/activate" \
  -H "Content-Type: application/json" \
  -d '{
    "site_id": "site-002",
    "site_name": "Sandton Office",
    "module_type": "dali"
  }'

# Re-test - Rule 4 should now fire during daytime
curl "http://localhost:9095/api/energy/comparison-summary?site_id=site-002"
```

---

## Endpoints

### GET /energy/comparison-summary

Get side-by-side actual vs SENTINEL energy comparison with rules-based predictions.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `site_id` | string | Site identifier (e.g., "site-002") | "site-002" |
| `method` | string | Optimization method: "rules_based" or "hardcoded" | "rules_based" |

**Response:** `ComparisonSummary`

```json
{
  "actual": {
    "total_kwh": 9000.0,
    "total_cost_zar": 45000.0,
    "carbon_kg": 3150.0,
    "hvac_kwh": 5400.0,
    "hvac_percent": 60.0,
    "lighting_kwh": 2700.0,
    "lighting_percent": 30.0,
    "power_kwh": 900.0,
    "power_percent": 10.0,
    "timestamp": "2025-01-15T12:00:00"
  },
  "sentinel": {
    "total_kwh": 7884.0,
    "total_cost_zar": 39420.0,
    "carbon_kg": 2759.4,
    "hvac_kwh": 4707.24,
    "hvac_percent": 59.7,
    "lighting_kwh": 2633.1,
    "lighting_percent": 33.4,
    "power_kwh": 543.66,
    "power_percent": 6.9,
    "timestamp": "2025-01-15T12:00:00"
  },
  "daily_savings_zar": 5580.0,
  "daily_savings_percent": 12.4,
  "progress_to_target_percent": 35.4,
  "ai_confidence_percent": 84.5
}
```

**Status Codes:**
- `200 OK` - Success
- `404 Not Found` - Site or energy data not found
- `500 Internal Server Error` - Failed to generate prediction

**Example:**

```bash
# Rules-based with DALI active (Rule 4 fires)
curl -s "http://localhost:9095/api/energy/comparison-summary?site_id=site-002" | jq '.by_system'

# Hardcoded (fixed 30% savings)
curl -s "http://localhost:9095/api/energy/comparison-summary?site_id=site-002&method=hardcoded" | jq '.daily_savings_percent'
```

---

### GET /energy/actual

Get actual (monitored) energy consumption data.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `site_id` | string | Site identifier | "site-002" |
| `days` | integer | Number of days (1-365) | 30 |

**Response:** `EnergyActual`

```json
{
  "site_id": "site-002",
  "period_days": 30,
  "metrics": [
    {
      "total_kwh": 9000.0,
      "total_cost_zar": 45000.0,
      "carbon_kg": 3150.0,
      "hvac_kwh": 5400.0,
      "hvac_percent": 60.0,
      "lighting_kwh": 2700.0,
      "lighting_percent": 30.0,
      "power_kwh": 900.0,
      "power_percent": 10.0,
      "timestamp": "2025-01-15T12:00:00"
    }
  ],
  "period_start": "2024-12-16",
  "period_end": "2025-01-15"
}
```

**Status Codes:**
- `200 OK` - Success
- `404 Not Found` - No energy data found

---

### GET /energy/prediction

Get predicted/optimized energy consumption for a scenario.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `site_id` | string | Site identifier | "site-002" |
| `scenario` | string | "sentinel_optimized", "standard_ems", or "baseline" | "sentinel_optimized" |
| `days` | integer | Number of days (1-365) | 30 |

**Scenarios:**

| Scenario | Savings | Confidence |
|----------|---------|-----------|
| `sentinel_optimized` | ~30% (rules-based 0-35%) | 78-92% (learning curve) |
| `standard_ems` | ~10% | 65% |
| `baseline` | 0% | 50% |

**Response:** `EnergyPrediction`

```json
{
  "site_id": "site-002",
  "scenario": "sentinel_optimized",
  "period_days": 30,
  "metrics": [
    {
      "total_kwh": 6300.0,
      "total_cost_zar": 31500.0,
      "carbon_kg": 2205.0,
      "hvac_kwh": 3780.0,
      "hvac_percent": 60.0,
      "lighting_kwh": 1890.0,
      "lighting_percent": 30.0,
      "power_kwh": 630.0,
      "power_percent": 10.0,
      "timestamp": "2025-01-15T12:00:00"
    }
  ],
  "period_start": "2024-12-16",
  "period_end": "2025-01-15",
  "model_confidence": 85.0
}
```

---

### GET /energy

Get daily energy consumption data (aggregated by system type).

Data source behavior:
- Supabase is authoritative by default.
- If no rows match, returns an empty `data` array.
- Synthetic fallback is disabled by default and only enabled when `ENERGY_ALLOW_MOCK_FALLBACK=true`.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `site_id` | string | Filter by site ID (optional) | None |
| `days` | integer | Number of days (1-365) | 30 |

**Response:** `EnergyResponse`

```json
{
  "days": 30,
  "site_id": "site-002",
  "data": [
    {
      "date": "2024-12-16",
      "site_id": "site-002",
      "site_name": "Sandton Office",
      "hvac_kwh": 180.0,
      "lighting_kwh": 90.0,
      "other_kwh": 30.0,
      "total_kwh": 300.0
    },
    ...
  ]
}
```

---

### POST /energy/seed

Seed energy consumption data for demo purposes.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `building_id` | string | Building code (optional, seeds all if not specified) | None |
| `days` | integer | Number of days to seed (1-365) | 90 |

**Response:**

```json
{
  "success": true,
  "message": "Seeded 2700 energy consumption records",
  "buildings": ["site-002", "site-005", "site-012"],
  "days": 90,
  "date_range": "2024-10-16 to 2025-01-15"
}
```

---

### GET /comparison

Get 3-tier energy comparison (baseline, with DALI, with SENTINEL).

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `site_id` | string | Site identifier | "site-002" |
| `days` | integer | Number of days (1-365) | 30 |

**Response:**

```json
{
  "site_id": "site-002",
  "period_days": 30,
  "scenarios": [
    {
      "name": "Baseline (No DALI)",
      "kwh": 12857.14,
      "description": "Traditional lighting controls",
      "savings_percent": 0
    },
    {
      "name": "With DALI (Tridonic)",
      "kwh": 10285.71,
      "description": "Occupancy & daylight harvesting",
      "savings_percent": 20,
      "savings_kwh": 2571.43
    },
    {
      "name": "With SENTINEL (AI)",
      "kwh": 9000.0,
      "description": "AI optimization on top of DALI",
      "savings_percent": 30,
      "savings_kwh": 3857.14
    }
  ]
}
```

---

## Rules-Based Optimization (Phase 084)

### How It Works

When `method=rules_based` (default), the API evaluates 5 optimization rules:

**Rule 1: Chiller Staging (5% max)**
- Activates when chiller load > 60%
- Scales linearly: 60% load → 0%, 100% load → 5%

**Rule 2: Thermal Pre-Cooling (3% max)**
- Activates when tariff is off-peak AND temp > 20°C
- Scales with temperature: 20°C → 0%, 35°C → 3%

**Rule 3: Occupancy-Based HVAC (2% max)**
- Activates when occupancy < 30%
- Scales inversely: 30% occupancy → 0%, 0% occupancy → 2%

**Rule 4: Daylight Harvesting (4% max, DALI-only)**
- Activates when DALI module active + daylight > 500 lux + 07:00-18:00
- Scales with daylight: 500 lux → 0%, 1000 lux → 4%
- **Module-conditional:** Must activate DALI module first

**Rule 5: Peak Load Shaving (2% max)**
- Activates when peak tariff + demand > 100 kW
- Scales with demand: 100 kW → 0%, 200 kW → 2%

### Total Savings Cap

Total savings never exceed 35%, even if all rules combine. Safety feature to prevent unrealistic predictions.

### Learning Curve Confidence

Confidence increases over deployment duration:

```
Month 1-2:   78-80%  (Learning phase)
Month 3-6:   82-88%  (Tuning phase)
Month 7-12:  90-92%  (Mature phase)
Month 12+:   92%     (Stable phase)
```

**Note:** Deployment date syncs with `lifecycle_orchestrator.simulation_start_time`, so confidence increases with simulated time during demos.

### System Breakdown

Savings allocated to HVAC/Lighting/Power using allocation matrix:

```
Rule 1 (Chiller): 100% HVAC
Rule 2 (Pre-cool): 100% HVAC
Rule 3 (Occupancy): 85% HVAC, 15% Power
Rule 4 (Daylight): 90% Lighting, 10% Power
Rule 5 (Peak): 40% HVAC, 30% Lighting, 30% Power
```

### Helper Functions

Rules engine uses helper functions that try orchestrator first, fallback to heuristics:

- `_estimate_occupancy()` - Occupancy % (0-100%)
- `_estimate_daylight()` - Daylight lux (0-1200)
- `_estimate_chiller_load()` - Chiller load % (0-100%)
- `_get_tariff_band()` - Tariff band (peak/standard/off_peak)
- `_get_seasonal_temp()` - Ambient temperature (13-24°C)

---

## Data Types

### ComparisonSummary

```typescript
{
  actual: EnergyMetrics           // Actual consumption
  sentinel: EnergyMetrics         // Optimized consumption
  daily_savings_zar: number       // Daily cost savings (R)
  daily_savings_percent: number   // Daily savings (%)
  progress_to_target_percent: number  // % toward 35% target
  ai_confidence_percent: number   // ML confidence (78-92%)
}
```

### EnergyMetrics

```typescript
{
  total_kwh: number           // Total consumption (kWh)
  total_cost_zar: number      // Total cost (ZAR)
  carbon_kg: number           // Carbon intensity (kg CO₂)
  hvac_kwh: number            // HVAC consumption (kWh)
  hvac_percent: number        // HVAC % of total
  lighting_kwh: number        // Lighting consumption (kWh)
  lighting_percent: number    // Lighting % of total
  power_kwh: number           // Power consumption (kWh)
  power_percent: number       // Power % of total
  timestamp: string           // ISO timestamp
}
```

### EnergyActual

```typescript
{
  site_id: string            // Site identifier
  period_days: number        // Number of days
  metrics: EnergyMetrics[]   // Daily metrics
  period_start: string       // Start date (ISO)
  period_end: string         // End date (ISO)
}
```

### EnergyPrediction

```typescript
{
  site_id: string            // Site identifier
  scenario: string           // Optimization scenario
  period_days: number        // Number of days
  metrics: EnergyMetrics[]   // Predicted metrics
  period_start: string       // Start date (ISO)
  period_end: string         // End date (ISO)
  model_confidence: float    // Model confidence (%)
}
```

### EnergyResponse

```typescript
{
  days: number               // Number of days
  site_id?: string          // Site filter (optional)
  data: EnergyDataPoint[]   // Daily data points
}
```

### EnergyDataPoint

```typescript
{
  date: string              // Date (ISO)
  site_id: string           // Site identifier
  site_name: string         // Site display name
  hvac_kwh: number          // HVAC consumption (kWh)
  lighting_kwh: number      // Lighting consumption (kWh)
  other_kwh: number         // Other consumption (kWh)
  total_kwh: number         // Total consumption (kWh)
}
```

---

## Error Handling

### Common Errors

**404 Not Found**
```json
{
  "detail": "No energy data found for site site-002"
}
```

**500 Internal Server Error**
```json
{
  "detail": "Failed to generate prediction"
}
```

### Graceful Degradation

If rules engine fails:
1. Logs warning with error details
2. Falls back to hardcoded method
3. Returns 200 OK with hardcoded savings (30%)
4. Returns original ai_confidence_percent (85%)

```python
try:
    output = engine.evaluate_rules(state, modules, baseline_kwh)
except Exception as e:
    logger.warning(f"Rules engine failed, falling back: {e}")
    # Falls back to hardcoded method
```

---

## Performance

| Operation | Time |
|-----------|------|
| Rules evaluation | <5ms |
| Helper functions | <20ms |
| Supabase fetch | <30ms |
| API response | <50ms total |
| Learning curve calc | <1ms |
| System breakdown | <2ms |

**Notes:**
- Rules engine uses singleton pattern (instantiated once)
- Deployment date cached at initialization
- No external API calls except orchestrator check

---

## Integration Examples

### Python

```python
import httpx

async with httpx.AsyncClient() as client:
    response = await client.get(
        "http://localhost:9095/api/energy/comparison-summary",
        params={"site_id": "site-002", "method": "rules_based"}
    )
    data = response.json()
    print(f"Savings: {data['daily_savings_percent']}%")
    print(f"Confidence: {data['ai_confidence_percent']}%")
```

### JavaScript

```typescript
const response = await fetch(
  '/api/energy/comparison-summary?site_id=site-002&method=rules_based'
);
const data = await response.json();

console.log(`Savings: ${data.daily_savings_percent}%`);
console.log(`Confidence: ${data.ai_confidence_percent}%`);
```

### cURL

```bash
# Get comparison with rules
curl -s "http://localhost:9095/api/energy/comparison-summary?site_id=site-002" \
  | jq '.daily_savings_percent, .ai_confidence_percent'

# Test fallback method
curl -s "http://localhost:9095/api/energy/comparison-summary?site_id=site-002&method=hardcoded" \
  | jq '.daily_savings_percent'

# Export to file
curl "http://localhost:9095/api/energy/comparison-summary" > energy_comparison.json
```

---

## Testing

### Unit Tests

```bash
pytest backend/tests/services/test_energy_rules_engine.py -v
```

### Manual Testing

```bash
# Test rules-based (dynamic)
curl "http://localhost:9095/api/energy/comparison-summary?site_id=site-002" | jq

# Test hardcoded (fixed 30%)
curl "http://localhost:9095/api/energy/comparison-summary?site_id=site-002&method=hardcoded" | jq

# Check DALI impact
curl -X POST "http://localhost:9095/api/modules/activate" \
  -H "Content-Type: application/json" \
  -d '{"site_id": "site-002", "site_name": "Sandton Office", "module_type": "dali"}'

curl "http://localhost:9095/api/energy/comparison-summary?site_id=site-002" | jq '.daily_savings_percent'
```

---

## Rate Limits

No explicit rate limiting, but recommended:
- Max 10 requests per second per client
- Cache responses (data changes infrequently)
- Batch requests when possible

---

## Related Endpoints

- **Modules API** - Activate/deactivate modules (affects Rule 4)
  - `POST /api/modules/activate` - Activate DALI module
  - `GET /api/modules/site/{site_id}/active` - List active modules

- **Buildings API** - Site and building information
  - `GET /api/buildings` - List all buildings

- **Equipment API** - Equipment telemetry
  - `GET /api/equipment/{id}` - Get equipment details

---

## Changelog

### Version 1.0 (Phase 084 - 2026-02-15)
- ✅ Energy Rules Engine implemented
- ✅ 5 optimization rules with conditional activation
- ✅ Learning curve confidence progression
- ✅ Module-conditional DALI rule
- ✅ System breakdown allocation
- ✅ Backward compatible with hardcoded method
- ✅ 16 test cases covering all rules

---

## Questions?

See detailed documentation:
- [Phase 084: Energy Rules Engine](../04-features/PHASE_084_ENERGY_RULES_ENGINE.md)
- [Phase 083: Energy Comparison API](../04-features/PHASE_083_ENERGY_COMPARISON_API.md)
