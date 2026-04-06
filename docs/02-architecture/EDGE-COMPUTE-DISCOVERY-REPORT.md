---
title: "SENTINEL Edge Compute Discovery Report"
type: "architecture"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-03-31"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# SENTINEL Edge Compute Discovery Report

**Date:** 2026-03-11 | **Target Hardware:** Jetson Orin Nano Super (8GB) | **Status:** Discovery Complete

---

## Executive Summary

**Verdict: The Orin Nano Super (8GB) is NOT sufficient. The Orin NX 16GB is REQUIRED.**

The DeepSeek-R1-Distill-Qwen-14B at 4-bit quantisation alone consumes 7-8GB. SENTINEL's ML inference stack (TensorFlow LSTM + Autoencoder models) requires ~150-200MB at runtime, and the FastAPI backend with all services requires ~300-500MB. There is no memory headroom for concurrent LLM + ML inference on 8GB.

With the Orin NX 16GB, the system fits: ~8GB LLM + ~0.5GB ML + ~0.5GB FastAPI + ~2GB OS = ~11GB peak, leaving ~5GB headroom for CUDA overhead and bursts.

---

## 1. LLM Inference (AIOptimizerService)

### Location & Structure
- **File:** `backend/app/services/ai_optimizer.py` (3,095 lines)
- **Class:** `AIOptimizerService` (singleton via `get_ai_optimizer()`)
- **LLM Client:** `backend/app/services/claude_service.py` (line 383-536)

### Trigger Mechanism
- **APScheduler Job ID:** `run_optimization_analysis`
- **Poll interval:** Every 30 seconds real-time; fires when 8 sim-hours elapsed OR 900s (15 min) real-time fallback
- **Occupied-hours gating:** YES — **Weekdays 07:00-17:59 only**. Skips weekends and 19:00-06:59.
- **Additional gates:** Site must be in `automatic` mode; `optimization_enabled` flag must be true
- **max_instances:** 1 (no overlap)

### Current Model Target
- **Background model:** `claude-haiku-4-5-20251001` (cost-optimised constant `BACKGROUND_AI_MODEL` in `settings.py:9`)
- **Interactive model:** `claude-sonnet-4-20250514` (default `claude_model` in `settings.py:65`)
- **Provider routing:** Supports `anthropic`, `openai`, `zai` via `settings.ai_cloud_provider`
- **Configurable override:** `settings.optimization_model` can override per-environment

### Prompt Assembly — What's Injected
The prompt is built by `_build_optimization_prompt()` (lines 1050-1350) and includes:

| Section | Source | Approx Tokens |
|---------|--------|---------------|
| System instructions | Hardcoded JSON schema + rules | ~800 |
| Current conditions | `_gather_current_conditions()` — telemetry snapshot | ~500-1,000 |
| Equipment inventory | Device manager — types, health scores, anomalies | ~300-800 |
| ML context | `_gather_ml_context()` — LSTM forecasts, anomaly scores, fault classifications, health trends | ~400-800 |
| Decision memory | Recent decisions + outcomes + patterns | ~200-500 |
| Module success rates | ML feedback service scores | ~100-200 |
| Building schedule | Occupancy data, time-of-day | ~100-200 |
| Optimization profile | Active profile constraints | ~100-200 |
| Lighting zones | DALI zone data (if lighting module active) | ~200-400 |

**Estimated total prompt size:** ~2,500-5,000 tokens typical, up to ~8,000 tokens worst case with full fleet.

### Generation Config
- **max_tokens:** 1,536 (from `settings.claude_max_tokens`, `settings.py:66`)
- **Streaming:** Yes — `_llm_service.stream_response()` with async generator
- **Response format:** JSON (parsed from markdown code blocks)

### Blocking Behavior
- **Non-blocking / async:** Uses `async for chunk in stream_response()` — does not block the event loop
- **max_instances=1:** Only one optimization run at a time, but other scheduler jobs run concurrently

