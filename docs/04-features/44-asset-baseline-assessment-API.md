---
title: "Phase 44: Asset Baseline Assessment - API Documentation"
type: "api-documentation"
status: "implemented"
version: "44.1"
date: "2026-02-01"
phase: "44"
implements: "Asset Baseline Assessment (Technical Phase 44)"
---

# Phase 44: Asset Baseline Assessment API

This document describes the REST API endpoints for capturing and managing equipment baselines as part of Phase 44 implementation.

## Overview

The baseline assessment system allows engineers to:
1. Capture baseline readings during equipment onboarding and maintenance
2. Compare current sensor values to baselines to detect degradation
3. Track baselines at both equipment and element level (bearings, filters, etc.)
4. Generate reports identifying equipment that has drifted from baseline

## Key Features

- **Equipment Baselines**: Store baseline readings for all equipment metrics
- **Element Baselines**: Track baselines for individual components (bearings, filters, coils)
- **Automated Capture**: Automatically capture baselines from BMS sensor averages
- **Deviation Detection**: Compare current readings and flag deviations >15%
- **Reporting**: Generate JSON, HTML, and PDF baseline assessment reports

## Database Schema

### Tables Created

1. **equipment_baselines**: Stores equipment-level baseline readings
2. **equipment_elements**: Defines individual elements within equipment
3. **element_baselines**: Stores element-level baseline readings
4. **baseline_comparisons**: Stores comparison results and deviations

### Views Created

1. **v_equipment_baseline_summary**: Summary of baseline status for all equipment
2. **v_critical_baseline_deviations**: Recent critical deviations (last 30 days)

## API Endpoints

### Equipment Baseline Operations

#### Capture Manual Baseline
```http
POST /api/equipment/{equipment_id}/baseline
```

Capture baseline readings manually entered by engineer.

**Request Body:**
```json
{
  "captured_by": "John Smith",
  "baseline_type": "initial",
  "baseline_values": {
    "chw_supply_temp": 7.2,
    "chw_return_temp": 12.5,
    "motor_current": 145.2
  },
  "measurement_conditions": {
    "ambient_temp": 22,
    "load_percent": 85
  },
  "notes": "Baseline captured during commissioning",
  "attachment_urls": ["https://storage.example.com/photo1.jpg"]
}
```

**Response:**
```json
{
  "success": true,
  "message": "Baseline captured successfully",
  "baseline_id": "123e4567-e89b-12d3-a456-426614174000",
  "equipment_id": "chiller-001",
  "metrics_captured": 3
}
```

#### Capture Automated Baseline
```http
POST /api/equipment/{equipment_id}/baseline/automated
```

Automatically capture baseline by averaging BMS sensor readings over 24 hours.

**Query Parameters:**
- `baseline_type` (optional): Type of baseline (default: "periodic")
- `captured_by` (optional): Defaults to "automated"

**Response:** Same as manual capture

#### Get Active Baseline
```http
GET /api/equipment/{equipment_id}/baseline
```

Retrieve the most recent active baseline for equipment.

