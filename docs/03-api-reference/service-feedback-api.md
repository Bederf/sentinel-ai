---
title: "Service Feedback API Reference"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-02-06"
updated: "2026-02-06"
author: "Sentinel Development Team"
tags: ["api", "service-feedback", "technician", "health-scoring"]
domain: "bms"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 8
---

# Service Feedback API Reference

Phase 41-01 Service Feedback Collection endpoints. Enables technicians to submit structured feedback (readings, observations, photos, audio) after completing work orders, with automatic health score impact calculation.

Base path: `/api/service-feedback`

## Start Feedback Session

### POST `/api/service-feedback/start`

Start a feedback collection session for a completed work order. Returns equipment-type-specific prompts and required items.

**Request Body:**
```json
{
  "work_order_id": "WO-2024-001",
  "equipment_code": "S002-CHILLER-B1-001",
  "service_type": "preventive"
}
```

**Response:**
```json
{
  "session_id": "fb_abc123",
  "equipment_code": "S002-CHILLER-B1-001",
  "equipment_type": "chiller",
  "required_items": ["chw_supply_temp", "chw_return_temp", "compressor_current"],
  "optional_items": ["oil_level", "vibration_reading", "photos"],
  "first_prompt": "What is the chilled water supply temperature?"
}
```

## Session Status

### GET `/api/service-feedback/session/{session_id}`

Get progress of a feedback session.

**Response:**
```json
{
  "session_id": "fb_abc123",
  "status": "in_progress",
  "progress": 0.4,
  "items_collected": 2,
  "next_item": "compressor_current"
}
```

## Submit Reading

### POST `/api/service-feedback/session/{session_id}/reading`

Submit a numerical measurement. Validated against equipment baselines.

**Request Body:**
```json
{
  "item_key": "chw_supply_temp",
  "value": 7.2,
  "unit": "°C",
  "notes": "Stable reading"
}
```

**Response:**
```json
{
  "item_key": "chw_supply_temp",
  "item_type": "reading",
  "value": 7.2,
  "health_impact": "positive",
  "deviation_percent": 2.1
}
```

Health impact values: `positive` (+2), `neutral` (0), `negative` (-3), `critical` (-5)

## Submit Observation

### POST `/api/service-feedback/session/{session_id}/observation`

Submit a text observation or technician notes.

**Request Body:**
```json
{
  "item_key": "visual_inspection",
  "content": "Minor corrosion on pipe fittings, no active leaks",
  "notes": "Recommend monitoring next service"
}
```

## Submit Photo

### POST `/api/service-feedback/session/{session_id}/photo`

Submit a photo for condition assessment. Multipart form upload.

**Form Fields:**
- `item_key` — feedback item key (e.g., `equipment_photo`)
- `notes` — optional description
- `file` — image file (JPEG, PNG)

## Submit Audio

### POST `/api/service-feedback/session/{session_id}/audio`

Submit an audio recording for anomaly detection. Multipart form upload.

**Form Fields:**
- `item_key` — feedback item key (e.g., `bearing_audio`)
- `notes` — optional description
- `file` — audio file (WAV, MP3)

## Complete Session

### POST `/api/service-feedback/session/{session_id}/complete`

Finalize session and update equipment health score.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| force | bool | false | Complete even if required items missing |

**Response:**
```json
{
  "success": true,
  "health_score_change": 2.5,
  "items_collected": 5,
  "feedback_summary": "All readings within normal range",
  "warnings": []
}
```

## Templates

### GET `/api/service-feedback/template/{equipment_type}`

Get feedback template for an equipment type.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| service_type | string | null | Filter by service type |

### GET `/api/service-feedback/templates`

List all available feedback templates with equipment types and configurations.

### GET `/api/service-feedback/health-impact-rules`

Get health score impact calculation rules.