### Files Referencing LLM Client (19 files)
```
backend/app/services/ai_optimizer.py          ← PRIMARY (optimization)
backend/app/services/claude_service.py        ← Anthropic client wrapper
backend/app/services/openai_service.py        ← OpenAI provider
backend/app/services/zai_service.py           ← ZAI provider
backend/app/services/ollama_client.py         ← Ollama local LLM client (EXISTS)
backend/app/services/hybrid_ai_service.py     ← Ollama+Claude routing
backend/app/services/query_handler.py         ← Chat/query responses
backend/app/services/explanation_service.py   ← Natural-language explanations
backend/app/services/maintenance_recommender.py ← Maintenance suggestions
backend/app/services/email_intake_agent.py    ← Email classification
backend/app/services/checklist_generator_service.py ← Dynamic checklists
backend/app/services/job_card_processing_service.py ← Job card parsing
backend/app/services/digital_twin_service.py  ← Digital twin narratives
backend/app/services/rag_service.py           ← RAG retrieval
backend/app/services/ocr_service.py           ← Document OCR
backend/app/services/vision_service.py        ← Image analysis
backend/app/services/tts_service.py           ← Text-to-speech
backend/app/services/phyphox_analyzer.py      ← Vibration analysis
backend/app/services/ai_interfaces.py         ← Abstract LLM interface
```

**Key finding:** `ollama_client.py` already exists — Ollama integration has been partially built. The edge deployment needs to route `ai_optimizer.py` through this client instead of `claude_service.py`.

---

## 2. ML Inference Services

### A. LSTMInferenceService

| Aspect | Detail |
|--------|--------|
| **File** | `backend/app/services/ml_inference.py` (lines 34-191) |
| **Pattern** | Lazy-loading singleton via `get_lstm_service()` |
| **Framework** | TensorFlow/Keras (lazy-imported) |
| **Architecture** | 3-layer LSTM (128-64-32 units), batch norm, dropout, L2 |

**7 Active Equipment Types:**
1. Chiller — 5 features (chw_supply_temp, chw_return_temp, suction_pressure, discharge_pressure, compressor_current)
2. AHU — 5 features (supply_temp, return_temp, filter_dp, fan_current, mixed_air_temp)
3. Generator — 4 features
4. FCU — 3 features
5. UPS — 3 features
6. VAV — 5 features
7. Pump — 5 features

**Trigger:** On-demand only (API calls, Claude context bridge). No scheduled execution.
**Input window:** 168 hours (7 days)
**Forecast horizons:** 24h, 48h, 72h
**Loading:** Lazy — models NOT loaded until first `.predict()` call. Cache invalidated on registry generation change.
**Per-model memory:** ~1.6 MB .h5 + ~100 KB scaler
**Runtime footprint (all 7 loaded):** ~50 MB base + 7 × 1.7 MB = ~62 MB

### B. AnomalyDetectionService

| Aspect | Detail |
|--------|--------|
| **File** | `backend/app/services/ml_inference.py` (lines 194-401) |
| **Pattern** | Lazy-loading singleton via `get_anomaly_service()` |
| **Architecture** | Autoencoder (24→16→8→4→8→16→24) |
| **Detection** | Reconstruction error vs 99th percentile threshold |

**7+ Active Equipment Types:** Same as LSTM (chiller, ahu, generator, fcu + others)
**Trigger:** On-demand (API, alert pipeline, Claude context bridge)
**Input window:** 24 hours
**Per-model memory:** 2-4 MB .h5 + ~100 KB scaler
**Runtime footprint (all loaded):** ~50 MB base + 7 × 4 MB = ~78 MB

### C. FailureClassificationService

| Aspect | Detail |
|--------|--------|
| **File** | `backend/app/services/classification_service.py` |
| **Pattern** | Singleton, direct instantiation (not lazy) |
| **Algorithm** | Random Forest (sklearn), 100 trees, max_depth=10 |

**5 Equipment Types:** Chiller (6 classes), AHU (6), Generator (6), FCU (5), UPS (5)
**Trigger:** On-demand (anomaly chain, work order creation)
**Per-model memory:** 0.6-0.9 MB joblib
**Runtime footprint:** ~20 MB base + 5 × 0.8 MB = ~24 MB

### D. Survival Analysis (RUL)

