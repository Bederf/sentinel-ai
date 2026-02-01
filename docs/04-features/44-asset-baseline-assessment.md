---
title: "Asset Baseline Assessment & Cost Modeling"
type: "guide"
status: "approved"
version: "44"
date: "2026-02-01"
---

# Asset Baseline Assessment & Cost Modeling

Phase 44 implements AI-powered asset baseline assessment during building onboarding. The system analyzes each piece of equipment (generators, HVAC, energy centre components) to establish a condition baseline and calculate maintenance costs using engineer input combined with ML models.

## Overview

```mermaid
graph TB
    subgraph Phase 1: Data Ingestion
        BMS[BMS / Desigo CC Exports]
        SIMBIOT[SIMBIOT MCP Tools]
        EquipmentDB[Equipment Database]
    end

    subgraph Phase 2: Engineer Assessment
        Engineer[Engineer Inspection]
        Physical[Physical Condition Notes]
        History[Maintenance History]
        Issues[Known Issues/Observations]
    end

    subgraph Phase 3: AI/ML Analysis
        Trends[Historical Trend Analysis]
        Anomaly[Autoencoder Baseline]
        LSTM[Performance Prediction]
        Health[Health Score Calculation]
    end

    subgraph Phase 4: Baseline Report
        Condition[Condition Score (0-100)]
        Category[Category (New/Good/Fair/Poor/Critical)]
        Risk[Risk Level (H/M/L)]
        RUL[Remaining Useful Life]
    end

    subgraph Phase 5: Cost Modeling
        AnnualCost[Annual Maintenance Cost]
        FiveYear[5-Year TCO]
        CriticalItems[Critical Replacements]
        Schedule[Maintenance Schedule]
    end

    BMS --> SIMBIOT
    SIMBIOT --> EquipmentDB

    Engineer --> Physical
    Engineer --> History
    Engineer --> Issues

    EquipmentDB --> Trends
    EquipmentDB --> Anomaly
    EquipmentDB --> LSTM

    Physical --> Health
    History --> Health
    Trends --> Health
    Anomaly --> Health
    LSTM --> Health

    Health --> Condition
    Health --> Category
    Health --> Risk
    Health --> RUL

    Condition --> AnnualCost
    Category --> AnnualCost
    RUL --> AnnualCost
    CriticalItems --> FiveYear
    AnnualCost --> FiveYear
```

## Onboarding Workflow

### Step 1: SIMBIOT Data Ingestion

Import equipment from BMS using SIMBIOT MCP tools:

```bash
# 1. Import equipment from BMS point list
POST /api/onboarding/import-point-list
{
  "building_id": "site-002",
  "bms_vendor": "desigo",
  "point_list": [
    {"point_name": "AHU-L12-01.SupplyAirTemp", "value": 14.2, "units": "°C"},
    {"point_name": "GEN-SAN-001.EngineRPM", "value": 0, "units": "rpm"},
    {"point_name": "CHILLER-001.ChwSupplyTemp", "value": 7.0, "units": "°C"}
  ]
}

# Result: 125 equipment assets identified and created
```

**See Also:** [AI-Assisted Onboarding](ai-assisted-onboarding.md) for detailed SIMBIOT tool usage.

### Step 2: Engineer Assessment Input

Engineers conduct physical inspections and provide structured input:

```json
{
  "assessment_id": "assess-sandton-20260201",
  "building_id": "site-002",
  "engineer": "John Smith, Senior HVAC Engineer",
  "assessment_date": "2026-02-01",

  "equipment_observations": [
    {
      "equipment_id": "AHU-L11-01",
      "equipment_type": "ahu",
      "visual_condition": "good",
      "noise_level": "normal",
      "observed_issues": ["slight_vibration_on_bearings"],
      "last_service_date": "2025-12-15",
      "service_notes": "Belt tension adjusted, filters replaced"
    },
    {
      "equipment_id": "GEN-SAN-001",
      "equipment_type": "generator",
      "visual_condition": "fair",
      "noise_level": "elevated",
      "observed_issues": ["oil_leak_at_pan", "high_exhaust_temp"],
      "last_service_date": "2025-11-15",
      "service_notes": "Oil leak noted, monitoring required"
    }
  ]
}
```

