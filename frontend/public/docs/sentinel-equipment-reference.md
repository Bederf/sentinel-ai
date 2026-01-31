# SENTINEL Equipment Reference
## Sandton Building - Quick Reference Card

**BMS:** Siemens Desigo CC (BACnet/IP) | **Lighting:** DALI-2 (Tridonic Scenecom)

---

### Zone-to-Equipment Mapping

| Zone | Floor | FCU | VAV | AHU | Status |
|------|-------|-----|-----|-----|--------|
| Zone-L12-N | L12 | FCU-L12-03 | VAV-L12-03A | AHU-L12-01 | ● Online |
| Zone-L12-S | L12 | FCU-L12-04 | VAV-L12-04A | AHU-L12-01 | ● Online |
| Zone-L11-N | L11 | FCU-L11-01 | VAV-L11-01A | AHU-L11-01 | ● Online |
| Zone-L11-S | L11 | FCU-L11-02 | VAV-L11-02A | AHU-L11-01 | ● Fault |
| Zone-L10-N | L10 | FCU-L10-01 | VAV-L10-01A | AHU-L10-01 | ● Online |

---

### Equipment Hierarchy

```
CHILLER (011-stc-chiller-001)
    │
    ├── AHU-L12-01
    │   ├── VAV-L12-03A ──► FCU-L12-03 ──► Zone-L12-N (Desks 201-206)
    │   └── VAV-L12-04A ──► FCU-L12-04 ──► Zone-L12-S (Desks 207-212)
    │
    ├── AHU-L11-01
    │   ├── VAV-L11-01A ──► FCU-L11-01 ──► Zone-L11-N (Desks 101-106)
    │   └── VAV-L11-02A ──► FCU-L11-02 ──► Zone-L11-S (Desks 107-112)
    │
    └── AHU-L10-01
        └── VAV-L10-01A ──► FCU-L10-01 ──► Zone-L10-N (Desks 001-012)
```

---

### SENTINEL Control Points

| Equipment | Read | Write | Safety Limit |
|-----------|------|-------|--------------|
| **FCU** | | | |
| - room_temp | ✓ | - | - |
| - room_temp_setpoint | ✓ | ✓ | 16-28°C |
| - fan_speed | ✓ | ✓ | - |
| - valve_position | ✓ | - | - |
| **VAV** | | | |
| - damper_position | ✓ | ✓ | 10-100% |
| - airflow_actual | ✓ | - | - |
| - reheat_valve | ✓ | ✓ | 0-100% |
| **AHU** | | | |
| - supply_air_temp | ✓ | - | - |
| - fan_status | ✓ | ✓ | - |
| - chw_valve | ✓ | - | - |
| **Chiller** | | | |
| - chw_supply_temp | ✓ | - | - |
| - status | ✓ | - | - |

---

### DALI Lighting Zones

| DALI Zone | Controllers | Sensors | Luminaires |
|-----------|-------------|---------|------------|
| Zone-L12-N | DALI-L12-01 to 03 | 10 | 5 |
| Zone-L12-S | DALI-L12-04 to 06 | 5 | 3 |
| Zone-L11-N | DALI-L11-01 to 03 | 6 | 3 |
| Zone-L11-S | DALI-L11-04 to 06 | 5 | 3 |
| Zone-L10-N | DALI-L10-01 to 03 | 4 | 3 |

---

### Quick Actions (SENTINEL)

| Complaint | SENTINEL Action |
|-----------|-----------------|
| "Too hot at desk" | Check lux (solar?), lower FCU setpoint, dim lights |
| "Too cold at desk" | Check diffuser, increase VAV reheat, raise setpoint |
| "Stuffy" | Increase VAV airflow, check AHU outside air damper |

---

**SENTINEL BMS Intelligence** | Sandton Building | v1.0
