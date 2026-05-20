---
title: "Site Compliance Annex — SITE_ID"
type: "compliance-annex"
status: "draft"
version: "0.1.0"
created: "__CREATED_DATE__"
updated: "__CREATED_DATE__"
author: "SENTINEL Compliance Team"
tags: ["compliance", "annex", "site-specific", "__SITE_ID__", "multi-site"]
domain: "compliance"
audience: "compliance, facilities, engineering, legal"
complexity: "intermediate"
estimated_read_time: 15
---

# Site Compliance Annex — __SITE_ID__

## 1. Site Identification

| Field | Value |
|-------|-------|
| **Site ID** | `__SITE_ID__` |
| **Building Name** | __BUILDING_NAME__ |
| **Building Type** | __BUILDING_TYPE__ |
| **Address** | __ADDRESS__ |
| **Floor Area (m²)** | __FLOOR_AREA_SQM__ |
| **Number of Floors** | __FLOOR_COUNT__ |
| **Legal Entity** | Asikhwele Building Projects (Pty) Ltd (reg 2015/010878/07) |
| **Data Controller** | Asikhwele Building Projects (Pty) Ltd |
| **Site Classification** | __SITE_CLASSIFICATION__ (commercial / mixed-use / residential) |
| **Onboarding Date** | __CREATED_DATE__ |
| **Compliance Annex Version** | 0.1.0 |

---

## 2. Equipment Register

### 2.1 HVAC Equipment

| Equipment | Code | BACnet/DALI/Modbus | Safety-Critical | SENTINEL Tier | BMS Protocol |
|-----------|------|-------------------|----------------|---------------|---------------|
| __HVAC_EQUIP_1__ | __HVAC_CODE_1__ | __HVAC_PROTO_1__ | __HVAC_SAFETY_1__ | __HVAC_TIER_1__ | __HVAC_BUS_1__ |
| __HVAC_EQUIP_2__ | __HVAC_CODE_2__ | __HVAC_PROTO_2__ | __HVAC_SAFETY_2__ | __HVAC_TIER_2__ | __HVAC_BUS_2__ |
| __HVAC_EQUIP_3__ | __HVAC_CODE_3__ | __HVAC_PROTO_3__ | __HVAC_SAFETY_3__ | __HVAC_TIER_3__ | __HVAC_BUS_3__ |
| __HVAC_EQUIP_4__ | __HVAC_CODE_4__ | __HVAC_PROTO_4__ | __HVAC_SAFETY_4__ | __HVAC_TIER_4__ | __HVAC_BUS_4__ |
| __HVAC_EQUIP_5__ | __HVAC_CODE_5__ | __HVAC_PROTO_5__ | __HVAC_SAFETY_5__ | __HVAC_TIER_5__ | __HVAC_BUS_5__ |

**Safety-Critical classification:**
- Chillers, boilers, heat pumps → **Safety-critical** (Tier 2 minimum, operator approval required)
- Fire dampers, smoke exhaust, emergency systems → **Life safety** (no Tier 3 auto-execute)
- AHUs, FCUs → **Standard** (Tier 3 auto-execute eligible)

### 2.2 Energy and Metering

| Meter | Code | Type | Location | SENTINEL Tracked |
|-------|------|------|----------|-----------------|
| Grid Import | __GRID_METER_CODE__ | __GRID_METER_TYPE__ | __GRID_METER_LOC__ | ✅ |
| Solar Generation | __SOLAR_CODE__ | __SOLAR_TYPE__ | __SOLAR_LOC__ | ✅ |
| BESS | __BESS_CODE__ | __BESS_TYPE__ | __BESS_LOC__ | ✅ |
| HVAC Sub-meter | __HVAC_SUBMETER_CODE__ | __HVAC_SUBMETER_TYPE__ | __HVAC_SUBMETER_LOC__ | ✅ / ❌ |
| Lighting Sub-meter | __LIGHTING_SUBMETER_CODE__ | __LIGHTING_SUBMETER_TYPE__ | __LIGHTING_SUBMETER_LOC__ | ✅ / ❌ |