| Aspect | Detail |
|--------|--------|
| **File** | `backend/app/services/survival_service.py` |
| **Algorithm** | Cox Proportional Hazards (lifelines) |
| **Model** | 1 universal model, C-index 0.897 |
| **Size** | 33 KB joblib |
| **Runtime footprint** | ~10 MB |

### ML Inference Summary

| Service | Models | Per-Model | Total Runtime | Loading |
|---------|--------|-----------|---------------|---------|
| LSTM | 7 | 1.7 MB | ~62 MB | Lazy |
| Autoencoder | 7 | 4 MB | ~78 MB | Lazy |
| Classifier | 5 | 0.8 MB | ~24 MB | Direct |
| Survival | 1 | 33 KB | ~10 MB | Lazy |
| **Total** | **20** | — | **~174 MB** | — |

**Note:** TensorFlow itself adds ~150-300 MB to process memory on import. Total ML runtime footprint including TF: **~350-500 MB**.

---

## 3. ML Training Pipeline (SentinelMLFeeder)

| Aspect | Detail |
|--------|--------|
| **File** | `backend/app/services/sentinel_ml_feeder.py` |
| **Secondary** | `backend/ml/training/retraining_scheduler.py`, `background_scheduler.py` |
| **Trigger** | After 500 simulated hours data → rechecks every 24 hours |
| **Retraining job** | `ml_retraining` — 86,400s (24h) interval, trains 1 stale model per cycle |

### Real Wall-Clock Training Frequency
- Simulation at 10× speed: 500 sim-hours = 50 real hours (~2 days) for initial
- After initial: 1 model retrained per 24 real hours (if stale >30 days or R² <0.65)
- **On physical BMS (no simulator):** Data accumulates in real-time. 500 hours = ~21 days of real equipment data before first training.

### Training Data Source
- **Simulation mode:** In-memory buffers in `SentinelMLFeeder._buffers` (accumulated per equipment type)
- **Production mode:** Supabase `equipment_sensor_readings` table (or local telemetry buffer)
- **Edge consideration:** Needs local telemetry storage — currently depends on Supabase

### Training Artifacts
- Output: `.h5` + `_scaler.joblib` per model
- Path: `backend/ml/models/{lstm|autoencoder}/` — **hardcoded, not configurable**
- No `MODEL_STORAGE_PATH` environment variable exists

### Training vs Inference Blocking
- **Training runs synchronously in the same process** — BLOCKS inference during training
- Training a single LSTM model takes ~30-120 seconds on x86 CPU
- On Jetson Orin: expect ~2-5× slower → 1-10 minutes per model
- **Critical:** Training allocates additional GPU/CPU memory. If LLM is loaded, OOM is likely on 8GB.

### Can Training Be Disabled on Edge?
- No explicit `DISABLE_ML_TRAINING` flag exists
- The `ml_retraining` job can be prevented by not registering it in startup
- **Recommendation:** Add an `EDGE_MODE=true` flag that skips training job registration. Train centrally, push models to edge.

---

## 4. SIMBIOT / Telemetry Pipeline

| Aspect | Detail |
|--------|--------|
| **MCP Server** | `backend/app/mcp/simbiot_server.py` (MCP tools for AI chat) |
| **Device Abstraction** | `backend/app/services/device_abstraction.py` |
| **Data Source** | Protocol-agnostic: BACnet, Modbus TCP, DALI-2, REST |

### On Physical Edge
- **Data source:** Desigo BMS over IP (BACnet/IP or Modbus TCP), DALI-2 via gateway
- **Polling interval:** Configurable per protocol adapter — typically 15-60 seconds
- **Device manager:** In-memory device state cache, updated per poll

### Local Telemetry Buffer
- **Current:** Writes to Supabase `equipment_sensor_readings` table
- **Air-gapped fallback:** JSON files in `backend/app/data/` (readings.json — currently 23.65 MB)
- **Edge requirement:** SQLite or local PostgreSQL to replace Supabase for telemetry persistence
- **Memory footprint:** Device manager ~50-100 MB at steady state (depends on equipment count)

### Continuous vs Scheduled
- **Device polling:** Continuous (runs as long as the process is alive)
- **Telemetry ingestion:** Event-driven (writes on each poll cycle)

---

## 5. Outcome Verification Service

