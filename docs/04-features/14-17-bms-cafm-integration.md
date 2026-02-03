---
title: "BMS/CAFM Integration & Onboarding"
type: "feature"
status: "implemented"
version: "1.0.0"
created: "2026-02-03"
updated: "2026-02-03"
author: "SENTINEL Development Team"
tags: ["integration", "bms", "cafm", "onboarding", "wizard", "data-ingestion"]
domain: "integration"
audience: "developers"
complexity: "advanced"
estimated_read_time: 15
phase: "14-17"
---

# BMS/CAFM Integration & Onboarding

Comprehensive data integration framework for ingesting BMS alarm logs, trend data, and CAFM work orders into SENTINEL's unified platform.

## Overview

Phases 14-17 implement SENTINEL's overlay architecture:
- **Phase 14**: Integration database schema and parsing services
- **Phase 15**: Multi-step onboarding wizard UI
- **Phase 16**: Monitoring dashboard with quality metrics
- **Phase 17**: Go-live validation checklist

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                  BMS/CAFM Integration Flow                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   External Systems                                              │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐                    │
│   │   BMS    │  │  CAFM    │  │   BCC    │                    │
│   │ (Alarms) │  │ (Assets) │  │ (Trends) │                    │
│   └────┬─────┘  └────┬─────┘  └────┬─────┘                    │
│        │             │             │                           │
│        ▼             ▼             ▼                           │
│   ┌─────────────────────────────────────────┐                  │
│   │           Log Parser Service            │                  │
│   │  • Auto-detect format (CSV/Excel/JSON)  │                  │
│   │  • Detect BMS vendor patterns           │                  │
│   │  • Normalize date/time formats          │                  │
│   └────────────────┬────────────────────────┘                  │
│                    │                                            │
│                    ▼                                            │
│   ┌─────────────────────────────────────────┐                  │
│   │          Point Matcher Service          │                  │
│   │  • Extract asset IDs from point names   │                  │
│   │  • Fuzzy match to CAFM assets           │                  │
│   │  • Confidence scoring (exact/fuzzy)     │                  │
│   └────────────────┬────────────────────────┘                  │
│                    │                                            │
│                    ▼                                            │
│   ┌─────────────────────────────────────────┐                  │
│   │        Integration Database             │                  │
│   │  • log_sources, column_mappings         │                  │
│   │  • ingested_alarms, ingested_trends     │                  │
│   │  • point_asset_mappings, sync_jobs      │                  │
│   └─────────────────────────────────────────┘                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Database Schema (Phase 14)

### Tables

| Table | Purpose |
|-------|---------|
| `log_sources` | Data source configuration |
| `column_mappings` | Field mapping definitions |
| `point_asset_mappings` | BMS point → CAFM asset links |
| `alarm_taxonomy` | 17 standard alarm codes |
| `severity_mappings` | Vendor severity normalization |
| `ingested_alarms` | Normalized alarm history |
| `ingested_trends` | Normalized telemetry data |
| `sync_jobs` | Ingestion run tracking |
| `cafm_assets` | Cached CAFM asset master |
| `cafm_workorders` | Historical work orders |

### Migration

```sql
-- supabase/migrations/010_integration_schema.sql
-- 368 lines, 27 performance indexes
```

## Log Parser Service (Phase 14)

### Auto-Detection

Automatically detects:
- File format: CSV, Excel (.xlsx, .xls), JSON
- Delimiter: comma, semicolon, tab, pipe
- Date format: ISO, SA (dd/mm/yyyy), US (mm/dd/yyyy), EU
- BMS vendor: Honeywell, Siemens, JCI, Schneider

### Vendor Pattern Detection

```python
VENDOR_PATTERNS = {
    "honeywell": r"^[A-Z]{2,4}\d{2,4}[-_]",  # e.g., HVAC01-AHU
    "siemens": r"^S[A-Z]\d{4}",               # e.g., SA1234
    "jci": r"^JCI[-_]",                       # e.g., JCI-CHW-001
    "schneider": r"^SE[-_]"                   # e.g., SE-VAV-001
}
```

### API

```bash
# Detect format
POST /api/integration/detect-format
Content-Type: multipart/form-data

file: <alarm_log.csv>

Response:
{
  "file_format": "csv",
  "delimiter": ",",
  "encoding": "utf-8",
  "row_count": 1543,
  "columns": ["timestamp", "point_id", "value", "status"],
  "detected_vendor": "honeywell",
  "suggested_mappings": {
    "timestamp": "timestamp",
    "point_id": "point_id",
    "value": "value",
    "status": "alarm_state"
  },
  "date_format": "dd/mm/yyyy HH:mm:ss"
}
```

## Point Matcher Service (Phase 14)

### Matching Logic

1. **Extract asset ID** from BMS point name using regex
2. **Exact match** against CAFM asset register
3. **Fuzzy match** using SequenceMatcher (threshold: 0.8)
4. **Confidence scoring** based on match type

