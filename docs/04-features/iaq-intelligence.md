---
title: "Indoor Air Quality (IAQ) Intelligence"
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

# Indoor Air Quality (IAQ) Intelligence

**Phase:** Building Operations Orchestration
**Status:** Built and active
**Version:** 1.0

## Overview

IAQ Intelligence calculates per-zone air quality scores from existing telemetry (CO2, humidity, temperature, VOC, PM2.5), generates threshold-based alerts, and produces compliance reports for WELL v2 and ESG certification.

## Architecture

```
HVAC Zone Telemetry → IAQ Service → Scored Zones + Alerts + Compliance Reports
                         ↑
              HVACZoneRepository (Supabase) or JSON fallback
```

The module reads from existing HVAC zone data — no new sensors or ingestion pipelines required.

## IAQ Score Calculation

Each zone receives a composite score (0–100) from five weighted components:

| Component | Weight | Excellent | Good | Warning | Critical |
|-----------|--------|-----------|------|---------|----------|
| CO2 | 30% | < 600 ppm | < 800 ppm | < 1000 ppm | > 1500 ppm |
| Humidity | 20% | 40–55% | 30–60% | > 60% or < 30% | > 70% or < 20% |
| Temperature | 25% | < 0.5C dev | < 1C dev | < 2C dev | > 3C dev |
| VOC | 15% | < 100 ppb | < 300 ppb | < 500 ppb | > 1000 ppb |
| PM2.5 | 10% | < 10 ug/m3 | < 15 ug/m3 | < 25 ug/m3 | > 50 ug/m3 |

Score classification:
- **90+** — Excellent
- **70–89** — Good
- **50–69** — Poor
- **< 50** — Unhealthy

Missing sensors default to 75 (neutral) so the score degrades gracefully.

## Alerts

Alerts are generated when thresholds are breached:

| Alert Type | Warning | Critical |
|------------|---------|----------|
| co2_high | > 1000 ppm | > 1500 ppm |
| humidity_high | > 60% | > 70% |
| humidity_low | — | < 20% |
| temp_deviation | > 2C from setpoint | > 3C from setpoint |
| voc_high | > 500 ppb | > 1000 ppb |
| pm25_high | > 25 ug/m3 | > 50 ug/m3 |

## Compliance Reports

### WELL v2 Air Concept

Checks against WELL Building Standard preconditions:
- CO2 < 800 ppm (precondition)
- Humidity 30–60% (optimization)
- Temperature within 1C of setpoint

Returns: zones compliant/non-compliant, avg CO2, avg humidity, whether WELL Air precondition is met.

### ESG Sustainability

Returns: zone distribution by IAQ status, active alerts breakdown, overall score vs ESG target (80).

## API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/iaq/zones/{site_id}` | IAQ scores for all zones in a site |
| `GET` | `/api/iaq/zones/{site_id}/{zone_id}` | Detailed IAQ for a specific zone |
| `GET` | `/api/iaq/alerts/{site_id}` | Active IAQ alerts |
| `GET` | `/api/iaq/compliance/{site_id}?report_type=well` | WELL compliance report |
| `GET` | `/api/iaq/compliance/{site_id}?report_type=esg` | ESG compliance report |

## Files

| File | Purpose |
|------|---------|
| `backend/app/models/iaq.py` | Pydantic models (IAQZoneScore, IAQAlert, etc.) |
| `backend/app/services/iaq_service.py` | Scoring engine, alert generation, compliance reports |
| `backend/app/api/iaq.py` | FastAPI router (5 endpoints) |
| `backend/app/api/registrars/building.py` | Router registration |
| `backend/tests/services/test_iaq_service.py` | 55 tests |

## Data Sources

- **Primary:** `hvac_zones` table in Supabase (via HVACZoneRepository)
- **Fallback:** `backend/app/data/hvac_zones.json`
- **Fields used:** `co2_ppm`, `humidity`, `current_temp`, `setpoint`, `zone_id`, `zone_name`, `floor`, `site_id`
- **Future:** `voc_ppb`, `pm25_ugm3` when sensors are added

## Integration Points

- **HVAC module:** shares zone data and setpoints
- **Occupancy module:** ventilation demand correlates with occupancy levels
- **Sustainability module:** IAQ metrics feed into ESG reporting
- **Digital Twin:** zone IAQ scores can be visualized on floor plans
- **Event Intelligence:** IAQ alerts can be emitted as operational events