**Required Engineer Input:**
- Physical condition (visual inspection)
- Operational observations (noise, vibration, leaks)
- Maintenance history review
- Recent service records
- Known issues or concerns
- Component age and replacement schedule

**Form Location:** `GET /api/onboarding/assessment-form` for structured template

### Step 3: AI/ML Baseline Analysis

System runs multiple AI/ML models to assess equipment condition:

#### A. Historical Trend Analysis

Analyzes historical data to establish baseline performance:

```python
# Analyzes last 30 days of BMS trend data
trend_analysis = {
  "equipment_id": "AHU-L11-01",
  "analysis_period": "30_days",
  "baseline_metrics": {
    "supply_temp": {"avg": 14.2, "std_dev": 0.8, "min": 12.1, "max": 16.4},
    "fan_current": {"avg": 8.2, "std_dev": 0.4, "min": 7.6, "max": 9.1},
    "filter_dp": {"avg": 145, "std_dev": 15, "min": 120, "max": 185}
  },
  "trend_direction": "stable_with_slight_degradation",
  "observations": [
    "Filter dp increasing 3Pa per week (normal for 30 day period)",
    "Fan current within expected range for this stage of filter life"
  ]
}
```

**API Endpoint:** `POST /api/ml/trends/analyze-baseline`

#### B. Autoencoder Anomaly Baseline

Trains autoencoder on "normal" operation to detect future anomalies:

```python
# Trains for 7 days on current equipment data
autoencoder_result = {
  "equipment_id": "AHU-L11-01",
  "training_duration_days": 7,
  "reconstruction_error_threshold": 0.00068,
  "normal_operation_confidence": 0.94,
  "anomalies_detected_in_training": 2,
  "anomaly_context": [
    {"timestamp": "2026-01-28T14:30:00Z", "severity": "low", "cause": "startup_transient"},
    {"timestamp": "2026-01-29T09:15:00Z", "severity": "low", "cause": "filter_change_event"}
  ]
}
```

**API Endpoint:** `POST /api/ml/autoencoder/train-baseline`

#### C. LSTM Performance Prediction

Runs LSTM model to predict 24/48/72h performance:

```python
lstm_prediction = {
  "equipment_id": "GEN-SAN-001",
  "predictions": {
    "24h": {
      "coolant_temp": 75.2,
      "confidence": 0.87,
      "expected_range": [72.0, 78.5]
    },
    "48h": {
      "coolant_temp": 76.8,
      "confidence": 0.82,
      "expected_range": [73.5, 80.2]
    },
    "72h": {
      "coolant_temp": 78.1,
      "confidence": 0.78,
      "expected_range": [74.8, 81.9]
    }
  },
  "analysis": "Coolant temperature trending upward due to increasing ambient temperatures"
}
```

**API Endpoint:** `POST /api/ml/lstm/baseline-prediction`

#### D. Health Score Calculation

Combines all inputs to calculate comprehensive health score:

```python
health_calculation = {
  "equipment_id": "AHU-L11-01",
  "components": {
    "fan_motor": {
      "ml_health": 85,
      "engineer_health": 80,
      "weight": 0.30,
      "final_score": 83
    },
    "bearings": {
      "ml_health": 65,
      "engineer_health": 60,
      "weight": 0.25,
      "final_score": 63
    },
    "filters": {
      "ml_health": 55,
      "engineer_health": 50,
      "weight": 0.15,
      "final_score": 53
    },
    "controls": {
      "ml_health": 92,
      "engineer_health": 95,
      "weight": 0.30,
      "final_score": 93
    }
  },
  "overall_health_score": 75,
  "calculation_method": "weighted_average_engineer_ml_blend",
  "engineer_override": false,
  "override_reason": null
}
```

**Weight Factors by Equipment Type:**
```yaml
ahu:
  fan_motor: 0.30
  bearings: 0.25
  filters: 0.15
  controls: 0.30

chiller:
  compressor: 0.35
  condenser: 0.20
  evaporator: 0.20
  controls: 0.15
  refrigerant: 0.10

generator:
  engine: 0.40
  alternator: 0.25
  controls: 0.20
  fuel_system: 0.15
```

