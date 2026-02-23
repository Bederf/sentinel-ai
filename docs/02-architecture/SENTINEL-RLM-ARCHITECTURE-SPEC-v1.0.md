# SENTINEL + RLM Runner Architecture Specification v1.0

**Document**: Architecture Specification
**Version**: 1.0
**Date**: 2026-02-23
**Status**: Approved — all 10 sections locked
**Classification**: Internal / Vendor-Safe
**Pilot Site**: Site 002

---

## 1. Executive Summary

SENTINEL is a Building Management System (BMS) intelligence platform that monitors, analyses, and optimises building equipment across multiple sites. This document specifies the architecture for adding a Recursive Language Model (RLM) runner — a long-context evidence analysis service that extends SENTINEL's existing capabilities.

The RLM runner does not replace SENTINEL's existing LangGraph-based deterministic agents. It adds whole-case analysis over large evidence packs with recursive multi-pass investigation and an auditable trace. SENTINEL orchestrates; the runner analyses.

**Key design principles:**
- Runner is a black box behind port 8010 with a stable API contract
- Sentinel never knows or cares what runs behind that port
- Contract stays identical across all deployment targets (venv, Podman, GPU, SBC)
- Runner writes to filesystem only; Sentinel syncs to database
- All personal data is POPIA-governed throughout

---

## 2. System Context

### 2.1 Component Roles

| Component | Role | Runtime |
|-----------|------|---------|
| **Sentinel Backend** | API server, orchestration, business logic | FastAPI + systemd |
| **Sentinel Frontend** | Operator dashboard, case management | React + Vite |
| **LangGraph Agents** | Deterministic workflows, tool routing, scheduling | Inside backend process |
| **RLM Runner** | Long-context evidence analysis, recursive passes | Separate systemd service |
| **Ollama** | Local LLM inference (CPU) | Standalone, port 11434 |
| **Supabase** | Primary database (PostgreSQL) | Docker Compose |

### 2.2 Separation of Concerns

| System | Character |
|--------|-----------|
| SENTINEL | Controlled, appliance-like, predictable footprint |
| AimTheLaw | Experimental, heavy, k3s-based, growing |

These systems share a host in dev but are architecturally isolated. SENTINEL never runs inside k3s.

### 2.3 Data Flow

```
Evidence Ingestion → /var/lib/sentinel/cases/<case_id>/
                           │
                    Sentinel Backend
                     (orchestration)
                           │
                    POST /run ──→ RLM Runner (:8010)
                                      │
                                      ├─ reads evidence/
                                      ├─ calls Ollama (:11434)
                                      ├─ recursive passes
                                      │
                                      └─ writes /var/lib/sentinel/rlm_out/<run_id>/result.json
                           │
                    Sentinel reads result.json
                    Syncs to Supabase
                    Presents in UI
```

---

## 3. Operating Environment

### 3.1 Development Host (Current)

| Spec | Value |
|------|-------|
| Host | Contabo VPS |
| OS | Debian, kernel 6.1.0-43-cloud-amd64, KVM |
| CPU | AMD EPYC 8-core, 1 socket, no SMT |
| RAM | 24 GB |
| Disk | 200 GB ext4 |
| GPU | None |
| Network | Full internet access |

### 3.2 Production Target (Future)

| Spec | Value |
|------|-------|
| Platform | NVIDIA Jetson Orin NX (standard), Orin Nano (light), AGX (central hub) |
| RAM | 16 GB minimum |
| Storage | 512 GB NVMe minimum |
| GPU | Integrated NVIDIA (CUDA) |
| Cooling | Active |
| Topology | One SBC per site for local autonomy |

**Timeline:** Prototype in 6 months, first production 9-12 months, rollout year 2.

### 3.3 Network Policy

- Runner binds to `127.0.0.1` only
- In production: container with outbound internet blocked
- Only allowed to reach local inference server (Ollama/vLLM)

---

## 4. Process Management

### 4.1 Service Model

| Service | Runtime | User |
|---------|---------|------|
| Sentinel Backend | systemd + venv | `bederf` (migrate to dedicated user later) |
| Sentinel Frontend | systemd + npm preview | `bederf` |
| RLM Runner | systemd + venv (Podman later) | `sentinel-runner` (dedicated, created first) |
| Ollama | standalone daemon | system |
| Supabase | Docker Compose | docker |

**Rule:** SENTINEL never runs inside k3s. systemd + venv only, or Podman container.

### 4.2 Secrets Management

**Location:** `/etc/sentinel/` — root-owned, group-readable by service users.

