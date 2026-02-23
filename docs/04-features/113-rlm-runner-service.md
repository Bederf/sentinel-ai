---
title: "Phase 113: RLM Runner Service"
type: "spec"
status: "approved"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "Sentinel Development Team"
tags: ["rlm", "runner", "llm", "analysis", "evidence", "popia", "redaction"]
related: ["../03-api-reference/rlm-api.md", "../02-architecture/SENTINEL-RLM-ARCHITECTURE-SPEC-v1.0.md"]
domain: "general"
audience: "developers"
complexity: "advanced"
estimated_read_time: 12
---

# Phase 113: RLM Runner Service

Standalone long-context evidence analysis service that extends SENTINEL with recursive multi-pass LLM investigation over large evidence packs. The runner is a black box behind port 8010 with a stable API contract -- SENTINEL orchestrates, the runner analyses.

## Overview

The RLM (Recursive Language Model) runner does not replace SENTINEL's existing LangGraph agents. It adds whole-case analysis for scenarios requiring deep investigation of large evidence packs (logs, documents, data exports) with auditable traces and POPIA-compliant output redaction.

```
Sentinel Backend ──POST /run──> RLM Runner (:8010)
                                     |
                                     +-- reads case evidence
                                     +-- calls Ollama (:11434)
                                     +-- recursive multi-pass analysis
                                     +-- writes result.json + trace.jsonl
                                     |
Sentinel Backend <──GET /runs/──── reads result, syncs to DB
```

## Key Design Principles

- **Black box contract**: Runner exposes 4 HTTP endpoints. Sentinel never knows what runs behind port 8010.
- **Deployment-agnostic**: Same contract across venv, Podman, GPU SBC. No code changes.
- **Filesystem-only writes**: Runner writes to `/var/lib/sentinel/rlm_out/`. Never touches Supabase.
- **Feature-gated**: Disabled by default (`RLM_RUNNER_ENABLED=false`). Must be explicitly enabled.
- **Local inference**: Uses Ollama via OpenAI-compatible `/v1/chat/completions`. No cloud LLM calls.

## Architecture

### Components

| Component | Location | Responsibility |
|-----------|----------|----------------|
| **Runner App** | `runner/app/main.py` | FastAPI service, CORS localhost-only |
| **CaseLoader** | `runner/app/services/case_loader.py` | Reads manifest, enumerates evidence, validates file types |
| **RunManager** | `runner/app/services/run_manager.py` | State machine, atomic writes, trace management |
| **InferenceClient** | `runner/app/services/inference_client.py` | OpenAI-compatible HTTP client for Ollama |
| **RecursiveAnalyzer** | `runner/app/services/recursive_analyzer.py` | Multi-pass analysis with budget enforcement |
| **RedactionService** | `runner/app/services/redaction_service.py` | POPIA PII redaction on output |
| **TraceBuilder** | `runner/app/services/trace_builder.py` | Typed trace entries (file access, model calls, state changes) |
| **RLMRunnerClient** | `backend/app/services/rlm_runner_client.py` | Async HTTP proxy from Sentinel to runner |
| **Orchestration Router** | `backend/app/api/rlm_orchestration.py` | Auth-gated `/api/rlm/*` endpoints |

### State Machine

Runs follow a strict state machine with valid transitions only:

```
queued --> running --> complete
                  --> error
                  --> timeout
```

No implicit state paths. Invalid transitions are rejected.

### Analysis Flow

1. **Submit**: `POST /run` validates model against allowlist, checks case folder exists, creates run, returns `run_id` immediately.
2. **Background task**: `asyncio.create_task()` launches analysis. Status changes to `running`.
3. **Case loading**: CaseLoader reads `manifest.json`, enumerates evidence files, validates file types and sizes.
4. **Recursive analysis**: RecursiveAnalyzer reads text-based evidence, builds structured prompts, calls LLM via InferenceClient, accumulates findings. Multiple passes if the LLM signals further investigation is needed.
5. **Budget enforcement**: Time (120s default) and depth (6 passes default) limits. If exhausted, returns partial results with `needs_deeper_run: true`.
6. **Redaction**: RedactionService scrubs POPIA-governed PII from all output fields before writing.
7. **Result write**: Atomic write (tmp + rename) of `result.json` to output directory.

## Case Evidence

### Folder Structure

```
/var/lib/sentinel/cases/<case_id>/
  manifest.json              # Machine source of truth
  evidence/
    logs/                    # .jsonl, .csv, .log, .syslog
    documents/               # .pdf, .docx, .txt, .md
    media/                   # .png, .jpg, .jpeg, .webp
    exports/                 # .parquet, .json
```

### File Type Policy

| Allowed | Blocked |
|---------|---------|
| `.json`, `.jsonl`, `.csv`, `.parquet` | `.exe`, `.dll`, `.so` |
| `.pdf`, `.docx`, `.txt`, `.md` | `.sh`, `.bat`, `.ps1` |
| `.log`, `.syslog` | `.zip`, `.tar`, `.gz`, `.7z`, `.rar`, `.iso` |
| `.png`, `.jpg`, `.jpeg`, `.webp` | |

Unknown extensions are treated as blocked (fail-closed). Compressed evidence must be unpacked before ingestion.

### Size Limits

| Scope | Soft Cap | Hard Cap |
|-------|----------|----------|
| Per case (input) | 500 MB | 750 MB |
| Per run output | -- | 50 MB |

### Path Traversal Protection