| Aspect | Detail |
|--------|--------|
| **File** | `backend/app/services/recommendation_outcome_service.py` (403 lines) |
| **Job ID** | `outcome_verification` |
| **Interval** | 300 seconds (5 minutes) |
| **Settling period** | 30 minutes post-execution |
| **max_instances** | 1 |

### What It Compares
- Reads current sensor value from device manager (in-memory) or Supabase telemetry
- Compares against recommendation's `recommended_value`
- Tolerances: HVAC setpoint ±1.5°C, lighting ±15%, generic ±10%

### Output Destinations
1. Updates `recommendations` table (outcome_validated, outcome_notes)
2. Records to Decision Memory Service (JSON-based)
3. Records to ML Feedback Service

### Memory/CPU Footprint
- **Lightweight:** ~5-10 MB. Simple value comparison, no ML inference.

---

## 6. Decision Memory & Feedback Services

| Service | File | Persistence | Memory |
|---------|------|-------------|--------|
| **Decision Memory** | `backend/app/services/decision_memory_service.py` | **JSON only** (`decision_records.json`, `decision_patterns.json`) | ~20 MB |
| **ML Feedback** | `backend/app/services/ml_feedback_service.py` | JSON (`ml_feedback_records.json`) + Supabase | ~10 MB |
| **Outcome Repository** | `backend/app/database/repositories/outcome_repository.py` | Supabase + JSON fallback (`outcomes.json`) | ~5 MB |
| **Agent Memory** | `backend/app/database/repositories/agent_memory_repository.py` | Supabase + JSON fallback (`agent_memory.json`) | ~5 MB |

**Key finding:** Decision Memory is already JSON-first with no Supabase dependency. ML Feedback and Outcomes have JSON fallback. Agent Memory has JSON fallback. **All are edge-ready with minimal changes.**

---

## 7. APScheduler Jobs — Complete Inventory

### 26+ Registered Jobs

| # | Job ID | Interval | Gated? | LLM? | ML? | Memory |
|---|--------|----------|--------|------|-----|--------|
| 1 | `run_optimization_analysis` | 30s poll / 15min fire | **Weekday 07-18** | **YES** | context | ~50 MB |
| 2 | `generate_predictions` | 300s | 24/7 | No | YES | ~20 MB |
| 3 | `generate_recommendations` | 30s poll / 10min fire | **Weekday 06-19** | No | context | ~30 MB |
| 4 | `outcome_verification` | 300s | 24/7 | No | No | ~5 MB |
| 5 | `ml_retraining` | 86400s | 24/7 | No | **TRAINS** | ~500 MB peak |
| 6 | `drift_detection` | 3600s | 24/7 | No | YES | ~20 MB |
| 7 | `mv_verification` | 900s | 24/7 | No | No | ~5 MB |
| 8 | `feedback_scoring_refresh` | 900s | 24/7 | No | No | ~5 MB |
| 9 | `feedback_retraining_trigger` | 3600s | 24/7 | No | No | ~5 MB |
| 10 | `popia_retention_enforcement` | 86400s | 24/7 | No | No | ~5 MB |
| 11 | `integration_sync` | 900s | 24/7 | No | No | ~5 MB |
| 12 | `process_sentry_notifications` | 30s | 24/7 | No | No | ~10 MB |
| 13 | `process_simulation_queue` | 10s | 24/7 | No | No | ~5 MB |
| 14 | `site_mode_policy_dry_run_{site}` | 300s | 24/7 | No | No | ~5 MB |
| 15 | `occupancy_control_{site}` | 60s | 24/7 | No | No | ~10 MB |
| 16 | `aegis_cycle_{site}` | 300s | 24/7 | No | No | ~10 MB |
| 17 | `aegis_evidence_{site}` | 86400s | 24/7 | No | No | ~5 MB |
| 18 | `system_health_snapshot` | 300s | 24/7 | No | No | ~5 MB |
| 19 | `system_error_auto_resolve` | 86400s | 24/7 | No | No | ~5 MB |
| 20 | `event_intelligence_evaluation` | 120s | 24/7 | No | No | ~10 MB |
| 21 | `space_ghost_room_monitor` | 60s | 24/7 | No | No | ~5 MB |
| 22 | `space_sensor_health_{site}` | 60s | 24/7 | No | No | ~5 MB |
| 23 | `mip_dispatch_optimize` | 900s | 24/7 | No | No | ~20 MB |
| 24 | `load_forecast` | 900s | 24/7 | No | YES | ~20 MB |
| 25 | `demand_aware_coordination` | 300s | 24/7 | No | No | ~10 MB |
| 26 | `generate_demo_audit_data` | 60s | 24/7 | No | No | ~5 MB |

