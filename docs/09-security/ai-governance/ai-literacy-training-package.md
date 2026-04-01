---
title: "AI Literacy Training Package"
type: "training"
status: "active"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Governance Team"
tags: ["ai-governance", "training", "eu-ai-act", "article-4", "literacy", "iso-42001"]
domain: "compliance"
audience: "all"
complexity: "intermediate"
estimated_read_time: 18
---

# AI Literacy Training Package

## 1. Purpose

Article 4 of the EU AI Act (Regulation (EU) 2024/1689) requires providers and deployers of AI systems to take measures to ensure, to the best extent possible, a sufficient level of AI literacy of their staff and other persons dealing with the operation and use of AI systems on their behalf.

This training package defines what each SENTINEL role needs to know about AI systems, how to interact with them safely, and how to meet their compliance obligations. Completion of the relevant modules constitutes the organisation's primary evidence of Article 4 compliance.

### 1.1 Relationship to Other Documents

| Document | Relationship |
|----------|-------------|
| [`ai-management-policy.md`](ai-management-policy.md) | Overarching AI governance policy (this training implements its training requirement) |
| [`01-risk-classification.md`](01-risk-classification.md) | Risk tiers referenced in Module 2 |
| [`06-human-oversight-and-approval.md`](06-human-oversight-and-approval.md) | Approval workflow referenced in Module 3 |
| [`competence-training-register.md`](competence-training-register.md) | Tracks completion of this training |
| [`control-applicability-matrix.md`](control-applicability-matrix.md) | Maps this package to ISO 42001 A.6.3 and NIST GV-3.1 |

---

## 2. Module 1: AI System Fundamentals

**Target audience:** All roles (AI Engineering Lead, Operations Lead, Facility Manager, Technician, Compliance Officer, Security Lead)

### 2.1 What SENTINEL AI Does

SENTINEL BMS Intelligence uses AI and machine learning to support building management operations across three core capabilities:

1. **Predictive Maintenance** -- Analyses equipment telemetry (temperatures, pressures, vibrations, runtimes) to predict failures before they occur. Models are trained per equipment type (AHU, Chiller, FCU, UPS, Generator, DALI).

2. **Optimization Recommendations** -- Generates energy-saving and comfort-balancing recommendations based on equipment state, weather, occupancy, and building physics. Recommendations include confidence scores and expected savings.

3. **Anomaly Detection** -- Identifies unusual sensor readings, operational patterns, or performance deviations that warrant investigation.

### 2.2 How AI Decisions Are Made

Every AI recommendation passes through a structured pipeline before any action is taken:

```
Data Collection --> Model Inference --> Quality Gate Evaluation --> Tier Routing --> Approval (if required) --> Execution --> Monitoring
```

- **Quality Gates** evaluate 14 metrics across data quality, model health, and operational safety. If gates fail, recommendations are suppressed or confidence is capped.
- **Tier Routing** assigns each recommendation to a tier based on confidence, risk level, and equipment criticality.
- **Approval** is required for Tier 2 recommendations. Tier 1 is advisory only. Tier 3 autonomous execution operates within pre-approved guardrails.

### 2.3 Mode Discipline

All SENTINEL AI features follow a strict deployment progression:

| Mode | Description | AI Authority |
|------|-------------|-------------|
| **Simulation** | Pipeline runs against simulated data. No real device interaction. | No authority -- testing only |
| **Shadow Live** | Pipeline runs against live data. No device writes. Outputs logged for comparison. | No authority -- observation only |
| **Supervised** | Recommendations presented to operators for manual approval before execution. | Recommends -- human decides |
| **Automatic (live_control)** | Approved tiers execute within quality gates and safety rules. | Bounded execution within guardrails |

No AI feature may skip a mode. Progression requires meeting entry criteria documented in [`live-control-entry-criteria.md`](live-control-entry-criteria.md).

### 2.4 Key Concept: AI Advises, Humans Decide

SENTINEL AI operates on an advisory-first principle:

- **Tier 1 (Advisory):** AI provides information. No execution authority. No approval required.
- **Tier 2 (Approval Required):** AI recommends an action. A qualified operator must approve before execution occurs.
- **Tier 3 (Controlled Autonomous):** AI executes within pre-approved guardrails, with post-action review and rollback readiness.

