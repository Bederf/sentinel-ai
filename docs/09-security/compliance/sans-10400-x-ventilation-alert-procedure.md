---
title: "SANS 10400-X Ventilation Rate ACH Alert — Implementation Procedure"
type: "procedure"
status: "draft"
version: "0.1.0"
created: "2026-05-19"
updated: "2026-05-19"
author: "SENTINEL Compliance Team"
tags: ["sans-10400-x", "ventilation", "ach", "carbon-dioxide", "outdoor-air", "ohs", "compliance", "hvac"]
domain: "compliance"
audience: "compliance, engineering, facilities, hvac"
complexity: "intermediate"
estimated_read_time: 15
---

# SANS 10400-X Ventilation Rate ACH Alert — Implementation Procedure

## 1. Purpose

This procedure ensures SENTINEL monitors zone ventilation rates against SANS 10400-X minimum requirements and fires a Prometheus alert when CO₂ levels indicate insufficient outdoor air supply. It defines ACH (Air Changes per Hour) minimums per zone type, CO₂ trigger thresholds, and the implementation path in `shadow_mode_polling.py`.

**Reference:** SANS 10400-X:2020 — Ventilation for buildings other than dwellings; Table X3 (minimum ventilation rates) and Table X4 (outdoor air rates).
**Owner:** AI Engineering Lead.
**Implementation target:** 2026-08-31.

---

## 2. SANS 10400-X Ventilation Requirements

### 2.1 Minimum Outdoor Air Rates by Zone Type

SANS 10400-X Table X4 prescribes minimum outdoor air rates (in L/s per person or L/s per m²):

| Zone Type | Example | Min Outdoor Air Rate | Notes |
|-----------|---------|---------------------|-------|
| Office (open plan) | Floors 1-5 | 7.5 L/s per person + 1 L/s per m² | Occupancy density ~10m²/person |
| Office (enclosed) | Meeting rooms | 10 L/s per person | Higher density |
| Lobby / reception | Ground floor | 10 L/s per person | High turnover |
| Plant room | Mechanical room | 5 L/s per m² | No occupancy |
| Basement / parking | Underground area | 5 L/s per m² ( dilution ventilation ) | |
| Server room | IDF/data closets | 10 L/s per m² | Equipment heat |
| Toilet / ablution | Sanitary areas | Exhaust only (no supply minimum) | Extract fans |
| Emergency egress corridor | Stairwells | 0.5 L/s per m² | Smoke control |

### 2.2 ACH Conversion

For SENTINEL monitoring (which uses CO₂ as proxy), outdoor air adequacy is determined by ACH (Air Changes per Hour) based on zone CO₂ levels:

| Zone Type | Target ACH | CO₂ Proxy Threshold | Alert Trigger |
|-----------|-----------|---------------------|---------------|
| Office (occupied) | ≥4 ACH | <800 ppm (advisory) | >900 ppm = investigate; >1000 ppm = alert |
| Meeting rooms (occupied) | ≥6 ACH | <800 ppm | >900 ppm = investigate; >1000 ppm = alert |
| Lobby | ≥4 ACH | <900 ppm | >1000 ppm = investigate; >1100 ppm = alert |
| Server room | ≥8 ACH | <1000 ppm | >1200 ppm = alert (equipment) |

> **Important note:** SANS 10400-X uses outdoor air rate (L/s/person), not ACH. CO₂ is a proxy for occupancy-driven ventilation need. When CO₂ exceeds the threshold, it indicates the outdoor air damper may not be providing adequate dilution ventilation — not a direct ACH measurement.

### 2.3 SANS 10400-X Table X3 — CO₂ Concentration Limits

| Space Type | Max CO₂ concentration (ppm) above outdoor | Guideline |
|------------|-------------------------------------------|-----------|
| Offices | 350 ppm above outdoor (≈650 ppm total) | Advisory |
| Meeting rooms | 350 ppm above outdoor | Advisory |
| Classrooms | 350 ppm above outdoor | Advisory |
| **Absolute limit** | **1000 ppm total** | **Must not exceed — alert** |

Outdoor ambient CO₂: ~420 ppm (urban Johannesburg). Therefore:
- Advisory threshold: 420 + 350 = **770 ppm** (approximate)
- Absolute alert threshold: **1000 ppm** (per GBCSA Green Star)

---

## 3. Implementation in SENTINEL

### 3.1 Zone CO₂ Monitoring

SENTINEL already monitors zone CO₂ via `shadow_mode_polling.py` `_sync_equipment_status()` which reads `ZONE_CO2` points from the BACnet integration.

**Current implementation:**
- CO₂ readings are logged to `equipment_status` table with `sensor_type='co2_ppm'`
- Threshold check: no automatic alert currently fires when CO₂ > 1000 ppm

**Gap:** No Prometheus alert fires on CO₂ exceedance. No ACH calculation against zone type minimums.

### 3.2 Required Changes

Two changes are required in `shadow_mode_polling.py`:

1. **Add CO₂ threshold mapping per zone type** in `__init__`
2. **Add `_check_ventilation_compliance()` method** that evaluates CO₂ against zone type
3. **Expose `sentinel_ventilation_alert` Prometheus metric** for alerting

