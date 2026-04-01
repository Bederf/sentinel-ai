---
title: "Training Evidence Filing Instructions"
type: "process"
status: "active"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Governance Team"
tags: ["ai-governance", "training", "evidence", "iso-42001"]
domain: "compliance"
---

# Training Evidence Filing Instructions

## 1. Purpose

This directory stores evidence of AI literacy training completion for ISO 42001 audit and EU AI Act Article 4 compliance purposes. Each in-scope individual must have a signed completion record filed here after completing their required training modules.

## 2. Directory Structure

```
docs/ai-governance/evidence/training/
  README.md                    -- This file (filing instructions)
  .gitkeep                     -- Preserves directory in version control
  {surname}-{firstname}.md     -- Individual completion records
```

### 2.1 File Naming Convention

Individual training records use the format: `{surname}-{firstname}.md` (lowercase, hyphenated).

Examples:
- `smith-john.md`
- `van-der-merwe-pieter.md`
- `chen-david.md`

## 3. Filing Process

1. **Complete training** -- The participant completes all required modules per the [`competence-training-register.md`](../../competence-training-register.md)
2. **Pass assessment** -- The assessor administers the knowledge check and records the score
3. **Complete sign-off** -- The assessor fills in the sign-off template from [`ai-literacy-training-package.md`](../../ai-literacy-training-package.md) Section 9
4. **File evidence** -- Create a markdown file in this directory using the template below
5. **Update register** -- Update the corresponding row in [`competence-training-register.md`](../../competence-training-register.md) Section 3

## 4. Individual Training Record Template

Create a new file using the naming convention above and populate it with this template:

```markdown
---
title: "Training Record -- {Full Name}"
type: "evidence"
status: "active"
created: "{date}"
role: "{role}"
---

# Training Record: {Full Name}

| Field | Value |
|-------|-------|
| **Name** | {Full Name} |
| **Role** | {Role Title} |
| **Date** | {Completion Date} |

## Modules Completed

| Module | Score | Result | Assessor |
|--------|-------|--------|----------|
| Module 1: AI System Fundamentals | {x}/5 | PASS/FAIL | {Assessor Name} |
| Module 2: Risk and Safety Controls | {x}/5 | PASS/FAIL | {Assessor Name} |
| Module 3: Approval Workflow | {x}/5 | PASS/FAIL | {Assessor Name} |
| Module 4: Privacy and Compliance | {x}/5 | PASS/FAIL | {Assessor Name} |

**Assessment Level:** Basic / Intermediate / Advanced
**Overall Result:** PASS / FAIL

## Assessor Sign-Off

| Field | Value |
|-------|-------|
| **Assessor Name** | {Name} |
| **Assessor Role** | {Role} |
| **Date** | {Date} |

## Next Refresh

| Field | Value |
|-------|-------|
| **Next refresh due** | {Date -- typically 12 months from completion} |
| **Trigger conditions** | Annual review, major system change, or post-incident retraining |

## Notes

{Any additional notes, accommodations, or observations}
```

## 5. Tracking and Audit

- The [`competence-training-register.md`](../../competence-training-register.md) is the master tracking document
- Individual files in this directory provide the detailed evidence backing each register entry
- During an audit, the auditor should be able to trace from the register to the individual evidence file and verify: modules completed, scores achieved, assessor identity, and completion date

## 6. Retention

Training evidence records are retained for a minimum of **5 years** from the date of completion, or for the duration of the individual's employment in an in-scope role, whichever is longer. This aligns with the ISO 42001 documented information retention requirement.

## 7. Confidentiality

Training records may contain personal information (names, roles, assessment scores). Handle in accordance with the SENTINEL data privacy policy (`docs/09-security/data-privacy-policy.md`). Access is restricted to the Compliance Officer, the individual's line manager, and authorised auditors.
