---
title: "Deepseek + GSD Prompt Pack (FSR Closure, Context-Safe)"
type: "policy"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-03-31"
tags: ["sentinel", "documentation"]
related: []
domain: "security"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# Deepseek + GSD Prompt Pack (FSR Closure, Context-Safe)

Use these prompts exactly as packetized runs. Do not combine packets in one session.

## Model Choice (Recommended)

If your current model keeps hitting context limits, switch to a model with a larger context window for document-heavy packets (`FSRQ-*`, `EP-*`).

- Prefer your larger-context model for mapping, questionnaire drafting, and evidence manifests.
- Keep smaller/faster models for narrow edits (`SIEM-*` and tracker-only updates).
- Always run one packet per fresh chat regardless of model.

## Global Guardrails (Prefix Every Prompt)

```text
You are executing one bounded packet. Hard limits:
1) Use only the listed input files.
2) Do not browse unrelated files.
3) Produce only the listed output artifact.
4) If blocked, write "BLOCKED" with exact blocker and stop.
5) Keep response concise and execution-focused.
6) Treat this packet as stateless: do not rely on prior chat history.
7) Max output 120 lines.
8) Stop immediately after writing the output artifact.
```

---

## Token-Safe Mode (Use In Every Packet)

Copy this block under the packet prompt:

```text
Token-safe mode:
- New chat only (no prior thread continuation).
- Read only listed inputs, once each.
- Do not quote large file content.
- Keep reasoning implicit; return only execution result.
- If task expands, return BLOCKED instead of broadening scope.
```

## Recovery Prompt (After Context Overflow)

```text
Recovery mode. Do not load prior conversation.
Read only:
1) docs/ai-governance/fsr-execution-tracker.md
2) <last artifact you wrote>

Task:
- Update tracker packet status and next action.
- Add one session log row.

Hard limits:
- Max 80 lines output.
- No additional reads.
- Stop after tracker update.
```

## Stream A: External Audit

### Packet EA-A — Shortlist + Criteria Matrix

**Inputs (max 5):**
- `docs/ai-governance/independent-audit-readiness-pack.md`
- `.planning/phases/68-fsr-external-compliance/VENDOR-RESEARCH-SUMMARY.md`
- `.planning/phases/68-fsr-external-compliance/RFQ-TEMPLATE.md`
- `.planning/phases/68-fsr-external-compliance/VENDOR-TRACKING.md`
- `docs/09-security/FSR_GAP_ANALYSIS_UPDATE.md`

**Output:**
- Update `.planning/phases/68-fsr-external-compliance/VENDOR-TRACKING.md` with top 3 candidates and scoring table.

**Prompt:**
```text
Execute packet EA-A.
Task: Build a ranked shortlist of 3 external audit firms using ISO 42001 + AI governance + SA regulatory fit criteria.
Write only to `.planning/phases/68-fsr-external-compliance/VENDOR-TRACKING.md`.
Add: scorecard table, justification per vendor, and recommendation.
If missing required vendor data, mark BLOCKED and list exact fields needed.
```

### Packet EA-B — RFQ Outreach Log

**Inputs:**
- `.planning/phases/68-fsr-external-compliance/VENDOR-TRACKING.md`
- `.planning/phases/68-fsr-external-compliance/RFQ-TEMPLATE.md`
- `.planning/phases/68-fsr-external-compliance/QUICK-START-RFQ-OUTREACH.md`
- `docs/ai-governance/independent-audit-readiness-pack.md`

**Output:**
- Update `.planning/phases/68-fsr-external-compliance/VENDOR-TRACKING.md` with outreach log section and response status.

**Prompt:**
```text
Execute packet EA-B.
Task: Add RFQ outreach log template and current status per shortlisted vendor.
Write only to `.planning/phases/68-fsr-external-compliance/VENDOR-TRACKING.md`.
Include: contact date, response SLA, status, next follow-up date, owner.
If contact details are missing, mark BLOCKED with exact missing fields.
```

### Packet EA-C — Selection Memo + Approval

**Inputs:**
- `.planning/phases/68-fsr-external-compliance/VENDOR-TRACKING.md`
- `docs/ai-governance/independent-audit-readiness-pack.md`
- `docs/09-security/FSR_GAP_ANALYSIS_UPDATE.md`
- `compliance.md`

**Output:**
- Update `docs/ai-governance/independent-audit-readiness-pack.md` with vendor selection decision note and approval checklist status.

**Prompt:**
```text
Execute packet EA-C.
Task: Add a concise "Selection Decision" section with preferred vendor, rationale, and approval checklist status.
Write only to `docs/ai-governance/independent-audit-readiness-pack.md`.
Do not fabricate approvals. If budget/signoff absent, keep as pending and clearly mark owner/action.
```

---

## Stream B: SIEM Closure

### Packet SIEM-A — Rule Verification Checklist

**Inputs:**
- `infrastructure/grafana/provisioning/alerting/security-alerts.yaml`
- `docs/10-operations/monitoring-stack.md`
- `TODO.md`
- `TODOdone.md`

**Output:**
- Update `docs/10-operations/monitoring-stack.md` with a "FSR SIEM Verification Checklist" section.