**Jobs that overlap with LLM inference window:**
- `generate_predictions` (5min) — ML inference runs concurrently
- `drift_detection` (1h) — may coincide with optimization cycle
- `event_intelligence_evaluation` (2min) — lightweight, concurrent

**Jobs to DISABLE on edge:**
- `process_simulation_queue` — no simulator on edge
- `generate_demo_audit_data` — demo-only
- `aegis_evidence_{site}` — pilot-only
- `ml_retraining` — train centrally, push to edge

---

## 8. Concurrent Process Map — 15-Minute Cycle

```
T+00:00   ┌─ Telemetry poll (device_abstraction) ────────────────── continuous ──┐
T+00:00   │  Memory: ~100 MB steady state                                        │
T+00:00   ├─ Event Intelligence fires (120s interval)                             │
T+00:00   │  Memory: ~10 MB, duration: <1s                                        │
T+00:00   ├─ Sentry notifications (30s poll)                                      │
T+00:00   │  Memory: ~10 MB, duration: <1s                                        │
T+00:00   ├─ Occupancy control (60s poll)                                         │
T+00:00   │  Memory: ~10 MB, duration: <1s                                        │
          │                                                                        │
T+00:30   ├─ Optimization gate check (30s poll)                                   │
T+00:30   │  → Checks if 15min elapsed since last fire                            │
T+00:30   │  → If YES: begins optimization cycle                                  │
          │                                                                        │
T+01:00   ├─ ML context gathering begins ─────────────────────────────            │
          │  → LSTM predict for fleet (lazy-load models if needed)                 │
          │  → TensorFlow import: +150-300 MB (first time only)                    │
          │  → 7 LSTM models loaded: +12 MB                                        │
          │  → 7 Autoencoder models loaded: +28 MB                                 │
          │  → Anomaly check for fleet                                             │
          │  → Fault classification for anomalous equipment                         │
          │  → Duration: 2-5 seconds (all ML models cached after first load)       │
          │                                                                        │
T+01:05   ├─ Prompt assembly ─────────────────────────────────────────            │
          │  → _build_optimization_prompt(): ~3,000-5,000 tokens                   │
          │  → Duration: <1 second                                                 │
          │                                                                        │
T+01:06   ├─ LLM inference starts ────────────────────────────────────            │
          │  → DeepSeek-R1-Distill-Qwen-14B (4-bit) via Ollama                    │
          │  → Model already resident in memory: 7-8 GB                            │
          │  → Input: ~3,000-5,000 tokens                                          │
          │  → Output: up to 1,536 tokens (max_tokens setting)                     │
          │  → Duration: 30-120 seconds (14B model on Orin, 4-bit)                 │
          │  → ASYNC: does not block other scheduler jobs                           │
          │                                                                        │
T+02:30   ├─ LLM inference completes ─────────────────────────────────            │
          │  → JSON parsed, recommendations extracted                               │
          │  → Stored to Supabase/JSON                                             │
          │  → Duration: <1 second                                                 │
          │                                                                        │
T+05:00   ├─ Prediction generation fires (300s interval)                           │
          │  → Uses already-loaded ML models                                       │
          │  → Duration: 1-3 seconds                                               │
          │                                                                        │
T+05:00   ├─ System health snapshot fires (300s interval)                          │
          │  → Lightweight telemetry aggregation                                   │
          │  → Duration: <1 second                                                 │
          │                                                                        │
T+05:00   ├─ AEGIS dispatch cycle fires (300s interval)                            │
          │  → Solar/BESS optimization (CP-SAT solver)                             │
          │  → Duration: 1-5 seconds                                               │
          │                                                                        │
T+15:00   ├─ Outcome verification fires (checks recs from ~30 min ago)             │
          │  → Simple sensor comparison, ~5 MB                                     │
          │  → Duration: <1 second per recommendation                              │
          │                                                                        │
T+15:00   └─ Next optimization cycle begins ──────────────────────────            │
```

