# Sprint 0 Hardware Integration Sign-Off

> **Status:** PENDING ON-SITE | **Version:** v27.0 | **Site:** site-002

## Go / No-Go Rule

Sprint 0 is **GO** when ALL of the following are true:
- [ ] 30+ minutes of clean read telemetry on real hardware
- [ ] At least one successful charge command on real hardware
- [ ] At least one successful discharge command on real hardware
- [ ] Idle/stop command returns BESS to neutral
- [ ] One rollback test completed and documented
- [ ] Inverter firmware version captured
- [ ] BESS firmware version captured
- [ ] Audit log reviewed (no unexpected entries)
- [ ] Billing sanity check passed (tariff rates match invoice)

If ANY checkbox is unchecked, Sprint 0 is **NO-GO**.

## Pre-Site Validation (Completed 2026-02-24)

- [x] Kill switch tested in 3 states: normal, Modbus failing, AEGIS open with dispatch
- [x] Kill switch always ends with gate CLOSED + mode SIMULATION
- [x] "Who" field provenance validated (dispatch_scheduler, operator_kill_switch, watchdog, test_suite, sentinel)
- [x] 179 unit tests passing, 0 failures
- [x] 22 integration tests correctly skipped (awaiting hardware)
- [x] Sprint 0 hard limits enforced (5kW / 10min)
- [x] Audit fields populated on every write (correlation_id, requested_kw, clamped_kw, who, reason)
- [x] Billing sanity tests created (tariff bands, demand charge)

## Quick Commands

```bash
cd /opt/bms-intelligence/backend

# Read-only tests (safe):
pytest tests/integration/test_sprint0_hardware.py -m "readonly" -v --timeout=120

# Write tests (requires AEGIS + ALLOW_WRITE_TESTS):
AEGIS_BESS_WRITER_ENABLED=true ALLOW_WRITE_TESTS=true \
  pytest tests/integration/test_sprint0_hardware.py -m "writetest" -v --timeout=180

# Billing sanity:
pytest tests/integration/test_sprint0_hardware.py -k "phase_g" -v

# Full suite:
pytest tests/integration/test_sprint0_hardware.py -v --timeout=300

# Kill switch (emergency):
curl -X POST http://localhost:9095/api/dispatch-optimizer/kill-switch
```

## Sign-Off Report

```bash
# Generate machine-readable report:
pytest tests/integration/test_sprint0_hardware.py -k "test_f1" -v
cat backend/tests/integration/sprint0_reports/sprint0_signoff.json | python3 -m json.tool
```

## Documentation

- **Full protocol:** [`docs/10-operations/sprint0-hardware-test-protocol.md`](docs/10-operations/sprint0-hardware-test-protocol.md)
- **AEGIS runbook:** [`docs/10-operations/aegis-enablement-runbook.md`](docs/10-operations/aegis-enablement-runbook.md)
- **Register map:** [`backend/app/data/solar/register_maps/huawei_v27.0.json`](backend/app/data/solar/register_maps/huawei_v27.0.json)

## Sign-Off

```
Signed off by: ________________________
Date:          ________________________
Site:          ________________________
Notes:         ________________________
```
