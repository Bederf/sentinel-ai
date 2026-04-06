---
title: "Sprint 0 Hardware Integration Test Protocol"
type: "guide"
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

# Sprint 0 Hardware Integration Test Protocol

> **Version:** 1.1 | **Gate for:** v27.0 pilot deployment | **Estimated time:** 2-3 hours on site

## Purpose

Prove real reads, prove safe writes, prove rollback. Sprint 0 is **not complete** until every gate below is signed off.

---

## Automated Test Suite

All checks below have matching automated tests in:
```
backend/tests/integration/test_sprint0_hardware.py
```

Run phases incrementally:

```bash
cd /opt/bms-intelligence/backend

# Phase A+B+C: Safe read-only checks (run first, always safe)
pytest tests/integration/test_sprint0_hardware.py -m "readonly" -v --timeout=120

# Phase D: Controlled writes (requires AEGIS gate open)
pytest tests/integration/test_sprint0_hardware.py -m "writetest" -v --timeout=180

# Phase E: Failure/rollback tests
pytest tests/integration/test_sprint0_hardware.py -m "failuretest" -v --timeout=120

# Full suite
pytest tests/integration/test_sprint0_hardware.py -v --timeout=300
```

---

## A. Pre-Flight

### A1. Network Path

```bash
# Verify connectivity to inverter/BESS Modbus TCP
ping -c 3 $MODBUS_BESS_IP

# Verify port is open
nc -zv $MODBUS_BESS_IP 502

# Record in site config
echo "IP: $MODBUS_BESS_IP, Port: $MODBUS_BESS_PORT, Unit: $MODBUS_BESS_UNIT_ID"
```

**Requirements:**
- [ ] Edge box on same VLAN as SUN2000 and LUNA2000
- [ ] IP, port, and unit ID recorded
- [ ] NTP synchronized: `timedatectl status | grep synchronized`

### A2. Safety Controls

**Requirements:**
- [ ] Hard power limits set in `backend/app/data/solar/site-002_config.json`
- [ ] Emergency stop path agreed (who can flip `AEGIS_BESS_WRITER_ENABLED=false`)
- [ ] Manual override available on BESS hardware panel

### A3. Environment Configuration

```bash
# Verify .env on edge box
grep -E "SOLAR_CONNECTOR_MODE|MODBUS_BESS|AEGIS|DEMO_MODE" .env
```

Expected:
```
DEMO_MODE=false
SOLAR_CONNECTOR_MODE=live
MODBUS_BESS_IP=10.1.1.100
MODBUS_BESS_PORT=502
MODBUS_BESS_UNIT_ID=1
MODBUS_BESS_TIMEOUT_S=5
MODBUS_WRITE_VERIFY=true
AEGIS_BESS_WRITER_ENABLED=false    # Start with gate CLOSED
```

**Gate:** All details captured and validated.

---

## B. Read-Only Validation

**AEGIS gate: CLOSED.** No writes happen in this phase.

### B1. Inverter Telemetry

```bash
# Read inverter data via API
curl -s http://localhost:9095/api/solar/sites/site-002/inverters | python3 -m json.tool

# Check specific fields
curl -s http://localhost:9095/api/solar/sites/site-002/inverters | \
  python3 -c "
import json, sys
data = json.load(sys.stdin)
for inv in data.get('inverters', []):
    print(f\"  {inv['inverter_id']}: {inv['ac_power_kw']:.1f} kW, {inv['frequency_hz']:.2f} Hz, status={inv['status']}\")
"
```

**Pass criteria:**
- [ ] Values match inverter portal within 5% for power
- [ ] Frequency 49.5-50.5 Hz
- [ ] Status is `online` or `standby` (not `fault` or `unknown`)
- [ ] No decode errors in `journalctl -u sentinel-backend -f` for 30 minutes

### B2. Battery Telemetry

```bash
# Read BESS data
curl -s http://localhost:9095/api/solar/sites/site-002/bess | python3 -m json.tool

# Watch SOC over time (every 30s for 5 minutes)
for i in $(seq 1 10); do
  SOC=$(curl -s http://localhost:9095/api/solar/sites/site-002/bess | \
    python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('soc_pct','?'))")
  echo "$(date +%H:%M:%S) SOC: ${SOC}%"
  sleep 30
done
```

**Pass criteria:**
- [ ] SOC matches BESS portal within 2-3%
- [ ] SOC trend direction correct when charging/discharging manually
- [ ] Temperature 15-45C (realistic range)
- [ ] Mode reflects actual BESS state

### B3. Firmware Capture

```bash
# Run automated firmware capture
pytest tests/integration/test_sprint0_hardware.py -k "test_b5_firmware" -v

# Review captured firmware versions
cat tests/integration/sprint0_reports/firmware_versions.json | python3 -m json.tool
```

