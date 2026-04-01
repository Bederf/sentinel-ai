# FSR Questionnaire Control Mapping Index

**Document:** SENTINEL-FSRQ-001
**Version:** 1.0.0
**Created:** 2026-03-20
**Updated:** 2026-03-20
**Author:** SENTINEL Compliance Team
**Purpose:** Map FSR Privacy and Service Risk Assessment Questionnaire V8 themes to existing SENTINEL evidence artifacts for audit readiness.

## Mapping Methodology

Each of the 18 FSR assessment domains (from `docs/09-security/FSR_GAP_ANALYSIS_UPDATE.md` v3.1) is mapped to:

1. **ISO 42001 / NIST AI RMF / EU AI Act controls** from `docs/ai-governance/control-applicability-matrix.md`
2. **Evidence artifacts** from `docs/ai-governance/evidence/README.md` directories
3. **Security documentation** from `docs/09-security/` inventory
4. **Technical controls** from codebase and Supabase migrations

## Control Mapping Table

| FSR Domain (v3.0 Score) | Control IDs (Matrix) | Key Evidence Paths | Evidence Notes |
|-------------------------|----------------------|-------------------|----------------|
| **1. Information Security Governance** (4.0) | ISO-A.2.2, ISO-A.2.3, NIST-GV-1.2, NIST-GV-1.5 | `docs/ai-governance/ai-management-policy.md`<br>`docs/architecture-repository/governance/architecture-board-charter.md`<br>`docs/ai-governance/control-applicability-matrix.md`<br>`docs/09-security/information-security-framework.md` | AI Management Policy (ISO 42001 AIMS), Architecture Board charter, unified control matrix, 3-tier policy hierarchy |
| **2. Asset Management** (4.5) | ISO-A.6.1, EU-Art.15 | `docs/09-security/asset-lifecycle-policy.md`<br>`backend/app/services/health_data_quality_gate.py`<br>`backend/app/services/encryption_service.py` | Asset lifecycle policy, health snapshots, lifecycle state machine, baseline assessment |
| **3. Information Classification** (4.0) | ISO-A.5.1, EU-Art.10, EU-Art.26 | `docs/09-security/data-privacy-policy.md`<br>`docs/09-security/information-classification-policy.md`<br>`backend/app/middleware/pii_guard.py`<br>`docs/09-security/popia-cross-border-register.md` | 4-tier classification policy, PII guard middleware, POPIA cross-border register, data privacy policy |
| **4. Human Resource Security** (3.8) | NIST-GV-3.1, EU-Art.4 | `docs/ai-governance/ai-literacy-training-package.md`<br>`docs/ai-governance/competence-training-register.md`<br>`docs/ai-governance/live-control-entry-criteria.md`<br>`docs/09-security/hr-security-policy.md` | AI literacy training (4 modules), competence register, live-control entry gate, HR security policy |
| **5. Physical Access Security** (4.0) | *Not AI-specific* | `docs/09-security/physical-access-security-policy.md` (implied) | On-premises deployment; physical security out of scope for AI governance |
| **6. Network Security** (4.3) | EU-Art.15 (cybersecurity) | `infrastructure/ssh/sshd_hardening.conf`<br>Cloudflare WAF 9 rules (documented in gap analysis) | SSH hardening (Ed25519+TOTP), OT/IT segmentation, WAF rules |
| **7. Logical Access Control** (4.0) | ISO-A.2.3, NIST-GV-1.2 | `supabase/migrations/035_user_site_access.sql`<br>`supabase/migrations/037_mfa_secrets.sql`<br>`supabase/migrations/054_mfa_backup_codes.sql`<br>`backend/app/services/mfa_service.py`<br>`docs/09-security/logical-access-control-policy.md` | User site access control, MFA (TOTP+backup), token blacklist, session tracking, brute force protection |
| **8. System Security** (4.0) | EU-Art.15 (robustness) | `infrastructure/ssh/sshd_hardening.conf`<br>Wazuh FIM monitoring<br>Docker non-root containers, Trivy scanning | Wazuh FIM (`/etc/passwd`, SSH config, Docker config, `.env`, crontab), SSH hardening config |
| **9. Application Security** (4.0) | ISO-A.6.2, NIST-MS-2.6, EU-Art.15 | `backend/app/services/safety_interlocks.py`<br>`backend/app/services/quality_gate_evaluator.py`<br>`docs/09-security/application-security-policy.md`<br>`.pre-commit-config.yaml` (6 security hooks) | Safety interlocks engine (6 rule types), quality gate evaluator (14 metrics), pre‑commit hooks, secure coding standards |
| **10. Vulnerability Management** (4.5) | *Not AI-specific* | `docs/09-security/vulnerability-management-process.md`<br>`docs/09-security/vulnerability-disclosure-policy.md`<br>`.github/workflows/security-scan.yml` (5 jobs)<br>`.github/dependabot.yml` | 6-phase lifecycle, 5 CI jobs, Dependabot, remediation SLAs (Critical 7d), disclosure policy |
| **11. Communication Management** (4.0) | *Not AI-specific* | `docs/09-security/communication-management-policy.md` (implied) | Standard IT governance; out of scope for AI |
| **12. Cryptography and Key Management** (4.3) | ISO-A.8.2, EU-Art.15 | `docs/09-security/cryptography-key-management-policy.md`<br>`backend/app/data/audit_log.json` (Fernet encrypted)<br>`backend/app/services/encryption_service.py` | Fernet encryption at rest (audit logs), JWT rotation (15min/7d), key management policy |
| **13. Incident Detection** (4.0) | ISO-A.8.1, NIST-MS-2.8, EU-Art.62 | `supabase/migrations/036_login_audit_log.sql`<br>`backend/app/services/audit_logger.py`<br>`docs/09-security/logging-architecture.md`<br>`docs/09-security/intrusion-detection.md` | Login audit log, suspicious activity detection, 6 SIEM rules, Wazuh IDS, centralized logging (Promtail→Loki→Grafana) |
| **14. Incident Management** (4.0) | NIST-MG-4.3, EU-Art.62 | `docs/09-security/incident-response-policy.md`<br>`docs/09-security/incident-response-process.md` (v1.1)<br>`docs/ai-governance/incident-tabletop-report.md`<br>`docs/ai-governance/evidence/rca-postmortems/tabletop-001-bad-model.md` | NIST SP 800‑61‑aligned IR process, AI incident playbook (Section 10.4), tabletop exercise (TABLETOP‑001), RCA postmortem |
| **15. Business Continuity Management** (3.6) | *Not AI-specific* | `docs/09-security/business-continuity-policy.md`<br>`docs/09-security/bcp-dr-procedures.md`<br>`infrastructure/bcpdr/dr-runbook.md`<br>`infrastructure/bcpdr/bcp-test-plan.md` | BCP/DR policy, 3-tier fallback architecture (Supabase→Redis→JSON), daily VM snapshots, DR runbook |
| **16. Third Party Security Management** (4.0) | ISO-A.7.1, EU-Art.62 | `docs/09-security/third-party-security-register.md`<br>`docs/ai-governance/third-party-ai-risk-register.md`<br>`docs/09-security/pia-claude-api.md`<br>`docs/09-security/pia-sentry-messaging.md` | Third‑party security register (6 vendors), AI‑specific risk register, PIAs (Claude API, Sentry), POPIA cross‑border register |
| **17. Risk and Compliance** (4.0) | ISO-A.4.1, ISO-A.4.2, NIST-GV-1.5, EU-Art.9, EU-Art.50 | `docs/ai-governance/01-risk-classification.md`<br>`backend/app/services/quality_gate_policy.py`<br>`docs/ai-governance/nist-control-effectiveness-review.md`<br>`docs/ai-governance/eu-ai-act-assurance-review.md`<br>`docs/ai-governance/compliance-closure-report.md` | Risk classification (9 AI features), quality gate enforcement, NIST effectiveness review (87%), EU AI Act assurance (75%), compliance closure report |
| **18. Information Security Audit** (3.5) | ISO-A.8.2, NIST-MS-2.8, EU-Art.12 | `docs/09-security/security-audit-programme.md`<br>`docs/ai-governance/internal-audit-plan.md`<br>`docs/ai-governance/evidence/iso42001-evidence-bundle.md`<br>`docs/ai-governance/independent-audit-readiness-pack.md`<br>`docs/ai-governance/nonconformity-capa-register.md` | Internal audit plan (24 controls), ISO 42001 evidence bundle (13 controls), TOGAF governance evidence, CAPA register (6 NCs), audit readiness pack |

