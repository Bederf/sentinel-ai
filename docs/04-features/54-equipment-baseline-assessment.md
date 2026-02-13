---
title: "Equipment Baseline Assessment"
type: "guide"
status: "complete"
version: "54"
date: "2026-02-03"
phase: 54
milestone: "v12.0 Workflow Integration"
---

# Phase 54: Equipment Baseline Assessment

**Completed:** 2026-02-03  
**Status:** ✅ Complete (3/3 plans)  
**Milestone:** v12.0 Workflow Integration (Phases 53-57)

## Overview

Equipment baseline assessment is the foundation of conditional maintenance. Phase 54 implements equipment-level baseline capture, storage, and comparison for detecting equipment degradation and predicting maintenance needs.

**Purpose:** Establish reference baselines for each piece of equipment (generators, chillers, AHUs, etc.), then compare real-time readings to baselines to detect deviations that indicate degradation.

```
Building Onboarding (Phase 53)
    ↓
Equipment Baselines Established (Phase 54) ← YOU ARE HERE
    ↓
Routine Inspection Workflows (Phase 55)
    ↓
Conditional Maintenance Optimization (Phase 56)
    ↓
Repair Effectiveness Validation (Phase 57)
```

## Architecture

### Data Model

**Equipment Baselines Table:**
- `id` (UUID) - Primary key
- `equipment_id` (UUID) - Reference to equipment
- `baseline_date` (timestamp) - When baseline was captured
- `baseline_type` (enum) - initial, periodic, post_repair, seasonal
- `status` (enum) - active, archived, superseded
- `captured_by` (string) - Technician name or system
- `baseline_data` (JSONB) - Element-level readings
- `tolerance_config` (JSONB) - Per-element tolerances
- `source_type` (enum) - manual, bms_average, mobile_sensor
- `measurement_conditions` (JSONB) - Context (ambient temp, load, etc.)

**Element-Level Baseline Storage:**
```json
{
  "filter_dp": {
    "value": 250,
    "unit": "Pa",
    "tolerance": 50,
    "tolerance_type": "absolute"
  },
  "discharge_temp": {
    "value": 72,
    "unit": "°C",
    "tolerance": 5,
    "tolerance_type": "percentage"
  },
  "vibration_rms": {
    "value": 1.2,
    "unit": "mm/s",
    "tolerance": 0.5,
    "tolerance_type": "absolute"
  },
  "bearing_temp": {
    "value": 65,
    "unit": "°C",
    "tolerance": 10,
    "tolerance_type": "absolute"
  }
}
```

### Multi-Source Baseline Capture

**Three Capture Methods Supported:**

#### 1. Manual Entry (Engineer Input)
- Technician enters readings during site visit
- Used during onboarding for initial baseline
- High confidence, manual validation

#### 2. BMS Device Integration
- Automatic averaging from BMS device points
- Real-time or historical data
- Requires device mapping from Phase 53 onboarding

#### 3. Mobile/Phone Sensors
- Vibration measurement via phone accelerometer
- Audio frequency analysis via microphone
- Requires phyphox app or similar
- Useful for remote diagnostics

### Intelligent Default Tolerances

**Per Equipment Type:**

| Equipment Type | Temperature | Pressure | Vibration | Special |
|---|---|---|---|---|
| **Chiller** | ±2°C | ±10% | ±0.3 mm/s | - |
| **Generator** | ±5°C | ±15% | ±0.5 mm/s | ±2 Hz frequency |
| **AHU** | ±3°C | - | ±0.4 mm/s | ±50 Pa filter_dp |
| **FCU** | ±3°C | - | ±0.5 mm/s | ±30 Pa filter_dp |
| **Pump** | ±5°C | ±15% | ±0.5 mm/s | - |
| **UPS** | ±2°C | ±5% | ±0.2 mm/s | ±5V DC |
| **Default** | ±5°C | ±15% | ±0.5 mm/s | ±10% generic |

**Mobile Sensor Tolerances:**
- Vibration RMS: ±20%
- Frequency peaks: ±15%
- Audio level: ±10 dBA
- Noise floor: ±10 dBA

Defaults are applied automatically and can be overridden per equipment.

## REST API

### Create Equipment Baseline

```http
POST /api/equipment/{equipment_id}/baselines
```

**Request:**
```json
{
  "baseline_type": "initial",
  "source_type": "manual",
  "captured_by": "John Smith",
  "baseline_data": {
    "filter_dp": {"value": 250, "unit": "Pa"},
    "discharge_temp": {"value": 72, "unit": "°C"},
    "vibration_rms": {"value": 1.2, "unit": "mm/s"}
  },
  "measurement_conditions": {
    "ambient_temp": 25,
    "load_percent": 80,
    "runtime_hours": 1250
  }
}
```