**API Endpoint:** `POST /api/onboarding/calculate-health-score`

### Step 4: Asset Baseline Report

Combines all analysis into comprehensive baseline report:

```json
{
  "report_id": "baseline-sandton-20260201",
  "building_id": "site-002",
  "building_name": "Sandton City Office Tower",
  "report_date": "2026-02-01",
  "generated_by": "AI/ML Baseline Engine",
  "assessing_engineer": "John Smith",

  "summary": {
    "total_assets": 125,
    "critical": 3,
    "poor": 8,
    "fair": 34,
    "good": 45,
    "new": 35
  },

  "assets": [
    {
      "equipment_id": "AHU-L11-01",
      "equipment_type": "ahu",
      "equipment_name": "Air Handling Unit Level 11",
      "area": "L11 North Zone",

      "baseline": {
        "health_score": 75,
        "condition_category": "FAIR",
        "risk_level": "MEDIUM",
        "remaining_useful_life_months": 36,
        "anomaly_threshold": 0.00068
      },

      "assessment_factors": {
        "ml_health_score": 78,
        "engineer_score": 80,
        "age_factor": 0.85,
        "runtime_hours": 43500,
        "design_life_hours": 60000,
        "maintenance_compliance": 0.92
      },

      "findings": [
        {
          "severity": "medium",
          "finding": "Bearing vibration elevated",
          "source": "engineer_interview",
          "action_required": "schedule_bearing_inspection"
        },
        {
          "severity": "low",
          "finding": "Filter differential pressure trending upward",
          "source": "ml_trend_analysis",
          "action_required": "monitor_filter_life"
        }
      ],

      "recommendations": {
        "immediate": ["bearing_vibration_analysis"],
        "short_term": ["filter_replacement_within_30_days"],
        "long_term": ["bearing_replacement_within_12_months"]
      }
    },
    {
      "equipment_id": "GEN-SAN-001",
      "equipment_type": "generator",
      "equipment_name": "Generator 1 (Primary)",

      "baseline": {
        "health_score": 58,
        "condition_category": "POOR",
        "risk_level": "HIGH",
        "remaining_useful_life_months": 18,
        "failure_probability_12m": 0.42
      },

      "assessment_factors": {
        "ml_health_score": 62,
        "engineer_score": 45,
        "engineer_override": true,
        "override_reason": "Oil leak observed, elevated exhaust temps"
      },

      "findings": [
        {
          "severity": "high",
          "finding": "Oil leak at oil pan gasket",
          "source": "engineer_physical_inspection",
          "action_required": "immediate_repair"
        },
        {
          "severity": "high",
          "finding": "Exhaust temperature 15% above specification",
          "source": "engineer_measurement",
          "action_required": "immediate_investigation"
        },
        {
          "severity": "medium",
          "finding": "Autoencoder detects combustion pattern variance",
          "source": "ml_anomaly_detection",
          "action_required": "engine_performance_analysis"
        }
      ],

      "recommendations": {
        "immediate": [
          "oil_leak_repair",
          "exhaust_system_inspection",
          "compression_test"
        ],
        "short_term": ["fuel_injector_service", "cooling_system_flush"],
        "long_term": ["engine_overhaul_within_18_months"]
      }
    }
  ],

  "report_footer": {
    "methodology": "AI/ML models combined with engineer physical assessment",
    "confidence_level": "High (ML: 87%, Engineer: Field verified)",
    "next_assessment_recommended": "2026-05-01 (3 months or after major maintenance)"
  }
}
```

**API Endpoint:** `GET /api/onboarding/baseline-report/{building_id}`

### Step 5: Maintenance Cost Modeling

AI calculates maintenance costs based on condition baselines:

#### Methodology