| Secret Category | Examples |
|----------------|----------|
| Backend | JWT signing key, encryption key, Supabase credentials, API keys (Twilio, Meta, ElevenLabs) |
| Runner | MODEL_BASE_URL, MODEL_NAME allowlist, budget limits, feature flags |

**Rules:**
- No secrets in home directories
- No secrets in git
- No secrets in case folders
- No user credentials or evidence data in config

---

## 5. Runner API Contract

**This contract is locked. It must not change across deployment targets.**

### 5.1 Endpoints

```
POST /run              Submit analysis job
GET  /runs/{run_id}    Full result JSON
GET  /runs/{run_id}/trace    Trace only
GET  /health           Health check
```

### 5.2 Request

```json
POST /run
{
  "case_id": "TEST001",
  "question": "Summarise the key findings from this evidence pack",
  "model": "phi3:mini"
}
```

- `model` is optional — defaults to `MODEL_NAME` environment variable
- Runner validates model against an allowlist; rejects unknown models

### 5.3 Response

```json
{ "run_id": "TEST001_20260223_083012_ab12cd34", "status": "queued" }
```

**Run ID format:** `{case_id}_{YYYYMMDD}_{HHMMSS}_{8-char-hex}`

### 5.4 Result Schema

```json
{
  "status": "queued | running | complete | error | timeout",
  "summary": "...",
  "findings": [],
  "anomalies": [],
  "timeline": [],
  "recommended_actions": [],
  "confidence": 0.0,
  "needs_deeper_run": false,
  "trajectory": {
    "steps": 0,
    "files_read": 0,
    "bytes_read": 0,
    "elapsed_s": 0.0
  }
}
```

### 5.5 Budget Limits (Dev)

| Parameter | Value |
|-----------|-------|
| Max runtime per run | 120 seconds |
| Max recursion depth | 4-6 |
| Max tokens per LLM call | 600-1200 |
| Temperature | 0.1 |
| Max files read | 50 |
| Max bytes read | 50 MB |

If recursion hits depth limit: return partial result with `"needs_deeper_run": true`.

---

## 6. Inference Layer

### 6.1 Architecture

Runner uses **OpenAI-compatible HTTP** to call the local inference server. This keeps the backend swappable (Ollama today, vLLM or LM Studio tomorrow) without changing runner code.

### 6.2 Environment Configuration

```
MODEL_BASE_URL=http://127.0.0.1:11434/v1
MODEL_NAME=phi3:mini
EMBED_MODEL=nomic-embed-text
```

### 6.3 Model Selection

| Model | Size | Use case |
|-------|------|----------|
| phi3:mini | 2.2 GB | Default — best analysis quality that's CPU-viable |
| llama3.2:1b | 1.3 GB | Fast triage, field extraction, simple summarise |
| tinydolphin | 636 MB | Cheap summarise only — falls over on reasoning |
| nomic-embed-text | 274 MB | Embedding for RAG |

Model is a per-run override via the `model` field in the request. Runner validates against an allowlist.

### 6.4 Cross-Border Rule

Evidence and inference stay in South Africa. Cloud LLM calls only if: explicitly approved, data anonymised, and logged. Otherwise local models only.

---

## 7. Evidence & Data Model

### 7.1 Case Folder Schema

```
/var/lib/sentinel/cases/<case_id>/
├── manifest.json              # machine source of truth
├── evidence/                  # runner reads this + manifest only
│   ├── logs/                  # .jsonl, .csv, .log, .syslog
│   ├── documents/             # .pdf, .docx, .txt, .md
│   ├── media/                 # .png, .jpg, .jpeg, .webp
│   └── exports/               # .parquet, .json
├── metadata/                  # governance and audit
│   ├── tags.json
│   ├── chain_of_custody.json
│   └── notes.md
└── README.md                  # optional human summary
```

### 7.2 File Type Policy

**Allowed (v1):**

| Category | Extensions |
|----------|-----------|
| Structured | `.json`, `.jsonl`, `.csv`, `.parquet` |
| Documents | `.pdf`, `.docx`, `.txt`, `.md` |
| Logs | `.log`, `.jsonl`, `.syslog` |
| Media | `.png`, `.jpg`, `.jpeg`, `.webp` |

**Blocked — no exceptions:**

| Category | Extensions |
|----------|-----------|
| Executables | `.exe`, `.dll`, `.so` |
| Scripts | `.sh`, `.bat`, `.ps1` |
| Archives | `.zip`, `.tar`, `.gz`, `.7z`, `.rar`, `.iso` |

Compressed evidence must be unpacked and validated before entering the case folder.

### 7.3 Size Limits