**Response:**
```json
{
  "id": "baseline-001",
  "equipment_id": "S002-CHILLER-B1-001",
  "baseline_date": "2026-02-03T10:30:00Z",
  "baseline_type": "initial",
  "status": "active",
  "baseline_data": {
    "filter_dp": {
      "value": 250,
      "unit": "Pa",
      "tolerance": 50,
      "tolerance_type": "absolute"
    },
    "discharge_temp": {
      "value": 72,
      "unit": "°C",
      "tolerance": 5,
      "tolerance_type": "absolute"
    }
  }
}
```

### Retrieve Equipment Baseline

```http
GET /api/equipment/{equipment_id}/baselines
```

**Query Parameters:**
- `baseline_type` - Filter by type (initial, periodic, post_repair, seasonal)
- `status` - Filter by status (active, archived, superseded)
- `limit` - Max results (default 10)
- `offset` - Pagination offset

### Compare Current Readings to Baseline

```http
POST /api/equipment/{equipment_id}/baselines/{baseline_id}/compare
```

**Request:**
```json
{
  "current_readings": {
    "filter_dp": {"value": 290, "unit": "Pa"},
    "discharge_temp": {"value": 75, "unit": "°C"},
    "vibration_rms": {"value": 1.5, "unit": "mm/s"}
  }
}
```

**Response:**
```json
{
  "comparison_id": "comp-001",
  "equipment_id": "S002-CHILLER-B1-001",
  "baseline_id": "baseline-001",
  "comparison_date": "2026-02-03T14:00:00Z",
  "overall_severity": "warning",
  "deviations": [
    {
      "element": "filter_dp",
      "baseline_value": 250,
      "current_value": 290,
      "tolerance": 50,
      "deviation_percent": 16,
      "severity": "warning",
      "status": "within_tolerance"
    },
    {
      "element": "vibration_rms",
      "baseline_value": 1.2,
      "current_value": 1.5,
      "tolerance": 0.5,
      "deviation_percent": 25,
      "severity": "critical",
      "status": "exceeds_tolerance"
    }
  ],
  "recommendations": [
    {
      "element": "vibration_rms",
      "action": "schedule_inspection",
      "urgency": "high",
      "reason": "Vibration 25% above baseline tolerance indicates potential bearing wear"
    }
  ],
  "trend_analysis": {
    "degradation_rate": "0.2 mm/s per month",
    "estimated_critical_date": "2026-03-15",
    "rul_estimate_days": 40
  }
}
```

### Element-Level Baselines (Sub-Components)

```http
GET /api/equipment/{equipment_id}/baselines/{baseline_id}/elements
```

Retrieve baselines for sub-components (e.g., compressor, condenser fan, chiller pump).

## Deviation Detection & Alerting

### Severity Thresholds

- **Green:** 0-50% of tolerance
- **Yellow:** 50-75% of tolerance  
- **Orange:** 75-100% of tolerance
- **Red:** >100% of tolerance (exceeds tolerance)

### Automatic Alerts

When deviations are detected:

1. **Critical Deviation** (Red):
   - Immediate alert to operations team
   - Auto-create work order with HIGH priority
   - Suggest immediate inspection

2. **Warning Deviation** (Orange):
   - Schedule future inspection
   - Track trending over time
   - Escalate if trend accelerating

3. **Caution Deviation** (Yellow):
   - Log for historical reference
   - Included in routine reports
   - No action required

### Trend Analysis

The system tracks:
- **Degradation Rate** - How fast the element is changing (units/month)
- **Estimated Critical Date** - When reading will exceed tolerance
- **Remaining Useful Life (RUL)** - Days until critical threshold
- **Linear vs Non-Linear** - Change pattern analysis

## Report Generation

### PDF/HTML Baseline Comparison Reports

Generate professional reports comparing baseline to current readings:

```
Equipment: S002-CHILLER-B1-001
Date: 2026-02-03
Baseline: Initial Baseline (2026-01-15)

FILTER DIFFERENTIAL PRESSURE
  Baseline: 250 Pa (Tolerance: ±50 Pa)
  Current: 290 Pa
  Deviation: 40 Pa (+16%)
  Status: ✓ Within Tolerance
  Trend: Increasing 2.5 Pa/week

DISCHARGE TEMPERATURE
  Baseline: 72°C (Tolerance: ±5°C)
  Current: 75°C
  Deviation: 3°C (+4%)
  Status: ✓ Within Tolerance
  Trend: Stable

VIBRATION (RMS)
  Baseline: 1.2 mm/s (Tolerance: ±0.5 mm/s)
  Current: 1.5 mm/s
  Deviation: 0.3 mm/s (+25%)
  Status: ✗ EXCEEDS TOLERANCE (Red Alert)
  Trend: Increasing 0.05 mm/s/week
  Estimated Critical Date: 2026-03-15

RECOMMENDATIONS
1. Schedule bearing inspection within 7 days
2. Monitor vibration weekly
3. Prepare bearing replacement kit
```

