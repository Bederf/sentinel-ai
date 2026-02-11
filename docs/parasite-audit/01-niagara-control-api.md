# Niagara BACnet Control API Specification

**Phase:** 67-01 Niagara BACnet Control API Audit
**Status:** Complete
**Last Updated:** 2026-02-11

## Overview

This document provides a comprehensive specification of the Niagara BACnet/IP Control API capabilities, including all write-capable endpoints, supported object types, priority handling, and error management. This audit is essential for the PARASITE autonomous control system to understand what can and cannot be autonomously controlled.

## Table of Contents

1. [API Architecture](#api-architecture)
2. [BACnet Write API Specification](#bacnet-write-api-specification)
3. [Supported Object Types & Writability Matrix](#supported-object-types--writability-matrix)
4. [Point Discovery API](#point-discovery-api)
5. [Priority Array System](#priority-array-system)
6. [COV (Change of Value) Subscriptions for Feedback](#cov-change-of-value-subscriptions-for-feedback)
7. [Error Handling](#error-handling)
8. [Identified Gaps & Limitations](#identified-gaps--limitations)
9. [Implementation Details](#implementation-details)

---

## API Architecture

### Core Components

| Component | Location | Purpose |
|-----------|----------|---------|
| **BACnet API Router** | `backend/app/api/niagara_bacnet.py` | FastAPI endpoint definitions (7 endpoints) |
| **BACnet Client** | `backend/app/services/niagara/bacnet_client.py` | Low-level BACnet/IP protocol implementation using BAC0 library |
| **Pydantic Models** | `backend/app/models/niagara.py` | Request/response data validation |
| **Point Classifier** | `backend/app/services/niagara/point_classifier.py` | Determines point writability & type |
| **Point Discovery** | `backend/app/services/niagara/point_discovery.py` | Enumerates all available points on devices |

### Protocol Details

- **Library:** BAC0 (Python BACnet library) - https://bac0.readthedocs.io/
- **Network Interface:** UDP port 47808 (BACnet/IP standard)
- **Device Type:** Tridium Niagara JACE/Supervisor devices
- **Broadcast:** WhoIs/IAm for device discovery
- **Format:** BACnet application protocol (ISO 16663)

---

## BACnet Write API Specification

### Endpoint: `POST /api/niagara/bacnet/devices/{device_id}/points/{object_type}/{instance}/write`

**Purpose:** Write a value to a single BACnet point with priority array support.

#### Request

```
POST /api/niagara/bacnet/devices/1000/points/analogOutput/0/write
Content-Type: application/json

{
  "value": 22.5,           // Value to write (type depends on point)
  "priority": 8            // BACnet priority (1-16, default 8)
}
```

**Request Model:**
```python
class BACnetPointWriteRequest(BaseModel):
    value: Any = Field(..., description="Value to write")
    priority: int = Field(8, description="BACnet priority (1-16, default 8)", ge=1, le=16)
```

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `device_id` | int | BACnet device instance number (typically 1000-9999) |
| `object_type` | str | BACnet object type (e.g., "analogOutput", "binaryOutput") |
| `instance` | int | Object instance number on the device (0-4194303) |

**Query Parameters:** None

#### Response (Success: HTTP 200)

```json
{
  "success": true,
  "device_id": 1000,
  "object_type": "analogOutput",
  "instance": 0,
  "value": 22.5,
  "priority": 8,
  "message": "Value written to analogOutput,0 on device 1000"
}
```

**Response Model:**
```python
class BACnetPointWriteResponse(BaseModel):
    success: bool = Field(..., description="Whether the write succeeded")
    device_id: int = Field(..., description="BACnet device instance number")
    object_type: str = Field(..., description="BACnet object type")
    instance: int = Field(..., description="Object instance number")
    value: Any = Field(None, description="Value written")
    priority: int = Field(8, description="Priority used")
    message: str = Field("", description="Status message")
```

#### Error Responses

| Status | Error | Description | Cause |
|--------|-------|-------------|-------|
| **503** | `Client Not Started` | BACnet client is not running | API must start client first |
| **504** | `Write Timeout` | Device did not respond within timeout | Device offline or network latency |
| **502** | `Write Error` | Write operation failed on device | Value out of range, write-protected, device error |
| **404** | (Device not found) | Device ID not recognized | Device not on network or discovery incomplete |
| **422** | `Invalid Priority` | Priority outside 1-16 range | Client validation error |
| **500** | `Internal Server Error` | Unexpected BACnet error | BAC0 library error |

#### Implementation Details

**BAC0 Write Format:**
```
"{device_id} {object_type},{instance} presentValue {value} - {priority}"

Example:
"1000 analogOutput,0 presentValue 22.5 - 8"
```

**Execution Flow:**
1. Validate priority is 1-16 (raise ValueError if not)
2. Format BAC0 write string with device_id, object_type, instance, value, priority
3. Execute write via BAC0 library with retry logic (max 3 retries, 1s delay)
4. On success: log write operation, return HTTP 200
5. On failure: raise BACnetWriteError, return HTTP 502

**Retry Logic:**
- Max retries: 3 attempts
- Retry delay: 1 second between attempts
- Transient failures (timeouts) may succeed on retry
- Permanent failures (write protection, type mismatch) fail immediately

**Value Type Support:**
- **Analog types** (AO, AV): Numeric (int, float)
- **Binary types** (BO, BV): Boolean (true/false, 0/1, "on"/"off", "active"/"inactive")
- **Multi-state types** (MSO, MSV): Integer state number (1-N)
- **Special**: String values for device names, descriptions

---

## Supported Object Types & Writability Matrix

### BACnet Object Type Reference

| Object Type | Abbreviation | Typical Use | Writable? | Data Type | Examples |
|-------------|--------------|-------------|-----------|-----------|----------|
| **Analog Input** | AI | Temperature sensors, pressure sensors, flow meters | ❌ NO | Real (float) | Room temp, supply pressure, water flow |
| **Analog Output** | AO | Setpoint commands, valve positions, damper angles | ✅ YES | Real (float) | Cooling setpoint (°C), damper position (%) |
| **Analog Value** | AV | Calculated values, derived parameters | ⚠️ MAYBE | Real (float) | Average temp, normalized value |
| **Binary Input** | BI | On/off status, alarm conditions, mode indicators | ❌ NO | Boolean | Pump running, fire alarm, occupancy |
| **Binary Output** | BO | On/off commands, relay control, mode changes | ✅ YES | Boolean | Compressor start/stop, mode select |
| **Binary Value** | BV | Binary calculated values | ⚠️ MAYBE | Boolean | Override flag, reset command |
| **Multi-state Input** | MI | Multi-mode status, enumerated readings | ❌ NO | Integer (1-N) | Fan mode (off/low/med/high), valve position state |
| **Multi-state Output** | MSO | Multi-mode commands, enumerated control | ✅ YES | Integer (1-N) | Fan speed (1-4), valve state (0-3) |
| **Multi-state Value** | MSV | Multi-state calculated values | ⚠️ MAYBE | Integer (1-N) | Mode selection, schedule override |

### Write Protection Rules

**Always Writable (Primary Control):**
- **AO (Analog Output):** Yes - designed for setpoint control
- **BO (Binary Output):** Yes - designed for on/off commands
- **MSO (Multi-state Output):** Yes - designed for mode/state selection

**May Be Writable (Depends on Device):**
- **AV (Analog Value):** Some devices allow; check `writable` flag in point discovery
- **BV (Binary Value):** Some devices allow; check `writable` flag in point discovery
- **MSV (Multi-state Value):** Some devices allow; check `writable` flag in point discovery

**Never Writable (Inputs Only):**
- **AI (Analog Input):** No - sensor inputs are read-only
- **BI (Binary Input):** No - status inputs are read-only
- **MI (Multi-state Input):** No - mode inputs are read-only
- **Device:** No - device object itself is read-only
- **Schedule, Calendar, TrendLog, NotificationClass:** No - read-only metadata

### Writability Detection

**How the API determines if a point is writable:**

1. **Point Discovery** reads the BACnet `writable` property (bit flag in BACnet specification)
2. **Point Classifier** (`point_classifier.py`) categorizes each discovered point
3. **Point Info Response** includes `writable: bool` field
4. **Write Attempt** on read-only point → HTTP 502 (Write Error)

**Code Example:**
```python
# Discover points and check writability
GET /api/niagara/bacnet/devices/1000/points?type=analogOutput
Response: {
  "device_id": 1000,
  "points": [
    {
      "object_type": "analogOutput",
      "instance": 0,
      "name": "Cooling_Setpoint",
      "writable": true,  # ← Can be written to
      "units": "celsius"
    }
  ]
}

# Attempt write
POST /api/niagara/bacnet/devices/1000/points/analogOutput/0/write
{
  "value": 22.5,
  "priority": 8
}
Response: 200 OK (success)
```

---

## Point Discovery API

### Endpoint: `GET /api/niagara/bacnet/devices/{device_id}/points`

**Purpose:** Enumerate all BACnet objects/points on a device; identify which are writable.

#### Request

```
GET /api/niagara/bacnet/devices/1000/points?type=analogOutput&use_cache=true
```

#### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `type` | string | None | Filter by object type (e.g., "analogOutput", "binaryOutput") |
| `use_cache` | boolean | true | Use cached point list (faster, may be stale) |

#### Response (HTTP 200)

```json
{
  "device_id": 1000,
  "count": 45,
  "points": [
    {
      "object_type": "analogOutput",
      "instance": 0,
      "name": "Cooling_Setpoint",
      "description": "Chilled water cooling setpoint",
      "units": "celsius",
      "present_value": 22.5,
      "writable": true
    },
    {
      "object_type": "analogOutput",
      "instance": 1,
      "name": "Heating_Setpoint",
      "description": "Hot water heating setpoint",
      "units": "celsius",
      "present_value": 18.0,
      "writable": true
    },
    {
      "object_type": "analogInput",
      "instance": 0,
      "name": "Supply_Temperature",
      "description": "Supply air temperature sensor",
      "units": "celsius",
      "present_value": 15.2,
      "writable": false
    },
    {
      "object_type": "binaryOutput",
      "instance": 0,
      "name": "Compressor_Command",
      "description": "Compressor start/stop command",
      "units": "boolean",
      "present_value": 1,
      "writable": true
    }
  ]
}
```

**Response Model:**
```python
class BACnetPointDiscoveryResponse(BaseModel):
    device_id: int
    count: int
    points: List[BACnetPointInfo]

class BACnetPointInfo(BaseModel):
    object_type: str
    instance: int
    name: str
    description: str
    units: str
    present_value: Any
    writable: bool
```

#### Use Cases for PARASITE

1. **Device Capability Assessment:** Discover what each device can control
2. **Writable Point Inventory:** Filter `points` where `writable == true`
3. **Setpoint Identification:** Find AO/BO/MSO points (typically setpoints/commands)
4. **Sensor Validation:** Find AI/BI/MI points to read before/after writes

#### Caching Strategy

- **Cache Enabled (`use_cache=true`):** Returns previously discovered points (24-hour TTL)
- **Cache Disabled (`use_cache=false`):** Live discovery (slower, always current)
- **Recommendation for PARASITE:** Use cached discovery during operation; refresh on startup or after 24 hours

---

## Priority Array System

### BACnet Priority Hierarchy

BACnet uses a **16-level priority array** on each writable point to resolve conflicts when multiple systems try to write the same point.

**Priority Levels (1 = Highest, 16 = Lowest):**

```
Priority  Level          Typical User             Who Controls?
--------  -----          ---------------          ---------------
   1      Life Safety    Fire alarm system         Emergency override (always wins)
   2      -              -
   3      -              -
   4      -              -
   5      -              -
   6      -              -
   7      Manual         Technician override      On-site technician
   8      Manual         Manual operator          PARASITE (autonomous AI)
   9-15   -              -
   16     Default        Default/fallback value   Lowest priority (rarely used)
```

### PARASITE Priority Assignment

**Default Priority for Autonomous Control: 8 (Manual Operator)**

- Lowest among operator-level commands (below technician priority 7)
- Higher than default/fallback (priority 16)
- Can be overridden by technician or emergency systems
- Allows graceful degradation if technician intervenes

**Example Priority Conflict:**

```
Scenario: PARASITE tries to set cooling setpoint, technician intervenes

Time T0: PARASITE writes 22°C at priority 8
         BACnet point value = 22°C (PARASITE's write active)

Time T1: Technician writes 24°C at priority 7 (higher priority)
         BACnet point value = 24°C (Technician's write wins)

Time T2: PARASITE writes 20°C at priority 8
         BACnet point value = 24°C (Technician's priority 7 still active)

Time T3: Technician clears their write (writes null to priority 7)
         BACnet point value = 20°C (PARASITE's priority 8 now active)
```

### Conflict Resolution Rules

1. **Highest priority wins:** If multiple systems write at different priorities, highest priority value is used
2. **Same priority:** Undefined behavior (device-dependent, typically last write wins)
3. **Null/Released:** If a priority is released (null value), next-highest priority becomes active
4. **Default:** If all priorities are null, device uses default/fallback value

### Writing with Different Priorities

**Use Case:** Override PARASITE decisions with technician command

```python
# PARASITE writes at priority 8
POST /api/niagara/bacnet/devices/1000/points/analogOutput/0/write
{
  "value": 22.5,
  "priority": 8
}

# Technician writes at priority 7 (overrides PARASITE)
POST /api/niagara/bacnet/devices/1000/points/analogOutput/0/write
{
  "value": 25.0,
  "priority": 7
}

# To release technician override, write null to priority 7
# (See release_point endpoint below)
```

### Release Priority (Revert to Lower Priority)

**Endpoint:** (Not yet exposed via REST, but available in client)

```python
# Internal client method:
await client.release_point(
    device_id=1000,
    object_type="analogOutput",
    instance=0,
    priority=7  # Release priority 7 so priority 8 (PARASITE) becomes active
)
```

**Implementation Note:** This would write `null` to the priority level, allowing the next-highest priority to take effect.

---

## COV (Change of Value) Subscriptions for Feedback

### Purpose of COV Subscriptions

BACnet **Change-of-Value (COV)** subscriptions provide **real-time feedback** on point value changes. PARASITE uses COV to:

1. **Verify writes succeeded:** Did the setpoint actually change after we wrote it?
2. **Detect equipment response:** Did the device respond to the command (compressor started, valve moved)?
3. **Detect conflicts:** Did another system override our write?
4. **Timeout detection:** If expected change doesn't arrive, the write likely failed

### Endpoint: `POST /api/niagara/bacnet/subscribe`

**Purpose:** Create a COV subscription for real-time point change notifications.

#### Request

```json
POST /api/niagara/bacnet/subscribe
Content-Type: application/json

{
  "device_id": 1000,
  "points": [
    {
      "object_type": "analogOutput",
      "instance": 0
    },
    {
      "object_type": "analogInput",
      "instance": 5
    }
  ],
  "lifetime": 60
}
```

**Request Model:**
```python
class BACnetCOVSubscribeRequest(BaseModel):
    device_id: int
    points: List[BACnetCOVPoint]
    lifetime: int = Field(60, description="Subscription lifetime in seconds", ge=10, le=3600)

class BACnetCOVPoint(BaseModel):
    object_type: str
    instance: int
```

#### Response (HTTP 200)

```json
{
  "subscription_id": "sub-abc123def456",
  "device_id": 1000,
  "points": [
    {
      "object_type": "analogOutput",
      "instance": 0
    },
    {
      "object_type": "analogInput",
      "instance": 5
    }
  ],
  "lifetime": 60,
  "created_at": "2026-02-11T14:30:00.000000Z",
  "expires_at": "2026-02-11T14:31:00.000000Z",
  "active": true
}
```

### Subscription Lifecycle

**Automatic Renewal:**
- Subscriptions automatically renew before expiration
- Renewal happens when `expires_at < current_time + 30s`
- If renewal fails, subscription becomes inactive

**Timeout:** Subscriptions expire after `lifetime` seconds if not renewed

**Cancellation:** Use DELETE endpoint to manually cancel

### Endpoint: `GET /api/niagara/bacnet/subscriptions`

**List all active COV subscriptions:**

```json
GET /api/niagara/bacnet/subscriptions

Response (HTTP 200):
{
  "count": 3,
  "subscriptions": [
    {
      "subscription_id": "sub-abc123def456",
      "device_id": 1000,
      "points": [...],
      "lifetime": 60,
      "created_at": "2026-02-11T14:30:00.000000Z",
      "expires_at": "2026-02-11T14:31:00.000000Z",
      "active": true
    }
  ]
}
```

### Endpoint: `DELETE /api/niagara/bacnet/subscribe/{subscription_id}`

**Cancel a COV subscription:**

```
DELETE /api/niagara/bacnet/subscribe/sub-abc123def456

Response (HTTP 200):
{
  "success": true,
  "message": "Subscription sub-abc123def456 cancelled"
}
```

### How PARASITE Uses COV for Verification

**Workflow:**

```
1. Subscribe to setpoint before writing
   POST /api/niagara/bacnet/subscribe
   {device_id: 1000, points: [{type: "analogOutput", instance: 0}]}
   → subscription_id: "sub-xyz"

2. Write new setpoint value
   POST /api/niagara/bacnet/devices/1000/points/analogOutput/0/write
   {value: 22.5, priority: 8}

3. Wait for COV notification (internal callback)
   Device sends: "analogOutput,0 = 22.5" (COV update)
   → Write successful! ✓

4. If no COV update within 5 seconds
   → Write probably failed, retry or escalate
   → Log alert for technician

5. Cancel subscription when done
   DELETE /api/niagara/bacnet/subscribe/sub-xyz
```

### Implementation Notes

**Callback Mechanism:**
- COV updates invoke an async callback function
- Default callback: `_log_callback()` logs to backend.log
- PARASITE would override callback to store verify results
- Callback receives: `(point_key: str, new_value: Any)`

**Point Key Format:**
```
"{object_type},{instance}"  # e.g., "analogOutput,0"
```

---

## Error Handling

### Exception Hierarchy

```python
BACnetException (base)
├── BACnetTimeoutError       → HTTP 504
├── BACnetWriteError         → HTTP 502
├── BACnetReadError          → HTTP 502
├── BACnetDeviceNotFoundError → HTTP 404 (implied)
└── ValueError               → HTTP 422 (client validation error)
```

### Detailed Error Scenarios

#### 1. Device Offline / Network Unreachable

**Symptom:** Write request hangs then times out

```
Timeout after 3 retries (1s each) = ~3-4s total latency

Response (HTTP 504):
{
  "detail": "Write timed out: Connection timed out to device 1000"
}
```

**PARASITE Action:** Retry with exponential backoff; mark device offline if persistent

#### 2. Write-Protected Point

**Symptom:** Point object has write protection bit set (vendor-specific)

```
Response (HTTP 502):
{
  "detail": "Write error: Write to analogOutput,0 failed: Access denied"
}
```

**PARASITE Action:** Log as non-controllable point; update equipment profile

#### 3. Value Out of Range

**Symptom:** Written value exceeds point's min/max limits

```
POST /api/niagara/bacnet/devices/1000/points/analogOutput/0/write
{"value": 100.0, "priority": 8}

Response (HTTP 502):
{
  "detail": "Write error: Value 100.0 out of range (5-12°C for this point)"
}
```

**PARASITE Action:** Clamp value to valid range; log why clamping was needed

#### 4. Invalid Priority

**Symptom:** Priority outside 1-16 range

```
POST /api/niagara/bacnet/devices/1000/points/analogOutput/0/write
{"value": 22.5, "priority": 17}

Response (HTTP 422):
{
  "detail": "BACnet priority must be 1-16, got 17"
}
```

**PARASITE Action:** Validation error on request; never happens if using standard priorities

#### 5. Device Not Found

**Symptom:** Device ID not discovered or offline

```
POST /api/niagara/bacnet/devices/9999/points/analogOutput/0/write

Response (HTTP 404):
{
  "detail": "Device 9999 not found"
}
```

**PARASITE Action:** Re-run device discovery; escalate if not found

#### 6. Client Not Started

**Symptom:** BACnet client crashed or not initialized

```
POST /api/niagara/bacnet/devices/1000/points/analogOutput/0/write

Response (HTTP 503):
{
  "detail": "BACnet client is not started. Start the client first."
}
```

**PARASITE Action:** Restart BACnet client; escalate if restart fails

### Retry Strategy (Implemented in Client)

**Configuration:**
```python
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 1.0  # 1 second between retries
```

**Logic:**
1. Attempt write → if succeeds, return True
2. On timeout or transient error → wait 1s, retry
3. After 3 failed attempts → raise BACnetWriteError
4. On permanent error (write-protected, value out of range) → fail immediately, don't retry

**Exponential Backoff (Optional Enhancement):**
```
Retry 1: 1 second
Retry 2: 2 seconds
Retry 3: 4 seconds
Total: ~7 seconds max latency
```

---

## Identified Gaps & Limitations

### 1. COV Callback Registration

**Issue:** COV subscriptions use hardcoded logging callback

**Impact:** PARASITE can't receive real-time feedback through REST API (websocket option would be needed)

**Current Status:** Callbacks stored in memory only; if API restarts, subscriptions lost

**Required for PARASITE:**
- [ ] WebSocket endpoint for COV events: `ws://api:9095/ws/cov/{subscription_id}`
- [ ] Or: Polling endpoint: `GET /api/niagara/bacnet/cov-updates/{subscription_id}?timeout=5`

**Workaround:** PARASITE reads setpoint after write + delays 100-200ms for device response

### 2. Priority Release via REST

**Issue:** No REST endpoint to release a priority level (revert to lower priority)

**Impact:** Technician override workflow incomplete; can't programmatically release technician command

**Current Status:** Method exists in client (`release_point()`), not exposed via API

**Required for PARASITE:**
```
POST /api/niagara/bacnet/devices/{device_id}/points/{object_type}/{instance}/release
{
  "priority": 8  // Release this priority level
}
```

### 3. Batch Write Operations

**Issue:** No endpoint for writing multiple points in one request

**Impact:** Writing damper + fan speed + mode = 3 separate HTTP requests + latency

**Current Status:** Only single-point writes supported

**Required for PARASITE:**
```
POST /api/niagara/bacnet/batch-write
{
  "device_id": 1000,
  "writes": [
    {"object_type": "analogOutput", "instance": 0, "value": 22.5, "priority": 8},
    {"object_type": "binaryOutput", "instance": 0, "value": true, "priority": 8},
    {"object_type": "multiStateOutput", "instance": 1, "value": 2, "priority": 8}
  ]
}
```

### 4. Conditional Writes (Read-Modify-Write)

**Issue:** No atomic read-then-write operation

**Impact:** Race condition possible: read value X, write value Y, but another system wrote between read and write

**Current Status:** Separate read and write endpoints only

**Required for PARASITE:**
```
POST /api/niagara/bacnet/devices/{device_id}/points/{object_type}/{instance}/update
{
  "expected_value": 22.5,  // Read check: fail if current != expected
  "new_value": 23.0,
  "priority": 8
}
```

### 5. Property Read (Not Just Present Value)

**Issue:** Only `presentValue` property is supported for reads/writes

**Impact:** Can't read/write other properties (minValue, maxValue, units, resolution)

**Current Status:** Hardcoded to `presentValue` in BAC0 write string

**Impact Level:** Low (setpoint control only needs presentValue)

### 6. Point Writability Cache

**Issue:** Point writability determined at discovery time; may change if device reconfigured

**Impact:** Obsolete cached info if Niagara configuration changes

**Current Status:** 24-hour TTL on cached point list

**Recommended:** Refresh every 6 hours or on device re-discovery

### 7. Unsupported BACnet Types

**Status:** Currently supported object types:

```python
Supported: analogInput, analogOutput, analogValue,
           binaryInput, binaryOutput, binaryValue,
           multiStateInput, multiStateOutput, multiStateValue,
           device, schedule, calendar, trendLog, notificationClass

Untested: other types (command, event-log, group, loop, etc.)
```

**Known Limitations:**
- Bitstring objects not tested
- Unsigned/signed integers not tested on some devices
- Character string objects not tested
- Time values not tested
- Date values not tested

**Recommendation for PARASITE:** Validate data types on target points before writing

---

## Implementation Details

### BAC0 Library Usage

**Write Format String Syntax:**
```
"{device_id} {object_type},{instance} presentValue {value} - {priority}"
```

**Examples:**
```
"1000 analogOutput,0 presentValue 22.5 - 8"     # Set cooling setpoint to 22.5°C
"1000 binaryOutput,0 presentValue 1 - 8"        # Turn on binary output
"1000 multiStateOutput,5 presentValue 3 - 8"    # Set multi-state to state 3
```

### Client Initialization

```python
from app.services.niagara.bacnet_client import get_bacnet_client

# Singleton client access
client = get_bacnet_client()

# Start BACnet service
await client.start()  # Initialize BAC0 and listen on port 47808

# ... use client ...

# Stop when done
await client.stop()
```

### Example: Write and Verify with COV

```python
import asyncio
from app.services.niagara.bacnet_client import get_bacnet_client

async def write_and_verify(device_id: int, object_type: str, instance: int, value: float):
    client = get_bacnet_client()

    # Step 1: Subscribe to point changes
    sub = await client.subscribe_to_points(
        device_id=device_id,
        points=[(object_type, instance)],
        callback=my_callback,
        lifetime=10
    )

    # Step 2: Write new value
    await client.write_point(
        device_id=device_id,
        object_type=object_type,
        instance=instance,
        value=value,
        priority=8
    )

    # Step 3: Wait for COV notification (5-second timeout)
    verification_result = await asyncio.wait_for(
        verify_write_event.wait(),
        timeout=5.0
    )

    # Step 4: Cancel subscription
    await client.cancel_subscription(sub.subscription_id)

    return verification_result

async def my_callback(point_key: str, new_value):
    print(f"COV Update: {point_key} = {new_value}")
    # Signal verification event
    verify_write_event.set()
```

### Configuration

**Environment Variables:**

```bash
# BACnet network interface (optional, auto-detect if not set)
BACNET_INTERFACE=0.0.0.0

# BACnet port (default 47808)
BACNET_PORT=47808

# Point discovery cache TTL (seconds, default 86400 = 24 hours)
BACNET_CACHE_TTL=86400

# Device discovery timeout (seconds, default 5)
BACNET_DISCOVERY_TIMEOUT=5

# Write operation timeout (seconds, default 10)
BACNET_WRITE_TIMEOUT=10

# Point read timeout (seconds, default 10)
BACNET_READ_TIMEOUT=10
```

---

## Summary: What PARASITE Can Control

### Write-Capable Point Types

✅ **Fully Supported for PARASITE:**
- Analog Output (AO) - Temperature setpoints, valve positions, damper angles
- Binary Output (BO) - Equipment on/off, relay commands, mode selection
- Multi-State Output (MSO) - Fan speed (1-4), valve states, equipment modes

⚠️ **Conditionally Supported:**
- Analog Value (AV) - Only if `writable: true` on device
- Binary Value (BV) - Only if `writable: true` on device
- Multi-State Value (MSV) - Only if `writable: true` on device

❌ **Not Writable:**
- Analog Input (AI), Binary Input (BI), Multi-State Input (MI) - sensors only
- Device object - metadata only
- Schedules, calendars, trend logs - infrastructure only

### Control Workflow Summary

```
1. Discover devices:     POST /api/niagara/bacnet/discover
2. List points:          GET /api/niagara/bacnet/devices/{id}/points
3. Filter writable:      Where point.writable == true
4. Subscribe for feedback: POST /api/niagara/bacnet/subscribe
5. Write command:        POST /api/niagara/bacnet/devices/{id}/points/{type}/{inst}/write
6. Verify:               Wait for COV update or read point
7. Cancel subscription:  DELETE /api/niagara/bacnet/subscribe/{id}
```

### Key Constraints for PARASITE

- **Priority 8:** Can be overridden by technician (priority 7) or emergency (priority 1)
- **Retry 3x:** Transient failures recover automatically
- **COV Feedback:** Use for write verification (alternative: read-back with delay)
- **Batch Operations:** Not yet supported (multiple writes = multiple requests)

---

## References

- **BAC0 Documentation:** https://bac0.readthedocs.io/
- **BACnet Standard:** ISO 16663-5 (BACnet/IP)
- **Implementation:** `/backend/app/services/niagara/bacnet_client.py`
- **API Endpoints:** `/backend/app/api/niagara_bacnet.py`
- **Data Models:** `/backend/app/models/niagara.py`
