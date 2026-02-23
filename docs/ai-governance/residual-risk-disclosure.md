---
title: "Residual Risk Disclosure for Operators"
type: "disclosure"
status: "active"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Governance Team"
tags: ["ai-governance", "residual-risk", "nist-ai-rmf", "operators", "safety"]
domain: "compliance"
audience: "operators"
complexity: "basic"
estimated_read_time: 10
nist_reference: "MS 2.6"
---

# Residual Risk Disclosure for Operators

## Purpose

This document is written for **operations staff and facility managers** who work with the SENTINEL BMS Intelligence Platform. It explains, in plain language, what residual risks remain after all safety controls and quality gates have been applied. Understanding these risks helps you make informed decisions when acting on SENTINEL recommendations.

**Who should read this:** Building operators, facility managers, site engineers, and anyone who reviews or acts on SENTINEL AI recommendations.

---

## 1. What SENTINEL Can Do Autonomously

### 1.1 Tier 1: Advisory Recommendations (No System Changes)

SENTINEL continuously analyses building telemetry data and generates advisory recommendations. These are **informational only** -- SENTINEL does not make any changes to building systems at this tier.

Examples:
- "Consider reducing chiller staging during low-occupancy hours to save energy"
- "AHU-201 fan belt may need replacement within 30 days"
- "Zone 105 temperature trending 2 degrees C above setpoint"

**Your role:** Review the recommendation, decide whether to act on it, and execute any changes manually through your BMS console.

### 1.2 Tier 2: Operator-Approved Actions

SENTINEL proposes specific setpoint changes or scheduling adjustments, but **requires your explicit approval** before any change is made. You will see the proposed change, its expected impact, and the confidence level.

Examples:
- "Reduce chilled water supply temperature from 7 degrees C to 6.5 degrees C (estimated 3% energy saving)"
- "Shift AHU start time from 06:00 to 06:30 based on occupancy patterns"

**Your role:** Review the proposal, approve or reject it. If approved, SENTINEL executes the change through the BMS.

### 1.3 Tier 3: Auto-Execute (When Approved by Site Policy)

When a site has enabled automatic execution mode, SENTINEL can autonomously adjust setpoints **within strict safety boundaries**. This mode is only active when:
- The site administrator has explicitly enabled it
- Quality gate checks pass (14 metrics must be within acceptable ranges)
- The proposed change falls within safety limits

### 1.4 What Safety Interlocks Prevent

Regardless of the tier, SENTINEL's Safety Engine enforces hard boundaries that **cannot be overridden by AI**:

| Parameter | Safety Boundary | Why |
|-----------|----------------|-----|
| Zone temperature | 16--28 degrees C | Occupant comfort and health |
| Chilled water supply | 5--12 degrees C | Freeze protection and cooling capacity |
| System pressure | Equipment-specific limits | Equipment protection |
| Conflicting commands | Blocked automatically | Prevents simultaneous heat/cool |
| Equipment runtime | Minimum run/rest cycles | Anti-short-cycling protection |

If the AI ever recommends a value outside these boundaries, the Safety Engine rejects the command before it reaches the equipment. No exception is possible.

---

## 2. Residual Risks

Even with all controls in place, the following risks remain. These are risks that have been reduced to an acceptable level but cannot be fully eliminated.

### R-001: Model Accuracy Degrades in Unseen Conditions

| Attribute | Detail |
|-----------|--------|
| **Description** | SENTINEL's ML models were trained on historical data from specific buildings, climates, and operating conditions. If conditions change significantly (unusual weather events, major occupancy changes, new equipment installations), the models may produce less accurate predictions. |
| **Likelihood** | Medium |
| **Impact** | Medium -- Recommendations may be suboptimal (higher energy use, less accurate failure predictions), but safety boundaries prevent dangerous outcomes. |
| **Existing Controls** | Quality gate evaluation (14 metrics); model drift monitoring with automated alerts; daily staleness checks with automatic retraining; confidence scoring displayed on all recommendations. |
| **Residual Level** | Low |
| **Acceptance Status** | Accepted -- Drift monitoring and automatic retraining reduce window of degraded accuracy. Safety interlocks prevent harmful actions regardless of model accuracy. |