In all cases, humans retain the ability to override, reject, or disable AI recommendations at any time through the kill switch hierarchy (equipment-level, site-level, global).

### 2.5 Module 1 -- Knowledge Check

1. Name the three core AI capabilities SENTINEL provides.
2. What is the role of quality gates in the AI decision pipeline?
3. List the four deployment modes in order. Why can a mode not be skipped?
4. In which tier(s) does a human operator need to approve recommendations before execution?
5. What is the kill switch hierarchy and when would you use it?

---

## 3. Module 2: Risk and Safety Controls

**Target audience:** Operations Leads, Facility Managers, Technicians

### 3.1 Risk Classification Tiers

Every SENTINEL AI feature is classified according to the EU AI Act risk framework:

| Risk Level | What It Means | SENTINEL Controls |
|-----------|--------------|-------------------|
| **High Risk** | Feature involves autonomous actuation of building systems with potential safety implications | Full conformity assessment, mandatory quality gates, human approval, post-market monitoring |
| **Limited Risk** | Feature generates content or recommendations that users interact with | AI disclosure labels, transparency documentation |
| **Minimal Risk** | Feature provides analytical insights with no direct operational impact | Standard development practices, voluntary safeguards |

The complete per-feature classification is recorded in [`01-risk-classification.md`](01-risk-classification.md).

### 3.2 Safety Interlocks

Safety interlocks are automated rules that prevent AI recommendations from causing harm:

- **Temperature limits** -- Prevent setpoints outside safe operating ranges
- **Pressure boundaries** -- Block commands that would exceed equipment pressure ratings
- **Runtime guards** -- Prevent equipment from running beyond safe continuous operation windows
- **Cascade protection** -- Prevent cascading failures when multiple systems are affected
- **Rate limiting** -- Prevent rapid successive changes that could stress equipment
- **Emergency shutdown** -- Trigger immediate equipment stop when critical thresholds are breached

Safety interlocks operate independently of AI and cannot be overridden by AI recommendations. They are documented in `docs/06-safety-compliance/safety-interlocks-engine.md`.

### 3.3 Quality Gate Enforcement

The quality gate evaluator assesses 14 metrics before any recommendation proceeds:

- If a metric **fails** in `live_control` mode, the recommendation is blocked entirely (fail-closed behaviour)
- If a metric **warns**, Tier 3 autonomous actions are suppressed; Tier 1-2 may proceed with capped confidence
- Enforcement actions: `NORMAL`, `CAP_CONFIDENCE`, `SUPPRESS_TIER3`, `BLOCK_WRITES`

### 3.4 Kill Switch Hierarchy

SENTINEL provides a three-level kill switch for immediate AI disengagement:

1. **Equipment-level** -- Disables AI recommendations for a single piece of equipment
2. **Site-level** -- Disables all AI recommendations for an entire site
3. **Global** -- Disables all AI recommendations across all sites

Any authorised operator can activate a kill switch without prior approval. Activation is logged in the audit trail.

### 3.5 What to Do If You Disagree with an AI Recommendation

If you believe an AI recommendation is incorrect, unsafe, or inappropriate:

1. **Do not approve it.** Reject the recommendation with a reason code.
2. **Report it.** Log the issue through the incident reporting process (see Module 4).
3. **Use the kill switch** if you believe the system is generating unsafe recommendations.
4. **Document your concern.** Your feedback improves future model performance through the ML feedback loop.

Your professional judgement always takes precedence over AI recommendations.

### 3.6 Module 2 -- Knowledge Check

1. What is the difference between a High Risk and Limited Risk AI feature?
2. Name three types of safety interlocks that protect against unsafe AI actions.
3. What happens when a quality gate metric fails in `live_control` mode?
4. Who can activate a kill switch, and is prior approval required?
5. What should you do if you disagree with an AI recommendation?

---

## 4. Module 3: Approval Workflow

**Target audience:** Operations Leads, Facility Managers

### 4.1 When and Why Approval Is Required

Approval is required for all **Tier 2** recommendations -- those where AI has sufficient confidence to recommend a specific action, but the action's impact warrants human review before execution.

Situations requiring approval include:

- Setpoint changes to HVAC systems affecting occupied zones
- Equipment staging changes (e.g., chiller sequencing)
- Load-shedding recommendations during peak tariff periods
- Any recommendation classified as HIGH or CRITICAL risk