## Integration Points

### Phase 53: Workflow Orchestration
- Baseline captured during equipment onboarding
- Stored in Supabase with RLS policies
- Available for workflow trigger decisions

### Phase 55: Routine Inspection
- Inspection workflows compare readings to baseline
- Automated pass/fail based on deviations
- Historical baseline tracking

### Phase 56: Conditional Maintenance
- Baseline degradation analysis drives RUL calculations
- Service timing optimization based on trend projection
- "Sweat the assets" by delaying service based on actual condition

### Phase 46: Repair Effectiveness & ML Feedback
- Post-repair baseline comparison validates fix
- Before/after metrics demonstrate repair success
- Feedback to ML models (Phase 45-02)
- Phase 54 comparison service powers Phase 46 pre/post baseline validation

**See Comprehensive Integration:**
- [Phases 44-46-54 Integration](44-46-54-integration-workflow.md) - Complete multi-phase workflow with Phase 54 at center

## Implementation Details

### Database Schema

**Main Tables:**
- `equipment_baselines` - Baseline records
- `equipment_elements` - Equipment sub-components
- `element_baselines` - Element-level baselines
- `baseline_comparisons` - Comparison results

**Indexes:**
- `idx_equipment_baselines_equipment_id` - Equipment lookup
- `idx_equipment_baselines_baseline_date` - Date range queries
- `idx_baseline_comparisons_equipment_id` - Comparison lookup
- `gin_equipment_baselines_data` - JSONB element queries

**Views:**
- `baseline_latest` - Latest baseline per equipment
- `baseline_critical_deviations` - All red-level deviations
- `equipment_baseline_trend` - Degradation trending

### Services

**File:** `backend/app/services/baseline_capture_service.py` (735 lines)
- Multi-source baseline capture
- Default tolerance application
- Data normalization

**File:** `backend/app/services/baseline_comparison_service.py` (620 lines)
- Deviation calculation
- Severity scoring
- Trend analysis
- Report generation

### API Routes

**File:** `backend/app/api/baselines.py` (345 lines)
- CRUD endpoints for baselines
- Comparison endpoint
- Report generation
- Element-level queries

## Data Flow

```
Engineer captures readings (Phase 54-02)
        ↓
BaselineCaptureService normalizes + applies tolerances
        ↓
equipment_baselines table (Supabase)
        ↓
Real-time readings arrive (Phase 55 inspection)
        ↓
BaselineComparisonService compares to baseline
        ↓
Deviations detected + severity scored
        ↓
Alerts generated + Work orders created (if critical)
        ↓
Reports generated for technician
        ↓
Repair effectiveness tracked (Phase 57)
        ↓
ML feedback loop updated
```

## Common Use Cases

### 1. Equipment Onboarding Baseline
```
New equipment installed
  → Engineer captures initial baseline
  → Tolerances applied automatically
  → Baseline stored for future comparison
```

### 2. Routine Inspection
```
Technician performs weekly inspection
  → Current readings compared to baseline
  → Deviations calculated + severity scored
  → Report shows status relative to baseline
  → Critical deviations auto-escalate
```

### 3. Trending & RUL
```
Monthly readings tracked
  → Degradation rate calculated
  → Linear projection of critical date
  → Maintenance scheduled before failure
  → Asset "sweated" by delaying replacement
```

### 4. Post-Repair Validation
```
Bearing replaced on compressor
  → Post-repair baseline captured
  → Compared to pre-repair baseline
  → Demonstrates repair effectiveness
  → Health score updated
```

## Success Metrics

- **Capture Accuracy:** >90% of baseline readings within ±5% of actual
- **Deviation Detection:** 95%+ of anomalies detected before failure
- **False Positives:** <5% (alerts that don't require action)
- **RUL Prediction:** Within ±10% of actual failure date
- **Report Generation:** <30 seconds for PDF generation

## See Also

- **[Phases 44-46-54 Integration](44-46-54-integration-workflow.md)** - Complete workflow showing how Phase 54 fits with baseline assessment, inspection, and repair validation
- **[Phase 45: Routine Inspection & Maintenance](45-routine-inspection-maintenance.md)** - Field inspection workflows that leverage Phase 54 baselines
- **[Phase 46: Repair Effectiveness](46-repair-effectiveness-ml-feedback.md)** - Uses Phase 54 pre/post repair comparison service
- **[Health Scoring System](health-scoring-system.md)** - Equipment health calculation with baseline context
- **[Asset Workflow Architecture](../05-integrations/asset-workflow-architecture.md)** - Phase 53 orchestration foundation

---

**Last Updated:** 2026-02-03  
**Author:** Sentinel Development Team  
**Status:** Complete - Phase 54 delivered all 3 plans