### R-002: Sensor Failure Leads to Incorrect Predictions

| Attribute | Detail |
|-----------|--------|
| **Description** | If a temperature sensor, pressure transducer, or other field device fails or drifts out of calibration, SENTINEL may base recommendations on incorrect data. A stuck sensor reading "22 degrees C" when the actual temperature is 30 degrees C could lead to under-cooling. |
| **Likelihood** | Medium |
| **Impact** | High -- Incorrect sensor data can lead to wrong setpoint recommendations, potentially affecting occupant comfort until detected. |
| **Existing Controls** | Data quality service with gap detection and anomaly flagging; sensor range validation (values outside physical limits are rejected); confidence scoring is penalised when default sensor values are used; health data quality gate with freshness checks. |
| **Residual Level** | Medium |
| **Acceptance Status** | Accepted with monitoring -- Operators should verify sensor readings during routine inspections. SENTINEL flags sensors with stale or anomalous data, but physical sensor failure requires manual verification. |

### R-003: Cascading Recommendations Amplify Errors

| Attribute | Detail |
|-----------|--------|
| **Description** | Multiple AI recommendations acting on interconnected systems (e.g., reducing chiller output while increasing AHU airflow) could compound to create an undesirable state. One suboptimal recommendation feeding into another could amplify the effect. |
| **Likelihood** | Low |
| **Impact** | Medium -- Temporary comfort deviation or increased energy use until corrected. Safety boundaries prevent equipment damage. |
| **Existing Controls** | Rate limiting on recommendation execution; 1-hour cooldown between autonomous actions on the same equipment; quality gate suppresses Tier 3 actions when metrics are degraded; cascade detection in lifecycle orchestrator. |
| **Residual Level** | Low |
| **Acceptance Status** | Accepted -- Rate limiting and cooldown periods prevent rapid cascading. Operators can intervene at any time. |

### R-004: Third-Party AI Model Changes Behaviour

