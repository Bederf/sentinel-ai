---
title: "SIMBIOT BMS Adapter Contract"
type: "spec"
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

- BACnet adapter
- oBIX adapter
- Modbus adapter
- simulation adapter

The simulation adapter may run locally and does not need to emulate BACnet on
the wire, but it must satisfy the same `BmsAdapter` contract exposed to
SENTINEL.

## Processing rule

`site_processing = off` is enforced above the adapter at the SIMBIOT/SENTINEL
connection layer. When processing is off, SENTINEL must not call adapter read,
write, or subscription operations for that building.
