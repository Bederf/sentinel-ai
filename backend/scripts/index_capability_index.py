#!/usr/bin/env python3
"""Index the SENTINEL Capability Index into the RAG.

This document maps natural-language client questions to SENTINEL platform
capabilities. It is the primary retrieval target for platform/capability
questions and ensures consistent, accurate answers even when the embedding
model's vocabulary doesn't match client phrasing.

Usage:
    cd backend && source venv/bin/activate
    python scripts/index_capability_index.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.supabase_client import get_supabase_client
from app.services.vector_db import get_vector_db_service

DOC_CODE = "DOC-CAPABILITY-INDEX"
DOC_TITLE = "SENTINEL Platform — Complete Capability Reference"
DOC_TYPE = "system_documentation"
EQUIP_TYPE = "general"
SOURCE = "system_docs"


# ---------------------------------------------------------------------------
# SENTINEL Capability Index — Full Text
# ---------------------------------------------------------------------------
# Dense Q&A format covering every question category clients actually ask.
# Written in natural language matching client phrasing patterns.
# Includes the full FSR (FirstRand Supplier) risk questionnaire coverage.
# ---------------------------------------------------------------------------

CAPABILITY_INDEX_TEXT = """
# SENTINEL Platform — Complete Capability Reference

SENTINEL is an AI-powered Building Management System (BMS) intelligence layer.
It sits on top of existing building control systems (Siemens Desigo, Tridium Niagara,
DALI-2, BACnet, KNX) and adds predictive maintenance, fault detection, energy
optimisation, comfort complaint resolution, compliance reporting, and mobile-first
operations workflows. SENTINEL does not replace the BMS — it complements it.

---

## Standards, Compliance, and Certification

**Does SENTINEL follow any standards? / What standards does SENTINEL comply with?**

SENTINEL is designed and operated in accordance with the following frameworks:

- **FSR (Financial Sector Regulation / FirstRand Supplier Risk Assessment):** SENTINEL undergoes FirstRand Group Privacy and Service Risk Assessment Questionnaire V8. SENTINEL meets 17 of 18 FSR assessment domains at or above target. The current average FSR score is 4.0 out of 5.0. One medium gap remains (Business Continuity at 3.6, target 4.0). Full FSR gap analysis is available on request. SENTINEL holds FSR Supplier Risk Assessment scores across 18 domains: Information Security Governance (4.0), Asset Management (4.5), Information Classification (4.0), Human Resource Security (3.8), Physical Access Security (4.0), Network Security (4.3), Logical Access Control (4.0), System Security (4.0), Application Security (4.0), Vulnerability Management (4.5), Communication Management (4.0), Cryptography and Key Management (4.3), Incident Detection (4.0), Incident Management (4.0), Business Continuity Management (3.6), Third Party Security Management (4.0), Risk and Compliance (4.0), Information Security Audit (3.5). Control evidence is mapped to ISO 42001, NIST AI RMF, and EU AI Act.

- **ISO 42001 (AI Management System):** SENTINEL implements the ISO 42001 AI management system standard. This covers AI governance, risk management for AI systems, data quality for AI training, model monitoring and drift detection, and human oversight of AI decisions. SENTINEL's AI decisions are explainable and subject to human-in-the-loop review for high-consequence actions. SENTINEL is rated 87% effective across 11 ISO 42001 controls per the internal NIST control-effectiveness review.

- **EU AI Act (Artificial Intelligence Act):** SENTINEL classifies as a limited-risk AI system under the EU AI Act Annex III (AI systems in employment, worker management, and access to essential services — not applicable; SENTINEL operates in facilities management). SENTINEL's risk classification covers 9 AI features against EU AI Act tiers. Risk management documentation, technical documentation, transparency obligations, and human oversight measures are maintained. SENTINEL is not a high-risk AI system — it does not make decisions about people (employment, credit, health, justice). EU AI Act assurance review shows 75% compliance across 4 articles.

- **NIST AI RMF (National Institute of Standards and Technology AI Risk Management Framework):** SENTINEL's AI risk management follows the NIST AI RMF Govern and Map functions. Govern: AI policies, roles, and accountability structures. Map: AI system categorisation, impact assessment, and risk framing. NIST AI RMF controls are mapped in the unified control applicability matrix alongside ISO 42001 and EU AI Act.

- **POPIA (Protection of Personal Information Act — South Africa):** SENTINEL processes personal information (occupant comfort data, desk locations, user email addresses) in accordance with POPIA. A POPIA consent guard determines whether cloud-based AI processing is permitted for each data subject. Local AI fallback is available when POPIA blocks cloud processing. Privacy Impact Assessments (PIAs) are completed for Claude API usage and Sentry error monitoring. A POPIA Section 72 Cross-Border Register documents all international data transfers. Data processing agreements (DPAs) are in place with all sub-processors.

