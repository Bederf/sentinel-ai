# Phase 2: Clean Install Decoupling — Audit Results

**Date:** 2026-02-28
**Goal:** SENTINEL deploys cleanly on SBC with zero simulated data

## Entanglement Findings

### DEMO_MODE References (207 total)
`DEMO_MODE` serves two unrelated purposes:
1. **Auth bypass + dev convenience** — localhost auth bypass, shorter recommendation intervals
2. **Simulator activation** — forces `IngestionMode.SIMULATION`, auto-starts 365-day lifecycle

These are now decomposed: `DEMO_MODE` retains purpose (1), new `SITE002_SOURCE_ENABLED` controls purpose (2).

### Startup Trace (events.py)
The startup path unconditionally:
- Loads 50+ devices from `mock_devices.json` via `devices_startup()`
- Recovers crashed simulations (`recover_crashed_simulations()`)
- Starts simulation queue processor (`add_simulation_queue_processor_job()`)
- Auto-starts sentinel_annual simulation (`auto_start_sentinel_simulation()`)

All simulation-related startup is now gated behind `settings.site002_source_enabled`.

### Device Loading Paths
Two independent device sources were conflated:
1. **Reference devices** (`mock_devices.json`) — Site-002 simulated equipment (50+ devices)
2. **Building equipment** (`data/buildings/*/equipment/`) — Deployer-configured equipment

Source (1) is simulator data → moved to `bms_simulator/data/reference_devices.json`, gated by `site002_source_enabled`.
Source (2) is deployment config → stays unconditional.

### Import Dependencies
- `device_abstraction.py` hard-imports `SimulatedDeviceAdapter` at module level
- Removing `bms_simulator/` directory would crash SENTINEL on import
- Fixed with lazy/conditional import in `_create_adapter()`

### Auto-Start Mechanisms
- `auto_start_sentinel_simulation()` — queues lifecycle sim if none active
- `recover_crashed_simulations()` — re-queues crashed sims from JSON store
- `add_simulation_queue_processor_job()` — polls for queued sims every 10s

All gated behind `site002_source_enabled`.

### Resolved Ingestion Mode
`resolved_ingestion_mode` property forced `SIMULATION` when `demo_mode=True`, regardless of whether a simulator was present. Now driven by `site002_source_enabled`.

## Files Changed

| File | Change | Risk |
|------|--------|------|
| `backend/app/config/settings.py` | Add `site002_source_enabled`, modify `resolved_ingestion_mode` | Low |
| `backend/app/startup/events.py` | Gate simulation startup behind `site002_source_enabled` | Medium |
| `backend/app/api/devices.py` | Rename `load_mock_devices` → `load_reference_devices`, gate | Medium |
| `backend/app/services/device_abstraction.py` | Lazy import `SimulatedDeviceAdapter` | Medium |
| `backend/app/services/ai_optimizer.py` | Gate reference device loading, update path | Low |
| `mock_devices.json` | Moved to `bms_simulator/data/reference_devices.json` | Low |
| `mock_devices.py` | Deleted (unused shim) | None |
| 10+ files | Path/comment updates | None–Low |
| `backend/tests/test_clean_install.py` | New verification tests | None |
