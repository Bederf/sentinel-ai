# Emergency Investigation Report — Site S003 Multi-System Failure

**Contractor:** CoolTech Services (Pty) Ltd
**Report Date:** 2026-02-10
**Investigation Period:** 2026-02-07 to 2026-02-09
**Classification:** Emergency — Cascading Multi-System Failure

---

## 1. Executive Summary

Site S003 experienced a cascading failure event over 72 hours (7-9 February 2026) affecting the chiller plant, air handling units, electrical systems, and fire detection. The root cause was progressive condenser fouling on Chiller-001 (lead unit) that had been inadequately addressed in previous maintenance cycles, compounded by simultaneous load shedding events and an aging fire panel communication bus.

Total impact: 3 days of severely degraded comfort, 47 formal occupant complaints, partial floor evacuations on Day 3, and estimated R350,000 in emergency repair costs plus R120,000 in lost productivity.

## 2. Timeline of Events

### Day 1 — 7 February 2026

- **00:00-06:00**: Night setback mode. Chiller-001 running as lead, CWT supply at 7.2C (setpoint 6.5C). COP measured at 3.8 (design: 5.2). Condenser approach temperature elevated at 8.5C vs design 3.0C.
- **06:30**: Building warm-up begins. Chiller-001 cannot achieve setpoint. Chiller-002 and 003 called as lag units.
- **08:00**: Zone temperatures L2 and L3 reaching 24-25C. First comfort complaints logged.
- **09:15**: Formal complaint CC-001 from L2-201.
- **12:00**: COP on Chiller-001 drops to 3.2. Compressor current 15% above nominal.
- **14:00**: Peak load. All three chillers running at 95%+ capacity. CWT supply fluctuating 8-9C.
- **16:00**: AHU supply air temperatures elevated to 16-17C (design 13C).

### Day 2 — 8 February 2026

- **07:00**: Overnight recovery incomplete. Building entered day at 24C ambient.
- **08:45**: Cold complaint CC-008 (overnight overcooling from chillers running catch-up at 2am).
- **09:30**: Temperature climb resumes. 12 complaints by noon.
- **12:00**: Chiller-001 COP at 2.8. High head pressure alarms every 30 minutes.
- **13:00**: Electrical burning smell reported from L0 (CC-018). Investigation finds MSB Phase B connection running hot (IR survey: 85C, threshold 60C). Connection retorqued under outage window.
- **15:00**: Load shedding Stage 4 begins. ATS transfers to generator. Transfer takes 8 seconds (spec: 3 seconds) due to pitted contacts.
- **15:05**: Chiller-001 trips on restart after power dip. Cannot restart — compressor thermal overload.
- **16:00**: Only Chiller-002 and 003 operational. Insufficient capacity for full building load.
- **17:00**: Staff departures accelerate due to heat. HR logs 15 early departures.

### Day 3 — 9 February 2026

- **07:30**: Electrical burning smell again from plant room. Generator exhaust backed up due to stuck louvre.
- **08:00**: Building at 26C at start of day. Crisis meeting called by facilities management.
- **09:00**: Board demands same-day resolution (CC-021).
- **10:00**: Chiller-001 compressor trip count: 12 in 48 hours. Emergency service call placed.
- **10:30**: Loud banging from chiller plant room (CC-025). Investigation: Chiller-003 compressor bearing noise, oil analysis from January confirmed elevated iron.
- **12:00**: Fire panel RS-485 bus fault on Loop 2. 4 zones show communication failure. Building warden briefed on manual fire watch.
- **14:00**: Zone temperatures peak at 30C (CC-032). Partial floor evacuation L2.
- **14:30**: Emergency contractor mobilises portable air conditioning units.
- **15:00**: Second load shedding event. Generator starts but ATS transfer causes voltage dip. UPS beeps, IT equipment reboots on some floors.
- **15:30**: Fire alarm activates in parking level (CC-037). False alarm traced to heat buildup in confined space near generator exhaust.
- **16:00**: Emergency condenser cleaning begins on Chiller-001 (mechanical rod-out).
- **18:00**: Chiller-001 back online after condenser clean. CWT supply drops to 7.0C. COP recovers to 4.5.
- **20:00**: Building temperatures stabilising at 24C. Portable units supplementing.
- **22:00**: Fire panel Loop 2 RS-485 termination resistor found corroded. Temporary replacement installed.

## 3. Root Cause Analysis

### Primary: Condenser Fouling (Chiller-001)

The chiller condenser tubes were severely fouled despite chemical cleaning in November 2025. The chemical treatment was ineffective against the type of biological growth (Legionella risk noted — water treatment company notified). Condenser approach temperature had degraded from 3.0C to 11.5C, reducing cooling capacity by approximately 35%.

