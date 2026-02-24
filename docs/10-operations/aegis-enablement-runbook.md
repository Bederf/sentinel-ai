# AEGIS BESS Writer Enablement Runbook

> **Version:** 1.0 | **Last Updated:** 2026-02-24 | **Status:** Ready for pilot

## Overview

This runbook covers the path from simulation-only BESS dispatch to live Modbus TCP writes against Huawei LUNA2000 hardware. All infrastructure code is already deployed — this document describes the configuration changes and validation steps to enable real writes.

## Prerequisites

- v27.0 deployed (config-driven tariffs, real connector, real SOC)
- **Sprint 0 Hardware Integration Test Protocol passed** — see [`sprint0-hardware-test-protocol.md`](sprint0-hardware-test-protocol.md)
- Physical access to Huawei LUNA2000-200KWH-2H1 Modbus TCP interface
- Network path from SENTINEL VPS to BESS Modbus TCP IP (typically 10.x.x.x:502)
- EskomSePush API token (optional, for load shedding integration)

## Environment Variables

```bash
# === Core mode switches ===
DEMO_MODE=false                     # Disable demo bypass
SOLAR_CONNECTOR_MODE=live           # Enable real Modbus TCP reads

# === Modbus TCP connection ===
MODBUS_BESS_IP=10.1.1.100          # LUNA2000 Modbus TCP IP address
MODBUS_BESS_PORT=502               # Standard Modbus TCP port
MODBUS_BESS_UNIT_ID=1              # Modbus slave/unit ID
MODBUS_BESS_TIMEOUT_S=5            # TCP connection/response timeout

# === Write safety ===
MODBUS_WRITE_VERIFY=true            # Read-back verification after every write
AEGIS_BESS_WRITER_ENABLED=false     # START WITH FALSE — enable after validation

# === Optional: Load shedding integration ===
ESKOMSEPUSH_API_TOKEN=xxx           # EskomSePush API token
ESKOMSEPUSH_AREA_ID=xxx             # Area ID (use /areas_search to find yours)
```

## Step-by-Step Enablement

### Phase 1: Read-Only Validation (AEGIS gate closed)

1. **Set environment variables** (above) with `AEGIS_BESS_WRITER_ENABLED=false`

2. **Restart backend:**
   ```bash
   sudo systemctl restart sentinel-backend.service
   ```

3. **Verify connector connected:**
   ```bash
   curl -s http://localhost:9095/api/solar/connectors/site-002 | python -m json.tool
   # Expect: "connected": true, protocol: "modbus_tcp"
   ```

4. **Verify BESS reads (real SOC):**
   ```bash
   curl -s http://localhost:9095/api/solar/bess/site-002 | python -m json.tool
   # Expect: real SOC value (not TOU-pattern simulated), real temperature
   ```

5. **Verify inverter reads:**
   ```bash
   curl -s http://localhost:9095/api/solar/inverters/site-002 | python -m json.tool
   # Expect: real ac_power_kw, real efficiency, firmware from register reads
   ```

6. **Run one dispatch cycle and check audit log:**
   ```bash
   # Trigger a dispatch cycle
   curl -s -X POST http://localhost:9095/api/dispatch/site-002/cycle | python -m json.tool

   # Check that AEGIS blocked the write
   tail -5 backend/app/data/modbus_audit/modbus_writes.jsonl
   # Expect: "aegis_blocked": true entries
   ```

7. **Validate tariff rates are from invoice (not hardcoded):**
   ```bash
   curl -s http://localhost:9095/api/dispatch-optimizer/site-002/schedule | \
     python -m json.tool | grep tariff_rate | head -5
   # Summer peak should be ~3.01, NOT 3.76
   ```

### Phase 2: Enable Live Writes (AEGIS gate open)

Only proceed after Phase 1 validation passes for at least 24 hours.

1. **Review audit log entries:**
   ```bash
   # All entries should show aegis_blocked: true with reasonable power values
   cat backend/app/data/modbus_audit/modbus_writes.jsonl | python -m json.tool
   ```

2. **Enable AEGIS writer:**
   ```bash
   # In .env:
   AEGIS_BESS_WRITER_ENABLED=true
   ```

3. **Restart backend:**
   ```bash
   sudo systemctl restart sentinel-backend.service
   ```

4. **Verify writes are executing:**
   ```bash
   tail -f backend/app/data/modbus_audit/modbus_writes.jsonl
   # Expect: "aegis_blocked": false, "write_success": true
   ```

5. **Monitor BESS response:**
   ```bash
   # Watch SOC changes in real-time
   watch -n 30 'curl -s http://localhost:9095/api/solar/bess/site-002 | python -m json.tool | grep soc_pct'
   ```

## Rollback

**Immediate rollback** (takes effect on next dispatch cycle, ~5 minutes):

```bash
# Option 1: Disable writes only (keeps reads)
# In .env:
AEGIS_BESS_WRITER_ENABLED=false
sudo systemctl restart sentinel-backend.service

# Option 2: Full revert to simulation
# In .env:
SOLAR_CONNECTOR_MODE=simulation
sudo systemctl restart sentinel-backend.service

# Option 3: Emergency — stop dispatch entirely
curl -s -X POST http://localhost:9095/api/dispatch/site-002/stop
```

The `AEGIS_BESS_WRITER_ENABLED` flag is checked on every write cycle. Setting it to `false` immediately blocks all Modbus writes without restart required (restart just ensures the setting is loaded from .env).

## Monitoring Checklist

| Metric | Expected Range | Alert If |
|--------|---------------|----------|
| SOC | 20-95% | < 15% or > 96% |
| BESS temperature | 20-35C | > 40C |
| Modbus write success rate | > 95% | < 80% |
| Dispatch cycle interval | 5 min | > 15 min gap |
| Grid import peak | < NMD (1820 kVA) | > 1700 kVA |

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Modbus connection refused" | Check IP/port, firewall rules, verify device is on network |
| "Read timeout" | Increase `MODBUS_BESS_TIMEOUT_S`, check network latency |
| "Write verify failed" | Register may be read-only; check Huawei register permissions |
| "AEGIS blocked" but should be enabled | Verify `AEGIS_BESS_WRITER_ENABLED=true` in .env, restart |
| SOC reads 0% constantly | Wrong unit_id or register address; verify with Modbus scanner |
| Tariff rates still hardcoded | Check `solar/tariffs/city_power_2025_26.json` exists |
