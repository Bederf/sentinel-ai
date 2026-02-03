---
title: "Autonomous Decision Engine"
type: "feature"
status: "implemented"
version: "1.0.0"
created: "2026-02-03"
updated: "2026-02-03"
author: "SENTINEL Development Team"
tags: ["autonomous", "decisions", "safety", "escalation", "control"]
domain: "automation"
audience: "developers"
complexity: "advanced"
estimated_read_time: 12
phase: "09"
---

# Autonomous Decision Engine

Level 4 bounded autonomy system enabling limited automatic control within strict safety boundaries, with multi-level escalation and emergency override capabilities.

## Overview

Phase 9 implements SENTINEL's autonomous control capabilities:
- **Plan 09-01**: Core decision engine with rule evaluation
- **Plan 09-02**: Multi-level escalation system
- **Plan 09-03**: Real-time monitoring dashboard
- **Plan 09-04**: Integration and testing

## Control Levels

SENTINEL implements 5 levels of control capability:

| Level | Name | Description | Phase |
|-------|------|-------------|-------|
| 1 | Advisory | AI recommendations only | 4 |
| 2 | Manual Remote | Operator-initiated control | 7 |
| 3 | Supervised | AI suggests, human approves | 8 |
| **4** | **Bounded Autonomy** | **Auto-execute within limits** | **9** |
| 5 | Full Autonomy | Unrestricted (not implemented) | - |

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                 Autonomous Decision Flow                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Trigger (Schedule/Condition/ML)                               │
│              │                                                  │
│              ▼                                                  │
│   ┌─────────────────────┐                                      │
│   │ AutonomousDecision  │                                      │
│   │      Engine         │                                      │
│   └─────────────────────┘                                      │
│              │                                                  │
│         Rule Evaluation                                         │
│              │                                                  │
│              ▼                                                  │
│   ┌─────────────────────┐     ┌─────────────────────┐         │
│   │  SafetyBoundary     │────►│    SafetyEngine     │         │
│   │     Service         │     │    (Phase 6)        │         │
│   └─────────────────────┘     └─────────────────────┘         │
│              │                                                  │
│       Boundary Check                                            │
│         │         │                                             │
│    Within     Approaching/                                      │
│    Limits     Exceeded                                          │
│         │         │                                             │
│         ▼         ▼                                             │
│   ┌──────────┐  ┌──────────────────┐                           │
│   │ Execute  │  │ EscalationEngine │                           │
│   │ Action   │  └──────────────────┘                           │
│   └──────────┘           │                                      │
│         │         ┌──────┴──────┬──────────┬──────────┐        │
│         │         ▼             ▼          ▼          ▼        │
│         │    Level 1       Level 2    Level 3    Level 4       │
│         │    Warning       Alert      Critical   Emergency     │
│         │    (75%)         (85%)      (95%)      (100%)        │
│         │         │             │          │          │        │
│         ▼         ▼             ▼          ▼          ▼        │
│   ┌──────────────────────────────────────────────────────┐     │
│   │                    Audit Logger                       │     │
│   └──────────────────────────────────────────────────────┘     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Safety Boundaries

All autonomous actions validated against strict limits:

| Boundary | Limit | Enforcement |
|----------|-------|-------------|
| Temperature (HVAC) | 16-28°C | 100% |
| Temperature (Chiller Supply) | >5°C | 100% |
| Runtime between starts | ≥5 minutes | 100% |
| Pressure (max) | 1200 kPa | 100% |
| Brightness (max) | 90% | 100% |

## Escalation Levels

```
┌─────────────────────────────────────────────────────────────┐
│                    Escalation Ladder                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   100% ─────────────────────────────── Level 4: EMERGENCY   │
│          │                             • Instant auto-stop   │
│          │                             • Emergency notify    │
│          │                             • Safe state restore  │
│    95% ─────────────────────────────── Level 3: CRITICAL    │
│          │                             • Slack urgent alert  │
│          │                             • Dashboard alert     │
│          │                             • Requires ack        │
│    85% ─────────────────────────────── Level 2: ALERT       │
│          │                             • Email notification  │
│          │                             • Operator awareness  │
│          │                                                   │
│    75% ─────────────────────────────── Level 1: WARNING     │
│          │                             • System logged       │
│          │                             • Dashboard indicator │
│          │                                                   │
│     0% ─────────────────────────────── NORMAL               │
│                                        • Within boundaries   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## API Endpoints

### Autonomous System

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/autonomous/status` | GET | System status and config |
| `/api/autonomous/enable` | POST | Enable autonomous mode |
| `/api/autonomous/disable` | POST | Disable autonomous mode |
| `/api/autonomous/decisions` | GET | Decision history |
| `/api/autonomous/boundaries` | GET | Boundary configuration |