Tier 1 (advisory) recommendations do not require approval -- they are informational only. Tier 3 (autonomous) recommendations operate within pre-approved guardrails and are reviewed post-execution.

### 4.2 How to Evaluate Recommendation Confidence Scores

Each recommendation includes a confidence score (0.0 to 1.0):

| Score Range | Interpretation | Recommended Action |
|------------|---------------|-------------------|
| **0.80 -- 1.00** | High confidence. Model has strong supporting evidence. | Review and approve if operationally appropriate |
| **0.60 -- 0.79** | Moderate confidence. Some uncertainty in inputs or conditions. | Review carefully, consider requesting additional context |
| **0.40 -- 0.59** | Low confidence. Significant uncertainty. Quality gates may cap at this level. | Proceed with caution; verify conditions independently |
| **Below 0.40** | Very low confidence. Recommendation may be suppressed by quality gates. | Generally should not reach approval queue |

Confidence is affected by data freshness, sensor coverage, model drift status, and feedback loop health.

### 4.3 How to Approve, Reject, or Request More Information

When a recommendation appears in the approval queue:

- **Approve** -- Confirms you have reviewed the recommendation and authorise execution. Your identity, role, and timestamp are recorded.
- **Reject** -- Declines execution. You must provide a reason code. The rejection is logged and feeds back into the ML training pipeline.
- **Request More Information** -- Defers the decision. The recommendation remains in the queue with a flag for the AI Engineering team to provide additional context.

### 4.4 What Happens After Approval

Once approved, the following sequence occurs:

1. **Safety validation** -- The Safety Interlocks Engine verifies the action is within safe bounds
2. **Execution** -- The command is sent to the BMS controller (setpoint or staging change)
3. **Monitoring** -- The system monitors the actual outcome against the predicted outcome
4. **Outcome capture** -- Actual vs. predicted performance is logged for model improvement
5. **Rollback readiness** -- If the outcome deviates beyond defined thresholds, the system can revert to the previous state

### 4.5 Module 3 -- Knowledge Check

1. Which recommendation tier requires human approval before execution?
2. What does a confidence score of 0.65 indicate about a recommendation?
3. What are the three actions available when a recommendation appears in the approval queue?
4. What happens immediately after you approve a recommendation (before the command is sent)?
5. Under what conditions might an approved action be rolled back?

---

## 5. Module 4: Privacy and Compliance

**Target audience:** All roles

### 5.1 POPIA Obligations

SENTINEL processes data under the Protection of Personal Information Act (POPIA). Key obligations for all staff:

- **Data minimisation** -- Only collect data necessary for building management purposes
- **Purpose limitation** -- Use collected data only for its stated purpose (equipment monitoring, energy optimisation, maintenance planning)
- **Storage limitation** -- Data retention follows defined schedules (see `docs/09-security/data-privacy-policy.md`)
- **Security safeguards** -- All data at rest is encrypted; access is role-based
- **Breach notification** -- Report suspected data breaches immediately to the Security Lead

Personal information categories handled by SENTINEL include: technician contact details, user login records, approval audit trails, and work order assignments. Equipment telemetry is not personal information.

### 5.2 AI Transparency

The EU AI Act requires that users interacting with AI systems are informed when AI is involved:

- **AI-generated labels** -- All AI-generated recommendations, predictions, and analyses are labelled as AI-generated in the user interface
- **Provenance tracking** -- Each AI output includes metadata identifying the model, version, and input data used
- **Explainability** -- Recommendations include a reasoning chain explaining why the action was suggested and what evidence supports it

Staff must not remove, obscure, or misrepresent AI-generated labels.

### 5.3 Incident Reporting

AI-related incidents must be reported when:

- An AI recommendation causes or could have caused equipment damage, safety risk, or significant energy waste
- The AI system produces outputs that appear biased, discriminatory, or systematically incorrect
- A data breach involves AI training data or model artifacts
- The quality gate or safety interlock system fails to prevent an unsafe action

**How to report:** Use the standard incident reporting process. Tag the incident as "AI-related" and include the recommendation ID, affected equipment, and your assessment of the impact.

Reference: [`07-incident-and-rollback.md`](07-incident-and-rollback.md) for the full incident handling procedure.

