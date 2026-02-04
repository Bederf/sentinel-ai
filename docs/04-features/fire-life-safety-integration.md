# Fire & Life Safety Integration

## Overview

SENTINEL integrates with the building's fire alarm panel via BACnet/IP for read-only monitoring, and coordinates HVAC shutdown, smoke damper control, stairwell pressurization, and smoke management in response to fire alarm events. The fire panel remains the authoritative source - SENTINEL enhances monitoring with AI-powered status aggregation and coordinates the building's mechanical response through the cause-effect matrix.

## Architecture

```
Fire Alarm Panel (Siemens Cerberus PRO FC726)
     |
     | BACnet/IP (read-only)
     |
SENTINEL Fire System Service
     |
     +-- Fire Zone Monitoring (15 zones)
     |
     +-- Alarm Lifecycle (trigger, acknowledge, clear)
     |
     +-- FireHVACCoordinator
          |
          +-- Cause & Effect Execution
          |     |-- HVAC Shutdown (AHU, FCU, VAV)
          |     |-- Damper Closure (Belimo actuators)
          |     |-- Pressurization Activation (stairwell fans)
          |     |-- Exhaust Activation (smoke extraction)
          |
          +-- Smoke Management Mode
          |     |-- Close supply dampers
          |     |-- Exhaust at 60% (smoke extraction)
          |     |-- Adjacent zone pressurization
          |
          +-- Reset Sequence
                |-- Staged damper re-opening (25% -> 50% -> 100%)
                |-- HVAC restart (AHUs first, then FCU/VAV)
                |-- Pressurization wind-down
```

## Fire Zones

15 fire zones across 3 floors for Sandton City Office Tower (site-002):

| Floor | Zone | Name | Type | Detectors |
|-------|------|------|------|-----------|
| L0 | FZ-L0-A | Lobby | lobby | 4 smoke + 2 MCP |
| L0 | FZ-L0-B | Open Office | office | 6 smoke + 1 MCP |
| L0 | FZ-L0-C | Corridor | corridor | 4 smoke + 2 MCP |
| L0 | FZ-L0-D | Plant Room | plant_room | 2 smoke + 3 heat + 1 MCP |
| L0 | FZ-L0-E | Stairwell A | stairwell | 2 smoke + 1 MCP |
| L1 | FZ-L1-A | Open Office | office | 8 smoke + 2 MCP |
| L1 | FZ-L1-B | Open Office | office | 6 smoke + 1 MCP |
| L1 | FZ-L1-C | Server Room | server_room | 4 smoke + 2 heat + 1 beam + 1 MCP |
| L1 | FZ-L1-D | Corridor | corridor | 4 smoke + 2 MCP |
| L1 | FZ-L1-E | Stairwell B | stairwell | 2 smoke + 1 MCP |
| L2 | FZ-L2-A | Open Office | office | 8 smoke + 2 MCP |
| L2 | FZ-L2-B | Open Office | office | 6 smoke + 1 MCP |
| L2 | FZ-L2-C | Corridor | corridor | 4 smoke + 2 MCP |
| L2 | FZ-L2-D | Plant Room | plant_room | 2 smoke + 3 heat + 1 MCP |
| L2 | FZ-L2-E | Stairwell A | stairwell | 2 smoke + 1 MCP |

## Cause & Effect Matrix

The cause-effect matrix defines the automatic building response to fire alarm triggers.

### Fire Alarm Effects

| Trigger Zone | Type | Effects |
|--------------|------|---------|
| FZ-L0-A (Lobby) | fire | Shutdown AHU-L0, Close DMR-L0-001 |
| FZ-L0-B (Office) | fire | Shutdown AHU-L0, Close DMR-L0-001, Close DMR-L0-002 |
| FZ-L0-E (Stairwell) | fire | Activate PRESS-SW-A (5s delay) |
| FZ-L1-A (Office) | fire | Shutdown AHU-L1, Close DMR-L1-001 |
| FZ-L1-C (Server Room) | fire | Shutdown AHU-L1, Close DMR-L1-002, Activate exhaust (10s delay) |
| FZ-L1-E (Stairwell) | fire | Activate PRESS-SW-B (5s delay) |
| FZ-L2-A (Office) | fire | Shutdown AHU-L2, Close DMR-L2-001 |
| FZ-L2-D (Plant Room) | fire | Shutdown AHU-L2, Close DMR-L2-002 |
| FZ-L2-E (Stairwell) | fire | Activate PRESS-SW-A (5s delay) |

### Fault Effects

| Trigger Zone | Type | Effects |
|--------------|------|---------|
| FZ-L1-C (Server Room) | fault | Alert only for AHU-L1 (no shutdown) |

### Smoke Management Effects

| Trigger Zone | Type | Effects |
|--------------|------|---------|
| FZ-L1-C | smoke_management | Close DMR-L1-002, Exhaust at 60% (5s), Pressurize both stairwells (10s) |
| FZ-L0-B | smoke_management | Close DMR-L0-001 + DMR-L0-002, Exhaust at 60% (5s) |
| FZ-L2-A | smoke_management | Close DMR-L2-001, Exhaust at 60% (5s), Pressurize stairwell A (10s) |

## HVAC Coordination

### Shutdown Sequence

When a fire alarm triggers:

1. **Immediate (Priority 1):** AHU supply fans OFF, smoke dampers CLOSE
2. **Within 5s (Priority 1):** Stairwell pressurization fans ACTIVATE
3. **Within 10s (Priority 2):** Exhaust fans to 60% for smoke extraction

### Damper Closure