```python
def calculate_maintenance_costs(equipment_baseline):
    """
    Calculates annual and 5-year maintenance costs based on:
    1. Equipment condition category
    2. Health score
    3. Remaining useful life
    4. Parts replacement schedules
    5. Labor requirements
    """

    # Base costs from equipment type
    base_costs = get_oem_costs(equipment_baseline.type)

    # Condition multiplier
    if equipment_baseline.category == "NEW":
        condition_factor = 1.0
    elif equipment_baseline.category == "GOOD":
        condition_factor = 1.2
    elif equipment_baseline.category == "FAIR":
        condition_factor = 1.8
    elif equipment_baseline.category == "POOR":
        condition_factor = 3.2
    else:  # CRITICAL
        condition_factor = 5.5

    # Calculate annual costs
    annual_costs = {
        "preventive": base_costs.preventive * condition_factor,
        "predictive": base_costs.predictive * (condition_factor * 0.8),
        "corrective": base_costs.corrective * condition_factor,
        "parts_inventory": calculate_inventory_cost(equipment_baseline)
    }

    # Critical items for next 12 months
    critical_items = identify_critical_items(equipment_baseline)

    # 5-year projection
    five_year_tco = project_costs_over_time(
        annual_costs=annual_costs,
        r_ul=equipment_baseline.remaining_useful_life,
        replace_cost=get_replacement_cost(equipment_baseline.type)
    )

    return {
        "annual_costs": annual_costs,
        "critical_items_12m": critical_items,
        "five_year_tco": five_year_tco
    }
```

#### Sample Cost Calculation

**Equipment: AHU-L11-01 (Health Score: 75%, FAIR condition)**

```json
{
  "equipment_id": "AHU-L11-01",
  "condition": "FAIR",
  "health_score": 75,

  "annual_maintenance_costs": {
    "preventive": {
      "description": "Scheduled PM activities",
      "estimated_annual_cost": 2800,
      "activities": [
        {"task": "Filter replacement", "frequency": "quarterly", "cost": 400},
        {"task": "Belt inspection/replacement", "frequency": "annual", "cost": 350},
        {"task": "Bearing lubrication", "frequency": "semi_annual", "cost": 280},
        {"task": "Controls calibration", "frequency": "annual", "cost": 650},
        {"task": "General inspection", "frequency": "quarterly", "cost": 400}
      ]
    },

    "predictive": {
      "description": "Condition-based monitoring",
      "estimated_annual_cost": 1200,
      "activities": [
        {"task": "Vibration analysis", "frequency": "semi_annual", "cost": 450},
        {"task": "Thermography", "frequency": "annual", "cost": 600},
        {"task": "Airflow measurement", "frequency": "annual", "cost": 350}
      ]
    },

    "corrective": {
      "description": "Expected repairs based on condition",
      "estimated_annual_cost": 2200,
      "items": [
        {"component": "Bearing replacement", "probability": 0.25, "cost": 2800},
        {"component": "VFD repairs", "probability": 0.15, "cost": 3200},
        {"component": "Controls repairs", "probability": 0.30, "cost": 1800}
      ]
    },

    "parts_inventory": {
      "description": "Recommended spare parts to hold",
      "annual_carrying_cost": 650,
      "recommended_parts": [
        {"part": "Fan belt", "quantity": 2, "unit_cost": 85},
        {"part": "Air filters", "quantity": 12, "unit_cost": 45},
        {"part": "Fan bearings", "quantity": 1, "unit_cost": 420}
      ]
    }
  },

  "critical_items_12_months": [
    {
      "component": "Fan bearings",
      "issue": "Elevated vibration noted",
      "probability_12m": 0.60,
      "estimated_cost": 2800,
      "recommended_action": "Schedule vibration analysis within 30 days",
      "urgency": "high"
    }
  ],

  "five_year_tco": {
    "year_1": 6850,
    "year_2": 7280,
    "year_3": 8900,
    "year_4": 12400,
    "year_5": {
      "maintenance": 15600,
      "replacement_evaluation": true,
      "estimated_replace_cost": 45000
    },
    "total_5_year": 50980,
    "npv_at_10_percent": 46520
  },

  "maintenance_schedule": {
    "monthly": ["filter_dp_check", "general_inspection"],
    "quarterly": ["filter_replacement", "belt_inspection"],
    "semi_annual": ["vibration_analysis", "bearing_lube"],
    "annual": ["thermography", "airflow_test", "controls_cal"]
  }
}
```

