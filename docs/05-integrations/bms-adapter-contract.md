---
title: "SIMBIOT BMS Adapter Contract"
type: "spec"
status: "draft"
version: "1.1.0"
created: "2026-03-31"
updated: "2026-06-19"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

title: "SIMBIOT BMS Adapter Contract"
type: "technical"
status: "draft"
version: "0.1.0"
created: "2026-03-16"
updated: "2026-03-16"
author: "Sentinel Development Team"
tags: [simbiot, bms, adapter, contract, architecture]
domain: "integration"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 10
---

# SIMBIOT BMS Adapter Contract

## Purpose

Define one building-level adapter contract for every BMS source that SENTINEL
can connect to through SIMBIOT.

Canonical boundary:

```text
building -> BMS source -> SIMBIOT adapter -> SENTINEL
```

This means:

- a live BMS and a lifecycle simulation must look the same to SENTINEL
- SENTINEL must not call the lifecycle orchestrator directly
- connection, discovery, reads, and writes all happen through the adapter

## Contract Location

Code contract:

- [bms_adapter.py](/opt/bms-intelligence/backend/app/services/simbiot/bms_adapter.py)

## Scope

This contract is for the building boundary, not the per-device boundary.

- `BmsAdapter` is the SIMBIOT-facing contract for a whole building source
- `DeviceAdapter` remains a lower-level internal abstraction for protocol or
  device IO

## Required operations

- `connect(config)`
- `disconnect()`
- `get_status()`
- `discover_devices()`
- `discover_points(device_id)`
- `read_point(device_id, point_id)`
- `write_point(request)`

Optional operations:

- `read_points(device_id, point_ids)` for efficient bulk reads
- `subscribe_points(device_id, point_ids)` and `unsubscribe(subscription_id)`
  for push-style updates

## Standard data shapes

- `BmsConnectionConfig`
- `BmsConnectionStatus`
- `BmsAdapterCapabilities`
- `BmsDeviceDescriptor`
- `BmsPointDescriptor`
- `BmsPointValue`
- `BmsWriteRequest`
- `BmsSubscription`

## Implementation rule

Every BMS source must implement the same adapter contract:

- BACnet adapter (`bacnet_bms_adapter.py`) — wraps Niagara BACnet client
- oBIX adapter (`obix_bms_adapter.py`) — wraps OBIXClient, read + write with verification
- Modbus adapter (`modbus_bms_adapter.py`) — 16/32-bit data types, configurable word order
- Bridge adapter (`bridge_bms_adapter.py`) — Shadow Bridge REST proxy
  with reads and supervised/automatic point writes when the site bridge config
  explicitly enables `supports_writes` and `write_enabled`
- KNX adapter (`knx_bms_adapter.py`) — wraps KNXClient, emergency group write-block
- Simulation adapter may run locally and does not need to emulate BACnet on
  the wire, but it must satisfy the same `BmsAdapter` contract exposed to
  SENTINEL.

## Write verification

All write-capable adapters must verify writes where the protocol allows
read-back. This catches silent no-ops (e.g. Niagara priority-array override
where PUT returns 200 but the point value doesn't change).

- **Modbus**: write → read back → compare raw register values
- **oBIX**: write → read back → compare with type-aware tolerance → return `False` on mismatch
- **Bridge**: sends point-value writes to `/api/sites/{site_id}/write`; the
  bridge response is treated as the acceptance signal and higher-level
  verification must read telemetry back on the next polling cycle
- **KNX**: no read-back (fire-and-forget protocol), but emergency group addresses are blocked before write

## Schedule and timer writes

The current adapter contract exposes `write_point(request)` for point-value
writes. It does not yet define a schedule/timer configuration write operation.

For recurring operating-state mismatches, SENTINEL may create a
`schedule_defect` recommendation, but that recommendation must be treated as
manual/advisory-only unless the site adapter exposes explicit schedule or timer
objects and a dedicated schedule write contract. Approving a temporary point
change is not the same as approving a permanent BMS schedule change.

## Safety: emergency group write-block

KNX adapter blocks writes to group addresses whose description matches
emergency patterns (`emergency`, `fire`, `evacuation`, `alarm`, `panic`).
Enforced at two layers:

1. Discovery: emergency points marked `writable=False`
2. Write: `_is_emergency_group()` check before protocol call — returns `False` without calling client

## Processing rule

`site_processing = off` is enforced above the adapter at the SIMBIOT/SENTINEL
connection layer. When processing is off, SENTINEL must not call adapter read,
write, or subscription operations for that building.