## Evidence Directories Reference

| Evidence Category | Path | FSR Domains Covered |
|------------------|------|---------------------|
| Training records | `docs/ai-governance/evidence/training/` | Human Resource Security (EU Art.4) |
| Drift reports | `docs/ai-governance/evidence/drift-reports/` | Risk and Compliance, Application Security |
| Audit log samples | `docs/ai-governance/evidence/audit-logs-samples/` | Incident Detection, Information Security Audit |
| RCA postmortems | `docs/ai-governance/evidence/rca-postmortems/` | Incident Management, Risk and Compliance |
| Model cards | `docs/ai-governance/evidence/model-cards/` | Risk and Compliance, Application Security |
| Data sheets | `docs/ai-governance/evidence/data-sheets/` | Information Classification, Risk and Compliance |
| ISO 42001 bundle | `docs/ai-governance/evidence/iso42001-evidence-bundle.md` | Information Security Governance, Risk and Compliance, Audit |
| TOGAF evidence | `docs/ai-governance/evidence/togaf-governance-evidence.md` | Information Security Governance, Audit |

## Gap Indicators

The following FSR domains have **planned/partial** controls per the applicability matrix:

1. **Third Party Security Management** (ISO-A.7.1 – Partial) → AI‑specific risk register expansion needed (target 2026‑04‑15)
2. **Human Resource Security** (NIST-GV-3.1 – Planned) → AI competence register not yet established (target 2026‑04‑30)
3. **Risk and Compliance** (ISO-A.10.2 – Partial) → Recommendation transparency templates incomplete (target 2026‑04‑30)
4. **Information Security Audit** (ISO-A.8.1 – Partial) → Control‑effectiveness metrics not fully wired (target 2026‑04‑15)

## Usage Notes

- **For questionnaire drafting**: Use the mapped evidence paths as direct references for each FSR domain.
- **Where control is "Not AI‑specific"**: Refer to general security documentation in `docs/09-security/`.
- **Evidence availability**: All referenced artifacts exist and are audit‑ready unless marked "Partial" or "Planned".
- **Cross‑references**: See `docs/09-security/FSR_GAP_ANALYSIS_UPDATE.md` Section 5 for full evidence inventory.

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026‑03‑20 | Initial mapping from FSR v3.1 domains to control matrix and evidence artifacts. |