- **ISO 27001 (Information Security):** SENTINEL maintains ISO 27001-aligned information security controls. Encryption at rest and in transit. Role-based access control. Audit logging of all administrative actions. Vulnerability management and penetration testing programme.

- **King IV (South African Governance Code):** SENTINEL supports King IV principles around technology governance, information security oversight, and stakeholder reporting. BMS health dashboards support board-level reporting on facilities performance.

**How does SENTINEL map to the FirstRand supplier risk questionnaire? / What is SENTINEL's FSR gap analysis score?**

SENTINEL's current FSR readiness assessment against FirstRand Group Privacy and Service Risk Assessment Questionnaire V8: 17 of 18 domains at or above target (average score 4.0/5.0). Key FSR assessment areas: Information Security Governance: 4.0/5.0 (AI Management Policy, Architecture Board Charter, control applicability matrix). Asset Management: 4.5/5.0 (asset lifecycle policy, health snapshots, lifecycle state machine). Information Classification: 4.0/5.0 (4-tier classification, PII guard middleware, POPIA cross-border register). Human Resource Security: 3.8/5.0 (AI literacy training 4 modules, competence register, live-control entry gate). Logical Access Control: 4.0/5.0 (MFA, role-based building access, JWT rotation, token blacklist, brute force protection). Application Security: 4.0/5.0 (safety interlocks, quality gate evaluator with 14 metrics, pre-commit security hooks, input validation). Vulnerability Management: 4.5/5.0 (6-phase vulnerability lifecycle, 5 CI jobs, Dependabot, remediation SLAs: Critical 7 days). Incident Management: 4.0/5.0 (NIST SP 800-61-aligned IR process, AI incident playbook, tabletop exercise TABLETOP-001 completed). Third Party Security Management: 4.0/5.0 (third-party AI risk register, PIAs for Claude API and Sentry, vendor DPAs). Risk and Compliance: 4.0/5.0 (AI risk classification 9 features, NIST/EU/ISO assurance reviews). Information Security Audit: 3.5/5.0 (internal audit plan 24 controls, ISO 42001 evidence bundle, CAPA register). One gap remains: Business Continuity Management at 3.6 (BCP policy, DR runbook, 3-tier fallback architecture complete, external audit target Q2 2026).

**Does SENTINEL have a gap analysis? / FSR gap analysis evidence?**

Yes. SENTINEL maintains a live FSR gap analysis document (SENTINEL-GAP-002 v3.1) that scores each of the 18 FirstRand assessment domains on a 1-5 scale. Evidence paths are mapped to specific documentation files, Supabase database migrations, and codebase components for each control. The FSR gap analysis is available to FirstRand security team on request. Control evidence is cross-referenced to ISO 42001 AI Management System controls, NIST AI RMF functions, and EU AI Act articles.

**Has SENTINEL been penetration tested?**

SENTINEL has an active penetration testing programme. The current scope includes: SAST/DAST in CI pipeline (Bandit, safety, pip-audit, Trivy, gitleaks — 5 security jobs), Docker non-root container enforcement, dependency vulnerability scanning via Dependabot, SSH hardening configuration (Ed25519 keys, TOTP), and Cloudflare WAF with 9 rules configured. Full penetration test reports are available under NDA to clients with specific security requirements. An independent external audit is planned for Q2 2026. SENTINEL has a vulnerability disclosure policy and a registered vulnerability management process with 6-phase lifecycle.

---

## Security and Authentication

**Is SENTINEL secure? / Can it be hacked? / Security concerns about SENTINEL**

SENTINEL implements defence-in-depth security across all layers: Network-level isolation with OT/IT segmentation, TLS 1.2+ encryption for all data in transit, AES encryption for data at rest (Fernet AES-128-CBC for audit logs), rate limiting on all API endpoints (5/15 min for auth, 100/min general, 30/min admin), SSO/SAML authentication via Supabase Auth, role-based access control with 5 tiers (Admin, Engineer, Operator, Tenant, Guest), audit logging of all user actions and API calls, AI safety pipeline with 5-stage output filter detecting and blocking prompt injection attacks, generic error handler (no stack traces in production), CORS restriction to configured origins only, security response headers (X-Frame-Options, HSTS), brute force protection (5 attempts / 15 minute lockout), subprocess call sanitisation, PII guard middleware (redacts SA ID numbers, phone numbers, email addresses), Wazuh FIM (File Integrity Monitoring on /etc/passwd, SSH config, Docker config, .env, crontab), and regular security reviews and vulnerability scanning. SENTINEL maintains an OWASP MCP Security Hardening framework mapping and an Agentic Security Framework mapping.