---

## 9. Peak Concurrent Memory Estimate

### Worst Case: All Processes Running Simultaneously

| Component | Memory (MB) | Notes |
|-----------|------------|-------|
| **OS (JetPack)** | 800-1,000 | Ubuntu + CUDA runtime |
| **Python process (FastAPI)** | 200-300 | Base interpreter + imports |
| **TensorFlow runtime** | 150-300 | Loaded on first ML call |
| **ML models (all 20 loaded)** | 50-100 | Cached model weights |
| **Device manager** | 50-100 | In-memory telemetry cache |
| **Scheduler + all jobs** | 50-100 | APScheduler overhead |
| **Decision memory + feedback** | 30-50 | JSON-backed in-memory |
| **Ollama process** | 200-400 | Server overhead (no model) |
| **DeepSeek-R1 14B (4-bit)** | 7,000-8,000 | VRAM/unified memory |
| **LLM KV cache (inference)** | 500-1,000 | During active generation |
| **TOTAL** | **9,030-11,350** | |

### By Hardware Option

| Hardware | RAM | Peak Load | Headroom | Verdict |
|----------|-----|-----------|----------|---------|
| **Orin Nano Super 8GB** | 8,192 MB | 9,030-11,350 MB | **-1 to -3 GB** | **INSUFFICIENT** |
| **Orin NX 16GB** | 16,384 MB | 9,030-11,350 MB | **5-7 GB** | **SUFFICIENT** |
| **AGX Orin 32GB** | 32,768 MB | 9,030-11,350 MB | 21-24 GB | Overkill (but room for growth) |

### Mitigation If 8GB Forced

If budget absolutely constrains to 8GB, these mitigations are possible but involve significant trade-offs:

1. **Smaller LLM:** DeepSeek-R1-Distill-Qwen-7B (4-bit) → ~4 GB. Quality loss on complex recommendations.
2. **Swap LLM to disk:** Possible but inference 5-10× slower (120s → 600-1200s per cycle). Kills the 15-min cadence.
3. **Unload LLM between cycles:** Load on demand, unload after inference. Adds 30-60s load time per cycle.
4. **Disable TensorFlow, use ONNX Runtime:** Convert .h5 → .onnx. Saves ~200 MB. Significant engineering effort.
5. **Sequential not concurrent:** Never run ML and LLM simultaneously. Requires architectural changes.

---

## 10. Storage Requirements

### Base Deployment Footprint

| Component | Size | Notes |
|-----------|------|-------|
| JetPack OS | 8-10 GB | Ubuntu + CUDA + cuDNN |
| Ollama + DeepSeek-R1 14B (4-bit) | 8-9 GB | Model weights |
| Python venv (trimmed for edge) | 800 MB-1.2 GB | Remove torch, transformers, dev deps |
| Backend application code | 50 MB | |
| Frontend build (dist/) | 1 MB | Static files |
| ML models (active only, 20 models) | 50-80 MB | After cleanup: keep only active version per type |
| Data files (JSON fallback) | 40 MB | Initial |
| Model registry (registry.json) | 2.5 MB | Pruned for active models only |
| **TOTAL BASE** | **~18-21 GB** | |

### Growth Projections

| Category | Daily Growth | Monthly | Yearly |
|----------|-------------|---------|--------|
| Telemetry (local SQLite) | 5-20 MB | 150-600 MB | 1.8-7.2 GB |
| Audit/decision logs | 0.5-2 MB | 15-60 MB | 180-720 MB |
| ML models (if training locally) | 15-25 MB | 450-750 MB | 5.4-9 GB |
| ML models (if training disabled) | 0 | 0 | 0 |
| **Total (with local training)** | **20-47 MB** | **615 MB-1.4 GB** | **7.4-17 GB** |
| **Total (no local training)** | **5-22 MB** | **165-660 MB** | **2-8 GB** |

### Storage Recommendation