**Contributing factors:**
- Water treatment regime not adjusted after cooling tower basin repair in October 2025
- Chemical cleaning in November was a half-measure — full mechanical rod-out was recommended but deferred to save costs
- No continuous condenser fouling monitoring (approach temperature not trended)

### Secondary: Electrical System Degradation

- MSB Phase B bus bar connection had been flagged in October thermographic survey (WO-2025-0345) as "retorqued" but the root cause (micro-fretting from thermal cycling) was not addressed
- ATS contactor pitting from frequent load shedding transfers (average 2.3 events/week since Stage 6 period)

### Tertiary: Fire Panel Communication

- RS-485 bus termination resistor corroded by moisture ingress from nearby chilled water pipe condensation
- Annual fire panel test (WO-2026-0056, 1 February) noted "RS-485 bus intermittent on loop 2" but no corrective action was scheduled

## 4. Affected Systems

| System | Impact | Duration |
|--------|--------|----------|
| Chiller Plant | 35% capacity reduction, lead unit offline 26 hours | 72 hours |
| AHU System | Supply air temp elevated 3-4C above design | 72 hours |
| Electrical | MSB hotspot, ATS slow transfer, voltage dips | Intermittent |
| Fire Detection | Loop 2 communication failure (4 zones) | 18 hours |
| Generator | Exhaust louvre stuck, noise complaints | 8 hours |
| UPS | Brief bypass during voltage dips | 2 events |

## 5. Recommendations

### Immediate (within 7 days)

1. **Chiller-001**: Full mechanical tube cleaning complete. Schedule follow-up approach temperature verification in 2 weeks.
2. **Chiller-003**: Schedule compressor bearing replacement before failure. Oil iron levels 3x threshold.
3. **Fire Panel Loop 2**: Replace all RS-485 terminators on loops 1-4. Install condensation drip tray above cable run.
4. **MSB Phase B**: Schedule bus bar connection replacement (not just retorque) during next planned outage.

### Short-term (within 30 days)

5. **Water Treatment**: Review and upgrade cooling tower water treatment regime. Engage specialist for biological growth assessment.
6. **Condenser Monitoring**: Install approach temperature trending with automatic alarm at +3C above baseline.
7. **ATS Replacement**: Replace ATS contactors (3500+ operations, well past 2000-cycle service life).
8. **Generator Exhaust**: Replace motorised exhaust louvre actuator and add position feedback monitoring.

### Medium-term (within 90 days)

9. **Chiller Plant Redundancy**: Current N+1 design is effectively N+0 when lead unit is degraded. Consider adding standby chiller or increasing individual unit capacity.
10. **Fire Panel Upgrade**: RS-485 bus is end-of-life technology for this panel. Budget for fibre loop upgrade in next CAPEX cycle.
11. **UPS Battery**: Schedule full battery string replacement — current string is 7 years old (design life: 5 years).
12. **Building Monitoring**: Implement continuous commissioning system with automated performance deviation alerting.

## 6. Cost Summary

| Item | Cost (ZAR) |
|------|-----------|
| Emergency chiller cleaning | R 85,000 |
| Portable AC rental (3 days) | R 45,000 |
| Fire panel temporary repair | R 8,500 |
| MSB emergency retorque | R 12,000 |
| Generator louvre repair | R 6,500 |
| ATS contactor cleaning | R 12,500 |
| Contractor emergency callout (2x) | R 35,000 |
| **Total emergency costs** | **R 204,500** |
| Estimated productivity loss (3 days, 200 staff) | R 120,000 |
| Potential lease penalty exposure | R 250,000 |
| **Total exposure** | **R 574,500** |

## 7. Preventive Maintenance Gap Analysis

The following maintenance activities were either deferred, incomplete, or inadequate:

| WO Reference | Gap |
|-------------|-----|
| WO-2025-0189 | Chemical clean insufficient — mechanical clean should have been done |
| WO-2025-0301 | Condenser fan motor replaced but fouling root cause not addressed |
| WO-2025-0345 | Bus bar retorqued but micro-fretting not diagnosed |
| WO-2026-0056 | RS-485 intermittent fault noted but no corrective WO raised |
| WO-2026-0067 | Emergency repair was reactive — should have been caught by trending |

## 8. Conclusion

This cascading failure was preventable. Each individual system had warning signs that were either missed, deferred, or inadequately addressed. The combination of a hot February, load shedding, and deferred maintenance created a perfect storm.

The most critical lesson: **approach temperature trending would have caught the condenser fouling 6-8 weeks before failure**. A R5,000 sensor installation could have prevented R574,000 in total exposure.

---

**Report Prepared By:** J. van der Merwe, Senior HVAC Engineer, CoolTech Services
**Reviewed By:** P. Naidoo, Technical Director, CoolTech Services
**Distribution:** Site S003 Facilities Management, Property Management, Insurance