```bash
POST /api/integration/match-points
Content-Type: application/json

{
  "building_id": "site-002",
  "points": ["AHU-L1-01-SAT", "CHW-001-FLOW", "VAV-L2-05-DAM"]
}

Response:
{
  "matches": [
    {
      "point_id": "AHU-L1-01-SAT",
      "extracted_asset": "AHU-L1-01",
      "matched_cafm_asset": "AHU-001",
      "confidence": 0.95,
      "match_type": "fuzzy"
    }
  ],
  "unmatched": ["CHW-001-FLOW"],
  "match_rate": 0.67
}
```

## Onboarding Wizard (Phase 15)

### Steps

```
┌─────────────────────────────────────────────────────────────┐
│                    Onboarding Wizard                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   Step 1: Upload          Step 2: Map           Step 3: Match
│   ┌─────────┐             ┌─────────┐           ┌─────────┐
│   │ Upload  │────────────►│ Column  │──────────►│ Point   │
│   │  File   │             │ Mapping │           │ Matching│
│   └─────────┘             └─────────┘           └─────────┘
│                                                      │
│                                                      ▼
│                           Step 4: Review            Step 5: Active
│                           ┌─────────┐           ┌─────────┐
│                           │ Review  │──────────►│ Go Live │
│                           │ Config  │           │   ✓     │
│                           └─────────┘           └─────────┘
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### UI Components

- `IntegrationWizard.tsx` - Multi-step container
- `FileUploadStep.tsx` - Drag-drop file upload
- `ColumnMappingStep.tsx` - Interactive mapping table
- `PointMatchingStep.tsx` - Asset matching review
- `ReviewStep.tsx` - Configuration summary

## Monitoring Dashboard (Phase 16)

### Health Summary

```bash
GET /api/integration/health

Response:
{
  "status": "healthy",
  "sources": {
    "total": 3,
    "active": 3,
    "failed": 0
  },
  "sync_status": {
    "last_sync": "2026-02-03T14:00:00Z",
    "records_synced": 1543,
    "errors": 0
  },
  "mappings": {
    "total_points": 450,
    "matched": 423,
    "unmatched": 27,
    "match_rate": 0.94
  }
}
```

### Quality Metrics

```bash
GET /api/integration/quality-metrics/site-002

Response:
{
  "building_id": "site-002",
  "quality_score": 87,
  "metrics": {
    "match_coverage": 94,
    "data_freshness": 98,
    "error_rate": 2,
    "duplicate_rate": 1
  },
  "thresholds": {
    "match_coverage": {"warning": 80, "critical": 50},
    "freshness_hours": {"warning": 24, "critical": 72}
  }
}
```

### Alerts

| Alert Type | Threshold | Action |
|------------|-----------|--------|
| Stale Data | >24 hours | Warning |
| Error Rate | >10% | Warning |
| Match Coverage | <50% | Critical |
| Sync Failure | Any | Alert |

## Go-Live Checklist (Phase 17)

### Validation Categories

1. **Data Source** (3 checks)
   - Source configured
   - Connection tested
   - Sample data parsed

2. **Point Mapping** (3 checks)
   - Mappings defined
   - >80% points matched
   - No critical unmapped

3. **Data Quality** (3 checks)
   - Quality score >70%
   - No stale data
   - Error rate <10%

4. **Configuration** (2 checks)
   - Sync schedule set
   - Notifications configured

### API

```bash
# Run validation
POST /api/integration/validation/run/site-002

Response:
{
  "building_id": "site-002",
  "status": "ready",
  "checks": [
    {"category": "data_source", "name": "Source configured", "status": "pass"},
    {"category": "point_mapping", "name": "Match rate >80%", "status": "pass"},
    {"category": "data_quality", "name": "Quality score >70%", "status": "warning", "value": 72}
  ],
  "summary": {
    "total": 11,
    "passed": 9,
    "warnings": 2,
    "failed": 0
  },
  "can_activate": true
}

# Activate building
POST /api/integration/validation/activate/site-002

Response:
{
  "building_id": "site-002",
  "status": "active",
  "activated_at": "2026-02-03T15:00:00Z"
}
```

## Implementation

**Database:**
- `supabase/migrations/010_integration_schema.sql`

**Services:**
- `backend/app/services/log_parser.py` - Format detection and parsing
- `backend/app/services/point_matcher.py` - Asset matching

**API:**
- `backend/app/api/integration.py` - Integration endpoints
- `backend/app/database/repositories/integration_repository.py`

**Frontend:**
- `frontend/src/components/IntegrationWizard.tsx`
- `frontend/src/components/IntegrationMonitoringPage.tsx`
- `frontend/src/components/GoLiveChecklist.tsx`

## Related Documentation

- [Asset Workflow Architecture](../05-integrations/asset-workflow-architecture.md)
- [CAFM Schema](../07-integrations/cafm-schema.md)