### 2.3 Compliance-Critical Equipment

| Equipment | Code | Compliance Domain | CoC Required | Last Inspection | Next Inspection |
|-----------|------|------------------|--------------|-----------------|-----------------|
| __COMP_EQUIP_1__ | __COMP_CODE_1__ | __COMP_DOMAIN_1__ | __COMP_COC_1__ | __COMP_LAST_1__ | __COMP_NEXT_1__ |
| __COMP_EQUIP_2__ | __COMP_CODE_2__ | __COMP_DOMAIN_2__ | __COMP_COC_2__ | __COMP_LAST_2__ | __COMP_NEXT_2__ |
| __COMP_EQUIP_3__ | __COMP_CODE_3__ | __COMP_DOMAIN_3__ | __COMP_COC_3__ | __COMP_LAST_3__ | __COMP_NEXT_3__ |

---

## 3. LEU Determination

**Building type:** `__BUILDING_TYPE__`
**Estimated monthly consumption:** `__EST_MONTHLY_KWH__` kWh/month
**LEU threshold:** 400,000 kWh/month

| Scenario | Result | Required Action |
|----------|--------|----------------|
| Estimated consumption < 400,000 kWh/month | **NOT LEU** | No DoE registration required. Energy balance template on standby. |
| Estimated consumption > 400,000 kWh/month | **LEU** | Register with DoE within 30 days. Submit annual energy balance. Implement ISO 50001 EnMS. |
| Site expands or adds equipment | **Reassess** | Re-run LEU determination immediately. |

**LEU Status:** `__LEU_STATUS__` (__LEU_DATE__)
**If LEU:** DoE registration number: `__DOE_REG_NO__`

---

## 4. Green Star / EDGE Eligibility

**Building type:** `__BUILDING_TYPE__`
**Green Star eligible:** `__GS_ELIGIBLE__`
**EDGE eligible:** `__EDGE_ELIGIBLE__`
**Pathway:** `__GS_PATHWAY__` / `__EDGE_PATHWAY__`
**GBCSA registered professional:** `__GS_RP__`

| Credit Category | Applicable? | Notes |
|----------------|-------------|-------|
| Energy | __GS_ENERGY__ | Energy intensity target: __GS_ENERGY_TARGET__ kWh/m²/yr |
| Indoor Environment | __GS_IEQ__ | CO₂ monitoring: __GS_CO2__ ppm target |
| BMS / Fault Detection | __GS_BMS__ | SENTINEL active as BAS evidence |
| HVAC Commissioning | __GS_HVAC__ | Commissioning date: __GS_HVAC_DATE__ |
| Water | __GS_WATER__ | Water meter: __GS_WATER_METER__ |
| Materials | __GS_MATERIALS__ | Not tracked by SENTINEL |

**Estimated Green Star points (energy category):** `__GS_POINTS__`

---

## 5. SANS 10400-X Zone Type Map

Zone types for this site (based on `__BUILDING_TYPE__`):

