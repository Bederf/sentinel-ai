---
title: "Model and Data Governance"
type: "guide"
status: "active"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Governance Team"
tags: ["ai-governance", "model-card", "data-sheet", "change-control"]
domain: "compliance"
audience: "all"
complexity: "intermediate"
estimated_read_time: 11
---

# Model and Data Governance

## Purpose

Standardize how models, prompts, and data sources are governed from development to production.

## Required Artifacts

- Model card per model version
- Data sheet per dataset/document corpus
- Prompt/tool/retrieval change log
- Validation and rollback record per production change

## Model Cards

Model cards document each ML model's purpose, training data, limitations, safety controls, and deployment history.

**Template:** [`model-cards/MODEL-CARD-TEMPLATE.md`](model-cards/MODEL-CARD-TEMPLATE.md)

### Active Model Cards

| Model | Equipment Type | R-squared | Status | Card |
|-------|---------------|-----------|--------|------|
| Chiller Failure Prediction | CHILLER | 0.6065 | Active | [`model-cards/CHILLER.md`](model-cards/CHILLER.md) |
| AHU Degradation Prediction | AHU | 0.4915 | Active | [`model-cards/AHU.md`](model-cards/AHU.md) |
| FCU Health Assessment | FCU | 0.4236 | Active (advisory-only) | [`model-cards/FCU.md`](model-cards/FCU.md) |
| UPS Battery Degradation | UPS | 0.4144 | Active | [`model-cards/UPS.md`](model-cards/UPS.md) |
| Generator Failure Prediction | GENERATOR | 0.3710 | Active (elevated thresholds) | [`model-cards/GENERATOR.md`](model-cards/GENERATOR.md) |
| DALI Lighting Optimization | DALI | N/A | Placeholder | [`model-cards/DALI.md`](model-cards/DALI.md) |

### Model Card Minimum Fields

- Model name/version and owner
- Training data description and date range
- Intended use and out-of-scope use
- Evaluation metrics and thresholds
- Known failure modes and limitations
- Safety/compliance considerations
- Deployment history and rollback triggers

## Data Sheets

Data sheets document each governed dataset's source, quality, sensitivity, bias risks, and retention policies.

### Active Data Sheets

| Dataset | Source | PII | Sheet |
|---------|--------|-----|-------|
| Equipment Telemetry | BACnet/Modbus/DALI sensors | None | [`data-sheets/EQUIPMENT-TELEMETRY.md`](data-sheets/EQUIPMENT-TELEMETRY.md) |
| Work Order Outcomes | Work order system + technician feedback | Technician names/phones (encrypted) | [`data-sheets/WORK-ORDER-OUTCOMES.md`](data-sheets/WORK-ORDER-OUTCOMES.md) |
| RAG Knowledge Base | User-uploaded documents (PDF, DOCX, TXT) | None expected | [`data-sheets/RAG-KNOWLEDGE-BASE.md`](data-sheets/RAG-KNOWLEDGE-BASE.md) |

### Data Sheet Minimum Fields

- Data source and lawful basis
- Collection period and refresh cadence
- Data quality checks and missing-data policy
- Sensitive fields and redaction/retention controls
- Known bias/skew risks and mitigations

## Change Control Rules

- Every change to prompts, tools, models, and retrieval index requires:
- change ticket ID
- reviewer sign-off
- pre/post validation evidence
- rollback plan

## Evidence Paths

- Model cards: `docs/ai-governance/model-cards/`
- Data sheets: `docs/ai-governance/data-sheets/`
- Drift evidence: `docs/ai-governance/evidence/drift-reports/`
- Postmortems: `docs/ai-governance/evidence/rca-postmortems/`
