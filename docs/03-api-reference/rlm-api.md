---
title: "RLM Runner & Orchestration API"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "Sentinel Development Team"
tags: ["rlm", "runner", "analysis", "api", "evidence"]
related: ["../04-features/113-rlm-runner-service.md", "../02-architecture/SENTINEL-RLM-ARCHITECTURE-SPEC-v1.0.md"]
domain: "general"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 10
---

# RLM Runner & Orchestration API

REST API for submitting evidence cases to the RLM runner for long-context analysis, retrieving results, and checking service health.

Two API layers exist:

| Layer | Base URL | Auth | Purpose |
|-------|----------|------|---------|
| **Runner (direct)** | `http://127.0.0.1:8010` | None (localhost only) | Standalone analysis service |
| **Orchestration (proxy)** | `/api/rlm` | Required (JWT) | Frontend-facing, feature-gated |

The orchestration layer in the Sentinel backend proxies to the runner. Frontend clients always use the orchestration endpoints.

## Feature Gate

The orchestration router is gated behind `RLM_RUNNER_ENABLED` (default: `false`).

| Setting | Env Var | Default | Description |
|---------|---------|---------|-------------|
| Enabled | `RLM_RUNNER_ENABLED` | `false` | Must be `true` to accept requests |
| Runner URL | `RLM_RUNNER_URL` | `http://127.0.0.1:8010` | Runner base URL |
| Timeout | `RLM_TIMEOUT_SECONDS` | `120` | HTTP timeout for runner calls |

When disabled, all orchestration endpoints return `409 Conflict`.

---

## Orchestration Endpoints (Backend)

Prefix: `/api/rlm`. All endpoints require authentication.

### POST /api/rlm/cases/{case_id}/analyse

Submit a case for analysis. Returns immediately with a run ID for polling.

**Status code:** `202 Accepted`

**Request:**

```json
{
  "question": "Summarise the key findings from this evidence pack",
  "model": "phi3:mini"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `question` | string | Yes | Analysis prompt (1-2000 chars) |
| `model` | string | No | Model override; defaults to runner config |

**Response:**

```json
{
  "run_id": "TEST001_20260223_083012_ab12cd34",
  "status": "queued"
}
```

**Error responses:**

| Code | Condition |
|------|-----------|
| 409 | `RLM_RUNNER_ENABLED=false` |
| 503 | Runner service unreachable |

### GET /api/rlm/runs/{run_id}

Retrieve the full result for an analysis run.

**Response:** See [Result Schema](#result-schema) below.

**Error responses:**

| Code | Condition |
|------|-----------|
| 404 | Run not found |
| 409 | RLM disabled |
| 503 | Runner unreachable |

### GET /api/rlm/runs/{run_id}/trace

Retrieve the audit trace for a run. Role-gated: admins see full trace, operators see redacted trace.

**Response:** Array of [Trace Entry](#trace-entry) objects.

**Error responses:**

| Code | Condition |
|------|-----------|
| 404 | Trace not found |
| 409 | RLM disabled |
| 503 | Runner unreachable |

### GET /api/rlm/health

Check runner health and feature gate status.

**Response:**

```json
{
  "enabled": true,
  "runner_available": true
}
```

---

## Runner Endpoints (Direct)

Base URL: `http://127.0.0.1:8010`. No authentication (bound to localhost only).

### POST /run

Submit an analysis job. Validates the model against the allowlist, creates the run, launches background analysis, and returns immediately.

**Request:**