Smoke dampers (Belimo actuators) are commanded to position 0% (fully closed) via the FireSafetyRepository dual-write pattern. The repository updates both Supabase and JSON state.

If a damper is in FAULT state (e.g., stuck at 35%), the closure command is logged but not applied - the fault is reported in the coordination results.

### Pressurization Activation

Stairwell pressurization fans target:
- **Speed:** 85% of rated capacity
- **Target pressure:** 50 Pa differential per SANS 10400-T
- **Ramp-up:** Simulated 90% of target during initial activation

### Smoke Management Mode

For sustained fire events, smoke management mode coordinates:

1. Close supply dampers to the fire zone (isolate)
2. Run exhaust fans at 60% to extract smoke
3. Pressurize adjacent zones with +5 Pa to contain smoke spread

## Reset Sequence

When all alarms are cleared (or via engineer force reset):

1. **Damper Re-opening (staged over ~60s):**
   - Stage 1: 25% open
   - Stage 2: 50% open
   - Stage 3: 100% open (normal)

2. **HVAC Restart (sequenced):**
   - AHUs restart first
   - FCU/VAV restart after 30s delay
   - Prevents pressure surges in ductwork

3. **Pressurization Wind-down:**
   - Fan speed reduced to 0%
   - Fans set to OFF

## Safety Rules

8 fire-specific safety rules in `safety_rules.json`:

| Rule | Type | Description |
|------|------|-------------|
| Fire Panel Weekly Test | Interlock | Weekly test required for panel health |
| Damper Exercise Weekly | Interlock | Dampers must cycle weekly to prevent sticking |
| Emergency Lighting Check | Interlock | Emergency lighting battery test (monthly) |
| Fire Pump Run Test | Interlock | Fire pump must run weekly for reliability |
| Battery Voltage Monitor | Custom | Alert if battery < 24.5V, critical < 23.0V |
| Detector Fault Threshold | Custom | Alert if > 2 detector faults simultaneously |
| Damper Position Fault | Custom | Alert if damper stuck (position != target for > 60s) |
| Pressurization Differential | Custom | Alert if pressure < 40 Pa during activation |

## API Reference

### Monitoring Endpoints (61-01)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/fire/status` | Overall fire system status |
| GET | `/api/fire/alarms` | Active fire alarms (optional zone filter) |
| GET | `/api/fire/zones` | All fire zones with detector counts |
| GET | `/api/fire/zones/{zone_id}` | Single zone detail with active alarms |
| GET | `/api/fire/dampers` | Smoke damper positions and health |
| GET | `/api/fire/pressurization` | Stairwell pressurization status |
| GET | `/api/fire/cause-effect` | Cause & effect matrix |
| GET | `/api/fire/health` | System health (battery, comms, faults) |
| POST | `/api/fire/simulate-alarm` | Demo: simulate alarm (legacy sync) |

### Coordination Endpoints (61-02)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/fire/coordination-status` | Current coordination mode and action log |
| POST | `/api/fire/trigger-alarm` | Trigger alarm with full cause-effect execution |
| POST | `/api/fire/clear-alarm` | Clear alarm, auto-reset if no alarms remain |
| POST | `/api/fire/smoke-management` | Enter smoke management mode for zone |
| POST | `/api/fire/reset` | Force reset (ENGINEER auth required) |
| GET | `/api/fire/action-log` | Audit trail of coordination actions |

### Example: Trigger Alarm

```bash
curl -X POST http://localhost:9095/api/fire/trigger-alarm \
  -H "Content-Type: application/json" \
  -d '{"zone_id": "FZ-L1-C", "alarm_type": "smoke"}'
```

Response includes:
- `alarm`: Created alarm details
- `cause_effect.triggered_effects`: List of actions taken
- `cause_effect.devices_affected`: Count of devices commanded
- `coordinator_mode`: Current coordinator state (fire_mode)

### Example: Clear Alarm

```bash
curl -X POST http://localhost:9095/api/fire/clear-alarm \
  -H "Content-Type: application/json" \
  -d '{"alarm_id": "ALM-DF345F9E"}'
```

If this was the last active alarm, the response includes `reset` with the full reset sequence details.

## Chat Integration

The AI chat tool `get_fire_system_status` (tool #16) generates structured markdown reports covering:
- Panel status (normal/alarm/fault)
- Active alarm list with zone details
- Damper health with fault detection
- Pressurization fan status
- Battery voltage and health assessment

## Data Storage

Fire safety data follows the dual-write pattern:

- **Static config** (zones, cause-effect matrix): `fire_system_config.json`
- **Dynamic state** (alarms, damper positions, pressurization, action log): Supabase (primary) + `fire_system_state.json` (fallback)
- **All state changes** go through `FireSafetyRepository` which handles dual-write automatically

## Demo Scenarios

### Pre-configured Demo State
- Panel FAULT status (1 detector fault)
- Stuck damper DMR-L1-001 at 35% (fault)
- Low battery at 25.2V (warning)
- System health: DEGRADED

### Smoke Alarm Simulation
Trigger alarm in FZ-L1-C (Server Room):
1. AHU-L1 shutdown
2. DMR-L1-002 closes
3. Exhaust fan activates at 60%
4. Coordinator enters fire_mode

### Force Reset
Engineer authorization triggers staged return to normal.

## Compliance References

- **SANS 10400-T:** Stairwell pressurization target 50 Pa differential
- **SANS 10139:** Fire detection and alarm systems
- **IEC 62034:** Emergency lighting systems
- **NFPA 72:** National Fire Alarm Code (reference)
- **NFPA 92:** Standard for Smoke Control Systems

---
*Phase: 61-fire-life-safety*
*Last updated: 2026-02-04*