Case IDs are validated via `resolve() + startswith()` to prevent directory traversal attacks. A case ID like `../etc` is rejected.

## POPIA Redaction

The RedactionService applies SA-specific PII patterns to all output fields:

| Pattern | Method |
|---------|--------|
| SA ID numbers (13-digit) | Luhn checksum validation to prevent false positives |
| Phone numbers (+27, 0XX formats) | Negative lookbehind/lookahead to avoid overlap with SA ID digits |
| Email addresses | Standard email regex |
| Credit card numbers | Luhn-validated |
| Account numbers | ACC-/CUST- prefix patterns |

Redaction applies to output only -- raw evidence is preserved for audit integrity.

## Audit Trace

Every run produces a `trace.jsonl` file with append-only entries. No raw prompts or raw LLM responses are stored -- only hashes.

| Event Type | Details Recorded |
|------------|-----------------|
| `file_access` | File path, SHA256 hash, size |
| `model_call` | Model name, prompt hash, response hash, token counts |
| `state_change` | From/to status |
| `analysis_step` | Pass number, findings count |

Trace access is role-gated: admins see full trace, operators see redacted trace.

## Configuration

### Runner Settings

All configurable via environment variables:

| Setting | Default | Description |
|---------|---------|-------------|
| `HOST` | `127.0.0.1` | Bind address (localhost only) |
| `PORT` | `8010` | Service port |
| `CASES_DIR` | `/var/lib/sentinel/cases` | Evidence input directory |
| `OUTPUT_DIR` | `/var/lib/sentinel/rlm_out` | Analysis output directory |
| `MODEL_BASE_URL` | `http://127.0.0.1:11434/v1` | Ollama OpenAI-compatible endpoint |
| `MODEL_NAME` | `phi3:mini` | Default model |
| `MODEL_ALLOWLIST` | phi3:mini, llama3.2:1b, tinydolphin, nomic-embed-text | Allowed models |
| `MAX_RUNTIME_SECONDS` | `120` | Per-run time budget |
| `MAX_RECURSION_DEPTH` | `6` | Maximum analysis passes |
| `MAX_TOKENS_PER_CALL` | `1200` | Token limit per LLM call |
| `TEMPERATURE` | `0.1` | LLM temperature |

### Backend Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `RLM_RUNNER_ENABLED` | `false` | Feature gate |
| `RLM_RUNNER_URL` | `http://127.0.0.1:8010` | Runner base URL |
| `RLM_TIMEOUT_SECONDS` | `120` | HTTP timeout for runner calls |

## Deployment

### systemd Service

The runner runs as `sentinel-runner` (dedicated system user) with security hardening:

- `ProtectSystem=strict` -- read-only filesystem except allowed paths
- `NoNewPrivileges=true` -- no privilege escalation
- `ReadWritePaths` limited to output directory and log directory
- `ReadOnlyPaths` for case evidence and install directory
- Bound to `127.0.0.1:8010` (no external access)

Unit file: `infra/systemd/rlm-runner.service`

### Deploy Script

`infra/scripts/deploy-rlm-runner.sh` handles:

1. Creates `sentinel-runner` system user
2. Creates required directories with correct ownership
3. Builds Python venv with rollback support (`venv_prev` backup)
4. Symlinks runner code
5. Installs systemd unit
6. Runs health check

### Rollback

```
/opt/rlm-runner/
  venv/          # symlink -> current
  venv_current/
  venv_prev/     # previous known-good
```

```bash
systemctl stop rlm-runner
ln -sfn venv_prev venv
systemctl start rlm-runner
```

Runner rolls back independently without affecting Sentinel.

### Output Pruning

`infra/scripts/prune-rlm-outputs.py` runs weekly via cron:

- 90-day retention for run outputs
- Keeps minimum 5 most recent runs per case
- Hardcoded base path (`/var/lib/sentinel/rlm_out`) with validation
- Ignores symlinks
- Supports `--dry-run` mode

## Filesystem Layout

```
/var/lib/sentinel/cases/<case_id>/...        # Evidence (inputs)
/var/lib/sentinel/rlm_out/<run_id>/          # Analysis (outputs)
  result.json                                # Full result schema
  trace.jsonl                                # Audit trace
/var/log/rlm-runner/                         # Runner logs
/etc/sentinel/                               # Secrets (root-owned)
```

## Test Coverage

53 tests across 6 test files:

| File | Tests | Scope |
|------|-------|-------|
| `runner/tests/test_api_contract.py` | 8 | Health, submit, invalid model, missing case, result, trace |
| `runner/tests/test_case_loader.py` | 8 | Valid load, missing manifest, file types, path traversal, size limits |
| `runner/tests/test_run_manager.py` | 13 | ID format, state transitions, atomic writes, trace |
| `runner/tests/test_inference_client.py` | 5 | HTTP calls, retry, token tracking |
| `runner/tests/test_redaction_service.py` | 6 | SA ID, phone, email, credit card, deep-walk |
| `runner/tests/test_recursive_analyzer.py` | 7 | Single/recursive passes, budget, error handling, redaction |
| `backend/tests/services/test_rlm_runner_client.py` | 6 | Submit, unavailable, result, poll, disabled |

## Related

- [RLM API Reference](../03-api-reference/rlm-api.md) -- endpoint details and schemas
- [Architecture Specification](../02-architecture/SENTINEL-RLM-ARCHITECTURE-SPEC-v1.0.md) -- full system design