### Step 6: Executive Summary Dashboard

AI generates executive summary for facility management:

```
═══════════════════════════════════════════════════════════
  SENTINEL ASSET BASELINE ASSESSMENT - EXECUTIVE SUMMARY
  Building: Sandton City Office Tower
  Assessment Date: 2026-02-01
  Total Assets Assessed: 125
═══════════════════════════════════════════════════════════

📊 CONDITION DISTRIBUTION
  New (95-100%):      35 assets  [████████████████░░░░░░░░] 28%
  Good (80-94%):      45 assets  [███████████████░░░░░░░░░] 36%
  Fair (60-79%):      34 assets  [██████████░░░░░░░░░░░░░░] 27%
  Poor (40-59%):       8 assets  [███░░░░░░░░░░░░░░░░░░░░░] 6%
  Critical (<40%):     3 assets  [█░░░░░░░░░░░░░░░░░░░░░░░] 2%

🚨 IMMEDIATE ATTENTION REQUIRED (3 assets)
  🔴 GEN-SAN-001 - Generator 1 (Health: 58%) - Oil leak, high exhaust temp
  🔴 UPS-002 - UPS System B (Health: 35%) - Battery degradation critical
  🔴 CHILLER-001 - Chiller 1 (Health: 42%) - Compressor oil analysis failed

💰 MAINTENANCE COST PROJECTIONS
  Annual Maintenance (Year 1):    R 847,500
  ├─ Preventive (planned):        R 325,000
  ├─ Predictive (condition-based): R 180,000
  ├─ Corrective (expected):       R 287,500
  └─ Critical (immediate):        R 55,000

  5-Year Total Cost of Ownership: R 4,845,000
  ├─ Maintenance (Years 1-5):     R 4,125,000
  └─ Equipment Replacements:      R 720,000 (3 assets)

⚡ CRITICAL FINDINGS
  1. Generator-001 requires immediate repair (oil leak)
  2. Plan UPS-002 replacement within 6 months
  3. Schedule chiller compressor analysis
  4. AHU-L11 bearing vibration trending upward

✅ RECOMMENDATIONS
  Immediate (Next 30 days):
  • Repair generator oil leak
  • Replace UPS-002 batteries
  • Conduct chiller oil analysis

  Short-term (3-6 months):
  • Prepare UPS-002 replacement budget
  • Schedule AHU-L11 bearing inspection
  • Review 8 "Poor" condition assets

  Long-term (6-12 months):
  • Replace 3 critical assets
  • Implement enhanced monitoring for "Fair" assets
  • Review maintenance schedules based on condition

📈 COMPARED TO INDUSTRY BENCHMARKS
  Your AHU health average: 78% (Industry: 72%) ✓ Above average
  Your generator health: 67% (Industry: 75%) ⚠ Below average
  Your annual cost/sqm: R 188 (Industry: R 205) ✓ Efficient

🎯 NEXT STEPS
  1. Review detailed baseline report (125 pages)
  2. Approve critical repair work orders
  3. Adjust maintenance budgets based on projections
  4. Schedule quarterly condition reassessments
  5. Set up continuous monitoring for high-value assets
───────────────────────────────────────────────────────────
```

## API Reference

### Baseline Assessment API

**Initiate Assessment**
```http
POST /api/onboarding/assessment/baseline

Query Parameters:
  building_id (required) - Building identifier
  include_generators (optional, default: true)
  include_hvac (optional, default: true)
  include_energy_centre (optional, default: true)
  assessment_date (optional, default: today)

Response:
{
  "assessment_id": "asst-20260201-a7f3",
  "status": "initiated",
  "estimated_completion": "2026-02-01T16:30:00Z",
  "total_assets": 125,
  "workflow_url": "/api/onboarding/assessment/asst-20260201-a7f3"
}
```

**Submit Engineer Assessment**
```http
POST /api/onboarding/assessment/engineer-input

Body:
{
  "assessment_id": "asst-20260201-a7f3",
  "engineer_name": "John Smith",
  "equipment_observations": [...]
}
```