| Attribute | Detail |
|-----------|--------|
| **Description** | SENTINEL uses the Anthropic Claude API for natural-language analysis and explanations. If Anthropic updates their model version, the quality or behaviour of AI-generated explanations, chat responses, or analysis summaries could change without notice. |
| **Likelihood** | Low |
| **Impact** | Low-to-Medium -- Chat responses or explanation quality may degrade. No direct impact on setpoint control (which uses SENTINEL's own ML models, not Claude). |
| **Existing Controls** | Model version pinning in API configuration; shadow testing of new model versions for 7 days before promotion; Ollama local fallback if Claude API is unavailable; safety interlocks validate all setpoints independently of LLM output. |
| **Residual Level** | Low |
| **Acceptance Status** | Accepted -- LLM output does not drive equipment control decisions. Version pinning and shadow testing reduce surprise. See [Third-Party AI Risk Register](third-party-ai-risk-register.md). |

### R-005: Operator Over-Reliance on AI Recommendations

| Attribute | Detail |
|-----------|--------|
| **Description** | Over time, operators may develop excessive trust in AI recommendations and reduce their own critical assessment. This could lead to accepting recommendations without proper review, especially during busy periods. |
| **Likelihood** | Medium |
| **Impact** | Medium -- If operators stop questioning AI output, suboptimal recommendations may be executed more frequently. Combined with R-001 or R-002, this could amplify impacts. |
| **Existing Controls** | Confidence scores displayed on all recommendations; "AI-generated" disclosure labels on AI output; operator training programme emphasising critical review; Tier 2 approval workflow requires active decision (not auto-approve). |
| **Residual Level** | Medium |
| **Acceptance Status** | Accepted with training -- Regular operator training reinforces that AI is a decision-support tool, not a replacement for engineering judgment. Confidence scores encourage critical review. |

---

## 3. Risk Summary Matrix

| Risk ID | Risk | Likelihood | Impact | Residual Level | Status |
|---------|------|-----------|--------|----------------|--------|
| R-001 | Model accuracy degradation | Medium | Medium | Low | Accepted |
| R-002 | Sensor failure | Medium | High | Medium | Accepted with monitoring |
| R-003 | Cascading recommendations | Low | Medium | Low | Accepted |
| R-004 | Third-party AI changes | Low | Low-to-Medium | Low | Accepted |
| R-005 | Operator over-reliance | Medium | Medium | Medium | Accepted with training |

---

## 4. How to Override or Escalate

If you believe SENTINEL is producing incorrect or unsafe recommendations, you have three levels of override available at all times.

### 4.1 Equipment Kill Switch

**What it does:** Immediately disables all AI recommendations and autonomous actions for a single piece of equipment.

**How to activate:**
1. Navigate to the equipment detail page in the SENTINEL dashboard
2. Click the "Disable AI" toggle
3. Confirm the action

**Effect:** The equipment continues to operate under its local BMS controller (Desigo, CAREL, etc.) without any SENTINEL influence. Manual override is immediate.

### 4.2 Site Kill Switch

**What it does:** Disables all AI recommendations and autonomous actions for an entire site.

**How to activate:**
1. Navigate to Site Settings in the SENTINEL dashboard
2. Click "Disable AI for Site"
3. Confirm the action

**Effect:** All equipment at the site reverts to local BMS control. No SENTINEL recommendations are generated or executed until re-enabled.

### 4.3 Global Kill Switch

**What it does:** Disables all SENTINEL AI operations across all sites.

**How to activate:**
1. Contact the Operations Lead or AI Engineering Lead
2. The global kill switch is activated via the administration console or emergency stop endpoint

**Effect:** Complete cessation of all AI activity. All sites revert to local BMS control.

### 4.4 Escalation Chain

If you are unsure whether to override, or if you observe unexpected AI behaviour, escalate through this chain:

| Step | Contact | When to Contact |
|------|---------|-----------------|
| 1 | **Operations Lead** | First point of contact for any concern about AI recommendations |
| 2 | **AI Engineering Lead** | If the Operations Lead needs technical investigation |
| 3 | **Architecture Board** | If the issue requires a policy or design change |

**Emergency contact:** For situations where occupant safety is at immediate risk, activate the equipment or site kill switch first, then contact the Operations Lead.

---

## 5. Acknowledgment Form

By signing below, I confirm that I have read and understood this Residual Risk Disclosure document. I understand:

- What SENTINEL can and cannot do autonomously
- The residual risks that remain after controls are applied
- How to override or disable AI actions at the equipment, site, or global level
- The escalation chain for reporting concerns

| Field | Value |
|-------|-------|
| **Operator Name** | _________________________________ |
| **Role / Title** | _________________________________ |
| **Site** | _________________________________ |
| **Date** | ____-____-____ |
| **Signature** | _________________________________ |

---

## 6. Cross-References

| Document | Purpose |
|----------|---------|
| [AI Risk Classification Register](01-risk-classification.md) | Per-feature risk tiers (EU AI Act) |
| [Control Applicability Matrix](control-applicability-matrix.md) | Unified control mapping (ISO 42001, NIST AI RMF, EU AI Act) |
| [Safety Interlocks Engine](../06-safety-compliance/safety-interlocks-engine.md) | Safety boundary rules and enforcement |
| [Write Policy and Rollout](../08-ai-ml/write-policy-and-rollout.md) | Mode discipline and kill switch procedures |
| [Third-Party AI Risk Register](third-party-ai-risk-register.md) | Vendor-specific AI risks (Anthropic, Ollama) |
| [Retraining Policy](retraining-policy.md) | Model retraining cadence and governance |
| [Incident Response Process](../09-security/incident-response-process.md) | Incident handling procedures |

---

## 7. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2026-02-23 | SENTINEL Governance Team | Initial residual risk disclosure with 5 risks, override procedures, and acknowledgment form |

---

*This document satisfies NIST AI RMF MS 2.6 (residual risk communication). It is reviewed annually or when significant changes are made to SENTINEL's AI capabilities.*