**Response:**
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "equipment_id": "chiller-001",
  "baseline_date": "2026-02-01T14:30:00Z",
  "captured_by": "John Smith",
  "baseline_type": "initial",
  "status": "active",
  "baseline_values": {
    "chw_supply_temp": 7.2,
    "chw_return_temp": 12.5,
    "motor_current": 145.2,
    "suction_pressure": 4.2,
    "discharge_pressure": 15.8
  },
  "measurement_conditions": {
    "ambient_temp": 22.0,
    "load_percent": 85
  },
  "source_type": "manual",
  "notes": "Baseline captured during commissioning",
  "attachment_urls": ["https://storage.example.com/photo1.jpg"]
}
```

#### Get Baseline History
```http
GET /api/equipment/{equipment_id}/baseline/history?limit=10
```

List all historical baselines for equipment.

**Query Parameters:**
- `limit` (optional): Maximum baselines to return (default: 10, max: 100)

**Response:** Array of baseline objects

#### Archive Baseline
```http
DELETE /api/equipment/{equipment_id}/baseline/{baseline_id}
```

Archive a baseline record (set status to archived).

**Response:** 204 No Content

### Baseline Comparison Operations

#### Compare Current to Baseline
```http
POST /api/equipment/{equipment_id}/baseline/compare
```

Compare current sensor readings to baseline and calculate deviations.

**Request Body (optional):**
```json
{
  "current_values": {
    "chw_supply_temp": 8.5,
    "motor_current": 168.5
  },
  "data_source": "bms_sensor"
}
```

If `current_values` is not provided, the system will fetch from BMS sensors automatically.

**Response:**
```json
{
  "success": true,
  "comparison_id": "123e4567-e89b-12d3-a456-426614174003",
  "overall_status": "warning",
  "max_deviation_percent": 18.1,
  "critical_count": 0,
  "warning_count": 2,
  "normal_count": 3
}
```

**Deviation Status Levels:**
- **Normal**: ≤10% deviation from baseline
- **Warning**: 10-20% deviation from baseline
- **Critical**: >20% deviation from baseline

#### Get Comparison History
```http
GET /api/equipment/{equipment_id}/baseline/comparisons?limit=10
```

List recent baseline comparison results.

**Query Parameters:**
- `limit` (optional): Maximum comparisons to return (default: 10, max: 50)

**Response:** Array of comparison objects with detailed deviation breakdown

#### Get Critical Deviations
```http
GET /api/equipment/{equipment_id}/baseline/deviations/critical?days=30
```

List baseline comparisons with critical deviations in specified timeframe.

**Query Parameters:**
- `days` (optional): Lookback period (default: 30, max: 365)

**Response:** Array of comparison objects

### Element Baseline Operations

#### Capture Element Baseline
```http
POST /api/equipment/{equipment_id}/elements/{element_id}/baseline
```

Capture baseline for a specific equipment element (bearing, filter, etc.).

**Request Body:**
```json
{
  "captured_by": "Sarah Johnson",
  "measurement_type": "vibration",
  "baseline_type": "initial",
  "baseline_values": {
    "vibration_rms": 1.2,
    "vibration_peak": 2.1,
    "frequency_1x": 50.0,
    "bearing_temp": 45.2
  },
  "measurement_conditions": {
    "load_percent": 85,
    "rpm": 1450
  },
  "notes": "Bearing baseline captured after installation",
  "attachment_urls": ["https://storage.example.com/vibration_spectrum.jpg"]
}
```

**Supported Measurement Types:**
- `vibration`: Vibration analysis (RMS, peak, frequency spectrum)
- `temperature`: Temperature measurements
- `visual_inspection`: Visual/tactile inspection results
- `sound`: Sound level measurements
- `electrical`: Electrical measurements
- `oil_analysis`: Oil analysis results

**Response:** Same format as equipment baseline capture

#### List Equipment Elements
```http
GET /api/equipment/{equipment_id}/elements
```

Get all elements defined for equipment.

**Response:**
```json
[
  {
    "id": "123e4567-e89b-12d3-a456-426614174001",
    "equipment_id": "chiller-001",
    "element_id": "compressor_bearing_1",
    "element_type": "bearing",
    "element_name": "Compressor Bearing #1",
    "manufacturer": "SKF",
    "model": "6316/C3",
    "criticality": "high"
  }
]
```

#### Get Active Element Baseline
```http
GET /api/equipment/{equipment_id}/elements/{element_id}/baseline
```

Get the most recent active baseline for an element.

**Response:** Element baseline object

### Reporting Endpoints

#### Generate JSON Report
```http
GET /api/equipment/{equipment_id}/baseline/report/json?include_elements=true&include_history=true
```

Generate comprehensive baseline assessment report in JSON format.

**Query Parameters:**
- `include_elements` (optional): Include element-level baselines (default: true)
- `include_history` (optional): Include comparison history (default: true)

**Response:** Complete report with equipment info, baseline status, deviation statistics, and recommendations

#### Generate HTML Report
```http
GET /api/equipment/{equipment_id}/baseline/report/html
```

Generate baseline report in HTML format.

**Response:** HTML content as string

#### Generate PDF Report
```http
GET /api/equipment/{equipment_id}/baseline/report/pdf
```

Generate baseline report in PDF format.

**Response:** PDF content as base64-encoded string

#### Get Baseline Summary
```http
GET /api/equipment/{equipment_id}/baseline/summary
```

Get summary statistics about baseline status.

**Response:**
```json
{
  "equipment_id": "chiller-001",
  "has_active_baseline": true,
  "total_baselines": 3,
  "total_elements": 5,
  "elements_with_baselines": 3,
  "last_baseline_date": "2026-02-01T14:30:00Z"
}
```

### Bulk Operations

#### Capture Multiple Baselines
```http
POST /api/equipment/baseline/capture-bulk
```

Initiate automated baseline capture for multiple equipment.

**Request Body:**
```json
{
  "equipment_ids": ["chiller-001", "chiller-002", "ahu-001"],
  "baseline_type": "periodic"
}
```

**Response:**
```json
{
  "success": true,
  "results": [
    {
      "equipment_id": "chiller-001",
      "success": true,
      "baseline_id": "123e4567..."
    },
    {
      "equipment_id": "chiller-002",
      "success": false,
      "error": "No sensor data available"
    }
  ],
  "total": 3,
  "success_count": 2
}
```

## Integration with SIMBIOT

The baseline system integrates with SIMBIOT MCP tools:

### SIMBIOT Tools for Baseline Management

1. **get_asset_metrics_template** - Generate baseline templates for equipment types
2. **configure_asset_metrics** - Save customized baseline configuration

Example workflow:
```bash
# 1. Create building and equipment
→ SIMBIOT: create_building(building_id="sandton", ...)
← Building created

