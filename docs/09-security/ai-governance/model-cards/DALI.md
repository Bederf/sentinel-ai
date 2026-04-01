---
title: "Model Card: DALI Lighting Optimization"
type: "model-card"
status: "placeholder"
version: "0.1.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Governance Team"
model_id: "dali-placeholder-v0.1"
equipment_type: "DALI"
r_squared: null
tier2_threshold: 0.70
tier3_threshold: 0.85
tags: ["ai-governance", "model-card", "dali", "lighting", "tridonic", "placeholder"]
domain: "compliance"
audience: ["developers", "data-scientists", "auditors"]
complexity: "intermediate"
---

# Model Card: DALI Lighting Optimization

## 1. Model Information

| Field | Value |
|-------|-------|
| **Model Name** | DALI Lighting Optimization |
| **Model ID** | `dali-placeholder-v0.1` |
| **Model Type** | Placeholder (awaiting sufficient training data) |
| **Equipment Type** | DALI |
| **Version** | 0.1 (placeholder) |
| **Owner** | SENTINEL Development Team |
| **Status** | Placeholder |
| **R-squared (avg)** | N/A (no trained model yet) |
| **Last Retrained** | N/A |

**IMPORTANT -- Tridonic-First Principle:** Native DALI-2 capabilities (via Tridonic controllers) handle daylight harvesting, occupancy dimming, and scene management natively. SENTINEL AI does NOT duplicate these capabilities. AI adds value only in cross-system coordination, predictive maintenance (lumDATA Part 251/253), energy reporting (Part 252), and tariff-aware scheduling. See `TRIDONIC_DALI_ARCHITECTURE.md` for full architecture.

## 2. Intended Use

**Primary use case (when trained):** Cross-system lighting optimization that coordinates DALI lighting with HVAC occupancy data, tariff schedules, and building-wide energy management.

**In-scope (future):**
- Cross-system coordination: Use HVAC occupancy data to pre-dim zones before vacancy
- Predictive maintenance: Tridonic lumDATA Part 251/253 for luminaire health trending
- Energy reporting: lumDATA Part 252 for per-fixture energy consumption tracking
- Tariff-aware scheduling: Shift non-essential lighting loads to off-peak periods
- 4 DALI instances across active sites

**Out-of-scope (Tridonic handles natively -- AI must NOT duplicate):**
- Daylight harvesting (Tridonic DALI-2 native capability)
- Occupancy-based dimming (Tridonic DALI-2 native capability)
- Scene management and group control (Tridonic DALI-2 native capability)
- Emergency lighting control (regulated, hardware-controlled)
- Individual fixture dimming curves (manufacturer-specific)

## 3. Training Data

| Field | Value |
|-------|-------|
| **Source** | Pending -- awaiting sufficient DALI telemetry from Tridonic lumDATA |
| **Collection Period** | N/A (placeholder) |
| **Volume** | Insufficient for model training |
| **Features** | Planned: luminaire hours, dimming profiles, power consumption, fault codes |
| **Refresh Cadence** | TBD |
| **Preprocessing** | TBD |

**Data collection plan:**
- lumDATA Part 251: Luminaire operating hours, start count, thermal stress events
- lumDATA Part 252: Energy measurement per fixture/group
- lumDATA Part 253: Diagnostic data, failure prediction inputs
- Minimum 180 days of data required before model training begins

**Data sheet reference:** `docs/ai-governance/data-sheets/EQUIPMENT-TELEMETRY.md`

## 4. Evaluation Metrics

| Metric | Value |
|--------|-------|
| **R-squared** | N/A (placeholder) |
| **All metrics** | Pending model training |

**Confidence thresholds (configured but not active):**

| Tier | Threshold | Action |
|------|-----------|--------|
| Tier 2 (Advisory) | 0.70 | Will recommend to operator when model is trained |
| Tier 3 (Auto-execute) | 0.85 | Will execute within safety bounds when model is trained |

**Current behavior:** With no trained model, thresholds are configured but produce no recommendations. The graceful degradation strategy applies: threshold effectively acts as 1.0 (impossible to meet), so the system falls back to rule-based lighting control.

## 5. Known Limitations

- **Placeholder model:** No trained model exists; all current DALI intelligence comes from Tridonic-native DALI-2 capabilities
- **Training data insufficient:** Fewer than 180 days of lumDATA telemetry collected
- **Tridonic dependency:** AI value-add is limited to areas Tridonic does not cover natively; if Tridonic capabilities expand, AI scope narrows further
- **Luminaire diversity:** Different luminaire types (LED drivers, fluorescent ballasts) have different degradation characteristics

**Failure modes (anticipated):**
- Over-dimming: AI recommends lower lighting levels than occupant comfort requires
- False maintenance alert: Normal end-of-life dimming misclassified as fault
- Tariff scheduling conflict: Dimming schedule conflicts with occupied hours

**Environmental sensitivity:**
- Southern hemisphere: North-facing windows receive most daylight (sun in north sky in SA)
- Brightness cap: 90% maximum to extend luminaire life and reduce glare
- Emergency lighting: Minimum maintained regardless of AI recommendations

## 6. Safety and Compliance

**Safety controls:**
- **Brightness capped at 90%** -- extends luminaire life, reduces glare, saves energy
- **Minimum emergency lighting maintained** at all times (regulatory requirement)
- **Tridonic-native safety:** DALI-2 emergency lighting is hardware-controlled, not AI-controlled
- AI recommendations cannot override Tridonic scene management or occupancy dimming

**SENTINEL mode discipline:**
- Currently inactive (placeholder model)
- When trained: Simulation/Shadow first, then supervised, then automatic per standard rollout
- Emergency lighting never under AI control (hardwired safety)

**Regulatory alignment:**
- NIST AI RMF: MS 2.5 (model documentation), MS 2.9 (model card)
- ISO 42001: A.6.2.6 (AI system documentation)
- POPIA: No PII in training data (lighting telemetry only)
- SANS 10114: Emergency lighting compliance maintained
- Tridonic DALI-2: IEC 62386 compliance (handled by Tridonic controllers)

## 7. Deployment History

| Date | Event | Notes |
|------|-------|-------|
| 2026-02-06 | Placeholder registered | v9.0 ML Predictive Maintenance: DALI slot reserved |
| 2026-02-10 | Registry migration | Phase 68-03: database entry with threshold=0.70/0.85 |

**Model activation criteria (must ALL be met before training begins):**
- 180+ days of lumDATA telemetry from at least 2 sites
- At least 10 luminaire fault events for supervised training
- Tridonic integration stable (no firmware-related data gaps)
- Governance review and approval per change control rules

**Rollback triggers (when model is activated):**
- Any safety boundary violation (brightness or emergency lighting)
- Occupant complaint rate increases after AI lighting changes
- R-squared below 0.30 (minimum for advisory recommendations)

## 8. Ethical Considerations

- No personal data used in training or inference
- Occupancy data from Tridonic sensors is aggregate (zone-level), not individual tracking
- Lighting quality affects occupant wellbeing and productivity -- model must prioritize comfort
- Energy savings balanced against visual comfort requirements
- Circadian rhythm considerations planned for future versions (color temperature adjustment)

---

*This model card follows the SENTINEL AI Governance Framework. For updates, contact the SENTINEL Development Team.*
