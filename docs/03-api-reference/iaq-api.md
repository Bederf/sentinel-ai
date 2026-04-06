---
title: "Indoor Air Quality API"
type: "reference"
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

# Indoor Air Quality API

## Endpoints

### GET /api/iaq/zones/{site_id}

IAQ scores for all zones in a site.

**Response:**
```json
{
  "site_id": "site-002",
  "total_zones": 20,
  "avg_iaq_score": 82.5,
  "zones_excellent": 8,
  "zones_good": 10,
  "zones_poor": 2,
  "zones_unhealthy": 0,
  "zones": [...],
  "alerts": [...]
}
```

### GET /api/iaq/zones/{site_id}/{zone_id}

Detailed IAQ for a specific zone.

**Response:**
```json
{
  "zone_id": "Zone-001",
  "zone_name": "L0 North",
  "floor": "L0",
  "site_id": "site-002",
  "iaq_score": 85.3,
  "status": "good",
  "components": [
    {
      "component": "co2",
      "value": 695,
      "score": 95.2,
      "weight": 0.3,
      "status": "excellent",
      "unit": "ppm",
      "threshold_info": "695 ppm"
    }
  ],
  "alerts": [],
  "occupancy": 50,
  "area_sqm": 450
}
```

### GET /api/iaq/alerts/{site_id}

Active IAQ alerts for a site.

**Response:**
```json
{
  "site_id": "site-002",
  "total_alerts": 2,
  "critical": 0,
  "warning": 2,
  "alerts": [
    {
      "zone_id": "Zone-001",
      "zone_name": "L0 North",
      "floor": "L0",
      "site_id": "site-002",
      "alert_type": "temp_deviation",
      "severity": "warning",
      "message": "Temperature 24.6C deviates 2.6C from setpoint 22.0C",
      "current_value": 2.6,
      "threshold": 2.0,
      "unit": "C"
    }
  ]
}
```

### GET /api/iaq/compliance/{site_id}

IAQ compliance report.

**Query Parameters:**
- `report_type` — `well` (default) or `esg`

**WELL Response:**
```json
{
  "site_id": "site-002",
  "report_type": "well",
  "generated_at": "2026-03-06T10:00:00Z",
  "overall_score": 82.5,
  "zones_compliant": 16,
  "zones_non_compliant": 4,
  "metrics": {
    "avg_co2_ppm": 620.5,
    "max_co2_ppm": 895,
    "avg_humidity": 44.2,
    "zones_co2_compliant": 18,
    "zones_humidity_compliant": 17,
    "well_air_precondition_met": true
  },
  "recommendations": [
    "Investigate poor-scoring zones for ventilation issues"
  ]
}
```

**ESG Response:**
```json
{
  "site_id": "site-002",
  "report_type": "esg",
  "generated_at": "2026-03-06T10:00:00Z",
  "overall_score": 82.5,
  "zones_compliant": 18,
  "zones_non_compliant": 2,
  "metrics": {
    "total_zones": 20,
    "zones_excellent": 8,
    "zones_good": 10,
    "zones_poor": 2,
    "zones_unhealthy": 0,
    "active_alerts": 2,
    "alert_breakdown": {"temp_deviation": 2}
  },
  "recommendations": [
    "2 zones below 'good' threshold — review ventilation"
  ]
}
```