**Record:**
- [ ] Inverter firmware version: _______________
- [ ] BESS firmware version (if readable): _______________
- [ ] Register map version: v27.0
- [ ] File saved to `tests/integration/sprint0_reports/firmware_versions.json`

**Gate:** 30 minutes of clean reads, firmware versions captured.

---

## C. Command Dry Run (Write Gate Closed)

**AEGIS gate: CLOSED.** Commands are logged but never sent to hardware.

### C1. Issue Commands via API

```bash
# Trigger a dispatch cycle — command will be logged but AEGIS-blocked
curl -s http://localhost:9095/api/solar/sites/site-002/dispatch/schedule | python3 -m json.tool

# Or trigger via MIP optimizer
curl -s -X POST http://localhost:9095/api/dispatch-optimizer/site-002/solve | python3 -m json.tool
```

### C2. Verify Audit Log Shows Blocked

```bash
# Check audit log
tail -10 backend/app/data/modbus_audit/modbus_writes.jsonl | python3 -m json.tool

# Count blocked entries
grep -c '"aegis_blocked": true' backend/app/data/modbus_audit/modbus_writes.jsonl
```

**Pass criteria:**
- [ ] Charge request logged with `aegis_blocked: true`
- [ ] Discharge request logged with `aegis_blocked: true`
- [ ] Each entry has timestamp, target register, and computed power value
- [ ] System reports "blocked: write gate off" in service logs

**Gate:** Control pipeline is wired end-to-end before touching equipment.

---

## D. Controlled Write Validation

**AEGIS gate: OPEN.** Real hardware writes happen.

### D0. Open the Gate

```bash
# Edit .env
# AEGIS_BESS_WRITER_ENABLED=true

# Restart
sudo systemctl restart sentinel-backend.service

# Verify
curl -s http://localhost:9095/api/solar/sites/site-002/dispatch/status | \
  python3 -c "import json,sys; print('AEGIS gate:', json.load(sys.stdin))"
```

### D1. Battery Charge Test (5 kW, 5 minutes)

```bash
# Record SOC before
SOC_BEFORE=$(curl -s http://localhost:9095/api/solar/sites/site-002/bess | \
  python3 -c "import json,sys; print(json.load(sys.stdin).get('soc_pct','?'))")
echo "SOC before: $SOC_BEFORE%"

# Run automated charge test
pytest tests/integration/test_sprint0_hardware.py -k "test_d1_charge" -v --timeout=120

# Record SOC after
SOC_AFTER=$(curl -s http://localhost:9095/api/solar/sites/site-002/bess | \
  python3 -c "import json,sys; print(json.load(sys.stdin).get('soc_pct','?'))")
echo "SOC after: $SOC_AFTER%"
```

**Pass criteria:**
- [ ] Battery power shows charging within 60 seconds
- [ ] SOC direction correct (increasing or stable if near-full)
- [ ] No alarms triggered on BESS panel
- [ ] Audit log records: request, actual power, duration

### D2. Battery Discharge Test (5 kW, 5 minutes)

```bash
pytest tests/integration/test_sprint0_hardware.py -k "test_d2_discharge" -v --timeout=120
```

**Pass criteria:**
- [ ] Grid import drops as expected
- [ ] Battery power shows discharge
- [ ] SOC direction correct (decreasing or stable if near-empty)
- [ ] Audit log complete

### D3. Stop / Neutral Test

```bash
pytest tests/integration/test_sprint0_hardware.py -k "test_d3_idle" -v --timeout=60
```

**Pass criteria:**
- [ ] Battery returns to idle (power < 5 kW) within 15 seconds
- [ ] No alarms triggered

### D4. Close the Gate

```bash
# Immediately after write tests
# Edit .env: AEGIS_BESS_WRITER_ENABLED=false
sudo systemctl restart sentinel-backend.service
```

**Gate:** At least one charge and one discharge command successfully executed.

---

## E. Failure and Rollback Tests

### E1. Network Loss Simulation

```bash
# Option A: Block Modbus IP at firewall (reversible)
sudo iptables -A OUTPUT -d $MODBUS_BESS_IP -j DROP
sleep 120
sudo iptables -D OUTPUT -d $MODBUS_BESS_IP -j DROP

# Option B: Run automated test (simulates via unreachable IP)
pytest tests/integration/test_sprint0_hardware.py -k "test_e1" -v --timeout=60
```

**Pass criteria:**
- [ ] No uncontrolled BESS behaviour during network loss
- [ ] System logs the error cleanly (no crash/restart)
- [ ] System resumes normal reads when network restored

### E2. Mode Switchover to Simulation