| Zone Code | Zone Type | Min Outdoor Air (L/s/m²) | CO₂ Advisory | CO₂ Alert | ACH Min | SENTINEL Monitored |
|-----------|-----------|------------------------|-------------|-----------|---------|-------------------|
| __ZONE_CODE_1__ | __ZONE_TYPE_1__ | __ZONE_OA_1__ | __ZONE_CO2_ADV_1__ | __ZONE_CO2_ALERT_1__ | __ZONE_ACH_1__ | __ZONE_MON_1__ |
| __ZONE_CODE_2__ | __ZONE_TYPE_2__ | __ZONE_OA_2__ | __ZONE_CO2_ADV_2__ | __ZONE_CO2_ALERT_2__ | __ZONE_ACH_2__ | __ZONE_MON_2__ |
| __ZONE_CODE_3__ | __ZONE_TYPE_3__ | __ZONE_OA_3__ | __ZONE_CO2_ADV_3__ | __ZONE_CO2_ALERT_3__ | __ZONE_ACH_3__ | __ZONE_MON_3__ |
| __ZONE_CODE_4__ | __ZONE_TYPE_4__ | __ZONE_OA_4__ | __ZONE_CO2_ADV_4__ | __ZONE_CO2_ALERT_4__ | __ZONE_ACH_4__ | __ZONE_MON_4__ |
| __ZONE_CODE_5__ | __ZONE_TYPE_5__ | __ZONE_OA_5__ | __ZONE_CO2_ADV_5__ | __ZONE_CO2_ALERT_5__ | __ZONE_ACH_5__ | __ZONE_MON_5__ |
| __ZONE_CODE_6__ | __ZONE_TYPE_6__ | __ZONE_OA_6__ | __ZONE_CO2_ADV_6__ | __ZONE_CO2_ALERT_6__ | __ZONE_ACH_6__ | __ZONE_MON_6__ |

**Outdoor air damper BACnet points confirmed:** `__OA_DAMPER_POINTS__`
**BACnet point for outdoor air flow (if metered):** `__OA_FLOW_POINT__`

---

## 6. Compliance Domain Status

| Domain | Applicable? | Status | Last Record | Next Review | Notes |
|--------|-------------|--------|-------------|-------------|-------|
| OHS Act Checklist | __OHS_APPLICABLE__ | __OHS_STATUS__ | __OHS_LAST__ | __OHS_NEXT__ | __OHS_NOTES__ |
| Fire Safety (SANS 10400-T) | __FIRE_APPLICABLE__ | __FIRE_STATUS__ | __FIRE_LAST__ | __FIRE_NEXT__ | __FIRE_NOTES__ |
| Legionella Risk Management | __LEGIONELLA_APPLICABLE__ | __LEGIONELLA_STATUS__ | __LEGIONELLA_LAST__ | __LEGIONELLA_NEXT__ | __LEGIONELLA_NOTES__ |
| Electrical CoC (SANS 10142-1) | __ELEC_APPLICABLE__ | __ELEC_STATUS__ | __ELEC_LAST__ | __ELEC_NEXT__ | __ELEC_NOTES__ |
| Lift Safety Inspections | __LIFT_APPLICABLE__ | __LIFT_STATUS__ | __LIFT_LAST__ | __LIFT_NEXT__ | __LIFT_NOTES__ |
| Emergency Lighting (IEC 62034) | __EMLIGHT_APPLICABLE__ | __EMLIGHT_STATUS__ | __EMLIGHT_LAST__ | __EMLIGHT_NEXT__ | __EMLIGHT_NOTES__ |
| Ventilation CO₂ (SANS 10400-X) | __VENT_APPLICABLE__ | __VENT_STATUS__ | __VENT_LAST__ | __VENT_NEXT__ | __VENT_NOTES__ |
| Indoor Air Quality | __IAQ_APPLICABLE__ | __IAQ_STATUS__ | __IAQ_LAST__ | __IAQ_NEXT__ | __IAQ_NOTES__ |

---

## 7. Regulatory Obligations Matrix

