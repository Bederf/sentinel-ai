# Vulnerability Remediation Tracker

SENTINEL BMS Intelligence Platform - FSR Domain 4.10 Compliance

**Last updated:** 2026-02-04
**Next review:** 2026-04-06 (quarterly)

## SLA Reference

| Severity | Remediation SLA | Escalation Trigger | Escalation To |
|----------|----------------|-------------------|---------------|
| **Critical** | 7 days | 3 days unresolved | Management |
| **High** | 14 days | 7 days unresolved | Management |
| **Medium** | 30 days | 21 days unresolved | Team Lead |
| **Low** | 90 days | Review at next quarterly scan | Team Lead |

## Status Definitions

| Status | Description |
|--------|-------------|
| **Open** | Finding identified, not yet assigned |
| **In Progress** | Assigned and actively being remediated |
| **Remediated** | Fix applied, awaiting verification |
| **Verified** | Fix confirmed via re-scan or manual verification |
| **Accepted Risk** | Cannot remediate; compensating controls documented and approved |
| **False Positive** | Confirmed not a real vulnerability; documented rationale |

## Active Findings

| ID | Date Found | Source | Severity | Description | Affected Component | SLA Deadline | Status | Owner | Remediated Date | Verified By |
|----|-----------|--------|----------|-------------|-------------------|-------------|--------|-------|----------------|-------------|
| _No active findings - initial tracker setup_ | | | | | | | | | | |

<!-- Template row for new findings:
| VUL-001 | YYYY-MM-DD | External/Internal/CI | Critical/High/Medium/Low | Description of the vulnerability | Component/Service affected | YYYY-MM-DD | Open | Name | | |
-->

## Closed Findings

| ID | Date Found | Source | Severity | Description | Affected Component | Remediated Date | Verified By | Resolution |
|----|-----------|--------|----------|-------------|-------------------|----------------|-------------|------------|
| _No closed findings yet_ | | | | | | | | |

## Risk Acceptance Register

For vulnerabilities that cannot be remediated, document justification and compensating controls.

| ID | Vulnerability | Justification | Compensating Controls | Approved By | Approval Date | Review Date |
|----|--------------|---------------|----------------------|-------------|---------------|-------------|
| _No accepted risks_ | | | | | | |

### Risk Acceptance Process

1. **Request** - Vulnerability owner submits risk acceptance with:
   - Detailed justification for why remediation is not feasible
   - Proposed compensating controls
   - Residual risk assessment
2. **Review** - Security team evaluates compensating controls and residual risk
3. **Approval** - Management approval required for Critical/High; Team Lead for Medium/Low
4. **Documentation** - Record in Risk Acceptance Register above
5. **Re-review** - Re-evaluate at each quarterly scan or when circumstances change

## Quarterly Metrics

Track these metrics at each quarterly review to measure vulnerability management effectiveness.

### Q1 2026 (Jan-Mar)

| Metric | Value |
|--------|-------|
| Open findings (Critical) | 0 |
| Open findings (High) | 0 |
| Open findings (Medium) | 0 |
| Open findings (Low) | 0 |
| New findings this quarter | 0 |
| Closed findings this quarter | 0 |
| Mean time to remediate (Critical) | N/A |
| Mean time to remediate (High) | N/A |
| Mean time to remediate (Medium) | N/A |
| SLA compliance rate | N/A |
| Accepted risks | 0 |
| False positives | 0 |
| Lynis hardening index | TBD |

### Previous Quarters

_No previous quarters recorded yet._

## Scan History

| Date | Type | Scanner | Findings | Critical | High | Medium | Low | Report Location |
|------|------|---------|----------|----------|------|--------|-----|-----------------|
| _Initial setup - no scans run yet_ | | | | | | | | |

<!-- Template row:
| 2026-02-03 | External | external-scan.sh | 12 | 0 | 3 | 5 | 4 | security-reports/external/2026-02-03/ |
-->

## Finding ID Convention

Format: `VUL-{NNN}`

- Sequential numbering starting at VUL-001
- IDs are never reused even after closure
- Cross-reference with scan reports for full details

## References

- [Vulnerability Management Process](../../docs/08-security/vulnerability-management.md)
- [External Scanning Script](./external-scan.sh)
- [Internal Scanning Script](./internal-scan.sh)
- [Scanning README](./README.md)
