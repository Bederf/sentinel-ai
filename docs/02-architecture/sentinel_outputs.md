# SENTINEL Advisory Outputs

## Purpose

Define the core advisory outputs SENTINEL delivers to operators.

Each output must:

- be specific to equipment and time
- explain why it matters
- give a clear action

Format:

```text
[Mode]
What is happening
Why it matters
Recommended action
```

These outputs sit on top of SENTINEL's existing optimization and posture logic:

- comfort first
- cost saving
- sweating the asset

They are not generic alert categories. They are the operator-facing expressions of SENTINEL's governing decision lenses.

## 1. Comfort

### C1 - Temperature Drift During Occupied Hours

**What is happening**  
Zone FA2-01 is 2.5°C above setpoint during occupied hours (09:00-11:00)

**Why it matters**  
Occupants are likely to experience discomfort within the next 30-60 minutes

**Recommended action**  
Check AHU-01 airflow and supply temperature. Verify no damper or valve faults

### C2 - Inconsistent Zone Conditions

**What is happening**  
Adjacent zones FA2-01 and FA2-02 show a 4°C temperature difference

**Why it matters**  
Uneven conditions increase likelihood of complaints and manual overrides

**Recommended action**  
Inspect zoning control, dampers, and balancing. Check sensor calibration

### C3 - Slow Recovery After Occupancy Start

**What is happening**  
Zone temperatures remain outside setpoint 45 minutes after scheduled occupancy start

**Why it matters**  
Delayed comfort delivery impacts occupant experience and productivity

**Recommended action**  
Review start-up schedules and pre-conditioning strategy. Check plant readiness

## 2. Cost Saving

### S1 - After-Hours Runtime

**What is happening**  
AHU-03 ran from 18:00-06:00 outside scheduled occupancy

**Why it matters**  
Unnecessary runtime increases energy consumption with no occupant benefit

**Recommended action**  
Review schedule and check for manual overrides or control logic issues

### S2 - Conditioning Unoccupied Space

**What is happening**  
Cooling active in Zone FA1-Boardroom with no occupancy detected

**Why it matters**  
Energy is being used without demand

**Recommended action**  
Align HVAC operation with occupancy signals or booking schedules

### S3 - Simultaneous Heating and Cooling

**What is happening**  
Heating and cooling systems active in the same zone over the same period

**Why it matters**  
This creates direct energy waste and indicates control conflict

**Recommended action**  
Review control sequences and setpoint logic for overlap or misconfiguration

## 3. Sweating The Asset

### A1 - Underutilized Equipment Capacity

**What is happening**  
Chiller operating at 55% capacity during peak demand period

**Why it matters**  
Available capacity is not being used efficiently, limiting system optimization

**Recommended action**  
Evaluate load distribution and staging strategy to maximize utilization

### A2 - Conservative Setpoints

**What is happening**  
Supply air temperature is lower than required to maintain comfort thresholds

**Why it matters**  
System is over-performing, increasing energy use without added benefit

**Recommended action**  
Adjust setpoints incrementally and monitor impact on comfort

### A3 - Premature Equipment Escalation

**What is happening**  
Secondary plant engaged while primary system is below optimal load

**Why it matters**  
Additional equipment use increases wear and operating cost unnecessarily

**Recommended action**  
Optimize staging logic to delay secondary system activation

## Acceptance Criteria

An output is valid if:

- it identifies a specific system or zone
- it includes a time or condition context
- it leads to a clear operator action
- it aligns with one of:
  - comfort
  - cost saving
  - sweating the asset

## Notes

- Do not generate generic alerts
- Do not surface raw data without interpretation
- Every output must support a decision or action