**How does authentication and authorisation work? / What password and authentication policy does SENTINEL use?**

SENTINEL uses Supabase Auth with SSO/SAML support for enterprise identity providers. Authentication options: SSO/SAML integration (Okta, Azure AD, Google Workspace), MFA via TOTP (pyotp), 10 one-time MFA backup codes (hashed), minimum 8-character password with complexity requirements, session timeout after 30 minutes of inactivity, admin PIN for critical actions (bcrypt-hashed, validated server-side, audit-logged), JWT access tokens with 15-minute TTL, refresh tokens with 7-day TTL and rotation, token blacklist by JWT jti (Redis), session tracking and revocation APIs, and brute force protection (5 failed attempts → 15-minute lockout). Role hierarchy: Admin level 5 (full access, user management, settings, safety interlocks), Engineer level 4 (configure equipment and system parameters), Operator level 3 (acknowledge alerts, create work orders, adjust setpoints), Tenant level 2 (view equipment status, submit comfort complaints), Guest level 1 (read-only with limited visibility).

**What encryption does SENTINEL use? / Cryptography and key management**

SENTINEL's cryptography and key management follows ISO 27001 and FSR Cryptography and Key Management requirements (score: 4.3/5.0): Data at rest: Fernet AES-128-CBC encryption for audit logs, data in transit: TLS 1.2 minimum, JWT secret: strong secret configurable, validated at startup, API keys (Anthropic, OpenAI, ElevenLabs): stored as environment variables, never logged or exposed, MFA TOTP: hashed in database (bcrypt), JWT: rotation every 15 minutes (access) and 7 days (refresh), key management policy documented in Cryptography and Key Management Policy.

**What are the security vulnerabilities of SENTINEL? / Vulnerability management**

SENTINEL has a documented vulnerability management process (score: 4.5/5.0): 6-phase vulnerability lifecycle: Identify, Analyse, Treat, Report, Monitor, Close. Automated scanning: SAST (Bandit), dependency scanning (pip-audit, Dependabot), container scanning (Trivy), secrets scanning (gitleaks), DAST. Remediation SLAs: Critical: 7 days, High: 14 days, Medium: 30 days, Low: 90 days. SENTINEL maintains a vulnerability disclosure policy for external security researchers.

---

## Platform Capabilities and Features

**What can SENTINEL do? / What are SENTINEL's main features?**

SENTINEL provides: Predictive Maintenance (ML models predict equipment failure 7-30 days ahead using vibration, temperature, and operational patterns), Fault Detection and Diagnostics (real-time monitoring detects anomalies and provides root cause analysis), Energy Optimisation (setpoint recommendations, load-shedding coordination, tariff-aware scheduling), Comfort Complaint Resolution (desk-level HVAC diagnosis from natural-language complaint text), Work Order Management (automated work order creation from detected faults, with slash-command shortcuts), Compliance Reporting (FSR, POPIA, King IV, ISO 42001 reporting dashboards), Zone Health Assessment (aggregate HVAC health per zone including VAV box performance and outdoor air integration), Multi-Site Operations (centralised dashboard across all registered buildings), Chat AI (Claude-powered natural language interface for querying building data and controlling equipment), Incident Management (structured incident lifecycle with SLA tracking), Automated Fault Rectification (Phase B automation engine for setpoint corrections and demand response), SIMBIOT Universal Adapter (zero-code BMS integration for Siemens Desigo, Tridium Niagara, DALI-2, BACnet), DALI Lighting Control (direct DALI-2 luminaire control with fault monitoring and daylight harvesting), BMS Dashboard (live equipment status, health scores, alerts, predictions), Telegram Alerts (real-time push notifications to technicians with quick action buttons), WhatsApp Integration (comfort complaint submission and work order updates), Health Thresholds (configurable healthy/warning/critical percentages per equipment type), Module System (15 base + 12 toggleable modules: Zone Assessment, Energy, Work Orders, Incident Management, Zone Controller, Tenant Portal, Smart Scheduling, Fleet Learning, Automation, RAG Chat, AI Chat, Tenant Feedback), AI Governance (human-in-the-loop for all consequential AI decisions, explainable predictions, confidence scoring), AI Safety Interlocks (physical boundary enforcement for control actions, 6 rule types), Quality Gate Evaluator (14 metrics with 42 thresholds for automated AI decision quality), MCP Tools (Model Context Protocol tools for extending SENTINEL capabilities), and Cross-System Analysis (lighting + HVAC coordination, occupancy-aware comfort, energy waste detection).

**How does SENTINEL integrate with our existing BMS / building systems? / Can SENTINEL connect to our Desigo / Niagara / BACnet / DALI system?**

