# FNB FSR 2026-06-23 — Security & Deployment One-Pager

**Status:** Pre-session brief | **Date:** 2026-06-23

---

## Context

Sentinel was built to solve a real problem the user experienced first-hand in BMS operations. COI has been **disclosed and approved** by the user's employer. The goal is straightforward: roll Sentinel into FNB as the user's day job — build it, run it, own it.

---

## 1. Current Deployment

Sentinel runs on a **remote VPS** in production at site-002 (Sandton):

| Layer | Current | Location |
|-------|---------|----------|
| Application (FastAPI + React) | Cloud VPS | Movable |
| Database (Supabase) | **af-south-1** (Cape Town) | **Stays in SA** |
| LLM | Claude API (Anthropic) | US |
| Notifications | OpenClaw Gateway + WhatsApp/Telegram | VPS + platform infra |

**Core building data never leaves SA** — Supabase af-south-1 holds all telemetry, alarms, equipment state, and recommendations.

---

## 2. In-Country / On-Prem Path

The architecture is **portable by design** — on-prem is a config change, not a rewrite.

### What changes:

| Change | Effort |
|--------|--------|
| Move VPS to SA-based server | Provisioning, ~1 day |
| Swap Claude API → Ollama (local) | Config toggle, tested in dev |
| Re-point DNS, update env vars | ~30 min |
| **Total** | **~2 days** |

### What stays the same:
- Supabase stays af-south-1 (already here)
- Every API endpoint, every DB query, every frontend component — zero changes
- Equipment bindings, zone mappings, user config — untouched

**Result:** On-prem eliminates all cross-border data transfer at the application layer. No Claude API calls. No US routing. The only remaining cross-border is Telegram and WhatsApp, which is inherent to those platforms (alert text only, no PII in practice).

---

## 3. Cross-Border Data Register

| Path | Destination | What | Status |
|------|------------|------|--------|
| Supabase | **af-south-1** | All telemetry, alarms, equipment | **Stays in SA** |
| Claude API | US | Diagnostic context, chat messages | **Eliminated with on-prem** (Ollama swap) |
| Telegram Bot API | UAE/NL/SG | Alert text, commands | Inherent to platform, alert text only |
| Meta WhatsApp | US/Ireland | Alert text, YES/NO replies | Inherent to platform, alert text only |
| Gmail SMTP | US/Google Cloud | Work order emails | Replaceable with on-prem SMTP |

**s72 basis:** Contractual necessity (s72(1)(b)) for service delivery + consent (s72(1)(a)) where applicable.

---

## 4. Security & Access Control

### RBAC — 3 Layers

| Layer | Mechanism | What It Does |
|-------|-----------|-------------|
| **Endpoint gating** | `require_role()` / `require_site_access()` FastAPI deps | Blocks unauthenticated/unauthorized users at the route level. ADMIN bypasses all checks. 6 role levels (ADMIN→ENGINEER→DEVELOPER→OPERATOR→AUDITOR→BOT_AGENT). |
| **Service-level auth** | `AuthorizationService.check_authorization()` | Command-level authorization — maps commands (e.g. `setpoint_adjust`) to required levels (e.g. TECHNICIAN), enforced at runtime before execution. |
| **Response shaping** | `presentation_guidance` in MCP tool output | Role-based view design — LLM-level instruction block. `get_site_status()` includes `audience: "senior_manager"` — suppresses ML internals, raw counts, point-level telemetry. Operators see full detail. Consistent with least-privilege access design. |

### Site Isolation (BOLA Prevention)

`require_site_access()` — deployed on 94 endpoints (verified by grep). ADMIN sees all sites. Non-admin users scoped to their assigned sites via `user_site_access` table or access profile. Equipment-level binding via `require_equipment_access()` (extracts site from equipment code, checks against user's access).

### Security Controls

| Area | Status |
|------|--------|
| Encryption at rest + in transit | Done |
| Auth (JWT + API keys + role hierarchy) | Done — `require_role()` on 109 endpoints across 17+ API files (verified by grep) |
| POPIA (consent gates, access controls, purpose limitation) | Designed in, cross-border register active |
| BOLA prevention | `require_site_access()` on 94 endpoints + `require_equipment_access()` on 35 endpoints (verified by grep) |
| Automated external-surface scan (OWASP ZAP + Kali) | Completed 2026-06-23 — all API/auth/BOLA/injection tests clean. Findings: expired origin SSL (fixed), API version leak (fixed), missing headers (fixed). |
| Third-party penetration testing | Scoped and budgeted — next phase after onboarding. Not yet performed. |
| Audit logging | Append-only, visitor + recommendation lifecycle |

---

## 5. Data Flow

```
BMS Site → SIMBIOT Adapter → Sentinel Backend
                                ├──→ Supabase af-south-1 (all data)
                                ├──→ Ollama (local LLM, on-prem path)
                                └──→ OpenClaw Gateway → Telegram / WhatsApp / Email

On-prem: everything above runs on customer-managed infra. Zero external API dependencies.
```

---

## 6. Key Statements for the Room

| If they ask... | Say |
|----------------|-----|
| "Where does data live?" | Core telemetry in Supabase af-south-1. Building data never leaves SA. |
| "On-prem?" | Verified in dev, deploy when you want it. Two changes: move the server, swap the LLM. |
| "Cross-border?" | Eliminated with on-prem deployment. Claude API is the only current external call. |
| "POPIA?" | Designed for it. Consent gates, access controls, purpose limitation from day one. Cross-border register documented with s72 basis. |
| "RBAC?" | 3 layers: endpoint gating (`require_role()` on 109 endpoints, 6 role levels), service-level auth (per-command), response shaping (manager vs operator views). Site isolation: `require_site_access()` on 94 endpoints — ADMIN sees all, others scoped to assigned sites. Verified by grep. |
| "Response shaping?" | Built in. Senior managers see status/drivers only — no ML internals, no raw telemetry, no maintenance backlog unless they ask. Operators see full detail. Least-privilege access design principle, consistent with role-based view design. |
| "Pen tested?" | Automated external-surface scan completed — all API/auth/BOLA/injection tests clean (June 2026). Findings were infra config only, all fixed. Third-party pen test is scoped as next phase — independent assessment with formal report deliverable. |
| "Who runs this?" | I built it. I run it. I'll own the rollout. COI: disclosed and approved. |

---

## 7. Prep Before Session

- Build the data flow slide (copy from section 5 above)
- Have s72 wording ready (contractual necessity + consent)
- That's it

The cross-border and on-prem questions are **answerable, not defensive**. The product solves the problem, the deployment is flexible, and the person in the room is the one who built it.