| Scope | Soft cap | Hard cap | Typical |
|-------|----------|----------|---------|
| Per case (input) | 500 MB | 750 MB | varies |
| Per run output | — | 50 MB | < 10 MB |

Above hard cap: reject or require manual approval.

### 7.4 Filesystem Layout

```
/var/lib/sentinel/cases/<case_id>/…              evidence (inputs)
/var/lib/sentinel/rlm_out/<run_id>/result.json   analysis (outputs)
/var/log/rlm-runner/                              runner logs
/var/log/sentinel/                                sentinel logs
```

### 7.5 DB vs Filesystem Split

| Data | Where |
|------|-------|
| Evidence files, run outputs, traces | Filesystem |
| Case metadata, run status, result summaries, user assignments, audit trail | Supabase |

Runner writes to filesystem only. Sentinel reads `result.json` and syncs to database. Runner never touches Supabase directly.

---

## 8. Retention & Pruning

### 8.1 Retention Policy

| Data type | Retention | Notes |
|-----------|-----------|-------|
| Cases (evidence) | 180 days | Extendable per case; legal/compliance value |
| Run outputs/traces | 90 days | Operational artefacts; auto-delete |
| Model usage logs | 180 days | Runner-specific |
| Operational logs | 90 days | Inherited from Sentinel/FSR baseline |

### 8.2 Auto-Prune Script

**Implementation:** Python script (not shell). Weekly cron.

**Hard guards:**
- Only deletes under `/var/lib/sentinel/rlm_out`
- Refuses if resolved path is outside that directory
- Ignores symlinks
- Always keeps at least N most recent runs (configurable)

---

## 9. Security & Compliance

### 9.1 POPIA

**Applies fully.** All personal data is POPIA-governed.

**Sensitive categories:** PII (names, SA ID numbers, phone numbers, emails), financial data, client identifiers, internal asset IDs, location data linked to individuals.

**Ingestion:** Do NOT redact raw evidence. Preserve originals for audit.

**Output:** Runner MUST redact summaries, findings, and all UI-visible fields.

**Redaction targets:** SA ID numbers, phone numbers, email addresses, account numbers, customer IDs. Config stored centrally, not in runner code.

**Data Subject Access Requests:** Manual process initially (query, export, legal review). Automated later.

**Right to Deletion:** PII central to case — delete whole case. PII incidental — redact fields, regenerate outputs. Decision recorded in audit log.

### 9.2 Audit Trail (Append-Only)

| Event | What is logged |
|-------|---------------|
| Run lifecycle | Who triggered, when, case_id, model, budgets, status |
| File access | Files read (path + SHA256), size, timestamp |
| Model calls | Timestamp, model name, token counts, prompt hash, response hash |
| Result access | Who viewed, when, which fields |

**Do NOT store raw prompts or raw outputs in audit logs.**

Storage: database + immutable log file (WORM-style later).

### 9.3 Trace Access

| Role | Access level |
|------|-------------|
| Admin | Full trace: step log, file hashes, model metadata, prompt hashes, token usage |
| Operator | Redacted: no raw prompts, no sensitive paths, no raw excerpts |
| Other | No trace access |

Override to full trace: admin only, with audit log entry.

---

## 10. UI & Operator Workflow

### 10.1 Trigger Permissions

| Actor | Can trigger | Scope |
|-------|------------|-------|
| Operator | Yes | Assigned cases |
| Admin | Yes | Any case |
| LangGraph (system) | Yes | Conditional; must log trigger reason and rule |
| Read-only users | No | — |
| External API | No | Unless explicitly scoped |

### 10.2 Results Presentation

Integrated into the existing case page as an **Analysis tab**:

1. **Summary card** — status badge, summary, confidence, model, timestamp
2. **Findings** — structured bullet list
3. **Anomalies** — table: timestamp, source, severity
4. **Timeline** — vertical timeline component
5. **Recommended actions** — checklist-style
6. **View Trace** — button, opens separate role-gated page

Never dump raw JSON into the main UI.

### 10.3 Async Flow

1. User clicks "Analyse"
2. Status immediately changes to "Analysing" with spinner
3. UI polls every 5-10 seconds (no WebSocket for v1)
4. On complete: status updates, summary appears, optional toast
5. If user navigates away: run continues, result visible on return

### 10.4 Escalation

When `needs_deeper_run: true`:
- Banner: "Initial analysis incomplete. Deeper analysis recommended."
- Operator: approve deeper run or cancel
- Admin: force deeper run, override model
- LangGraph: auto-escalate only if policy allows, always with audit entry

### 10.5 Concurrency

**One active run per case.** If active: disable Analyse button, show "Run in progress." Admins can cancel.

---

## 11. CI/CD & Deployment

