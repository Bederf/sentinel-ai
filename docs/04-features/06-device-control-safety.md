---
title: "Device Control & Safety Interlocks"
type: "feature"
status: "implemented"
version: "1.0.0"
created: "2026-02-03"
updated: "2026-02-03"
author: "SENTINEL Development Team"
tags: ["devices", "control", "safety", "interlocks", "BACnet", "Modbus"]
domain: "device-management"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 10
phase: "06"
---

# Device Control & Safety Interlocks

Protocol-agnostic device abstraction layer with comprehensive safety validation for building equipment control.

## Overview

Phase 6 implements the foundation for SENTINEL's device control capabilities:
- **Plan 06-01**: Device abstraction layer with protocol-agnostic interface
- **Plan 06-02**: Safety interlock engine with rule-based validation

## Device Abstraction Layer

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Device Control Flow                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Frontend Request                                              │
│         │                                                       │
│         ▼                                                       │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐      │
│   │  REST API   │────►│   Safety    │────►│   Device    │      │
│   │  /devices   │     │   Engine    │     │   Manager   │      │
│   └─────────────┘     └─────────────┘     └─────────────┘      │
│                             │                    │              │
│                    Validation Result      Protocol Adapter      │
│                             │                    │              │
│                             ▼                    ▼              │
│                       ┌─────────────┐    ┌─────────────┐       │
│                       │ Block/Allow │    │  BACnet/    │       │
│                       │  + Reason   │    │  Modbus/    │       │
│                       └─────────────┘    │  Mock       │       │
│                                          └─────────────┘       │
│                                                 │               │
│                                          Audit Logger           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Device Interface

Protocol-agnostic interface supporting BACnet, Modbus, and mock implementations:

```python
class DeviceInterface:
    """Protocol-agnostic device interface."""

    async def read_point(self, point_name: str) -> PointValue
    async def write_point(self, point_name: str, value: Any) -> bool
    async def get_status(self) -> DeviceStatus
    async def get_points(self) -> List[DevicePoint]
```

### Device Manager

Singleton manager for device lifecycle:

```python
from app.services.device_abstraction import device_manager

# Discover devices
devices = await device_manager.discover_devices()

# Get specific device
device = device_manager.get_device("chiller-001")

# Control device
result = await device_manager.write_point(
    device_id="chiller-001",
    point_name="cooling_setpoint",
    value=22.0
)
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/devices` | GET | List all devices |
| `/api/devices/{id}` | GET | Get device details |
| `/api/devices/{id}/points` | GET | Get device points |
| `/api/devices/{id}/points/{point}` | GET | Read point value |
| `/api/devices/{id}/control` | POST | Write point value |
| `/api/devices/{id}/status` | GET | Get device status |
| `/api/sites/{site_id}/devices` | GET | Get devices by site |

### Example: Read Device Point

```bash
GET /api/devices/chiller-001/points/chw_supply_temp

Response:
{
  "device_id": "chiller-001",
  "point_name": "chw_supply_temp",
  "value": 7.2,
  "unit": "°C",
  "quality": "good",
  "timestamp": "2026-02-03T12:00:00Z"
}
```

### Example: Control Device

```bash
POST /api/devices/chiller-001/control
Content-Type: application/json

{
  "point_name": "cooling_setpoint",
  "value": 22.0
}

Response:
{
  "success": true,
  "device_id": "chiller-001",
  "point_name": "cooling_setpoint",
  "previous_value": 24.0,
  "new_value": 22.0,
  "safety_validation": {
    "passed": true,
    "rules_checked": ["temperature_range", "runtime_limit"]
  },
  "audit_id": "audit-20260203-001"
}
```

---

## Safety Interlock Engine

### Rule Types

| Rule Type | Description | Example |
|-----------|-------------|---------|
| `TemperatureRange` | Min/max temperature limits | 16-28°C for HVAC |
| `PressureLimit` | Maximum pressure threshold | 1200 kPa for chillers |
| `RuntimeLimit` | Minimum time between starts | 5 min for compressors |
| `BrightnessLimit` | Maximum brightness level | 90% for lighting |
| `Interlock` | Device dependency check | Pump must run before chiller |
| `Custom` | Custom validation logic | Site-specific rules |

### Severity Levels

| Level | Action | Use Case |
|-------|--------|----------|
| `WARNING` | Allow with notification | Approaching limits |
| `BLOCK` | Prevent execution | Safety violation |
| `ALARM` | Block + emergency alert | Critical safety issue |

### Safety Rules Configuration

```json
{
  "rules": [
    {
      "id": "temp-range-hvac",
      "name": "HVAC Temperature Range",
      "type": "TemperatureRange",
      "device_types": ["chiller", "ahu", "fcu"],
      "parameters": {
        "min_temp": 16,
        "max_temp": 28
      },
      "severity": "BLOCK",
      "message": "Temperature must be between 16°C and 28°C"
    },
    {
      "id": "runtime-compressor",
      "name": "Compressor Runtime Limit",
      "type": "RuntimeLimit",
      "device_types": ["chiller"],
      "parameters": {
        "min_runtime_minutes": 5
      },
      "severity": "BLOCK",
      "message": "Minimum 5 minutes between compressor starts"
    }
  ]
}
```

### Safety Validation API

```bash
# Validate before control
POST /api/safety/validate
Content-Type: application/json

{
  "device_id": "chiller-001",
  "point_name": "cooling_setpoint",
  "proposed_value": 15.0
}

Response:
{
  "valid": false,
  "blocked": true,
  "violations": [
    {
      "rule_id": "temp-range-hvac",
      "rule_name": "HVAC Temperature Range",
      "severity": "BLOCK",
      "message": "Temperature 15°C is below minimum 16°C"
    }
  ]
}
```

### Safety Status API

```bash
GET /api/devices/chiller-001/safety-status

Response:
{
  "device_id": "chiller-001",
  "safety_status": "safe",
  "active_rules": 3,
  "violations": [],
  "last_checked": "2026-02-03T12:00:00Z"
}
```

---

## Demo Devices

6 pre-configured devices for demonstration:

| Device | Type | Demo Scenario |
|--------|------|---------------|
| Gateway Chiller | Chiller | High pressure alarm |
| Level 3 AHU | AHU | Filter differential pressure |
| Lobby Lighting | Lighting | Brightness control |
| Main Entrance Access | Access | Life safety device |
| Fire Pump Controller | Fire | Life safety (read-only) |
| Office VAV | VAV | Temperature optimization |

---

## Implementation

**Services:**
- `backend/app/services/device_abstraction.py` - Device manager and interface
- `backend/app/services/mock_devices.py` - Mock device adapter
- `backend/app/services/safety_interlocks.py` - Safety engine

**API:**
- `backend/app/api/devices.py` - Device REST endpoints
- `backend/app/api/safety.py` - Safety validation endpoints

**Data:**
- `backend/app/data/mock_devices.json` - Device configurations
- `backend/app/data/safety_rules.json` - Safety rule definitions

**Tests:**
- `backend/tests/services/test_device_abstraction.py`
- `backend/tests/services/test_safety_interlocks.py`

---

## Related Documentation

- [Safety Interlocks Engine](../06-safety-compliance/safety-interlocks-engine.md)
- [Autonomous Decision Engine](09-autonomous-decisions.md)
- [Load Shedding Optimization](10-load-shedding-optimization.md)
