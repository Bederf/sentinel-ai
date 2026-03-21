---
title: "Semantic Classification API"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-03-21"
updated: "2026-03-21"
author: "Sentinel Development Team"
tags: ["api", "simbiot", "semantic", "classifier", "phase-162"]
domain: "integration"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 8
---

# Semantic classification API

## Overview

Four endpoints supporting the Phase 162 semantic point classifier. They allow callers to classify
individual BACnet/DALI points, batch-classify all points on a piece of equipment, and inspect the
canonical Haystack-inspired tag dictionary.

**Base path:** `/api/semantic-classification`

**Auth:** Bearer token (standard SENTINEL JWT). Role `OPERATOR` or above.

**Router registered in:** `backend/app/api/registrars/operations.py`

---

## POST /api/semantic-classification/classify-point

Classify a single BMS data point.

### Request body

```json
{
  "haystack_id": "S005/ahu-01/sat",
  "point_name": "AHU_01_SUPPLY_AIR_TEMP",
  "equipment_type": "AHU",
  "metadata": {
    "unit": "°C",
    "description": "Supply air temperature sensor AHU-01"
  },
  "value_samples": [18.5, 19.0, 18.8]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `haystack_id` | string | No | Haystack-formatted identifier |
| `point_name` | string | Yes | Raw point name from BMS scan |
| `equipment_type` | string | No | Equipment type code (e.g. `AHU`, `CHILLER`) |
| `metadata` | object | No | Free-form key-value metadata |
| `value_samples` | float[] | No | Recent readings for value-pattern matching |

### Response

```json
{
  "point_name": "AHU_01_SUPPLY_AIR_TEMP",
  "matched_tag": "supply_air_temperature_sensor",
  "confidence": 0.85,
  "confidence_level": "HIGH",
  "safety_class": "LOW",
  "evidence": [
    {
      "source": "point_name",
      "pattern": "*SUPPLY*TEMP*",
      "weight": 0.5,
      "matched": true
    },
    {
      "source": "equipment_type",
      "pattern": "AHU",
      "weight": 0.3,
      "matched": true
    }
  ],
  "validation_report": {
    "errors": [],
    "warnings": [],
    "completeness_score": 0.0,
    "completeness_grade": null,
    "timestamp": "2026-03-21T10:15:30Z"
  }
}
```

| Field | Description |
|-------|-------------|
| `matched_tag` | Best-matching tag name from dictionary. `null` if no tag exceeds LOW confidence. |
| `confidence` | 0.0 – 1.0 score from weighted evidence formula |
| `confidence_level` | `HIGH`, `MEDIUM`, or `LOW` |
| `safety_class` | `LOW`, `MEDIUM`, or `HIGH` — gates downstream control |
| `evidence` | Per-source breakdown of matched rules |
| `validation_report` | Bounds, rate-of-change, and conflict check results |

---

## POST /api/semantic-classification/classify-equipment

Batch-classify all points for a single piece of equipment. Returns individual classifications
plus a template completeness score for the equipment as a whole.

### Request body

```json
{
  "equipment_id": "S005-AHU-B1-001",
  "equipment_type": "AHU",
  "points": [
    {
      "point_name": "AHU_01_SUPPLY_AIR_TEMP",
      "equipment_type": "AHU"
    },
    {
      "point_name": "AHU_01_RETURN_AIR_TEMP",
      "equipment_type": "AHU"
    },
    {
      "point_name": "AHU_01_COOLING_VALVE",
      "equipment_type": "AHU",
      "value_samples": [45.0, 47.5, 46.0]
    }
  ]
}
```

### Response

```json
{
  "equipment_id": "S005-AHU-B1-001",
  "equipment_type": "AHU",
  "classifications": [
    {
      "point_name": "AHU_01_SUPPLY_AIR_TEMP",
      "matched_tag": "supply_air_temperature_sensor",
      "confidence": 0.85,
      "confidence_level": "HIGH",
      "safety_class": "LOW",
      "evidence": [ ... ],
      "validation_report": { ... }
    }
  ],
  "completeness_score": 0.78,
  "completeness_grade": "B",
  "missing_critical_points": ["chw_valve_position_actuator"],
  "missing_important_points": []
}
```

A `DATA_QUALITY_TOO_LOW` validation error is included when `completeness_score < 0.3`,
signalling that control decisions are blocked until critical points are resolved.

---

## GET /api/semantic-classification/dictionary/tags

List all tags in the semantic dictionary with their metadata.

### Query parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `equipment_type` | string | — | Filter tags by equipment domain (e.g. `HVAC`, `LIGHTING`) |
| `safety_class` | string | — | Filter by `LOW`, `MEDIUM`, or `HIGH` |

### Response

```json
{
  "tags": [
    {
      "name": "supply_air_temperature_sensor",
      "display_name": "Supply Air Temperature Sensor",
      "equipment_domain": "HVAC",
      "safety_class": "LOW",
      "writable": false,
      "required_evidence": 1.0,
      "rule_count": 4
    }
  ],
  "total": 47
}
```

---

## GET /api/semantic-classification/dictionary/tag/{name}

Retrieve the full definition for a single tag, including classification rules,
validation bounds, and control envelope.

### Path parameter

`name` — tag name, e.g. `supply_air_temperature_sensor`

### Response

```json
{
  "name": "supply_air_temperature_sensor",
  "display_name": "Supply Air Temperature Sensor",
  "equipment_domain": "HVAC",
  "safety_class": "LOW",
  "writable": false,
  "required_evidence": 1.0,
  "classification_rules": [
    { "source": "haystack_id", "pattern": "**/sat", "weight": 0.9 },
    { "source": "point_name", "pattern": "*SUPPLY*TEMP*", "weight": 0.5 }
  ],
  "negative_samples": ["*RETURN*TEMP*", "*EXHAUST*TEMP*"],
  "validation_bounds": {
    "min": -10.0,
    "max": 40.0,
    "rate_limit": 5.0,
    "alarm_if_exceeded": false
  },
  "control_envelope": null
}
```

Returns `404` if the tag name is not found in the dictionary.

---

## Error responses

| Status | Code | Meaning |
|--------|------|---------|
| 400 | `INVALID_REQUEST` | Missing required fields or malformed JSON |
| 404 | `TAG_NOT_FOUND` | Tag name not in dictionary |
| 422 | `VALIDATION_ERROR` | Pydantic model validation failure |
| 500 | `CLASSIFIER_ERROR` | Unexpected error during classification |

## Related documents

- [Semantic Control Foundation Architecture](../05-integrations/162-semantic-classifier.md) — design and data flow
- [SIMBIOT Universal Adapter Pattern](../05-integrations/simbiot-universal-adapter-pattern.md) — onboarding context
