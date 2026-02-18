# SENTINEL Asset Management Workflow Demo Script

**Target Audience:** Facilities Management CTO / Decision Maker  
**Duration:** 10 minutes  
**Goal:** Showcase complete asset lifecycle management from onboarding through repair validation

---

## Scene 1: Building Onboarding (1 minute)

**Narrative:** "I'll show you how SENTINEL helps manage building assets end-to-end, from initial onboarding through ongoing maintenance and repair validation."

### Script

**Demo:**
> "Let me show you how SENTINEL helps manage building assets end-to-end.
>
> Let's start by onboarding a new building. I'll use our SIMBIOT MCP Server to import equipment data from a BACnet export."

**Action:** Show building onboarding via SIMBIOT MCP tools

\`\`\`bash
# Call SIMBIOT MCP tool: create_building
{
  "building_id": "sandton-mall-demo",
  "name": "Sandton City Mall",
  "address": "83 5th St, Sandton, South Africa"
}

# Result: Building created with 125 equipment assets identified
\`\`\`

**Demo:**
> "125 equipment assets identified across 6 equipment types - chillers, AHUs, generators, cooling towers, pumps, and UPS systems.
>
> Now let's capture initial baselines for our critical equipment. This establishes what 'normal' looks like for each asset."

**Action:** Capture initial baseline for chiller

\`\`\`bash
POST /api/equipment/chiller-001/baseline
{
  "baseline_type": "initial",
  "captured_by": "Mike Chen",
  "baseline_values": {
    "vibration_rms": 1.8,
    "motor_current": 145.2,
    "bearing_temp": 45.1,
    "chw_supply_temp": 7.2,
    "chw_return_temp": 12.5
  },
  "notes": "Commissioning baseline - all values normal"
}

# Result: Baseline captured successfully
\`\`\`

**Demo:**
> "Baseline captured - this establishes our equipment's normal operating condition. We'll use this to detect degradation over time."

**Key Value Propositions:**
- Rapid onboarding via BACnet import (no manual data entry)
- Automated equipment discovery
- Baseline capture establishes "normal" for each asset
- Foundation for proactive maintenance

**Visual Elements:**
- Building onboarding form
- Equipment list (125 items)
- Baseline capture form with values

---

## Scene 2: Routine Inspection (1 minute)

**Narrative:** "SENTINEL automatically schedules inspections based on baseline criticality. Let me show you how this works."

### Script

**Demo:**
> "SENTINEL automatically schedules inspections based on baseline criticality.
>
> Here's our monthly inspection for the main chiller."

**Action:** Show inspection dashboard with due inspections

\`\`\`bash
GET /api/inspection/tasks?status=scheduled

# Result: List of pending inspections
[
  {
    "equipment_id": "chiller-001",
    "task_type": "monthly",
    "due_date": "2025-11-01T10:00:00Z",
    "assigned_to": "Mike Chen",
    "checklist_items": ["Visual inspection", "Vibration analysis", "Temperature readings"]
  }
]
\`\`\`

**Demo:**
> "The technician completes the inspection using our mobile app or web interface."

**Action:** Submit inspection results

\`\`\`bash
POST /api/inspection/results
{
  "equipment_id": "chiller-001",
  "inspection_date": "2025-11-01T10:00:00Z",
  "inspector": "Mike Chen",
  "overall_status": "pass",
  "findings": "Vibration elevated (2.5 vs 1.8 baseline). Recommend monitoring.",
  "current_readings": {
    "vibration_rms": 2.5,
    "motor_current": 148.1,
    "bearing_temp": 48.3
  }
}

# Result: Inspection recorded, baseline comparison auto-generated
\`\`\`

**Demo:**
> "SENTINEL automatically compares results to baseline and flags deviations.
>
> Look at this - vibration is up 39% from baseline. The system is flagging this for monitoring."

**Action:** Show baseline comparison

\`\`\`json
{
  "baseline_value": 1.8,
  "current_value": 2.5,
  "deviation_percent": 39,
  "status": "warning"
}
\`\`\`

**Key Value Propositions:**
- Automated inspection scheduling
- Baseline comparison happens automatically
- Deviations flagged without manual calculation
- Technicians get instant feedback

**Visual Elements:**
- Inspection calendar/dashboard
- Mobile inspection form
- Baseline comparison with color-coded deviations
- Warning callout for elevated vibration

---

## Scene 3: ML Anomaly Detection (2 minutes)

**Narrative:** "Our ML models detected something concerning. Let me show you the prediction and the explainable AI behind it."

### Script

**Demo:**
> "Three months later, our ML models detected something concerning.
>
> Let me show you the prediction for this chiller."

**Action:** Show ML prediction card

\`\`\`bash
GET /api/ml/predictions/equipment/chiller-001

# Result:
{
  "equipment_id": "chiller-001",
  "prediction_type": "failure",
  "failure_probability": 0.85,
  "timeframe": "7 days",
  "confidence": "high",
  "contributing_factors": [
    {"factor": "Bearing vibration trend", "weight": 0.40, "value": "+111% from baseline"},
    {"factor": "Motor current increase", "weight": 0.25, "value": "+16% from baseline"},
    {"factor": "Bearing temperature", "weight": 0.20, "value": "85°C vs 45°C baseline"},
    {"factor": "Asset age", "weight": 0.10, "value": "21 years (exceeds 20-year life)"},
    {"factor": "Repeat calls", "weight": 0.05, "value": "3 vibration complaints in 6 months"}
  ]
}
\`\`\`

**Demo:**
> "The AI is predicting an 85% probability of compressor bearing failure within the next 7 days.
>
> But the real power is explainable AI - the system tells us WHY it's concerned."

**Action:** Scroll through contributing factors

**Demo:**
> "Bearing vibration up 111% from baseline - that's the biggest factor at 40% weight.
>
> Motor current is up 16%, bearing temperature is at 85°C versus a 45°C baseline - that's critical.
>
> The asset is 21 years old, exceeding the recommended 20-year lifespan.
>
> All pointing to imminent bearing failure."

**Action:** Show natural language explanation

\`\`\`json
{
  "explanation": "The chiller shows declining efficiency indicating refrigerant leak and bearing wear. Vibration levels are 111% above baseline with bearing temperature at critical 85°C. Asset age exceeds recommended 20-year lifespan."
}
\`\`\`

**Demo:**
> "SENTINEL automatically created a critical inspection task based on this prediction."

**Action:** Show automated inspection task

\`\`\`bash
GET /api/workflow/triggers/inspections/chiller-001

# Result:
{
  "equipment_id": "chiller-001",
  "task_type": "special",
  "priority": "high",
  "triggered_by": "ml_anomaly",
  "description": "ML detected bearing failure risk. Verify and inspect."
}
\`\`\`

**Key Value Propositions:**
- Predictive maintenance (fix before failure)
- Explainable AI builds trust with technicians
- Contributing factors show exactly what to inspect
- Automated inspection task generation
- Risk-based prioritization

**Visual Elements:**
- ML prediction card with probability circle (85%)
- Contributing factors bar chart (weighted)
- Natural language explanation
- High-priority inspection task badge
- Alert notification

---

## Scene 4: Repair Workflow (3 minutes)

**Narrative:** "The inspection confirmed the issue. Let me show you the complete repair workflow and effectiveness validation."

### Script

**Demo:**
> "The technician completed the inspection and confirmed the issue. Let me show you what happened."

**Action:** Show inspection deficiency

\`\`\`bash
GET /api/inspection/results/equipment/chiller-001?latest=true

# Result:
{
  "inspection_date": "2026-01-01T10:00:00Z",
  "overall_status": "fail",
  "findings": "Vibration critical (3.8 vs 1.8 baseline). Frequency analysis confirms bearing defect.",
  "deficiencies": [
    {
      "title": "Critical Compressor Bearing Wear",
      "severity": "critical",
      "category": "mechanical",
      "description": "Vibration at 3.8 mm/s is 111% above baseline. Frequency analysis confirms bearing defect.",
      "recommended_action": "Replace compressor bearing before catastrophic failure",
      "estimated_repair_cost_min": 5000,
      "estimated_repair_cost_max": 8000,
      "estimated_repair_hours": 6
    }
  ]
}
\`\`\`

**Demo:**
> "Critical deficiency identified: compressor bearing failure is imminent.
>
> SENTINEL automatically created a work order and scheduled a pre-repair baseline."

**Action:** Show auto-generated work order

\`\`\`bash
GET /api/workflow/triggers/work-orders/chiller-001

# Result:
{
  "equipment_id": "chiller-001",
  "title": "Replace Compressor Bearing",
  "description": "Critical bearing wear detected. Replace bearing assembly.",
  "priority": "urgent",
  "status": "scheduled",
  "estimated_cost": 6500,
  "estimated_hours": 6
}
\`\`\`

**Demo:**
> "Here's the automated workflow:
>
> 1. Critical deficiency detected → Work order created
> 2. Pre-repair baseline scheduled (to measure repair effectiveness)
> 3. Repair completed by technician
> 4. Post-repair baseline captured
> 5. SENTINEL validates repair effectiveness"

**Action:** Show pre-repair baseline

\`\`\`json
{
  "baseline_type": "pre_repair",
  "captured_date": "2026-01-15T14:30:00Z",
  "baseline_values": {
    "vibration_rms": 4.2,
    "motor_current": 168.0,
    "bearing_temp": 85.0
  },
  "notes": "Pre-repair baseline: vibration 133% above initial"
}
\`\`\`

**Demo:**
> "After the repair, we capture a post-repair baseline."

**Action:** Show post-repair baseline

\`\`\`json
{
  "baseline_type": "post_repair",
  "captured_date": "2026-01-20T16:00:00Z",
  "baseline_values": {
    "vibration_rms": 1.9,
    "motor_current": 146.0,
    "bearing_temp": 46.0
  },
  "notes": "Post-repair baseline after compressor bearing replacement"
}
\`\`\`

**Demo:**
> "And SENTINEL automatically validates the repair effectiveness."

**Action:** Show effectiveness validation

\`\`\`bash
POST /api/workflow/triggers/validate-effectiveness
{
  "equipment_id": "chiller-001",
  "pre_repair_baseline_id": "bl-chiller-001-3",
  "post_repair_baseline_id": "bl-chiller-001-4"
}

# Result:
{
  "effectiveness_score": 0.55,
  "overall_status": "success",
  "improvements": [
    {"metric": "vibration_rms", "improvement_percent": 55, "status": "success"},
    {"metric": "motor_current", "improvement_percent": 13, "status": "success"},
    {"metric": "bearing_temp", "improvement_percent": 46, "status": "success"}
  ],
  "validation_result": "Repair validated as successful. All metrics back to baseline range."
}
\`\`\`

**Demo:**
> "The repair is validated as successful with a 55% overall improvement.
>
> This outcome feeds back to our ML models to improve future predictions."

**Key Value Propositions:**
- Automated workflow (deficiency → work order → repair → validation)
- Pre/post repair baselines prove effectiveness
- Quantified improvement (55% better)
- ML feedback loop (predictions get smarter)
- Full audit trail for compliance

**Visual Elements:**
- Critical deficiency alert
- Auto-generated work order
- Pre/post baseline comparison chart
- Effectiveness score (55% improvement circle)
- Success checkmark
- Repair timeline

---

## Scene 5: Portfolio Overview (2 minutes)

**Narrative:** "Let me show you the portfolio view to see how this scales across all your buildings."

### Script

**Demo:**
> "Let me show you our portfolio view.
>
> This scales across all your buildings and equipment."

**Action:** Show workflow dashboard with all equipment

\`\`\`bash
GET /api/workflow/status/all

# Result: Fleet-wide summary
{
  "total_equipment": 125,
  "healthy": 98,
  "anomalies_detected": 18,
  "active_repairs": 5,
  "pending_inspections": 4
}
\`\`\`

**Demo:**
> "Green equipment: Healthy, routine maintenance only.
>
> Yellow equipment: Anomalies detected, inspections scheduled.
>
> Red equipment: Active repairs, tracking effectiveness."

**Action:** Show equipment grid with state indicators

**Demo:**
> "For each piece of equipment, you can see:
>
> - Current state in the workflow
> - Baseline history and trends
> - ML predictions with explainability
> - Active inspections and work orders
> - Repair effectiveness validation"

**Action:** Drill down into generator-002 (healthy example)

\`\`\`bash
GET /api/workflow/status/generator-002

# Result:
{
  "equipment_id": "generator-002",
  "current_state": "healthy",
  "baseline_count": 2,
  "last_inspection": "2026-01-10",
  "inspection_status": "pass",
  "ml_prediction": {
    "failure_probability": 0.05,
    "prediction_type": "healthy"
  },
  "active_deficiencies": [],
  "active_work_orders": []
}
\`\`\`

**Demo:**
> "This generator has been healthy for 7 years. Stable baseline, no issues.
>
> Compare to our AHU that just flagged an issue."

**Action:** Drill down into ahu-003 (active issue example)

\`\`\`bash
GET /api/workflow/status/ahu-003

# Result:
{
  "equipment_id": "ahu-003",
  "current_state": "anomaly_detected",
  "baseline_count": 2,
  "last_inspection": "2026-01-28",
  "ml_prediction": {
    "failure_probability": 0.72,
    "timeframe": "14 days",
    "confidence": "medium"
  },
  "pending_inspections": 1,
  "inspection_priority": "high"
}
\`\`\`

**Demo:**
> "Fan motor showing early signs of bearing degradation.
>
> Inspection scheduled for tomorrow - we're catching it BEFORE it fails."

**Demo:**
> "SENTINEL provides complete visibility from initial onboarding through repair validation - all automated, all data-driven.
>
> And the system gets smarter with every repair, continuously improving its predictions and recommendations."

**Key Value Propositions:**
- Fleet-wide visibility
- State-based color coding (green/yellow/red)
- Risk-based prioritization
- Proactive vs reactive maintenance
- Continuous learning (ML feedback loop)
- Scales to thousands of assets

**Visual Elements:**
- Equipment grid with 3-color state indicators
- Summary stats (125 total, 98 healthy, 18 anomalies, 5 repairs)
- Equipment detail view with timeline
- ML prediction card
- Upcoming inspections list

---

## Closing (30 seconds)

### Script

**Demo:**
> "That's the complete SENTINEL asset management workflow:
>
> 1. **Onboard** - Import equipment via BACnet, capture baselines
> 2. **Monitor** - Automated inspections with baseline comparison
> 3. **Predict** - ML detects anomalies before failure
> 4. **Repair** - Automated workflow with effectiveness validation
> 5. **Learn** - System improves with every repair
>
> Complete visibility from onboarding through validation.
>
> Any questions?"

---

## Demo Preparation Checklist

### Before the Demo

1. **Start backend server:**
   \`\`\`bash
   cd /opt/bms-intelligence/backend
   source venv/bin/activate
   uvicorn app.main:app --reload --port 9095
   \`\`\`

2. **Start frontend server:**
   \`\`\`bash
   cd /opt/bms-intelligence/frontend
   npm run dev
   \`\`\`

3. **Load demo data:**
   \`\`\`bash
   cd /opt/bms-intelligence/backend
   python3 scripts/setup_demo_workflow_data.py
   \`\`\`

4. **Open browser to:** http://localhost:9096

### Demo URLs to Pre-Load

- Dashboard: http://localhost:9096/dashboard
- Workflow Status: http://localhost:9096/workflow
- Equipment Detail: http://localhost:9096/workflow/chiller-001
- API Docs: http://localhost:9095/docs

### Verified Demo Queries

1. **Building onboarding:**
   \`\`\`bash
   curl http://localhost:9095/api/equipment/chiller-001/baseline/history
   \`\`\`

2. **Inspection status:**
   \`\`\`bash
   curl http://localhost:9095/api/inspection/results/equipment/chiller-001
   \`\`\`

3. **ML predictions:**
   \`\`\`bash
   curl http://localhost:9095/api/ml/predictions/equipment/chiller-001
   \`\`\`

4. **Workflow status:**
   \`\`\`bash
   curl http://localhost:9095/api/workflow/status/chiller-001
   \`\`\`

---

## Timing Breakdown

| Scene | Duration | Cumulative |
|-------|----------|------------|
| Scene 1: Onboarding | 1:00 | 1:00 |
| Scene 2: Inspection | 1:00 | 2:00 |
| Scene 3: ML Detection | 2:00 | 4:00 |
| Scene 4: Repair Workflow | 3:00 | 7:00 |
| Scene 5: Portfolio | 2:00 | 9:00 |
| Buffer/Questions | 1:00 | 10:00 |
| **Total** | **10:00** | |

---

## Key Value Propositions Summary

1. **Automated Onboarding:** BACnet import, no manual data entry
2. **Baseline Management:** Establish "normal", detect deviations automatically
3. **Explainable AI:** Technicians trust predictions because they understand WHY
4. **Automated Workflows:** Deficiency → Work Order → Repair → Validation
5. **Quantified Effectiveness:** 55% improvement, not just "better"
6. **Fleet Visibility:** Green/Yellow/Red status at a glance
7. **Continuous Learning:** ML models improve with every repair
8. **Proactive Maintenance:** Fix before failure, not after

---

**Demo Script Version:** 1.0  
**Last Updated:** 2026-02-03  
**Phase:** 53-03 (Demo Data & Script)