SENTINEL uses the SIMBIOT Universal Adapter to connect to any BMS without requiring BMS vendor cooperation or protocol changes. Supported integrations: Siemens Desigo CC (BACnet/IP), Tridium Niagara 4 (BACnet, Modbus, LonWorks), DALI-2 lighting (direct DALI bus control with luminaire-level fault monitoring), BACnet/IP devices (standalone AHUs, chillers, RTUs), KNX (lighting and HVAC), Modbus TCP (power meters, energy loggers), and Niagara NAE direct connection. The SIMBIOT adapter uses a Software-Defined BMS approach: one SBC (single board computer) runs the adapter and translates between the proprietary BMS protocol and SENTINEL's standard data model. No changes to existing BMS configuration required. Point discovery and classification is automatic. Equipment naming follows the format: site-type-zone_id (e.g. S002-AHU-001, S002-CHILLER-B1-001, S002-FCU-104, S002-VAV-2-L1).

**Can SENTINEL handle call logging and service request management? / How does SENTINEL solve our call logging issues?**

Yes. SENTINEL has a complete call logging and service request system. Occupants can log comfort complaints through the chat interface ("desk 25 is too hot", "level 3 is freezing", "it's stuffy in the open plan"). SENTINEL automatically: resolves the desk to the relevant HVAC zone, diagnoses the likely cause (supply air temp, FCU filter, VAV box fault), looks up all HVAC equipment in the zone (FCU, VAV, AHU, sensors), gets live readings and health scores, and can trigger a work order. Call logs are stored and queryable for trends ("how many complaints at Fairlands last month?", "what are the top complaint areas?"). Work orders are managed through a full lifecycle: Created → Assigned → In-Progress → Completed → Verified. SLA tracking is available per priority level (Critical: 4 hours, High: 24 hours, Medium: 72 hours, Low: 7 days). Technicians receive Telegram alerts with quick action buttons.

**Does SENTINEL have predictive maintenance? / How does predictive maintenance work?**

Yes. SENTINEL's predictive maintenance system uses supervised ML models trained on historical fault data. For each monitored piece of equipment, the system tracks: Operating parameters (temperature, pressure, flow rates, power draw), Vibration signatures (for rotating equipment: chillers, fans, compressors), Alarm history and fault codes, Running hours and service interval timers, and Trend analysis (gradual degradation vs sudden change). When the model predicts failure within 7-30 days, SENTINEL generates a Prediction anomaly with: equipment ID and name, failure mode (e.g. "compressor bearing degradation"), confidence score (percentage), recommended action, estimated repair cost in ZAR, and estimated failure cost in ZAR. Predictions are presented to an Operator+ user for approval before any work order is created. All predictions are logged for model performance tracking. The Fleet Learning dashboard tracks model accuracy over time. Stress test scenarios (3 documented) validate model behaviour under edge conditions.

**What energy management features does SENTINEL have?**

SENTINEL provides: Real-time energy monitoring per equipment, zone, and building, Tariff-aware scheduling (Eskom peak/off-peak, demand charge management), Setpoint optimisation recommendations (based on outdoor temperature, occupancy, and grid conditions), Load-shedding coordination (prioritised load shedding during Eskom power curtailment events), Energy anomaly detection (identifies equipment consuming more energy than expected), CO2 monitoring and demand-controlled ventilation, Daylight harvesting coordination (DALI lighting with occupancy sensors), and Energy reporting by building, floor, and equipment type with trend analysis.

**How does the zone health assessment work?**

SENTINEL's Zone Health Assessment evaluates the complete HVAC chain for each zone: air handling unit (AHU) status and performance, VAV (Variable Air Volume) box position and temperature control, FCU (Fan Coil Unit) operation, supply air temperature and flow, outdoor air integration and CO2 levels, thermal comfort (temperature vs setpoint), complaints history for the zone, and recommendations prioritised by safety first, then comfort, then efficiency. Zone assessments are gated by onboarding phase: Phase A (Foundation — weeks 1-4): basic equipment health. Phase B (Intelligence — weeks 5-8): adds VAV diagnostics and automation recommendations. Phase C (Automation — weeks 9-12): adds full compliance and optimisation recommendations.

**Can SENTINEL be configured for air-gapped / on-premise environments?**

Yes. SENTINEL supports local-only AI mode for air-gapped environments where cloud processing is not permitted. The local AI runs Ollama with Phi-3-mini on-premise in the data centre. The POPIA consent guard automatically routes sensitive queries to local AI. Supabase database can also run in local-only mode.

---

## FSR Questionnaire — Specific Assessment Areas

**How does SENTINEL handle information security governance? / AI governance framework**