| NVMe Size | With Training | Without Training | Verdict |
|-----------|---------------|------------------|---------|
| 64 GB | 6 months | 2+ years | Tight |
| 128 GB | 2+ years | 5+ years | Comfortable |
| 256 GB | 5+ years | 10+ years | Overkill |

**Jetson Orin NX has no eMMC** — ships with NVMe M.2 slot. A **128 GB NVMe** is recommended.

**Critical:** Model storage path is currently hardcoded. Must add `MODEL_STORAGE_PATH` env var before edge deployment.

---

## 11. Supabase Dependency Map

### 96 Supabase Tables Referenced

Categorized by edge deployment strategy:

#### (a) MUST BE LOCAL — Core Edge Operation

| Table | Operations | Edge Replacement |
|-------|-----------|------------------|
| `equipment` | Read (lookup by code/site) | SQLite + startup preload |
| `sites` | Read (site config) | SQLite + startup preload |
| `zones` | Read (zone mapping) | SQLite + startup preload |
| `sensors` | Read/Write (telemetry) | SQLite (ring buffer) |
| `devices` | Read/Write (device state) | SQLite |
| `recommendations` | Write (AI output) | SQLite + JSON fallback |
| `outcomes` | Write (verification) | JSON fallback (already implemented) |
| `alerts` | Write (health alerts) | SQLite queue |
| `work_orders` | Write (auto-generated WOs) | SQLite queue |
| `parasite_decisions` | Write (control decisions) | JSON fallback (already implemented) |
| `agent_memory` | Read/Write | JSON fallback (already implemented) |
| `predictions` | Write (ML forecasts) | SQLite |
| `safety_rules` | Read (control constraints) | JSON + startup preload |

#### (b) DEFERRED SYNC — Write Locally, Sync When Connected

| Table | Operations | Sync Strategy |
|-------|-----------|---------------|
| `audit_log` | Write (append) | Batch upload on reconnection |
| `notification_delivery_log` | Write | Queue locally |
| `inspection_results` | Write | Queue locally |
| `inspection_tasks` | Write | Queue locally |
| `energy_consumption_history` | Write | Batch upload |
| `water_consumption` | Write | Batch upload |
| `workflow_events` | Write | Batch upload |

#### (c) NOT NEEDED ON EDGE — Cloud-Only

| Tables | Reason |
|--------|--------|
| `sentinel_users`, `user_entitlements`, `user_module_access`, `user_site_access` | Auth handled by edge-local config |
| `mfa_secrets`, `mfa_backup_codes` | No MFA on air-gapped node |
| `contracts`, `sla_terms`, `sla_performance` | Portfolio management |
| `budgets`, `budget_alerts` | Financial planning |
| `municipal_*` (5 tables) | Municipal billing |
| `compliance_audits`, `electrical_compliance` | Compliance reporting |
| `capex_analyses` | Capital planning |
| `dashboard_preferences` | UI preferences |
| `organizations` | Multi-org management |
| `desks`, `legionella_risk_assessment` | Specialized modules |
| `cafm_assets`, `point_asset_mappings` | CAFM integration |
| Most `fire_*`, `generator_groups`, DALI-specific | Module-specific tables |

#### Summary

| Category | Tables | Strategy |
|----------|--------|----------|
| Must be local | ~15 | SQLite + JSON fallback |
| Deferred sync | ~10 | Local queue → batch upload |
| Not needed on edge | ~70+ | Cloud-only |

---

## 12. Hardware Recommendation

### Primary: NVIDIA Jetson Orin NX 16GB

| Spec | Value |
|------|-------|
| **GPU** | 1024 CUDA cores, Ampere |
| **CPU** | 8-core Arm Cortex-A78AE |
| **RAM** | 16 GB LPDDR5 (unified) |
| **Storage** | M.2 NVMe slot → 128 GB recommended |
| **Power** | 10-25W |
| **AI Performance** | Up to 100 TOPS (INT8) |
| **Price** | ~$500-600 USD (module + carrier board) |

### Why Not Nano Super 8GB

1. **DeepSeek-R1 14B (4-bit) alone needs 7-8 GB** — leaves 0-1 GB for everything else
2. **TensorFlow import adds 150-300 MB** — insufficient headroom
3. **No room for ML model inference during LLM generation** — would require sequential processing, doubling cycle time
4. **OS + CUDA runtime needs ~1 GB** — pushes system into swap