### Escalation System

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/safety/escalation/status` | GET | Current escalation status |
| `/api/safety/escalation/acknowledge` | POST | Acknowledge alert |
| `/api/safety/escalation/history` | GET | Escalation history |
| `/api/safety/emergency-stop` | POST | Emergency stop (all) |

## Example: Decision Execution

```bash
# System makes autonomous decision
POST /api/autonomous/decisions
Content-Type: application/json

{
  "rule_id": "temp-optimization",
  "device_id": "ahu-001",
  "action": "adjust_setpoint",
  "parameters": {
    "point": "cooling_setpoint",
    "current_value": 22.0,
    "proposed_value": 24.0
  },
  "trigger": "schedule",
  "rationale": "Unoccupied period, reduce cooling"
}

Response:
{
  "decision_id": "dec-20260203-001",
  "status": "executed",
  "safety_check": {
    "passed": true,
    "boundary_usage": 0.67,
    "escalation_level": 0
  },
  "result": {
    "success": true,
    "energy_savings_kwh": 2.5,
    "comfort_impact": "none"
  },
  "audit_id": "audit-20260203-001"
}
```

## Example: Escalation Flow

```bash
# Query escalation status
GET /api/safety/escalation/status

Response:
{
  "current_level": 2,
  "level_name": "ALERT",
  "boundary_usage": 0.87,
  "active_alerts": [
    {
      "id": "alert-001",
      "device_id": "chiller-001",
      "boundary": "temperature",
      "current_value": 26.5,
      "limit": 28.0,
      "usage_percent": 87,
      "acknowledged": false,
      "timestamp": "2026-02-03T14:30:00Z"
    }
  ],
  "notifications_sent": ["email"],
  "requires_acknowledgment": true
}

# Acknowledge alert
POST /api/safety/escalation/acknowledge
Content-Type: application/json

{
  "alert_id": "alert-001",
  "acknowledged_by": "operator@facility.com",
  "notes": "Monitoring situation, external temp high"
}
```

## Example: Emergency Stop

```bash
POST /api/safety/emergency-stop
Content-Type: application/json

{
  "reason": "Pressure spike detected",
  "initiated_by": "operator@facility.com"
}

Response:
{
  "success": true,
  "autonomous_mode": "disabled",
  "devices_stopped": 3,
  "safe_state_restored": true,
  "notifications_sent": ["email", "slack", "dashboard"],
  "timestamp": "2026-02-03T15:00:00Z"
}
```

## Demo Scenarios

### 1. Temperature Optimization
- Autonomous adjustment 22°C → 24°C during unoccupied hours
- 5% energy savings
- Safety validation passed

### 2. Lighting Optimization
- Brightness based on occupancy
- 12% energy savings
- Runtime limit enforcement

### 3. Equipment Runtime
- Staggered starts for demand management
- R850/month demand charge savings
- Safety interlock compliance

### 4. Escalation Sequence
- Temperature approaching limit: 23.8°C (85%)
- Level 2 alert triggered
- Email notification sent
- Operator acknowledgment required

### 5. Emergency Response
- Rapid pressure increase simulation
- Level 3 critical alert at 95%
- Automatic stop at Level 4 (100%)
- Safe state restoration

## Implementation

**Services:**
- `backend/app/services/autonomous_decision_engine.py` - Core engine
- `backend/app/services/safety_boundary_service.py` - Boundary monitoring
- `backend/app/services/escalation_engine.py` - Escalation management
- `backend/app/services/notification_service.py` - Multi-channel notifications
- `backend/app/services/emergency_handler.py` - Emergency response

**API:**
- `backend/app/api/autonomous.py` - Autonomous system endpoints

**Frontend:**
- `frontend/src/components/AutonomousPanel.tsx` - Monitoring dashboard
- `frontend/src/components/EscalationAlerts.tsx` - Alert display
- `frontend/src/components/EmergencyControls.tsx` - Override controls

## Related Documentation

- [Device Control & Safety](06-device-control-safety.md)
- [Load Shedding Optimization](10-load-shedding-optimization.md)
- [AI Recommendation System](../08-ai-ml/ai-recommendation-system.md)
