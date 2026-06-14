# bacnet_device_id — S002 Operator Hand-off

**Status:** Blocks supervised setpoint writes (Telegram approve → live BACnet write).
**Last updated:** 2026-06-14.

---

## What is this

SENTINEL is now in **supervised** mode on site-002 (since 2026-06-11). Approve buttons on
Telegram advisories drive live setpoint writes through the Niagara JACE BACnet controllers.

To write a setpoint, SENTINEL needs the **BACnet device instance number** for each JACE
controller — the address used to reach the physical controller on the BACnet/IP network.
This is the number you see in tools like `Yabe`, `BACnetScan`, or in the Niagara station
under the device's "Device Object" property.

SENTINEL does not know these numbers. They must be set by the site operator.

---

## What you need to give us

**Three numbers** — one per Niagara JACE on site-002:

| Niagara station | Likely covers | Where to find the number |
|-----------------|---------------|--------------------------|
| JACE 1 (nc:18) | B1 plant — AHU, CHILLER, CT, PUMP, GEN, UPS, MTR | Niagara → station → device → Device Object → Instance |
| JACE 2 (nc:10) | L1 floor — FCU, VAV, LUM, DALI | same |
| JACE 3 (nc:15) | L2 floor — FCU, VAV, LUM | same |

If your JACE names or zones don't match the table above, that's fine — what matters is
which physical JACE each setpoint write must reach.

**Format:** a positive integer (e.g. `180001`, `100001`).

---

## How the numbers get applied

Once you have the three numbers, send them to the SENTINEL team. We run:

```bash
cd /opt/bms-intelligence/backend
# 1. Update the 3 numbers in scripts/populate_bacnet_device_ids.py
#    (BACNET_DEVICE_MAP at the top of the file)
$EDITOR scripts/populate_bacnet_device_ids.py

# 2. Preview which files will change
source venv/bin/activate
PYTHONPATH=. python3 scripts/populate_bacnet_device_ids.py --dry-run

# 3. Apply the change
PYTHONPATH=. python3 scripts/populate_bacnet_device_ids.py --apply

# 4. Verify
PYTHONPATH=. python3 scripts/populate_bacnet_device_ids.py --verify

# 5. Restart the backend so DeviceManager reloads the corrected metadata
sudo systemctl restart sentinel-backend
# Wait 30s before polling /api/health
```

After step 5, the next Telegram approve on a S002 advisory will attempt a live BACnet write.
Watch `/var/log/sentinel/backend.log` for `"BACnet write succeeded"` on the recommended
equipment.

---

## What if a JACE is in a different zone

If the JACE→zone mapping in the table above is wrong, edit the `JACE_TO_PREFIX` block at
the top of `scripts/populate_bacnet_device_ids.py`. The script will only update files whose
name contains one of the configured prefixes for that JACE. Run `--dry-run` first to see
the planned assignment before applying.

---

## Sanity check (optional)

If you have access to a BACnet browser on the same VLAN:

```bash
# Discover all BACnet devices on the network
bacnet-discover  # or use Yabe / a BACnet/IP scanner tool
# Look for the 3 device instance numbers you gave us — they should be online
```

If the numbers don't show up in a Who-Is scan, the SENTINEL write will time out and the
recommendation will be marked `write_failed` in the audit log.

---

## Reference

- SENTINEL memory: `~/.claude/projects/-opt-bms-intelligence/memory/bacnet-device-id-population.md`
- Script: `backend/scripts/populate_bacnet_device_ids.py`
- Adapter source: `backend/app/services/niagara/bacnet_adapter.py:110` (`bacnet_device_id` property)
- S002 supervised phase (verified write chain pre-gap): `~/.claude/.../memory/s002-supervised-phase-2026-06-13.md`