**Prompt:**
```text
Execute packet SIEM-A.
Task: Create a verification checklist mapping each security alert rule to validation steps and expected evidence.
Write only to `docs/10-operations/monitoring-stack.md`.
Checklist must be executable by ops without extra context.
```

### Packet SIEM-B — Alert-to-Response Mapping

**Inputs:**
- `infrastructure/grafana/provisioning/alerting/security-alerts.yaml`
- `docs/09-security/incident-response-process.md`
- `docs/09-security/incident-response-policy.md`

**Output:**
- Update `docs/09-security/incident-response-process.md` with alert-to-playbook mapping table (owner, SLA, escalation).

**Prompt:**
```text
Execute packet SIEM-B.
Task: Map each SIEM rule to concrete response runbook actions.
Write only to `docs/09-security/incident-response-process.md`.
Include: severity, owner role, initial response SLA, escalation path, closure evidence.
```

### Packet SIEM-C — Supabase Incident Logging Closure

**Inputs:**
- `backend/app/services/event_subscribers.py`
- `backend/app/security/audit_events.py`
- `backend/app/services/audit_logger.py`
- `docs/09-security/logging-architecture.md`

**Output (choose one):**
- Option 1: implement minimal persistence path in code, or
- Option 2: update `docs/09-security/logging-architecture.md` with approved defer decision and rationale.

**Prompt:**
```text
Execute packet SIEM-C.
Task: Close the "incident logging to Supabase" gap.
Prefer minimal implementation if low-risk and clear.
If implementation is ambiguous, do not guess: document defer decision with rationale, owner, and target date in `docs/09-security/logging-architecture.md`.
Touch the fewest files possible.
```

---

## Stream C: FSR Questionnaire

### Packet FSRQ-A — Control Mapping Index

**Inputs:**
- `docs/09-security/FSR_GAP_ANALYSIS_UPDATE.md`
- `docs/ai-governance/control-applicability-matrix.md`
- `docs/ai-governance/evidence/README.md`
- `compliance.md`

**Output:**
- Create or update `docs/ai-governance/fsr-questionnaire-control-mapping.md`.

**Prompt:**
```text
Execute packet FSRQ-A.
Task: Produce a control mapping index from FSR questionnaire themes to existing evidence artifacts.
Write only to `docs/ai-governance/fsr-questionnaire-control-mapping.md`.
Use explicit file paths and short evidence notes.
```




### Packet FSRQ-C — QA + Owner Assignment

**Inputs:**
- `docs/ai-governance/compliance-closure-report.md`
- `docs/ai-governance/fsr-questionnaire-control-mapping.md`
- `TODO.md`

**Output:**
- Update `docs/ai-governance/compliance-closure-report.md` to remove unresolved owner ambiguity and add final QA checklist.

**Prompt:**
```text
Execute packet FSRQ-C.
Task: Run consistency QA and resolve owner assignments in the draft answer section.
Write only to `docs/ai-governance/compliance-closure-report.md`.
Do not invent names; use role-based owners if named owners are unavailable.
```

---

## Stream D: Evidence Package Finalization

### Packet EP-A — Evidence Inventory Validation

**Inputs:**
- `docs/ai-governance/evidence/README.md`
- `docs/ai-governance/independent-audit-readiness-pack.md`
- `docs/09-security/FSR_GAP_ANALYSIS_UPDATE.md`

**Output:**
- Update `docs/ai-governance/evidence/README.md` with a validated manifest section (`present`, `stale`, `missing`).

**Prompt:**
```text
Execute packet EP-A.
Task: Normalize evidence inventory and classify artifacts as present/stale/missing.
Write only to `docs/ai-governance/evidence/README.md`.
Keep output audit-friendly and path-accurate.
```

### Packet EP-B — Submission Manifest

**Inputs:**
- `docs/ai-governance/evidence/README.md`
- `docs/ai-governance/independent-audit-readiness-pack.md`
- `docs/ai-governance/compliance-closure-report.md`

**Output:**
- Update `docs/ai-governance/independent-audit-readiness-pack.md` with a "Submission Manifest" section.

**Prompt:**
```text
Execute packet EP-B.
Task: Create final submission manifest grouped by governance, technical controls, and incident evidence.
Write only to `docs/ai-governance/independent-audit-readiness-pack.md`.
For each item include owner role and verification method.
```

### Packet EP-C — Final Readiness Memo

**Inputs:**
- `docs/ai-governance/independent-audit-readiness-pack.md`
- `docs/ai-governance/compliance-closure-report.md`
- `docs/09-security/FSR_GAP_ANALYSIS_UPDATE.md`
- `docs/ai-governance/fsr-execution-tracker.md`

**Output:**
- Update `docs/ai-governance/compliance-closure-report.md` with final go/no-go memo.

**Prompt:**
```text
Execute packet EP-C.
Task: Publish final readiness memo with go/no-go recommendation, residual risks, and critical blockers.
Write only to `docs/ai-governance/compliance-closure-report.md`.
Recommendation must align with tracker status.
```

---

## After Each Packet (Required)

Use this short update prompt:

```text
Update `docs/ai-governance/fsr-execution-tracker.md`:
1) set packet status,
2) add evidence path,
3) set next action,
4) add one row to Session Log.
Do not modify any other file.
```