### 5.4 Record-Keeping Responsibilities

All roles share responsibility for maintaining audit trail integrity:

- **Do not** delete, modify, or backdate audit log entries
- **Do** provide accurate reason codes when rejecting recommendations
- **Do** complete training sign-offs honestly and on time
- **Do** report gaps in record-keeping (missing logs, incomplete trails) to the Compliance Officer

### 5.5 Module 4 -- Knowledge Check

1. Name three POPIA obligations relevant to SENTINEL operations.
2. What must all AI-generated outputs include according to transparency requirements?
3. List two scenarios that would trigger an AI-related incident report.
4. What information should be included when reporting an AI incident?
5. What should you do if you notice a gap in the audit trail?

---

## 6. Assessment Criteria

### 6.1 Scoring

Each module is assessed via the knowledge check questions in sections 2.5, 3.6, 4.5, and 5.5. Assessment is pass/fail:

| Level | Passing Threshold | Applied To |
|-------|-------------------|-----------|
| **Basic** | 3 out of 5 correct per module | Technicians |
| **Intermediate** | 4 out of 5 correct per module | Operations Leads, Facility Managers, Security Leads |
| **Advanced** | 5 out of 5 correct per module | AI Engineering Lead, Compliance Officer |

### 6.2 Re-assessment

If a participant does not pass on first attempt:

1. Review the relevant module material
2. Re-attempt the knowledge check after a minimum 24-hour study period
3. If the second attempt fails, schedule a 1:1 walkthrough with the AI Engineering Lead or Compliance Officer
4. Document all attempts in the [`competence-training-register.md`](competence-training-register.md)

---

## 7. Delivery Method

Training is delivered as **self-paced document review** followed by a **knowledge check sign-off**:

1. **Self-study** -- Participant reads the relevant modules in this document
2. **Knowledge check** -- Participant answers the module knowledge check questions (written or verbal)
3. **Assessment** -- Assessor grades responses against the scoring criteria in Section 6
4. **Sign-off** -- Assessor records completion in the competence register

Estimated time per module:

| Module | Estimated Time |
|--------|---------------|
| Module 1: AI System Fundamentals | 25 minutes |
| Module 2: Risk and Safety Controls | 30 minutes |
| Module 3: Approval Workflow | 20 minutes |
| Module 4: Privacy and Compliance | 20 minutes |

---

## 8. Refresh Cadence

| Trigger | Action |
|---------|--------|
| **Annual review** | All in-scope personnel complete a refresher assessment once per calendar year |
| **Major system change** | When AI features are added, modified, or re-classified, affected modules are updated and personnel re-assessed within 30 days |
| **Regulatory update** | When EU AI Act obligations or POPIA requirements change, Module 4 is updated and re-delivered within 60 days |
| **Post-incident** | If a training gap is identified as a contributing factor in an AI incident, targeted re-training is scheduled within 14 days |

The Compliance Officer is responsible for monitoring refresh triggers and scheduling re-assessments.

---

## 9. Sign-Off Template

Use this template to record individual training completion. Filed copies are stored in `docs/ai-governance/evidence/training/`.

```
-----------------------------------------------------------------
AI LITERACY TRAINING -- COMPLETION RECORD
-----------------------------------------------------------------

Participant Name:    ___________________________________
Role:                ___________________________________
Date:                ___________________________________

Modules Completed:
  [ ] Module 1: AI System Fundamentals
  [ ] Module 2: Risk and Safety Controls
  [ ] Module 3: Approval Workflow
  [ ] Module 4: Privacy and Compliance

Assessment Level:    [ ] Basic  [ ] Intermediate  [ ] Advanced
Assessment Score:    _____ / _____ per module
Overall Result:      [ ] PASS  [ ] FAIL

Assessor Name:       ___________________________________
Assessor Role:       ___________________________________
Assessor Signature:  ___________________________________

Next Refresh Due:    ___________________________________

Notes:
_______________________________________________________________
_______________________________________________________________
-----------------------------------------------------------------
```

---

## 10. Document Control

| Field | Value |
|-------|-------|
| **Document owner** | Compliance Officer |
| **Review cycle** | Annual or on material change |
| **Approval authority** | AI Engineering Lead + Compliance Lead |
| **Distribution** | All in-scope SENTINEL personnel |
| **Classification** | Internal |
