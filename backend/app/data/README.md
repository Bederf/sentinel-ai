# BMS Intelligence Platform - Sample Data

## Overview

These CSV files represent **realistic FM data** that would be exported from:
- CAFM system (work orders, assets)
- BCC/BMS (alarms)
- Utility bills / smart meters (energy)

## Files

| File | Records | Description |
|------|---------|-------------|
| `work_orders.csv` | 28 | Work order history showing failure patterns |
| `assets.csv` | 19 | Asset register with age, condition, lifecycle data |
| `sites.csv` | 10 | Site information with BMS type and data availability |
| `alarms.csv` | 20 | BCC alarm history showing degradation trends |
| `energy_readings.csv` | 25 | Energy consumption for efficiency analysis |

---

## Key Stories in the Data

### 1. Centurion Mall AHU-002: The Failure That Was Predicted

**Asset:** `ASSET-011` / `CM-HVAC-AHU-002`

| Date | Event | Technician Said |
|------|-------|-----------------|
| Mar 2024 | Routine service | "Slight vibration on startup - monitoring" |
| Jun 2024 | No cooling call | "Vibration slightly worse. Bearings may need attention" |
| Sep 2024 | Quarterly service | "URGENT: Bearings need replacement. Quote R28,500" |
| Jan 2025 | Grinding noise | "Client hasn't approved quote. WILL fail." |
| Mar 2025 | Loud rattling | "4th call on bearings. Parts on 6 week lead time." |
| Apr 2025 | Motor overload | "Motor drawing 42A vs 38A. Being damaged each reset." |
| **May 2025** | **COMPLETE FAILURE** | **"Motor burnt out as predicted. R63,300 emergency cost."** |

**AI would have flagged this in September 2024** based on:
- Repeat calls (4 in 6 months)
- Fault code progression (VIB-01 → VIB-02 → OVL-01 → FAIL-01)
- Technician keywords ("urgent", "recommend", "will fail")
- Asset age (20 years)

---

### 2. Gateway Chiller: The Pattern Repeating NOW

**Asset:** `ASSET-020` / `GW-HVAC-CH-001`

| Date | Event | Warning Sign |
|------|-------|--------------|
| Jun 2025 | Routine service | "Minor vibration on startup - monitoring" |
| Aug 2025 | Night noise report | "Vibration 3.8mm/s. Similar to Centurion before failure" |
| Oct 2025 | Loud startup noise | "Oil analysis shows metal particles. EXACTLY like Centurion" |
| Dec 2025 | Vibration critical | "Quote pending. Maybe 4-8 weeks before complete failure" |

**AI flags this at 95% probability** because:
- Same fault code sequence as Centurion
- Technician explicitly notes pattern match
- Oil analysis confirms bearing wear
- 2 repeat calls in 4 months

**Potential savings:** R65,000 (failure) - R28,000 (proactive) = **R37,000**

---

### 3. The Learning: Proactive Success

**Asset:** `ASSET-010` / `CM-HVAC-AHU-001` (twin unit to failed AHU-002)

After the AHU-002 disaster, when AHU-001 showed first vibration sign in November 2025:
- Client **immediately approved** proactive bearing replacement
- Cost: R28,300 (vs R63,300+ if waited for failure)
- Technician note: "This is exactly what predictive maintenance should be"

---

## Data Schema

### work_orders.csv

```
work_order_id         - Unique ID (WO-YYYY-NNNN)
site_id               - Foreign key to sites
site_name             - Site name (denormalized for easy reading)
asset_id              - Foreign key to assets (nullable for site-level issues)
asset_tag             - Asset tag (denormalized)
asset_category        - hvac-ahu, hvac-chiller, generator, lift-passenger, etc.
reported_date         - When issue was reported
acknowledged_date     - When BCC acknowledged
arrived_date          - When technician arrived
completed_date        - When work completed
closed_date           - When administratively closed
fault_code            - Standardized fault code (HVAC-VIB-01, GEN-START-01, etc.)
category              - Work category (hvac-noise, hvac-breakdown, electrical-trip, etc.)
priority              - critical, high, medium, low
type                  - reactive, planned, project, inspection
description           - What was reported
resolution            - What was done
technician_notes      - FREE TEXT - gold mine for NLP
technician_name       - Who did the work
labour_hours          - Hours spent
labour_cost           - ZAR
parts_cost            - ZAR
contractor_cost       - ZAR (if subcontracted)
total_cost            - ZAR total
sla_target_hours      - SLA target for this priority
sla_met               - TRUE/FALSE
repeat_call           - TRUE if related to previous WO on same asset
related_wo            - Previous work order ID if repeat
```

### Pattern Detection Logic

The AI looks for:

1. **Fault Code Progression**
   ```
   HVAC-VIB-01 → HVAC-VIB-02 → HVAC-OVL-01 → HVAC-FAIL-01
   (warning)    (elevated)    (overload)    (failure)
   ```

2. **Repeat Calls**
   - Same asset, same category, within 6 months
   - Strong indicator of unresolved root cause

3. **Technician Keywords**
   - "recommend replacement"
   - "urgent"
   - "will fail"
   - "end of life"
   - "same pattern as"

4. **Asset Age vs Expected Life**
   - 20-year-old AHU with 20-year expected life = high risk

5. **Alarm Frequency Trending**
   - Increasing alarms on same asset = degradation

---

## How to Import

### Python (Pandas)

```python
import pandas as pd

# Load all data
work_orders = pd.read_csv('work_orders.csv', parse_dates=['reported_date', 'completed_date'])
assets = pd.read_csv('assets.csv', parse_dates=['install_date'])
sites = pd.read_csv('sites.csv')
alarms = pd.read_csv('alarms.csv', parse_dates=['triggered_at', 'cleared_at'])
energy = pd.read_csv('energy_readings.csv', parse_dates=['period_start', 'period_end'])

# Find repeat calls
repeat_calls = work_orders[work_orders['repeat_call'] == True]
print(f"Repeat calls: {len(repeat_calls)} ({len(repeat_calls)/len(work_orders)*100:.1f}%)")

# Find assets with failure progression
failure_assets = work_orders[
    work_orders['fault_code'].str.contains('FAIL', na=False)
]['asset_id'].unique()
print(f"Assets that failed: {failure_assets}")
```

### SQL (if loaded to database)

```sql
-- Find assets with 3+ work orders in 6 months (failure candidates)
SELECT
    asset_id,
    asset_tag,
    site_name,
    COUNT(*) as wo_count,
    SUM(CASE WHEN repeat_call = TRUE THEN 1 ELSE 0 END) as repeat_count
FROM work_orders
WHERE reported_date >= DATE_SUB(NOW(), INTERVAL 6 MONTH)
GROUP BY asset_id, asset_tag, site_name
HAVING COUNT(*) >= 3
ORDER BY wo_count DESC;
```

---

## Expanding This Data

For a real implementation, you'd want:

| Data Point | Ideal Volume | Source |
|------------|--------------|--------|
| Work orders | 5+ years, all sites | CAFM export |
| Assets | Complete register | Asset management module |
| Alarms | 2+ years | BCC historian |
| Energy | 2+ years monthly | Utility bills or meters |
| Technician observations | Ongoing | Mobile app capture |

The more historical failures you can tag, the better the AI learns the patterns.

---

## Contact

**Pieter van Rooyen**
pieter@aimthelaw.co.za