### 11.1 Repository Structure

Single repo. Runner alongside backend and frontend.

```
/opt/bms-intelligence/
  backend/              # Sentinel FastAPI
  frontend/             # Sentinel UI
  runner/               # RLM runner (NEW)
    app/
    tests/
    pyproject.toml
    requirements.txt    # pinned with hashes or uv lockfile
  infra/
    systemd/            # service unit files
    scripts/            # deploy, rollback scripts
```

Runner has its own venv. Separate requirements. Never shares deps with backend.

### 11.2 Branching & Releases

- Conventional commits, PR required, 1 review, all checks pass
- Component tags: `sentinel-vX.Y.Z`, `runner-vX.Y.Z`
- Runner can ship independently but always through main

### 11.3 Test Requirements (Merge Gate)

| Level | Scope |
|-------|-------|
| Unit | File type validation, manifest parsing, redaction, budget enforcement, state transitions |
| Contract | API schema compliance, needs_deeper_run behaviour |
| Integration | One smoke test: fixture case folder, mocked model client, no live Ollama |

### 11.4 Deployment

**Dev (systemd + venv):**
```bash
git pull origin main
/opt/rlm-runner/venv/bin/pip install -r runner/requirements.txt
systemctl restart rlm-runner.service
curl -sf http://127.0.0.1:8010/health
```

No auto-deploy from every merge. Manual trigger until ops are stable.

**Production (Podman, later):**
- Build container from `runner/`
- Tag with git SHA
- systemd runs container image
- Sentinel unchanged

### 11.5 Rollback

```
/opt/rlm-runner/
  venv/          # symlink → current
  venv_current/
  venv_prev/     # previous known-good
```

```bash
systemctl stop rlm-runner
ln -sfn venv_prev venv
git checkout runner-vX.Y.Z
systemctl start rlm-runner
```

**Rule:** Runner rolls back without touching Sentinel.

---

## 12. Scale & Roadmap

### 12.1 Growth Plan

| Phase | Sites | Runner concurrency |
|-------|-------|--------------------|
| Pilot | 1 (Site 002) | 1-2 |
| Early (12-18 mo) | 3-5 | 2-4/site |
| Medium (year 2) | 10-20 | 2-4/site |
| Long term | 30-50 | 5-10 centralised |

### 12.2 Tenancy

Single-tenant per site initially. Multi-tenant core only if needed at Phase 3 (separate schemas, storage roots, runner quotas).

### 12.3 Cloud Posture

On-prem / local first. Cloud allowed for: encrypted backups, offsite archive, anonymised cloud LLM. No live cloud dependency. Sentinel must run offline.

### 12.4 Integration Targets

| Timeframe | Systems |
|-----------|---------|
| Near term | BMS (Siemens, Schneider, Honeywell), BACnet, Modbus, OPC-UA via SIMBIOT |
| Medium term | Energy management, SCADA exports, CMMS |
| Long term | CCTV metadata, access control logs, fire panel logs |

Raw video and audio stay out unless strong compliance case.

---

## Appendix A: Building Onboarding

Building data ingestion uses the **SIMBIOT** pipeline (Phase 112, in progress):
- Replaces static JSON with simulation data adapter
- Reads equipment + sensor readings from Supabase
- Routing: BACnet → Simulation (Supabase) → JSON fallback
- Frontend wizard: "Connect BMS" or "Discover from Simulation"

SIMBIOT is the building onboarding path. Runner analysis is a separate concern that consumes case evidence. These pipelines must not be conflated.

---

## Appendix B: Existing Sentinel Agents

The RLM runner does not replace these. They continue to operate as-is.

| Agent | Framework | LLM Usage | Purpose |
|-------|-----------|-----------|---------|
| Recommendation Graph | LangGraph StateGraph | Zero (deterministic) | Process pending recommendations through approval/execution lifecycle |
| Desk Complaint Graph | LangGraph StateGraph | Zero (NLP regex) | Multi-turn complaint resolution |
| Background Scheduler | APScheduler | N/A | Periodic jobs (demo data, feedback, health sim) |
| HybridAI Router | Custom service | Routes to Ollama or Claude | Task-appropriate model selection |

**How they work together:** LangGraph decides when analysis is needed and creates the case workspace. It calls the runner via POST /run and presents results in the UI.

---

**End of document.**
**Approved:** 2026-02-23
**Implemented:** Phase 113 (2026-02-23) -- runner foundation, LLM analysis engine, Sentinel integration, and deployment infrastructure. See [Phase 113 feature doc](../04-features/113-rlm-runner-service.md).
**Next step:** Wire the first end-to-end pilot on Site 002.