### Why NX 16GB Works

1. **8 GB for LLM** — loaded once, stays resident
2. **0.5-1 GB for TensorFlow + ML models** — loaded on first call
3. **0.5-1 GB for FastAPI + services** — stable
4. **1 GB for OS + CUDA** — JetPack base
5. **4-5 GB headroom** — for KV cache, CUDA scratch, bursts

### Alternative: Smaller LLM on Nano Super

If the 14B model is not mandatory, a **7B model (4-bit, ~4 GB)** on the Nano Super 8GB is viable:
- 4 GB LLM + 1 GB ML + 0.5 GB FastAPI + 1 GB OS = 6.5 GB → 1.5 GB headroom
- Trade-off: significantly lower reasoning quality for building optimization
- May be acceptable for simple setpoint recommendations, not for complex multi-system coordination

---

## 13. Risks and Unknowns

### High Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| **TensorFlow + DeepSeek concurrent memory** | OOM on 8GB | Use 16GB NX; or serialize LLM/ML |
| **Training blocks inference** | 1-10 min freeze during retrain | Disable training on edge; push models from cloud |
| **No model storage path config** | Can't redirect to NVMe | Add `MODEL_STORAGE_PATH` env var before deployment |
| **96 Supabase table dependencies** | Edge won't boot without Supabase | Implement SQLite fallback layer |

### Medium Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Audit log unbounded growth** (9.5 MB already) | Storage exhaustion | Ring buffer with 5,000 entry cap |
| **Registry.json is 2.4 MB, 2,080+ entries** | Slow startup, memory waste | Prune to active models only |
| **19 services reference LLM client** | Multiple Ollama calls per cycle | Audit which services actually run on edge |
| **No Ollama warm-start guarantee** | First inference cold-start ~30-60s | Keep Ollama server running as systemd service |

### Unknown (Cannot Determine from Static Analysis)

| Unknown | Why It Matters | How to Determine |
|---------|---------------|------------------|
| **Actual TF memory on ARM** | ARM TF may differ from x86 | Benchmark on Jetson hardware |
| **DeepSeek-R1 14B quality on building ops** | May not match Claude Haiku quality | A/B test with sample prompts |
| **Ollama inference latency on Orin NX** | Determines if 15-min cycle is achievable | Benchmark: time per 1,536 output tokens |
| **CUDA memory fragmentation** | May reduce usable memory over time | Long-duration stress test (72h) |
| **Modbus TCP latency over USB-RS485** | May affect telemetry poll interval | Test with actual Desigo hardware |
| **NVMe I/O during model loading** | Affects cold-start time | Benchmark model load from NVMe |

---

## 14. Pre-Deployment Checklist

### Code Changes Required

1. [ ] Add `MODEL_STORAGE_PATH` environment variable (model paths are hardcoded)
2. [ ] Add `EDGE_MODE=true` flag to disable: ml_retraining, simulation_queue, demo_audit_data
3. [ ] Implement SQLite fallback layer for ~15 critical Supabase tables
4. [ ] Add audit log ring buffer (cap at 5,000 entries)
5. [ ] Prune registry.json to active models only (2,080 → 20 entries)
6. [ ] Configure telemetry batch writes (100 records or 60s timeout)
7. [ ] Route `ai_optimizer.py` through `ollama_client.py` instead of `claude_service.py`
8. [ ] Verify `ollama_client.py` supports streaming and the same response format
9. [ ] Add offline work order queue (SQLite)
10. [ ] Add offline alert queue (SQLite)

### Hardware Procurement

- [ ] Jetson Orin NX 16GB Developer Kit (or module + carrier board)
- [ ] 128 GB NVMe M.2 SSD
- [ ] Industrial-grade power supply (25W)
- [ ] DIN rail enclosure (if rack-mounted)
- [ ] USB-RS485 adapter (if Desigo uses Modbus RTU)
- [ ] Ethernet connection to BMS network

---

*Report generated by static code analysis. All memory estimates are approximate and should be validated with hardware benchmarks.*