SENTINEL's information security governance (FSR score: 4.0/5.0) includes: AI Management Policy (ISO 42001 AIMS — artificial intelligence management system), Architecture Board Charter (formal governance body with quarterly cadence), Control Applicability Matrix (13 ISO 42001 controls mapped alongside NIST AI RMF and EU AI Act), Management Review Template (quarterly governance cadence), and unified policy hierarchy (3-tier: policy → standard → procedure). The Architecture Board oversees all AI decisions, model changes, and safety incidents.

**How does SENTINEL manage third party security? / Third party AI risk management**

SENTINEL's third party security management (FSR score: 4.0/5.0) includes: Third-Party Security Register (6 vendors documented), Third-Party AI Risk Register (AI-specific risks for Anthropic Claude API and Ollama), Privacy Impact Assessments (PIAs) for Claude API usage and Sentry error monitoring, Vendor data processing agreements (DPAs), POPIA Section 72 Cross-Border Register, and Vendor change notification process with quarterly benchmark testing framework. Third-party risks are assessed against ISO 42001 A.7.1 and EU AI Act Article 62.

**How does SENTINEL manage incidents? / Incident response and management**

SENTINEL's incident management (FSR score: 4.0/5.0) includes: NIST SP 800-61-aligned Incident Response Policy (IRP v1.1), AI Model Incident Playbook (Section 10.4 in IRP), Tabletop Exercise completed (TABLETOP-001 — all pass criteria met), RCA postmortem process (root cause analysis for Major+ incidents), Incident detection (6 SIEM rules, Wazuh IDS, centralized logging with Promtail→Loki→Grafana), Incident management SLA tracking per severity class (Critical: 4 hours, High: 24 hours, Major: 72 hours, Minor: 7 days), and Compliance evidence for FSR audit.

**How does SENTINEL handle business continuity? / BCP and disaster recovery**

SENTINEL's business continuity (FSR score: 3.6/5.0 — one gap remaining, target Q2 2026) includes: BCP Policy and DR Procedures, 3-tier fallback architecture (Supabase → Redis → JSON local fallback), Daily VM snapshots, DR Runbook, BCP Test Plan, and SENTINEL chatbot local AI fallback when cloud AI is unavailable.

**How does SENTINEL handle human resource security? / AI literacy training**

SENTINEL's human resource security (FSR score: 3.8/5.0) includes: AI Literacy Training Package (4 modules covering AI basics, SENTINEL usage, AI safety, POPIA awareness), Competence Training Register (role matrix mapped to ISO 42001 7.2), Live Control Entry Criteria (training gate — staff must complete training before accessing AI control features), Fairness/Bias Baseline Assessment (6 models assessed), and Stress Test Scenarios (3 documented for ML model validation).

**How does SENTINEL handle application security? / AI safety and quality gates**

SENTINEL's application security (FSR score: 4.0/5.0) includes: Safety Interlocks Engine (6 rule types for physical boundary enforcement), Quality Gate Evaluator (14 metrics, 42 thresholds for automated AI decision quality), Pre-commit Security Hooks (6 security hooks in CI pipeline), Input Validation (Pydantic models on all API endpoints), OWASP MCP Security Hardening (Model Context Protocol security guidelines), Agentic Security Framework Mapping, and Generic error handler (no stack traces in production).

---

## Onboarding and Configuration

**How do I upload a building into SENTINEL? / How does the building onboarding process work?**

Building onboarding follows a structured three-phase approach with automated progress tracking: Phase A Foundation (weeks 1-4): Register the site, configure SIMBIOT adapter, discover all BACnet/DALI devices, classify equipment types, set up equipment codes (format: site-type-zone_id, e.g. S002-AHU-001), configure health thresholds (healthy, warning, critical percentages), upload equipment documentation (manuals, fault codes, maintenance procedures), and run initial equipment discovery. Phase B Intelligence (weeks 5-8): Configure ML model training data, set up alert thresholds and escalation rules, enable VAV zone diagnostics, configure work order templates, and run smoke tests on all systems. Phase C Automation (weeks 9-12): Enable automated setpoint corrections, configure demand response events, tune energy optimisation rules, run full compliance reporting, and enable proactive prediction alerts. A building cannot be "fully on-boarded" in less than 12 weeks — SENTINEL requires time to collect baseline data for ML model training. Onboarding completion unlocks full system capabilities. Each phase has entry criteria and exit criteria validated by the PhaseGateEngine.

**How do I configure alerts and escalation rules?**

Alerts are configured per site and per equipment type. Each alert has: name, trigger condition (threshold, rate-of-change, fault code), severity (Critical, Warning, Info), notification recipients (email, SMS, Telegram), escalation rules (time-based escalation if not acknowledged), and auto-remediation actions (if Phase C automation is enabled). Alert acknowledgements are tracked. Stale alerts (unacknowledged for >24 hours) escalate automatically.