### 3.3 Zone Type Mapping (Proposed)

Add to `ShadowModePollingService.__init__`:

```python
# SANS 10400-X ventilation thresholds per zone type
ZONE_VENTILATION_THRESHOLDS = {
    "office_floor": {"co2_advisory": 800, "co2_alert": 1000, "min_ach": 4},
    "meeting_room": {"co2_advisory": 800, "co2_alert": 1000, "min_ach": 6},
    "lobby": {"co2_advisory": 900, "co2_alert": 1100, "min_ach": 4},
    "server_room": {"co2_advisory": 1000, "co2_alert": 1200, "min_ach": 8},
    "plant_room": {"co2_advisory": 1200, "co2_alert": 1500, "min_ach": 5},
    "basement": {"co2_advisory": 1000, "co2_alert": 1500, "min_ach": 3},
}

# Zone type per FCU zone (from building.json registry)
ZONE_TYPE_MAP = {
    "S002-FCU-01": "office_floor",   # Floor 1 open plan
    "S002-FCU-02": "office_floor",   # Floor 2 open plan
    "S002-FCU-03": "office_floor",   # Floor 3 open plan
    "S002-FCU-04": "meeting_room",   # Floor 4 meeting room
    "S002-FCU-05": "office_floor",   # Floor 5 open plan
    "S002-FCU-06": "office_floor",   # Floor 6 open plan
    "S002-FCU-07": "office_floor",   # Floor 7 open plan
    "S002-FCU-08": "lobby",          # Ground floor lobby
}
```

### 3.4 `_check_ventilation_compliance()` Method (Proposed)

```python
def _check_ventilation_compliance(self, zone_code: str, co2_ppm: float) -> dict:
    """
    Evaluates zone CO₂ against SANS 10400-X thresholds.
    
    Returns dict with:
      - status: 'compliant' | 'advisory' | 'alert'
      - co2_ppm: current reading
      - threshold: applicable threshold
      - zone_type: the zone classification
    """
    zone_type = self.ZONE_TYPE_MAP.get(zone_code, "office_floor")
    thresholds = self.ZONE_VENTILATION_THRESHOLDS.get(zone_type, self.ZONE_VENTILATION_THRESHOLDS["office_floor"])
    
    if co2_ppm > thresholds["co2_alert"]:
        status = "alert"
    elif co2_ppm > thresholds["co2_advisory"]:
        status = "advisory"
    else:
        status = "compliant"
    
    return {
        "status": status,
        "co2_ppm": co2_ppm,
        "advisory_threshold": thresholds["co2_advisory"],
        "alert_threshold": thresholds["co2_alert"],
        "zone_type": zone_type,
        "equipment_code": zone_code,
        "site_id": self.site_id,
    }
```

### 3.5 Prometheus Metric for Alerting

Expose metric via `DISCIPLINE_REGISTRY`:

```python
# In __init__, register ventilation discipline
from app.core.prometheus_metrics import DISCIPLINE_REGISTRY

DISCIPLINE_REGISTRY.register(
    metric_name="sentinel_ventilation_co2_ppm",
    metric_type="gauge",
    description="Zone CO₂ concentration in ppm (SANS 10400-X monitoring)",
    labels=["site_id", "zone_code", "zone_type"],
    # Update in _sync_equipment_status() whenever a CO₂ reading is taken
)

# In _sync_equipment_status(), after reading ZONE_CO2:
vent_check = self._check_ventilation_compliance(zone_code, co2_reading)
DISCIPLINE_REGISTRY.record(
    "sentinel_ventilation_co2_ppm",
    value=co2_reading,
    labels={
        "site_id": self.site_id,
        "zone_code": zone_code,
        "zone_type": vent_check["zone_type"],
    }
)
```

---

## 4. Prometheus Alert Rules

Add to `infrastructure/prometheus/alerting-rules.yml`:

```yaml
- alert: SentinelVentilationCO2Exceedance
  expr: sentinel_ventilation_co2_ppm > 1000
  for: 5m
  labels:
    severity: warning
    category: compliance
  annotations:
    summary: "Zone CO₂ exceeds SANS 10400-X limit"
    description: "{{ $labels.zone_code }} at {{ $labels.site_id }}: {{ $value }} ppm CO₂ (limit: 1000 ppm, SANS 10400-X)"
    action: "Check outdoor air damper position on AHU serving this zone. Verify CO₂ sensor calibration."

- alert: SentinelVentilationCO2Critical
  expr: sentinel_ventilation_co2_ppm > 1200
  for: 2m
  labels:
    severity: critical
    category: compliance
  annotations:
    summary: "Zone CO₂ critically high — possible ventilation failure"
    description: "{{ $labels.zone_code }} at {{ $labels.site_id }}: {{ $value }} ppm (dangerous, >1200 ppm). Immediate HVAC inspection required."
    action: "CRITICAL: Check AHU outdoor air damper immediately. Do not leave zone occupied until cleared."

- alert: SentinelOutdoorAirDamperLow
  expr: |
    (
      sentinel_outdoor_air_damper_pct{site_id="site-002"} < 10
      and
      sentinel_ventilation_co2_ppm{site_id="site-002"} > 900
    )
    for: 10m
  labels:
    severity: warning
    category: compliance
  annotations:
    summary: "Outdoor air damper appears closed with elevated CO₂"
    description: "AHU {{ $labels.ahu_id }} outdoor air damper at {{ $value }}% while zone CO₂ >900 ppm. Possible damper failure or incorrect economizer setting."
    action: "Check AHU outdoor air damper actuator and control sequence. Verify BMS points."
```