```bash
# Switch to simulation mode
# Edit .env: SOLAR_CONNECTOR_MODE=simulation
sudo systemctl restart sentinel-backend.service

# Verify system continues running
curl -s http://localhost:9095/api/solar/sites/site-002/bess | python3 -m json.tool
# Should return simulated data, not error

# Check logs for clear mode indicator
journalctl -u sentinel-backend --since "1 min ago" | grep -i "simulat"
```

**Pass criteria:**
- [ ] System continues running with simulated data
- [ ] No crashes, no error responses
- [ ] Operator can see clear "simulation mode" indicator in logs

**Gate:** One rollback test completed and documented.

---

## F. Sign-Off

### Sprint 0 Acceptance Gate

Sprint 0 is **complete** when ALL of the following are signed off:

| # | Requirement | Status | Evidence |
|---|------------|--------|----------|
| 1 | 30+ minutes stable read telemetry on real hardware | [ ] | Phase B test log |
| 2 | At least one successful charge command on real hardware | [ ] | Audit log entry |
| 3 | At least one successful discharge command on real hardware | [ ] | Audit log entry |
| 4 | Idle/stop command returns BESS to neutral | [ ] | Phase D3 test log |
| 5 | One rollback test completed and documented | [ ] | Phase E test log |
| 6 | Inverter firmware version captured | [ ] | firmware_versions.json |
| 7 | BESS firmware version captured | [ ] | firmware_versions.json |
| 8 | Audit log reviewed (no unexpected entries) | [ ] | modbus_writes.jsonl |
| 9 | Billing sanity check passed (tariff rates match invoice) | [ ] | Phase G test log |
| 10 | Kill switch tested and working | [ ] | Kill switch response JSON |

### Generate Sign-Off Report

```bash
# Generate machine-readable sign-off report
pytest tests/integration/test_sprint0_hardware.py -k "test_f1" -v
cat tests/integration/sprint0_reports/sprint0_signoff.json | python3 -m json.tool
```

### Sign-Off

```
Signed off by: ________________________
Date:          ________________________
Site:          ________________________
Notes:         ________________________
```

---

## G. Billing Sanity Check

### G1. Tariff Rate Bands

```bash
pytest tests/integration/test_sprint0_hardware.py -k "test_g1" -v
```

**Pass criteria:**
- [ ] Peak rate R2.50-R4.00/kWh (matches City Power invoice)
- [ ] Standard rate R1.00-R2.50/kWh
- [ ] Off-peak rate R0.50-R1.50/kWh
- [ ] Peak > Standard > Off-peak ordering confirmed

### G2. Demand Charge Sanity

```bash
pytest tests/integration/test_sprint0_hardware.py -k "test_g2" -v
```

**Pass criteria:**
- [ ] Demand charge R300-R500/kVA/month
- [ ] Matches municipal billing invoice range

**Gate:** Tariff rates from config match what appears on the actual electricity bill.

---

## Kill Switch

### Emergency Stop

The kill switch is available at any time during Sprint 0:

```bash
curl -X POST http://localhost:9095/api/dispatch-optimizer/kill-switch | python3 -m json.tool
```

**What it does (in order):**
1. Sends idle command to BESS (`who=operator_kill_switch`)
2. Closes AEGIS write gate (runtime override)
3. Switches to simulation mode (runtime override)
4. Disconnects Modbus TCP connection

**Verified behavior:**
- Works when Modbus connection is healthy
- Works when Modbus connection is failing (steps 2-4 still execute)
- Works when AEGIS gate is already open with dispatch in progress
- Idempotent: safe to call multiple times
- Always ends with: gate CLOSED + mode SIMULATION

---

## Appendix: Known Register Map Variance

Huawei Modbus registers can drift across firmware versions. If any read returns unexpected values:

1. Check `tests/integration/sprint0_reports/firmware_versions.json` against the version the register map was built for
2. Use a Modbus scanner to verify register addresses:
   ```bash
   # Quick register read test (requires pymodbus)
   python3 -c "
   import asyncio
   from pymodbus.client import AsyncModbusTcpClient
   async def main():
       c = AsyncModbusTcpClient('$MODBUS_BESS_IP', port=502)
       await c.connect()
       r = await c.read_holding_registers(37004, count=1, slave=1)  # SOC register
       print(f'SOC register (37004): {r.registers[0] / 10}%')
       c.close()
   asyncio.run(main())
   "
   ```
3. If registers have moved, update `HUAWEI_SUN2000_REGISTERS` / `HUAWEI_LUNA2000_REGISTERS` in `solar_connector_huawei.py` and bump the register map version

**Known-good firmware versions:**
| Device | Model | Firmware | Register Map |
|--------|-------|----------|-------------|
| SUN2000 | 100KTL-M2 | V200R001C00SPC136 | v27.0 |
| LUNA2000 | 200KWH-2H1 | TBD (capture on site) | v27.0 |