**Can SENTINEL be configured for our specific site requirements?**

Yes. SENTINEL is highly configurable: Equipment type definitions are customisable per site, Health thresholds are configurable (healthy/warning/critical percentages), Alert thresholds are configurable per equipment type, Control limits for setpoint adjustments are configurable, AI policies are configurable per site (local-only mode, budget caps, tool permissions), Module system allows enabling/disabling specific features per site, MCP tools for extending SENTINEL capabilities, per-site AI policies for chat moderation and budget control.

---

## Data, Privacy, and AI Processing

**Where does SENTINEL process data? / Is data processed in South Africa / on-premise / cloud?**

SENTINEL uses a hybrid architecture: Local AI: Ollama with Phi-3-mini runs on-premise for air-gapped environments and low-latency control actions. Cloud AI: Anthropic Claude and OpenAI GPT process complex queries in the cloud. POPIA Consent Guard: determines per data subject whether cloud processing is permitted. On-premise data never leaves the building network unless POPIA consent is granted. Supabase hosts the relational database (PostgreSQL with Row Level Security) — South Africa primary region. Vector database (pgvector) is in Supabase for RAG. Infrastructure runs on AWS with South Africa region primary.

**What data does SENTINEL store? / How long is data retained? / GDPR / POPIA data protection**

SENTINEL stores: Equipment telemetry (temperature, pressure, power, flow — 2-year retention), Alert and fault history (5-year retention for compliance), Work order records (indefinite retention), Comfort complaint logs (2-year retention, anonymised after 12 months), Chat message history (user configurable, 90 days default, fully deletable on request), Audit logs (5-year retention), ML training data (anonymised, aggregated — no personal data), POPIA consent records (indefinite retention for proof of compliance). Data deletion requests are processed within 30 days. Export in JSON/CSV format available for all personal data. SENTINEL has a 4-tier information classification policy: Public, Internal, Confidential, Restricted.

**Does SENTINEL use AI to make decisions automatically? / Human oversight of AI**

SENTINEL's AI makes recommendations, not autonomous decisions, except in specific controlled scenarios: Predictive maintenance recommendations require Operator+ approval before work orders are created. Automated setpoint corrections require Phase C onboarding and Operator+ approval. Demand response events (load shedding) require explicit enablement and can be disabled at any time. Work order creation from fault detection requires Operator+ confirmation. Fire equipment, generator control, and safety interlocks cannot be remotely reset or automated — SENTINEL always requires manual intervention for these. Human-in-the-loop is maintained for all consequential decisions. SENTINEL's AI decisions are explainable — the reasoning is provided alongside each recommendation.

---

## Incident Management and Operations

**How does SENTINEL handle incidents and emergencies?**

SENTINEL has a structured incident management system aligned with NIST SP 800-61 and FSR requirements: Incident detection (from equipment faults, ML predictions, and operator reports), Incident classification (Safety, Critical, Major, Minor, Information), SLA tracking per incident class (Safety: 4 hours, Critical: 24 hours, Major: 72 hours, Minor: 7 days), Escalation rules (auto-escalate if SLA breached), Duty roster integration (notifies on-call technician via Telegram/SMS/email), Incident timeline (all actions, acknowledgements, and updates logged), Post-incident review (triggered after each Major+ incident, includes root cause and corrective action), and Compliance evidence (incident records available for FSR audit evidence). AI incidents follow a specific playbook (Section 10.4 of the Incident Response Policy). A tabletop exercise (TABLETOP-001) covering bad model output has been completed with all pass criteria met.

**Does SENTINEL have mobile access for technicians?**

Yes. SENTINEL is mobile-first. Technicians receive Telegram alerts with: Equipment ID and description, fault summary and recommended action, quick action buttons (/info, /inspect, /WO slash commands), and map location of equipment. The mobile-responsive web UI works on any device. Work orders are assigned and updated via Telegram or the web UI. No native mobile app required — everything runs in the browser.

**What slash commands are available in SENTINEL chat?**

SENTINEL supports slash commands in chat: /info_{CODE} — show full equipment diagnostics (e.g. /info_S002_FCU_104), /inspect_{CODE} — schedule a structured inspection with a technician, /WO_{CODE} — create a work order, /alerts — show active alerts across all equipment, /zone_{ZONE} — show zone health assessment, /energy_{PERIOD} — show energy summary (day/week/month). Commands work in Telegram and the web chat. Equipment codes use underscores (S002_FCU_104) not dashes in slash commands. Telegram bot commands only support letters, numbers, and underscores.

---

## Troubleshooting and Support

**The AI chat is giving wrong or fabricated answers. / How do I improve answer quality?**