# 2. Import equipment from BMS
→ SIMBIOT: import_point_list(building_id="sandton", point_list=[...])
← 125 equipment assets identified

# 3. Generate baseline templates
→ SIMBIOT: get_asset_metrics_template(building_id="sandton")
← Template with 52 metrics for 6 equipment types

# 4. Engineer captures baselines via REST API
→ POST /api/equipment/chiller-001/baseline
← Baseline captured
```

## Usage Examples

### Example 1: Initial Baseline Capture During Onboarding

```bash
# After creating building and equipment via SIMBIOT

# Capture initial baseline for main chiller
curl -X POST http://localhost:9095/api/equipment/chiller-001/baseline \
  -H "Content-Type: application/json" \
  -d '{
    "captured_by": "Mike Chen",
    "baseline_type": "initial",
    "baseline_values": {
      "chw_supply_temp": 7.2,
      "chw_return_temp": 12.5,
      "motor_current": 145.2,
      "suction_pressure": 4.2,
      "discharge_pressure": 15.8
    },
    "notes": "Baseline captured during commissioning - peak summer conditions"
  }'

# Capture baseline for compressor bearing
curl -X POST http://localhost:9095/api/equipment/chiller-001/elements/compressor_bearing_1/baseline \
  -H "Content-Type: application/json" \
  -d '{
    "captured_by": "Sarah Johnson",
    "measurement_type": "vibration",
    "baseline_type": "initial",
    "baseline_values": {
      "vibration_rms": 1.2,
      "vibration_peak": 2.1,
      "frequency_1x": 50.0,
      "bearing_temp": 45.2
    }
  }'
```

### Example 2: Monthly Baseline Comparison

```bash
# Run automated comparison every month
for equipment in chiller-001 chiller-002 chiller-003; do
  curl -X POST http://localhost:9095/api/equipment/$equipment/baseline/compare \
    -d '{"data_source": "bms_sensor"}'
done

# Check for equipment with critical deviations
curl http://localhost:9095/api/equipment/chiller-001/baseline/deviations/critical

# Generate report for critical equipment
curl http://localhost:9095/api/equipment/chiller-001/baseline/report/json > report.json
```

### Example 3: Post-Repair Validation

```bash
# Before major repair - capture pre-repair baseline
curl -X POST http://localhost:9095/api/equipment/chiller-001/baseline \
  -d '{
    "captured_by": "Service Team",
    "baseline_type": "pre_repair",
    "notes": "Pre-repair baseline before compressor overhaul"
  }'

# ... perform repair ...

# After repair - capture post-repair baseline
curl -X POST http://localhost:9095/api/equipment/chiller-001/baseline \
  -d '{
    "captured_by": "Service Team",
    "baseline_type": "post_repair",
    "notes": "Post-repair baseline after compressor overhaul"
  }'

# Compare baselines to validate repair effectiveness
curl -X POST http://localhost:9095/api/equipment/chiller-001/baseline/compare
```

## Implementation Status

✅ **Completed:**
- Database schema (equipment_baselines, equipment_elements, element_baselines, baseline_comparisons)
- REST API endpoints (equipment baselines, element baselines, comparisons, reports)
- Baseline service (capture, compare, deviation detection)
- Report generation (JSON, HTML, PDF formats)
- Integration with SIMBIOT asset metric templates

📋 **Integration Points:**
- InfluxDB integration for automated sensor capture
- Alert system for critical deviation notifications
- Frontend UI components (future enhancement)

## Next Steps for Technical Phases 45-47

With Phase 44 (Asset Baseline Assessment) now implemented, the foundation is set for:

1. **Phase 45 - Routine Inspection & Maintenance**
   - Build on baseline system to create inspection checklists
   - Schedule recurring inspections based on baseline intervals
   - Track inspection completion and results

2. **Phase 46 - Repair Effectiveness & ML Feedback**
   - Compare pre/post repair baselines
   - Automatically validate repair effectiveness
   - Feed results back to ML models

3. **Phase 47 - Conditional Maintenance**
   - Use baseline deviations to trigger maintenance
   - Optimize maintenance timing based on condition
   - Calculate remaining useful life from trend analysis

## API Testing

Run the development server:
```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 9095
```

Access API documentation:
- Swagger UI: http://localhost:9095/docs
- ReDoc: http://localhost:9095/redoc

Test baseline endpoints:
```bash
# Quick test
curl http://localhost:9095/api/equipment/chiller-001/baseline/summary
```
