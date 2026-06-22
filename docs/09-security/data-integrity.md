---
title: "Data Integrity"
type: "policy"
status: "approved"
version: "1.0.0"
created: "2026-06-14"
updated: "2026-06-14"
author: "SENTINEL Security Team"
tags: ["security", "audit", "integrity", "encryption", "compliance"]
domain: "security"
audience: "all"
complexity: "intermediate"
estimated_read_time: 6
---

# Data Integrity

## Guarantee

> **Every control action, safety validation, AI decision, and authentication event is
> recorded in an append-only, encrypted audit trail. No update or delete endpoint is
> exposed for audit records.**

---

## Audit Trail Architecture

SENTINEL maintains two complementary audit stores that together cover every write to
physical equipment:

| Store | What it captures | Location |
|-------|-----------------|----------|
| Event audit log | Individual events: control writes, safety validations, rollbacks, auth attempts | `audit_log.json` + `login_audit` Supabase table |
| Decision audit (`parasite_decisions`) | Full lifecycle of autonomous Tier 3 decisions: routing → execution → COV verification → outcome → rollback | `parasite_decisions` Supabase table |

The two stores are complementary: the event log is fine-grained (one row per event);
the decision table is lifecycle-grained (one row per recommendation, updated as it
progresses through states).

---

## Encryption at Rest

Sensitive fields in audit log entries are encrypted using **Fernet symmetric encryption
(AES-128-CBC + HMAC-SHA256)** via the Python `cryptography` library (Phase 81-01,
2026-02-19).

Encrypted fields: `user`, `device_id`, `metadata`.

```python
# backend/app/services/encryption_service.py
# EncryptionService.encrypt(value) wraps Fernet.encrypt()
# Key source: ENCRYPTION_KEY environment variable
# Key storage: /etc/sentinel/secrets.env (never in source control)
```

Encrypted entries carry `"encrypted": true`. The API layer decrypts transparently on
read. The raw JSON file is unreadable without the key.

---

## Append-Only Design

The audit log is append-only by implementation contract:

- **No update endpoints** are exposed for audit records.
- **No delete endpoints** are exposed. Deletion requires direct filesystem access and
  is itself recorded as a system event.
- The write buffer is flushed on service shutdown, preventing silent data loss.
- The `login_audit` Supabase table uses `INSERT`-only access patterns from the
  application layer.

There is no cryptographic hash-chaining (e.g. blockchain-style linking) at this time.
The immutability guarantee is architectural (no API surface for mutation) rather than
cryptographic.

---

## Correlation Threading

Every recommendation is assigned a `correlation_id` (UUID v4) at creation. This ID
threads through all downstream components:

```
Recommendation created  → correlation_id assigned
        │
        ▼
Safety validation       → logged with correlation_id
        │
        ▼
Device write            → logged with correlation_id
        │
        ▼
COV verification        → logged with correlation_id
        │
        ▼
parasite_decisions row  → full lifecycle visible by correlation_id
```

This makes it possible to reconstruct the full causal chain of any autonomous action
from a single UUID, without joining across multiple log files.

---

## What Is Recorded

### Control actions (every BMS write)
- Timestamp (UTC)
- User identity (encrypted)
- Device ID and point name (encrypted)
- Proposed value and actual value written
- Safety validation result
- Correlation ID

### Authentication events (`login_audit` table)
- Timestamp
- User email / API key prefix
- IP address
- Success / failure
- Role assigned

### AI decisions (`parasite_decisions`)
- Full recommendation lifecycle (routing → execution → COV → outcome)
- Approver identity and timestamp (Tier 2)
- Guardrail checks passed / failed (Tier 3)
- Rollback flag and reason if triggered

---

## How to Verify Integrity

### Check that a specific write has an audit record

```python
# Query audit_log for a correlation_id
result = supabase.table("audit_log") \
    .select("*") \
    .eq("correlation_id", "<uuid>") \
    .execute()
```

### Reconstruct a full autonomous decision lifecycle

```sql
SELECT *
FROM parasite_decisions
WHERE correlation_id = '<uuid>'
ORDER BY created_at;
```

### Verify no audit entries were deleted (entry count check)

```python
# Count should only ever increase between restarts
count_now  = supabase.table("audit_log").select("id", count="exact").execute().count
count_prev = <value from last check>
assert count_now >= count_prev, "Audit log entries were deleted"
```

---

## Known Scope Limits

| Gap | Status |
|-----|--------|
| No cryptographic hash-chaining between entries | By design — no current requirement for tamper-evident chaining |
| Audit log JSON backup is manual | Covered by VM snapshot backup (daily) per BCP/DR procedures |
| `parasite_decisions` table does not have RLS | Service-role only; no external write surface |

For the full backup and retention policy, see
[BCP/DR Procedures](bcp-dr-procedures.md).
For the secrets management policy covering `ENCRYPTION_KEY` rotation, see
[Secret Lifecycle](secret-lifecycle.md).