Possible causes and solutions: No relevant documents indexed — upload equipment manuals, fault codes, and maintenance procedures to the RAG system. POPIA consent blocking cloud AI — check if local-only mode is enabled for your site. Vocabulary mismatch — SENTINEL uses a Capability Index document to improve retrieval for free-form questions. Enable the "Include SENTINEL platform documentation" toggle for platform questions. Embedding model not matching vocabulary — the capability index document is designed to address this. Claude credits exhausted — check the chat status endpoint (/api/chat/status). Resolution steps: Upload relevant documents, enable cloud AI processing, enable the platform docs toggle, check API key configuration.

**Zone health shows no data. / How do I set up zone assessment?**

Possible causes: Zone not registered in the zone registry (use Zone Desk Mapping page). Equipment in zone not yet commissioned (Phase A must be complete). Zone has no active equipment. Zone assessment is gated by onboarding phase — only Phase B+ unlocks VAV diagnostics and automation recommendations. Resolution: Register zone in Zone Desk Mapping, complete Phase A equipment discovery, verify equipment health scores are populated.

**Predictive maintenance alerts are not appearing. / ML models not predicting failures.**

Possible causes: Insufficient historical data for ML training (minimum 90 days of operational data required). Equipment not flagged as predict-enabled in settings. Prediction model not yet trained for this equipment type. Zone/equipment not yet in Phase B onboarding. Resolution: Wait for data collection period (minimum 90 days), enable predictions in equipment settings, verify Phase B onboarding is complete, contact SENTINEL support to trigger model training.
"""


async def main():
    print("SENTINEL Capability Index — RAG Ingestion")
    print("=" * 55)

    client = get_supabase_client()
    vector_db = get_vector_db_service(client)

    existing = client.table("documents").select("id").eq("code", DOC_CODE).execute()

    if existing.data:
        doc_id = existing.data[0]["id"]
        print(f"Updating existing capability index: {doc_id}")
        client.table("document_chunks").delete().eq("document_id", doc_id).execute()
        client.table("documents").update(
            {
                "title": DOC_TITLE,
                "full_text": CAPABILITY_INDEX_TEXT,
                "summary": "SENTINEL platform capability reference: FSR risk questionnaire, ISO 42001, NIST AI RMF, EU AI Act, POPIA, security, features, onboarding, troubleshooting.",
                "keywords": [
                    "standards",
                    "ISO 42001",
                    "NIST AI RMF",
                    "EU AI Act",
                    "POPIA",
                    "FSR",
                    "FirstRand",
                    "supplier risk",
                    "gap analysis",
                    "FSR questionnaire",
                    "gap analysis score",
                    "control mapping",
                    "compliance",
                    "security",
                    "hack",
                    "breach",
                    "vulnerability",
                    "penetration test",
                    "cryptography",
                    "capability",
                    "feature",
                    "integration",
                    "BMS",
                    "SIMBIOT",
                    "call logging",
                    "predictive maintenance",
                    "energy",
                    "zone health",
                    "onboarding",
                    "configuration",
                    "setup",
                    "AI",
                    "work order",
                    "incident",
                    "authentication",
                    "encryption",
                    "data protection",
                    "GDPR",
                    "King IV",
                    "automation",
                    "DALI",
                    "BACnet",
                    "human oversight",
                    "human in the loop",
                    "AI governance",
                    "quality gate",
                    "safety interlocks",
                    "incident response",
                    "business continuity",
                    "third party",
                    "HR security",
                ],
                "indexing_status": "pending",
            }
        ).eq("id", doc_id).execute()
        print(f"  Updated document {doc_id}")
    else:
        print("Creating new capability index document...")
        result = (
            client.table("documents")
            .insert(
                {
                    "code": DOC_CODE,
                    "title": DOC_TITLE,
                    "document_type": DOC_TYPE,
                    "equipment_type": EQUIP_TYPE,
                    "full_text": CAPABILITY_INDEX_TEXT,
                    "source": SOURCE,
                    "summary": "SENTINEL platform capability reference: FSR risk questionnaire, ISO 42001, NIST AI RMF, EU AI Act, POPIA, security, features, onboarding, troubleshooting.",
                    "keywords": [
                        "standards",
                        "ISO 42001",
                        "NIST AI RMF",
                        "EU AI Act",
                        "POPIA",
                        "FSR",
                        "FirstRand",
                        "supplier risk",
                        "gap analysis",
                        "FSR questionnaire",
                        "gap analysis score",
                        "control mapping",
                        "compliance",
                        "security",
                        "hack",
                        "breach",
                        "vulnerability",
                        "penetration test",
                        "cryptography",
                        "capability",
                        "feature",
                        "integration",
                        "BMS",
                        "SIMBIOT",
                        "call logging",
                        "predictive maintenance",
                        "energy",
                        "zone health",
                        "onboarding",
                        "configuration",
                        "setup",
                        "AI",
                        "work order",
                        "incident",
                        "authentication",
                        "encryption",
                        "data protection",
                        "GDPR",
                        "King IV",
                        "automation",
                        "DALI",
                        "BACnet",
                        "human oversight",
                        "human in the loop",
                        "AI governance",
                        "quality gate",
                        "safety interlocks",
                        "incident response",
                        "business continuity",
                        "third party",
                        "HR security",
                    ],
                    "indexing_status": "pending",
                }
            )
            .execute()
        )

        if not result.data:
            print("ERROR: Failed to insert document")
            return
        doc_id = result.data[0]["id"]
        print(f"  Created document: {doc_id}")

    print("\nChunking and embedding...")
    chunk_count = vector_db.chunk_and_embed_markdown(
        doc_id,
        doc_title=DOC_TITLE,
        doc_type=DOC_TYPE,
        max_chunk_size=800,
    )
    print(f"  Indexed {chunk_count} chunks")

    print("\n" + "=" * 55)
    print("Verifying retrieval with test queries...")

    test_queries = [
        # FSR and standards
        ("Does SENTINEL follow any standards?", "FSR/standards"),
        ("what standards does SENTINEL comply with FSR ISO 42001", "FSR/standards"),
        ("FSR gap analysis scores ISO AI Act POPIA compliance", "FSR/standards"),
        ("FirstRand supplier risk assessment questionnaire", "FSR/standards"),
        ("does sentinel follow NIST AI RMF", "FSR/standards"),
        ("EU AI Act compliance sentinel", "FSR/standards"),
        ("how does SENTINEL map to the FirstRand risk questionnaire", "FSR"),
        ("what is SENTINEL's FSR score", "FSR"),
        # Security concerns
        ("we're worried SENTINEL can be hacked", "security"),
        ("can SENTINEL be breached what are the vulnerabilities", "security"),
        ("what is the password and authentication policy", "security/auth"),
        ("how does POPIA data protection work in SENTINEL", "privacy"),
        ("security vulnerabilities of SENTINEL", "security"),
        # Capabilities and features
        ("what can SENTINEL do what are its features", "capability"),
        ("how does SENTINEL solve call logging issues", "capability"),
        ("does SENTINEL handle service requests and work orders", "capability"),
        ("predictive maintenance how does it work", "capability"),
        ("energy management and optimisation", "capability"),
        ("zone health assessment how does it work", "capability"),
        # Integration
        ("how does SENTINEL integrate with our existing BMS", "integration"),
        ("SIMBIOT universal adapter BACnet DALI", "integration"),
        # Onboarding
        ("how do I upload a building into SENTINEL", "onboarding"),
        ("how does the onboarding process work", "onboarding"),
        ("building upload procedure", "onboarding"),
        # FSR specific questionnaire areas
        ("how does SENTINEL handle information security governance AI governance", "FSR/governance"),
        ("how does SENTINEL manage third party security third party AI risk", "FSR/third-party"),
        ("how does SENTINEL handle incident response incident management", "FSR/incidents"),
        ("how does SENTINEL handle business continuity BCP disaster recovery", "FSR/bcp"),
        ("how does SENTINEL handle human resource security AI literacy training", "FSR/hr"),
        ("how does SENTINEL handle application security AI safety quality gates", "FSR/app-sec"),
        # Troubleshooting
        ("AI chat is giving wrong answers fabricated information", "troubleshooting"),
        ("zone health shows no data", "troubleshooting"),
    ]

    all_passed = True
    for query, category in test_queries:
        results = vector_db.hybrid_search(
            query=query,
            n_results=5,
            site_id=None,
            keyword_weight=0.4,
            semantic_weight=0.6,
        )
        found = any(DOC_CODE in str(r.get("document_id", "")) for r in results)
        score_str = "PASS" if found else "FAIL"
        if not found:
            all_passed = False
        top_score = 0.0
        for r in results:
            if DOC_CODE in str(r.get("document_id", "")):
                top_score = r.get("hybrid_score") or r.get("similarity", 0)
                break
        print(f"  [{score_str}] [{category}] '{query[:55]}' → score: {top_score:.3f}")

    print(f"\n{'=' * 55}")
    print("Capability Index ingestion complete!")
    print(f"  Document code: {DOC_CODE}")
    print(f"  Chunks indexed: {chunk_count}")
    print(f"  Retrieval tests: {'ALL PASSED' if all_passed else 'SOME FAILED'}")
    if not all_passed:
        print("\n  NOTE: Some queries did not retrieve the capability index yet.")
        print("  This is expected if embedding has not completed.")
        print("  Re-run after confirming chunks are in document_chunks table.")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
