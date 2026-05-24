# Security Gap Report

**Document Type:** security_gap_report
**Template Version:** 1.0
**Status:** draft

---

## Gap Identification

| Field | Detail |
|-------|--------|
| **Gap ID** | GAP-___-______ |
| **Date Identified** | ____-__-__ |
| **Identified By** | |
| **Source** | [ ] Q&A Review / [ ] Code Audit / [ ] Penetration Test / [ ] Incident / [ ] Other: __ |
| **Severity** | CRITICAL / HIGH / MEDIUM / LOW / INFORMATIONAL |
| **CVSS Score** | ___ (0-10) |
| **Category** | [ ] Access Control / [ ] Data Isolation / [ ] Input Validation / [ ] Audit & Logging / [ ] Safety Controls / [ ] Authentication / [ ] Rate Limiting / [ ] Prompt Injection / [ ] Other: __ |

---

## Gap Description

**What the Q&A states (expected behavior):**

> _Quote the relevant Q&A passage here._

**What the code actually does (current behavior):**

> _Describe the actual implementation or behavior._

---

## Technical Details

### Affected Component(s)

- File(s): ``
- Function(s)/Method(s): ``
- API Endpoint(s): ``
- MCP Tool(s): ``

### Attack/Exploit Path

```
Step 1: _
Step 2: _
Step 3: _
```

### Prerequisites / Preconditions

- _
- _

### Impact

**What an attacker or faulty process can achieve:**

_

**Downstream effects:**

_

---

## Evidence

### Code Snippet or Log Output

```language
// Paste relevant code, query, or log output
```

### Reproduction Steps

1. _
2. _
3. _

---

## Recommended Remediation

| Priority | Remediation | Effort | Owner |
|----------|-------------|--------|-------|
| P0 — Must Fix | | | |
| P1 — Should Fix | | | |
| P2 — Consider | | | |

### Fix Notes

_

---

## Verification

| Check | Method | Expected Result | Verified By | Date |
|-------|--------|-----------------|-------------|------|
| Fix verification | | | | |
| Q&A accuracy check | | | | |

---

## Related

- **Q&A Document:** `docs/09-security/mcp-security-qa.md`
- **Q&A Section:** #
- **Related Gap:** GAP-___-______ (if any)
- **Related Issue/PR:** #

---

## Status History

| Date | Status | Notes |
|------|--------|-------|
| ____-__-__ | identified | Gap identified during _ |
| ____-__-__ | triage | Severity: _ / Category: _ |
| ____-__-__ | fix_committed | PR #_ — _ |
| ____-__-__ | verified | _ |
| ____-__-__ | closed | _ |
