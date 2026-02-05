---
title: "Service Feedback System"
type: "guide"
status: "approved"
version: "1.0.0"
created: "2026-02-05"
updated: "2026-02-05"
author: "Sentinel Development Team"
tags: ["feedback", "service", "technician", "health-score", "ml"]
domain: "general"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 10
---

# Service Feedback System

Equipment-type specific feedback collection from technicians after completing work orders. Feedback updates equipment health scores and feeds ML training data.

## Overview

After a technician completes a work order, they submit feedback through the Clawd Telegram bot. The feedback includes:

- Sensor readings (vibration, temperature, pressure, etc.)
- Photos of equipment condition
- Audio recordings (motor sounds, unusual noises)
- Observations and notes

Each equipment type has a specific feedback template defining which inputs are required or optional.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Feedback Collection Service                   │
│  (backend/app/services/feedback_collection_service.py)          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌───────────────┐   ┌───────────────┐   ┌───────────────┐     │
│  │   Template    │   │   Session     │   │   Health      │     │
│  │   Manager     │   │   Manager     │   │   Calculator  │     │
│  └───────┬───────┘   └───────┬───────┘   └───────┬───────┘     │
│          │                   │                   │              │
│          │    ┌──────────────┴──────────────┐    │              │
│          └────►  Feedback Session           ◄────┘              │
│               │  - work_order_id            │                   │
│               │  - equipment_id             │                   │
│               │  - items[]                  │                   │
│               │  - progress                 │                   │
│               └──────────────┬──────────────┘                   │
│                              │                                  │
└──────────────────────────────┼──────────────────────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
          ▼                    ▼                    ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  Equipment       │  │  ML Training     │  │  Clawd Bot       │
│  Health Update   │  │  Data Store      │  │  Notification    │
└──────────────────┘  └──────────────────┘  └──────────────────┘
```

## Feedback Templates

Templates are loaded from `backend/app/data/ml_data_templates.json` and define equipment-type specific feedback fields.

### Template Structure

```json
{
  "equipment_types": {
    "CHILLER": {
      "name": "Chiller",
      "readings": [
        {
          "key": "vibration_level",
          "label": "Vibration Level",
          "unit": "mm/s",
          "type": "numeric",
          "required": true,
          "baseline_comparison": true,
          "thresholds": {
            "good": [0, 4.5],
            "warning": [4.5, 7.1],
            "critical": [7.1, null]
          }
        }
      ],
      "observations": [
        {
          "key": "unusual_noise",
          "label": "Any unusual noises?",
          "type": "boolean",
          "required": true
        }
      ],
      "photos": [
        {
          "key": "compressor_photo",
          "label": "Compressor condition photo",
          "required": false
        }
      ],
      "audio": [
        {
          "key": "motor_sound",
          "label": "Motor running sound recording",
          "duration_seconds": 10,
          "required": false
        }
      ]
    }
  }
}
```

### Supported Equipment Types

| Type | Readings | Observations | Photos | Audio |
|------|----------|--------------|--------|-------|
| CHILLER | vibration, discharge_pressure, suction_pressure, oil_level, refrigerant_temp | unusual_noise, oil_leak, vibration_excessive | compressor, condenser | motor_sound |
| AHU | supply_air_temp, return_air_temp, filter_dp, fan_vibration | filter_dirty, belt_condition, damper_operation | filter, belt, coils | fan_sound |
| FCU | supply_air_temp, coil_dp, fan_speed | thermostat_response, condensate_drain | unit_condition | fan_sound |
| VAV | airflow, damper_position, zone_temp | actuator_operation, duct_seal | damper | actuator_sound |
| GEN | oil_pressure, coolant_temp, battery_voltage, fuel_level | exhaust_smoke, vibration, leak_check | engine, control_panel | running_sound |
| UPS | input_voltage, output_voltage, battery_percent, load_percent | alarm_status, fan_operation | front_panel, batteries | fan_sound |
| DALI | dimming_response, power_consumption | flicker, color_temp_accuracy | luminaire | - |

## API Endpoints

### Session Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/service-feedback/start` | POST | Start feedback session for work order |
| `/api/service-feedback/session/{id}` | GET | Get session status and progress |
| `/api/service-feedback/session/{id}/complete` | POST | Complete feedback session |

### Feedback Submission

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/service-feedback/session/{id}/reading` | POST | Submit sensor reading |
| `/api/service-feedback/session/{id}/observation` | POST | Submit observation |
| `/api/service-feedback/session/{id}/photo` | POST | Submit photo |
| `/api/service-feedback/session/{id}/audio` | POST | Submit audio recording |

### Templates

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/service-feedback/template/{type}` | GET | Get template for equipment type |
| `/api/service-feedback/templates` | GET | List all templates |
| `/api/service-feedback/health-impact-rules` | GET | Get health impact calculation rules |

## Health Impact Calculation

Feedback items are evaluated and categorized by impact:

| Category | Health Impact | Description |
|----------|---------------|-------------|
| `positive` | +2 points | Reading within "good" threshold, positive observation |
| `neutral` | 0 points | Reading acceptable, no issues noted |
| `negative` | -3 points | Reading in "warning" threshold, minor issues |
| `critical` | -5 points | Reading in "critical" threshold, major issues |

### Impact Calculation Flow

```
Feedback Item
     │
     ▼
┌─────────────────┐
│ Has Baseline?   │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
  Yes        No
    │         │
    ▼         ▼
┌─────────┐ ┌─────────────┐
│ Compare │ │ Use Static  │
│ to Base │ │ Thresholds  │
└────┬────┘ └──────┬──────┘
     │             │
     └──────┬──────┘
            │
            ▼
┌─────────────────────┐
│ Determine Category  │
│ (positive/neutral/  │
│  negative/critical) │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Apply Health Delta  │
│ (+2/0/-3/-5)        │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Update Equipment    │
│ Health Score        │
└─────────────────────┘
```

## Usage Examples

### Start Feedback Session

```bash
curl -X POST http://localhost:9095/api/service-feedback/start \
  -H "Content-Type: application/json" \
  -d '{
    "work_order_id": "WO-2024-001234",
    "equipment_id": "eq-uuid-here",
    "equipment_code": "S002-CHILLER-B1-001",
    "service_type": "minor"
  }'
```

**Response:**
```json
{
  "session_id": "fb-session-uuid",
  "equipment_type": "CHILLER",
  "template": {...},
  "required_items": ["vibration_level", "discharge_pressure", "unusual_noise"],
  "optional_items": ["compressor_photo", "motor_sound"]
}
```

### Submit Reading

```bash
curl -X POST http://localhost:9095/api/service-feedback/session/{id}/reading \
  -H "Content-Type: application/json" \
  -d '{
    "key": "vibration_level",
    "value": 3.2,
    "unit": "mm/s",
    "notes": "Measured at compressor housing"
  }'
```

**Response:**
```json
{
  "success": true,
  "item_key": "vibration_level",
  "impact": "positive",
  "health_delta": 2,
  "comparison": {
    "baseline": 2.8,
    "current": 3.2,
    "deviation_percent": 14.3,
    "within_tolerance": true
  }
}
```

### Submit Observation

```bash
curl -X POST http://localhost:9095/api/service-feedback/session/{id}/observation \
  -H "Content-Type: application/json" \
  -d '{
    "key": "unusual_noise",
    "value": false,
    "notes": "Normal operation sounds"
  }'
```

### Complete Session

```bash
curl -X POST http://localhost:9095/api/service-feedback/session/{id}/complete \
  -H "Content-Type: application/json" \
  -d '{
    "technician_notes": "Routine service completed. All readings within normal range.",
    "next_service_recommendation": "6 months"
  }'
```

**Response:**
```json
{
  "success": true,
  "session_id": "fb-session-uuid",
  "summary": {
    "items_submitted": 5,
    "required_complete": true,
    "health_impact": {
      "positive": 3,
      "neutral": 1,
      "negative": 1,
      "critical": 0,
      "net_delta": 3
    },
    "new_health_score": 95,
    "previous_health_score": 92
  }
}
```

## Clawd Bot Integration

The Clawd Telegram bot guides technicians through feedback submission:

```
Bot: Work order WO-2024-001234 marked complete.
     Please submit service feedback for Chiller CH-001.

Bot: 📊 Reading 1 of 3: Vibration Level
     Enter value in mm/s:

Tech: 3.2

Bot: ✅ Vibration: 3.2 mm/s (Good - within baseline)

     📊 Reading 2 of 3: Discharge Pressure
     Enter value in kPa:

Tech: 1450

Bot: ⚠️ Discharge Pressure: 1450 kPa (Elevated - 8% above baseline)
     Add notes? (or type 'skip')

Tech: Ambient temp was high today

Bot: 📸 Optional: Take a photo of the compressor
     Send photo or type 'skip'

Tech: skip

Bot: ✅ Feedback complete!
     Health impact: +2 points (92% → 94%)
     Next service: 6 months recommended
```

## Files

| File | Purpose |
|------|---------|
| `services/feedback_collection_service.py` | Core service with session management, validation, health calculation |
| `api/service_feedback.py` | REST API endpoints |
| `data/ml_data_templates.json` | Equipment-type specific feedback templates |

## Related Documentation

- [Health Scoring System](./health-scoring-system.md) - Health calculation
- [Clawd Integration](../CLAWD_INTEGRATION.md) - Telegram bot
- [Asset Lifecycle State Machine](../05-integrations/asset-lifecycle-state-machine.md) - Workflow states
- [Lifecycle Simulation](./lifecycle-simulation.md) - 24-hour simulation
- [Repair Effectiveness & ML Feedback](./46-repair-effectiveness-ml-feedback.md) - Post-repair validation