```json
{
  "case_id": "TEST001",
  "question": "Summarise the key findings from this evidence pack",
  "model": "phi3:mini"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `case_id` | string | Yes | Case folder name under `CASES_DIR` |
| `question` | string | Yes | Analysis prompt |
| `model` | string | No | Must be in allowlist; defaults to `MODEL_NAME` |

**Response (200):**

```json
{
  "run_id": "TEST001_20260223_083012_ab12cd34",
  "status": "queued"
}
```

**Run ID format:** `{case_id}_{YYYYMMDD}_{HHMMSS}_{8-char-hex}`

**Error responses:**

| Code | Condition |
|------|-----------|
| 400 | Model not in allowlist |
| 404 | Case folder not found |

### GET /runs/{run_id}

Return the full result JSON for a run, regardless of current status.

**Response:** See [Result Schema](#result-schema).

| Code | Condition |
|------|-----------|
| 404 | Run not found |

### GET /runs/{run_id}/trace

Return the trace log (array of trace entries from `trace.jsonl`).

**Response:** Array of [Trace Entry](#trace-entry) objects.

| Code | Condition |
|------|-----------|
| 404 | Trace not found |

### GET /health

Service health check. Probes Ollama via the OpenAI-compatible `/v1/models` endpoint.

**Response:**

```json
{
  "status": "ok",
  "version": "1.0.0",
  "ollama_available": true
}
```

---

## Schemas

### Result Schema

Returned by `GET /runs/{run_id}` (both layers).

```json
{
  "status": "complete",
  "summary": "Analysis identified 3 key findings...",
  "findings": ["Finding 1", "Finding 2"],
  "anomalies": [
    {"timestamp": "2026-02-23T08:30:00Z", "source": "access_log.csv", "severity": "high"}
  ],
  "timeline": [
    {"timestamp": "2026-02-23T06:00:00Z", "event": "System startup"}
  ],
  "recommended_actions": ["Review access logs for anomalous entries"],
  "confidence": 0.72,
  "confidence_label": "high",
  "needs_deeper_run": false,
  "trajectory": {
    "steps": 3,
    "files_read": 12,
    "bytes_read": 524288,
    "elapsed_s": 45.2
  },
  "scoring": {
    "version": 1,
    "threshold_medium": 0.4,
    "threshold_high": 0.7
  },
  "model_name": "phi3:mini",
  "model_provider": "ollama"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `status` | enum | `queued`, `running`, `complete`, `error`, `timeout` |
| `summary` | string | Human-readable summary of findings |
| `findings` | string[] | Structured list of findings |
| `anomalies` | object[] | Detected anomalies with timestamp, source, severity |
| `timeline` | object[] | Chronological event timeline |
| `recommended_actions` | string[] | Suggested next steps |
| `confidence` | float | Analysis confidence score (0.0 - 1.0). Stable for ML consumers. |
| `confidence_label` | enum | Computed from `confidence` using `scoring` thresholds. `"low"` / `"medium"` / `"high"`. For UI display and policy rules. |
| `needs_deeper_run` | bool | `true` if budget was exhausted before analysis completed |
| `trajectory` | object | Execution metrics (steps, files, bytes, time) |
| `scoring` | object | Snapshot of scoring config at result time: `version` (int), `threshold_medium` (float), `threshold_high` (float). Enables audit of old runs when thresholds change. Configurable via `SCORING_VERSION`, `CONFIDENCE_THRESHOLD_HIGH`, `CONFIDENCE_THRESHOLD_MEDIUM` env vars. |
| `model_name` | string | Model used for inference (e.g., `"phi3:mini"`) |
| `model_provider` | string | Inference backend (always `"ollama"` — local only) |

### Trace Entry

Single entry in the audit trace.

```json
{
  "timestamp": "2026-02-23T08:30:12.456Z",
  "event_type": "file_access",
  "details": {
    "path": "evidence/logs/access.csv",
    "sha256": "a1b2c3d4...",
    "size_bytes": 12345
  }
}
```

| Event Type | Details |
|------------|---------|
| `file_access` | `path`, `sha256`, `size_bytes` |
| `model_call` | `model`, `prompt_hash`, `response_hash`, `tokens_in`, `tokens_out` |
| `state_change` | `from_status`, `to_status` |
| `analysis_step` | `pass_number`, `findings_count` |

Raw prompts and raw LLM responses are never stored in the trace. Only SHA256 hashes are recorded for auditability.

---

## Polling Pattern

Analysis runs asynchronously. The recommended polling pattern:

```python
# 1. Submit
response = await client.post("/api/rlm/cases/TEST001/analyse", json={
    "question": "Summarise key findings"
})
run_id = response.json()["run_id"]

# 2. Poll every 5-10 seconds
while True:
    result = await client.get(f"/api/rlm/runs/{run_id}")
    data = result.json()
    if data["status"] in ("complete", "error", "timeout"):
        break
    await asyncio.sleep(5)

# 3. Check needs_deeper_run
if data["needs_deeper_run"]:
    # Budget was exhausted — offer operator the option to rerun
    pass
```

---

## Budget Limits

The runner enforces per-run resource limits:

| Parameter | Default | Env Var |
|-----------|---------|---------|
| Max runtime | 120s | `MAX_RUNTIME_SECONDS` |
| Max recursion depth | 6 | `MAX_RECURSION_DEPTH` |
| Max tokens per LLM call | 1200 | `MAX_TOKENS_PER_CALL` |
| Temperature | 0.1 | `TEMPERATURE` |

When budget is exhausted, the run completes with `needs_deeper_run: true` and partial results.

## Related

- [Phase 113: RLM Runner Service](../04-features/113-rlm-runner-service.md) -- feature overview
- [Architecture Spec](../02-architecture/SENTINEL-RLM-ARCHITECTURE-SPEC-v1.0.md) -- full specification
