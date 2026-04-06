---
title: "Audit Log Evidence Samples"
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

# Audit Log Evidence Samples

**Collection date:** 2026-02-23
**Collector:** SENTINEL Governance Team
**Review cycle:** Quarterly (management review preparation)

## Audit Log System Overview

SENTINEL maintains a comprehensive audit log at `backend/app/data/audit_log.json`:

| Property | Value |
|----------|-------|
| Total entries | 1,000 records |
| Encryption | Fernet encryption at rest (AES-128-CBC) |
| Fields encrypted | user_id, device_id, point_name |
| Retention | Per data privacy policy (3 years minimum) |
| Last updated | 2026-02-23 |

## Sample Entry Structure

Each audit log entry contains:

```json
{
  "id": "UUID",
  "timestamp": "ISO 8601",
  "action": "device_control",
  "user_id": "[encrypted]",
  "device_id": "[encrypted]",
  "point_name": "[encrypted]",
  "old_value": "value",
  "new_value": "value",
  "result": "success|failure",
  "safety_validation": {
    "rules_checked": ["list"],
    "rules_passed": ["list"]
  },
  "correlation_id": "UUID",
  "metadata": {
    "source": "api|simulation|automated",
    "confidence": 0.0-1.0,
    "priority": "string"
  }
}
```

## Evidence Collection Notes

- Audit log implements encryption at rest per Phase 081 (Security Encryption Remediation)
- Safety validation rules are checked and logged for every device control action
- Correlation IDs enable end-to-end tracing across services
- Encryption key managed via `ENCRYPTION_KEY` environment variable (never committed)
- Full audit log source: `backend/app/data/audit_log.json`
- Audit service implementation: `backend/app/services/audit_service.py`

## Compliance Mapping

| Framework | Control | Evidence |
|-----------|---------|----------|
| ISO 42001 | A.6.2.6 (Monitoring) | Audit trail with encrypted PII |
| NIST AI RMF | MG 4.1 (Model lifecycle) | Decision audit for AI recommendations |
| EU AI Act | Article 50 (Transparency) | AI provenance metadata in audit entries |
| POPIA | Condition 7 (Security) | Encryption at rest for personal information |
