---
title: "Sentinel ODS-E Export Endpoint Specification"
type: "spec"
status: "implemented"
version: "1.0.0"
created: "2026-05-18"
updated: "2026-05-18"
tags: ["sentinel", "ods-e", "asoba", "integration", "ltm", "energy-export"]
domain: "integration"
audience: "backend-engineers, integration-specialists"
complexity: "intermediate"
---

# Sentinel ODS-E Export Endpoint Specification

**Purpose:** Make Sentinel a compliant ODS-E data source, enabling direct ingestion by Asoba's eSUMS/Ona Platform and any other ODS-E-compatible consumer without custom integration work.

**Standard:** [ODS-E v0.4.0](https://opendataschema.energy/docs/) — Apache 2.0 / CC-BY-SA 4.0  
**Validation library:** `pip install odse`  
**Implementation:** Phase 209  
**Demo target:** Sandton City site-002 live data

---

## Overview

The ODS-E (Open Data Schema for Energy) export endpoints provide standardized energy data export functionality, allowing Sentinel to serve as a compliant data source for ODS-E consumers like Asoba's eSUMS/Ona Platform.

### Key Features

- **Standard Compliance**: Full ODS-E v0.4.0 schema compliance
- **Dual Format**: JSON and CSV export formats
- **Flexible Filtering**: By site, equipment, time range, and direction
- **Automatic Validation**: Built-in ODS-E validation with error reporting
- **Eskom Integration**: Automatic Megaflex tariff period classification
- **Health Mapping**: Sentinel health scores → ODS-E error types

---

## Endpoints

### 1. `GET /api/integration/odse/export`

Export Sentinel energy timeseries data in ODS-E format.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `site_id` | string | Yes | Sentinel site ID (e.g. `site-002`) |
| `start` | ISO 8601 datetime | Yes | Start of export window (UTC) |
| `end` | ISO 8601 datetime | Yes | End of export window (UTC) |
| `equipment_id` | string | No | Filter to single equipment (e.g. `S002-CHILLER-B1-001`) |
| `direction` | enum | No | `consumption` (default) \| `generation` \| `net` |
| `interval_minutes` | int | No | Aggregation interval — default `15` |
| `format` | enum | No | `json` (default) \| `csv` |

**Example Request:**
```bash
GET /api/integration/odse/export?site_id=site-002&start=2026-05-01T00:00:00Z&end=2026-05-02T00:00:00Z&direction=consumption&interval_minutes=15
```

**Example Response (JSON):**
```json
{
  "schema_version": "0.4.0",
  "source_system": "sentinel-bms",
  "site_id": "site-002",
  "exported_at": "2026-05-18T10:00:00Z",
  "record_count": 96,
  "records": [
    {
      "timestamp": "2026-05-01T00:00:00Z",
      "kWh": 12.4,
      "error_type": "normal",
      "direction": "consumption",
      "fuel_type": "electricity",
      "end_use": "cooling",
      "kVA": 13.1,
      "PF": 0.95,
      "tariff_currency": "ZAR",
      "tariff_period": "off_peak"
    }
  ],
  "asset_metadata": {
    "asset_id": "site-002",
    "asset_type": "commercial_building",
    "site_id": "site-002",
    "location": {
      "country_code": "ZA",
      "municipality_id": "za.gt.johannesburg",
      "municipality_name": "City of Johannesburg",
      "timezone": "Africa/Johannesburg",
      "latitude": -26.1076,
      "longitude": 28.0567
    },
    "building": {
      "building_type": "office",
      "floor_area_sqm": 4500,
      "vintage": "2000_to_2003",
      "climate_zone": "H4"
    }
  },
  "odse_validation": {
    "valid": true,
    "errors": [],
    "warnings": []
  }
}
```

**CSV Format:**
When `format=csv`, returns a text/csv response with metadata headers and data rows.

---

### 2. `GET /api/integration/odse/asset-metadata`

Export Sentinel equipment inventory as ODS-E asset metadata records.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `site_id` | string | Yes | Sentinel site ID |
| `equipment_type` | string | No | Filter by type (e.g. `CHILLER`, `AHU`, `METER`) |
| `include_health` | bool | No | Append current `health_score` to each record (default `true`) |

**Example Request:**
```bash
GET /api/integration/odse/asset-metadata?site_id=site-002&include_health=true
```

**Example Response:**
```json
{
  "schema_version": "0.4.0",
  "source_system": "sentinel-bms",
  "site_id": "site-002",
  "exported_at": "2026-05-18T10:00:00Z",
  "assets": [
    {
      "asset_id": "S002-CHILLER-B1-001",
      "asset_type": "chiller",
      "capacity_kw": 350,
      "site_id": "site-002",
      "oem": "Carrier",
      "location": {
        "country_code": "ZA",
        "municipality_id": "za.gt.johannesburg",
        "timezone": "Africa/Johannesburg"
      },
      "sentinel_extensions": {
        "health_score": 82,
        "equipment_code": "S002-CHILLER-B1-001",
        "floor": "B1",
        "zone": "plant-room",
        "protocol": "BACnet/IP",
        "last_seen": "2026-05-18T09:55:00Z"
      }
    }
  ]
}
```

---

## Implementation

### File Locations

```
backend/app/models/odse_models.py       # Pydantic models
backend/app/services/odse_service.py    # Transformation logic
backend/app/api/odse_export.py          # API router
backend/tests/services/test_odse_export.py  # Tests
```

### Dependencies

```bash
# Already added to backend/requirements.txt
odse>=0.4.0
```

### Router Registration

Registered in `backend/app/api/registrars/analytics.py`:
```python
from app.api import odse_export
app.include_router(odse_export.router, prefix="/api/integration/odse", tags=["ods-e"])
```

---

## Data Transformation

### Health Score → Error Type Mapping

| Sentinel Health Score | ODS-E error_type |
|----------------------|------------------|
| ≥ 80 | `normal` |
| ≥ 60 | `warning` |
| ≥ 40 | `critical` |
| < 40 | `fault` |
| None | `unknown` |

### Equipment Type → End Use Mapping

| Sentinel Equipment Type | ODS-E end_use |
|------------------------|---------------|
| CHILLER, AHU, FCU, VAV, CRAC, SPLIT, COOLING_TOWER, COLD_ROOM, KEF | `cooling` |
| BOILER | `heating` |
| DALI_CONTROLLER, LUMINAIRE | `lighting` |
| GEN, SOLAR_INVERTER | `generation` |
| UPS, MSB, ATS, INCOMER, METER | `other` |

### Eskom Megaflex Tariff Periods

Automatically calculated based on timestamp:

| Period | Weekday Hours | Weekend |
|--------|---------------|---------|
| `peak` | 07:00-10:00, 18:00-20:00 | N/A |
| `standard` | 06:00-07:00, 10:00-18:00, 20:00-22:00 | N/A |
| `off_peak` | All other hours | All day |

---

## Testing

Run tests:
```bash
cd backend
pytest tests/services/test_odse_export.py -v
```

Validate export manually:
```python
import httpx

resp = httpx.get(
    "https://bms.sentinel-ai.co.za/api/integration/odse/export",
    params={
        "site_id": "site-002",
        "start": "2026-05-17T00:00:00Z",
        "end": "2026-05-18T00:00:00Z",
        "interval_minutes": 15,
    },
    headers={"Authorization": "Bearer <token>"}
)
data = resp.json()
print(f"Exported {data['record_count']} records")
print(f"Valid: {data['odse_validation']['valid']}")
```

---

## Integration with Asoba

ODS-E export enables seamless integration with Asoba's eSUMS/Ona Platform:

1. Asoba polls `/api/integration/odse/export` for energy data
2. Asoba ingests `/api/integration/odse/asset-metadata` for asset inventory
3. Bidirectional intelligence: Sentinel health data enriches Asoba fault detection

See also: [Asoba Terminal API MCP Server](./asoba-mcp-server.md)

---

## Future Enhancements

- [ ] Direct EnergyRepository integration (currently using mock data)
- [ ] Real-time streaming export via WebSocket
- [ ] Additional fuel types (gas, water, thermal)
- [ ] Carbon intensity data integration

---

**Document Version:** 1.0.0  
**Last Updated:** 2026-05-18  
**Status:** Implemented (Phase 209)