**Note:** `sentinel_outdoor_air_damper_pct` requires a new BACnet point `OUTDOOR_AIR_DAMPER_PCT` to be read by `shadow_mode_polling.py`. This point must be added to the SIMBIOT/BACnet integration if not already present.

---

## 5. Outside Air Damper Monitoring

### 5.1 BACnet Point Requirements

To enable `SentinelOutdoorAirDamperLow` alert, the following BACnet points must be available from the Desigo BMS:

| Point Name | Description | Expected Range | Source |
|------------|------------|---------------|--------|
| `OUTDOOR_AIR_DAMPER_PCT` | Outdoor air damper position | 0-100% | AHU controller (PXC) |
| `SUPPLY_FAN_SPEED_PCT` | Supply fan speed | 0-100% | AHU controller (PXC) |
| `RETURN_AIR_DAMPER_PCT` | Return air damper position | 0-100% | AHU controller (PXC) |
| `OUTDOOR_AIR_FLOW_M3S` | Measured outdoor air flow (if metered) | 0-m³/s | Air flow station on AHU |

### 5.2 Damper Position Logic

| Damper Position | Interpretation | Action |
|----------------|---------------|--------|
| <10% for >10min with elevated CO₂ | Damper likely stuck closed or faulty | Alert — investigate immediately |
| 10-30% with CO₂ advisory | Partial opening; check economizer | Advisory — schedule maintenance |
| >30% with CO₂ compliant | Adequate outdoor air | No action |
| >95% | Full open (purge mode) | Normal for morning startup or high occupancy |

---

## 6. Implementation Timeline

| Step | Description | Owner | Target |
|------|-------------|-------|--------|
| 1 | Add `ZONE_VENTILATION_THRESHOLDS` and `ZONE_TYPE_MAP` to `ShadowModePollingService.__init__` | AI Engineering Lead | 2026-07-15 |
| 2 | Add `_check_ventilation_compliance()` method | AI Engineering Lead | 2026-07-15 |
| 3 | Register `sentinel_ventilation_co2_ppm` in `DISCIPLINE_REGISTRY` | AI Engineering Lead | 2026-07-15 |
| 4 | Add `_sync_ventilation()` call in main poll loop | AI Engineering Lead | 2026-07-15 |
| 5 | Confirm BACnet point `OUTDOOR_AIR_DAMPER_PCT` available from Desigo | Facilities | 2026-07-31 |
| 6 | Add `sentinel_outdoor_air_damper_pct` metric and reading | AI Engineering Lead | 2026-08-15 |
| 7 | Add Prometheus alerts to `alerting-rules.yml` | AI Engineering Lead | 2026-08-15 |
| 8 | Validate with live CO₂ data in shadow mode | AI Engineering Lead | 2026-08-31 |
| 9 | Document zone type mapping in `building.json` | AI Engineering Lead | 2026-08-31 |

---

## 7. Ventilation Compliance Dashboard

Add panel to Grafana "SENTINEL Compliance Overview" dashboard:

| Panel | Type | Query | Threshold Line |
|-------|------|-------|----------------|
| Zone CO₂ (ppm) — All Zones | Time series | `sentinel_ventilation_co2_ppm{site_id="site-002"}` | 800 (advisory), 1000 (alert) |
| Ventilation Compliance Summary | Stat | `count(sentinel_ventilation_co2_ppm{site_id="site-002"} < 800)` | — |
| Outdoor Air Damper Position | Time series | `sentinel_outdoor_air_damper_pct{site_id="site-002"}` | 30% (minimum) |
| Ventilation Alerts (90d) | Table | `sentinel_ventilation_alert{site_id="site-002"}` | — |

---

## 8. Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | 2026-05-19 | Compliance Team | Initial SANS 10400-X ventilation ACH alert procedure |

### Approval

- **AI Engineering Lead:** ___________________ Date: ___________
- **Facilities Manager:** ___________________ Date: ___________
- **Managing Director:** ___________________ Date: ___________

---

## 9. Related Documents

- [South African Regulatory Compliance Register](south-africa-regulatory-compliance-register.md)
- [Compliance Module](../../04-features/compliance-module.md)
- [Shadow Mode Polling Service](../../services/shadow_mode_polling.py)
- [SIMBIOT Universal Adapter Architecture](../../05-integrations/simbiot-universal-adapter-pattern.md)

---

*This document is a controlled record. Implementation must be completed by 2026-08-31 per regulatory compliance register.*