| Regulation | Act/Standard | Obligation | Status | Evidence |
|-----------|-------------|-----------|--------|---------|
| POPIA | Act 4/2013 | DPR, retention, rights | ✅ Active | `popia-monitoring-stack-dpr.md` (entity-wide) |
| EU AI Act | Regulation 2024/1689 | Art. 4 literacy, Art. 72 monitoring | ⚠️ If EU data subjects | `eu-ai-act-compliance-register.md` |
| Cybercrimes Act | Act 19/2020 | Reasonable steps, 72h reporting | ✅ Active | `cybercrimes-act-response-procedure.md` |
| National Energy Act | Act 34/2008 | LEU reporting | __LEU_OBLIGATION__ | `energy-balance-export-template.md` |
| ISO 50001 | ISO standard | Voluntary EnMS | ⚠️ If LEU or Green Star | `iso-50001-energymanagement-system-procedure.md` |
| COIDA | Act 130/1943 | 7-day accident reporting | ✅ Active | `coida-accident-reporting-procedure.md` |
| SANS 10400-T | NBR | Fire safety | ✅ Active | `compliance-module.md` + this annex |
| SANS 10400-X | NBR | Ventilation | ✅ Active | Zone type map above + `sans-10400-x-ventilation-alert-procedure.md` |
| SANS 10142-1 | SANS | Electrical CoC | ✅ Active | `compliance-module.md` + this annex |
| Green Star | GBCSA | Certification | __GS_OBLIGATION__ | `green-star-bas-evidence-package.md` + this annex |
| EDGE | GBCSA/IFC | Certification | __EDGE_OBLIGATION__ | `green-star-bas-evidence-package.md` + SANS 961 model |

---

## 8. Site-Specific Compliance Risks

| Risk | Likelihood | Impact | Mitigation | Owner |
|------|------------|--------|------------|-------|
| __RISK_1__ | __RISK_1_LIK__ | __RISK_1_IMP__ | __RISK_1_MIT__ | __RISK_1_OWNER__ |
| __RISK_2__ | __RISK_2_LIK__ | __RISK_2_IMP__ | __RISK_2_MIT__ | __RISK_2_OWNER__ |
| __RISK_3__ | __RISK_3_LIK__ | __RISK_3_IMP__ | __RISK_3_MIT__ | __RISK_3_OWNER__ |

---

## 9. ML Gate Status

| Metric | Threshold | Current Value | Gate Status | ML Hours Tracked |
|--------|-----------|--------------|-------------|------------------|
| ML training gate | 72 hours | __ML_HOURS__ h | __ML_GATE_STATUS__ | `sentinel_ml_hours_ingested{site_id="__SITE_ID__"}` |

**Phase flip eligible:** `__PHASE_FLIP_ELIGIBLE__` (eligible / not yet eligible)
**Estimated gate clear date:** `__ML_GATE_CLEAR_DATE__`

---

## 10. Next Review

| Review | Date | Owner |
|--------|-------|-------|
| **Next formal review** | __NEXT_REVIEW_DATE__ | Compliance Lead |
| LEU re-assessment | __LEU_REASSESSMENT_DATE__ | Energy Lead |
| Electrical CoC renewal | __ELEC_COC_RENEWAL_DATE__ | Facilities |
| Lift inspection | __LIFT_INSPECTION_DATE__ | Facilities |
| Green Star / EDGE milestone | __GS_MILESTONE_DATE__ | AI Engineering Lead |

---

## 11. Commissioning Evidence Location

- **Building JSON:** `buildings/__SITE_ID__/building.json`
- **Mode policy:** `buildings/__SITE_ID__/__SITE_ID__-mode-policy-state.json`
- **Commissioning docs:** `/home/bederf/sentinel-vault/sites/__SITE_ID__/commissioning/`
- **Compliance annex:** `/home/bederf/sentinel-vault/sites/__SITE_ID__/compliance/`
- **Equipment register:** `/home/bederf/sentinel-vault/sites/__SITE_ID__/equipment-register/`

---

## 12. Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | __CREATED_DATE__ | SENTINEL Compliance Team | Initial site compliance annex for __SITE_ID__ |

### Approval

- **Compliance Lead:** ___________________ Date: ___________
- **Facilities Manager:** ___________________ Date: ___________
- **Managing Director:** ___________________ Date: ___________

---

*This document is a controlled record for site __SITE_ID__. Update when building configuration changes, new equipment is added, or compliance domain status changes.*