**Get Baseline Report**
```http
GET /api/onboarding/assessment/report/{building_id}

Response: Asset Baseline Report (JSON format shown above)
```

**Get Cost Projections**
```http
GET /api/onboarding/assessment/costs

Query Parameters:
  building_id (required)
  timeframe (optional: 1yr, 3yr, 5yr, default: 5yr)
  include_npv (optional, default: true)

Response: Cost projections JSON as shown in examples
```

**Export to PDF**
```http
GET /api/onboarding/assessment/export/{building_id}.pdf

Returns: Full 125-page baseline assessment report
```

## Best Practices

### 1. Engineer Assessment Timing

- **Best:** Conduct physical inspection after initial data import
- **Schedule:** Allow 4-8 hours for 100-asset building
- **Team:** Pair junior engineers with senior for training
- **Photos:** Document all observations with photos

### 2. Historical Data Requirements

| Equipment Type | Historical Data Needed | Min Duration | Notes |
|----------------|------------------------|--------------|-------|
| HVAC (AHU/FCU) | Temperature, pressure, status | 14-30 days | Hourly minimum |
| Generators | Electrical, temps, runtime | 30-90 days | Includes exercised runs |
| Chillers | All parameters | 30-90 days | Seasonal patterns important |
| Power systems | kW, voltage, current | 7-14 days | Load profile critical |

### 3. AI/ML Confidence Factors

Confidence is **lower** when:
- < 7 days of historical data
- No engineer physical assessment
- Equipment irregular operation during learning period
- Missing critical sensor points

Confidence is **higher** when:
- 30+ days historical data
- Engineer validates AI findings
- Normal operation during baseline
- Complete sensor complement

### 4. Re-assessment Schedule

- **Critical assets:** Re-assess quarterly
- **Poor condition:** Re-assess semi-annually
- **Fair condition:** Re-assess annually
- **Good/New:** Re-assess every 2 years or after major work

### 5. Cost Model Refinement

Update cost models when:
- Actual maintenance costs deviate > 15% from predictions
- Part costs change significantly
- Labor rates change
- New failure modes identified
- Equipment replaced/upgraded

## Integration with Maintenance Systems

### Auto-Create Work Orders

```python
# Critical findings automatically create work orders
if equipment.baseline.condition == "CRITICAL":
    work_order = {
        "priority": "HIGH",
        "equipment_id": equipment.id,
        "generated_by": "baseline_assessment",
        "reason": f"Critical condition: {equipment.baseline.health_score}%",
        "tasks": equipment.baseline.recommendations.immediate,
        "estimated_cost": equipment.costs.critical_items_12m
    }
```

**See:** [Integration Wizard](integration-wizard.md) for CMMS integration details

### Budget Planning Integration

Export cost projections for financial planning:
```http
GET /api/onboarding/assessment/export-budget
?building_id=site-002
&years=1,3,5
&format=excel
```

## Troubleshooting

### Insufficient Historical Data

**Error:** "Cannot train autoencoder: < 7 days of data"

**Solutions:**
1. Collect more historical BMS data
2. Run assessment in "engineer_override" mode
3. Use manufacturer baseline models
4. Accept lower confidence scores

### AI/ML Findings Disagree with Engineer

**When ML says "Good" but engineer says "Poor":**

1. **ML might be missing:** Recent physical degradation not yet in data
2. **Engineer might see:** Wear that hasn't affected performance yet
3. **Resolution:** Engineer assessment takes precedence (override ML)
4. **Adjust:** Add weight to engineer input in scoring algorithm

### Cost Projections Seem High/Low

**Verification steps:**
1. Validate equipment categorization
2. Review OEM cost benchmarks
3. Adjust condition multipliers
4. Include local labor rates
5. Check for missing critical items

## Related Documentation

- [AI-Assisted Onboarding](ai-assisted-onboarding.md) - SIMBIOT data import
- [ML Model Development](43-ml-model-development.md) - LSTM and Autoencoder details
- [Technician Chat](technician-chat.md) - Field assessment integration
- [Energy Centre](../07-integrations/energy-centre.md) - Generator asset specifics
