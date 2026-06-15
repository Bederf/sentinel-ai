# bacnet_device_id — S002 Operator Hand-off

**Status:** Blocks supervised setpoint writes (Telegram approve → live BACnet write).
**Last updated:** 2026-06-14 (revised for Desigo CC).

---

## Context: how SENTINEL reaches your equipment

SENTINEL is now in **supervised** mode on site-002 (since 2026-06-11). Approve buttons on
Telegram advisories drive live setpoint writes that travel:

```
Telegram approve
  → SENTINEL backend
  → BACnet/IP write (BAC0 client)
  → your BACnet network
  → field device (PXC/PXM panel, VAV controller, FCU controller, etc.)
```

SENTINEL does **not** use Desigo CC's REST API. It uses standard **BACnet/IP**. So we need
the **BACnet device instance number** for every BACnet-speaking device on site-002's
network — not the Desigo CC object designation, and not the Desigo CC automation station
name.

This applies regardless of which front-end manages the system (Desigo CC, Niagara, BACnet
only). The transport is BACnet/IP either way.

---

## What we need

**A list of `{equipment_code} → {BACnet device instance number}` pairs** for every BACnet
device on the site-002 BACnet network. Each piece of equipment in SENTINEL's catalog
(`S002-AHU-B01`, `S002-FCU-001`, `S002-CHILLER-R001`, etc.) is reachable as exactly one
BACnet device.

Easiest approach: do a **BACnet Who-Is scan** and return the mapping table.

### Option A — Give us the scan output

From any machine on the site-002 BACnet VLAN, run a BACnet discovery tool. Yabe (BACnet
Explorer) is the simplest:

1. Install Yabe (Windows) or `BAC0` (Python: `pip install BAC0`) on a laptop on the BACnet
   network
2. Run a Who-Is scan
3. Export the device list as CSV / JSON
4. For each device, look up its `object_name` (or vendor/description) and match it to
   SENTINEL equipment codes (`S002-AHU-B01` etc.)
5. Send us the table:

   ```csv
   bacnet_device_instance,equipment_code,vendor,description
   180001,S002-AHU-B01,Siemens,PXC automation station basement
   180002,S002-CHILLER-001,Siemens,Chiller 1 controller
   ...
   ```

   If `object_name` already matches `S002-AHU-B01` etc., the mapping is trivial.

### Option B — Give us only the automation station instances

If the PXC/PXM panels proxy BACnet to the field devices, we may only need the **automation
station** (PXC) device instance, and the field devices share that number with different
object instances. In that case:

- 1 number per PXC/PXM (typically 3–5 numbers for the whole site)
- Confirm whether the field-level FCUs/VAVs/valves are reachable on BACnet directly or
  proxied through the PXC

**Tell us which option applies** when you send the data back.

---

## How to find the numbers in Desigo CC

If you don't have a BACnet scanner handy, the Desigo CC Management Console also exposes
device instance numbers:

1. Open Desigo CC → **System Management** → **Devices**
2. Filter by **Protocol = BACnet**
3. The **Device Instance** column shows the BACnet device instance number
4. The **Object Name** (or **Description**) is the human-readable label that should match
   our equipment code

Export the filtered list and send it over.

---

## How the numbers get applied

Once you send the mapping, we run:

```bash
cd /opt/bms-intelligence/backend
# 1. Update BACNET_DEVICE_MAP (or a CSV ingest step) at the top of:
$EDITOR scripts/populate_bacnet_device_ids.py

# 2. Preview which files will change
source venv/bin/activate
PYTHONPATH=. python3 scripts/populate_bacnet_device_ids.py --dry-run

# 3. Apply
PYTHONPATH=. python3 scripts/populate_bacnet_device_ids.py --apply

# 4. Verify via the production transform
PYTHONPATH=. python3 scripts/populate_bacnet_device_ids.py --verify

# 5. Restart the backend so DeviceManager reloads
sudo systemctl restart sentinel-backend
# Wait 30s before polling /api/health
```

After step 5, the next Telegram approve on a S002 advisory will attempt a live BACnet write.
Watch `/var/log/sentinel/backend.log` for `"BACnet write succeeded"`.

---

## What if a JACE/panel is in a different zone

If the equipment→controller mapping in the heuristic doesn't match your site layout, edit
the `JACE_TO_PREFIX` block (or a CSV) at the top of `scripts/populate_bacnet_device_ids.py`.
The script only updates equipment whose name contains one of the configured prefixes for
that controller. Run `--dry-run` first.

The cleanest fix is to give us the **per-equipment mapping** (Option A above) and skip the
prefix heuristic entirely.

---

## Sanity check (optional)

If you can do a Who-Is scan from the SENTINEL backend's network, the numbers should be
visible to the BAC0 client. Failure mode is: numbers are on a separate VLAN or behind a
BACnet router we can't reach — the write will time out and the recommendation will be
marked `write_failed` in the audit log.

---

## Reference

- SENTINEL memory: `~/.claude/projects/-opt-bms-intelligence/memory/bacnet-device-id-population.md`
- Script: `backend/scripts/populate_bacnet_device_ids.py`
- Adapter contract: `backend/app/services/niagara/bacnet_adapter.py:110` (reads `device.metadata["bacnet_device_id"]`)
- Transport: `backend/app/services/niagara/bacnet_client.py` (generic BAC0, not Niagara-specific despite the name)
- S002 supervised phase (verified write chain pre-gap): `~/.claude/.../memory/s002-supervised-phase-2026-06-13.md`
