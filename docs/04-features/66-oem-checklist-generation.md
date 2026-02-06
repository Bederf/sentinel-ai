---
title: "OEM-Specific Checklist Generation"
type: "guide"
status: "approved"
version: "1.0.0"
created: "2026-02-06"
updated: "2026-02-06"
author: "Sentinel Development Team"
tags: ["inspection", "checklist", "oem", "ai-generation", "maintenance", "technician"]
domain: "bms"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 8
---

# OEM-Specific Checklist Generation

AI-generated inspection and maintenance checklists tailored to specific equipment manufacturers and models. Replaces generic templates with OEM-specific tolerances, tools, PPE, and safety requirements.

## Overview

Technicians need equipment-specific inspection checklists when assigned work orders via the Clawd Telegram bot. Previously, only 7 generic templates existed covering basic equipment types. This feature generates manufacturer-specific checklists (e.g., Carrier 30HXC vs York YCAL chillers have different tolerances, service intervals, and required tools).

### Key Capabilities

- **Claude AI Generation**: Generates 3 template variants per equipment OEM: routine inspection, preventive maintenance, annual major service
- **OEM-Specific Tolerances**: Manufacturer documentation-based measurement ranges (e.g., Carrier chiller suction pressure 3.5-5.5 bar vs York 3.0-5.0 bar)
- **Supabase-First Storage**: Templates stored in `inspection_checklist_templates` table with JSON file fallback
- **Idempotent Generation**: Checks for existing OEM templates before generating, avoiding duplicate Claude API calls
- **Demo Mode**: Pre-built demo templates returned without API calls when `DEMO_MODE=true`
- **Client-Editable**: Generated templates are defaults; clients can customize items, tolerances, and tools

## Architecture

```
Equipment Ingestion (SIMBIOT)
         │
         ▼
  ┌──────────────────────┐
  │ ChecklistGenerator    │  ← Claude AI (temp=0.1)
  │   Service             │     or Demo Mode
  └──────────┬───────────┘
             │ 3 templates (routine, preventive, annual)
             ▼
  ┌──────────────────────┐
  │ ChecklistTemplate     │  ← Supabase CRUD
  │   Repository          │     inspection_checklist_templates table
  └──────────┬───────────┘
             │
             ▼
  ┌──────────────────────┐
  │ ChecklistService      │  ← Supabase-first, JSON fallback
  │   (updated)           │     Serves templates to Clawd + API
  └──────────────────────┘
```

## Components

### ChecklistTemplateRepository

**File:** `backend/app/database/repositories/checklist_template_repository.py`

Supabase CRUD for the `inspection_checklist_templates` table (migration 026).

| Method | Description |
|--------|-------------|
| `create_template(data)` | Insert new template |
| `get_template(id)` | Get by UUID |
| `get_templates_for_equipment_type(type)` | All templates for equipment type |
| `get_oem_template(type, manufacturer, model)` | OEM-specific lookup via `ilike` name matching |
| `upsert_template(data)` | Insert or update (conflict on name + type) |
| `update_template(id, updates)` | Update with auto version increment |
| `list_all_templates(is_active)` | List all active templates |
| `delete_template(id)` | Soft delete (set `is_active=false`) |

**OEM Matching Strategy:** Since the `inspection_checklist_templates` table doesn't have dedicated manufacturer/model columns, OEM lookup uses PostgreSQL `ilike` on `template_name` (e.g., `%Carrier%` matches "Carrier 30HXC Chiller Routine Inspection").

### ChecklistGeneratorService

**File:** `backend/app/services/checklist_generator_service.py`

Generates OEM-specific checklists using Claude AI.

| Method | Description |
|--------|-------------|
| `generate_checklists(type, manufacturer, model)` | Generate 3 template variants |
| `generate_for_equipment(equipment_code)` | Lookup metadata, then generate |
| `_build_prompt(...)` | Structured Claude prompt with JSON schema |
| `_parse_response(text)` | Extract and validate JSON from Claude response |

**Template Variants Generated:**

| Variant | Frequency | Duration | Items |
|---------|-----------|----------|-------|
| Routine Inspection | Weekly/Monthly | 15-45 min | 7-10 items |
| Preventive Maintenance | Quarterly | 60-120 min | 8-12 items |
| Annual Major Service | Annual | 120-240 min | 10-15 items |

**Claude API Configuration:**
- Model: `claude-sonnet-4-5-20250929` (from settings)
- Temperature: 0.1 (deterministic output)
- Max tokens: 4096
- Structured JSON output with explicit schema

### ChecklistService (Updated)

**File:** `backend/app/services/checklist_service.py`

Updated with Supabase-first lookups and JSON fallback.

**Changes from Phase 55:**
- All lookup methods try Supabase repository first, fall back to JSON
- New `get_oem_template(equipment_type, manufacturer, model)` method
- `list_all_templates()` merges Supabase + JSON results, deduplicates by name
- Lazy Supabase repository initialization (never crashes if unavailable)

**Fallback Guarantee:** If Supabase is down or not configured, all methods fall back to JSON file behavior identically to the original Phase 55 implementation.

## Checklist Item Schema

Each checklist item follows the established schema from Phase 55:

```json
{
  "category": "Compressor",
  "item_id": "compressor_1_vibration",
  "question": "Compressor #1 Vibration (Carrier spec)",
  "item_type": "measurement",
  "parameter_name": "compressor_1_vibration_rms",
  "unit": "mm/s",
  "tolerance_min": 0.0,
  "tolerance_max": 2.5,
  "required": true,
  "photos_required": false
}
```

**Item Types:**
- `checklist` — Multiple choice with ok/warning/critical options
- `measurement` — Numerical value with OEM-specific tolerance range
- `visual_inspection` — Text notes + optional photos

## Data Flow

### Generation Flow
```
1. Equipment ingested (SIMBIOT MCP) → manufacturer/model known
2. ChecklistGeneratorService.generate_for_equipment(code)
3. Check Supabase for existing OEM templates → if found, return
4. Build Claude prompt with equipment specs
5. Claude returns JSON array of 3 templates
6. Parse, validate, store in Supabase via repository
7. Return stored templates
```

### Lookup Flow (Clawd Bot)
```
1. Technician assigned work order for S002-CHILLER-B1-001
2. Clawd requests checklist: GET /api/clawd/inspection-checklist/chiller
3. ChecklistService.get_template_for_inspection("chiller", "routine")
4. Try Supabase → OEM template found (Carrier 30HXC) → return
5. If not found → fall back to generic JSON chiller_weekly template
```

## Database Schema

Uses existing `inspection_checklist_templates` table from migration 026:

```sql
CREATE TABLE inspection_checklist_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_name TEXT NOT NULL,
    equipment_type TEXT NOT NULL,
    inspection_type TEXT NOT NULL,
    frequency_type TEXT,
    estimated_duration_minutes INTEGER,
    is_active BOOLEAN DEFAULT true,
    version INTEGER DEFAULT 1,
    checklist_items JSONB,          -- Flexible item structure
    required_tools TEXT[],
    required_skills TEXT[],
    safety_requirements TEXT[],
    ppe_required TEXT[],
    created_by TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
```

## Configuration

No new environment variables required. Uses existing settings:

| Setting | Purpose |
|---------|---------|
| `DEMO_MODE` | When `true`, returns pre-built demo templates without Claude API |
| `anthropic_api_key` | Required for live Claude API checklist generation |
| `claude_model` | Model used for generation (default: claude-sonnet-4-5-20250929) |
| Supabase credentials | Required for template storage (JSON fallback if unavailable) |

## Key Design Decisions

1. **One-time generation**: Checklists generated once during ingestion, stored permanently. No repeated Claude calls.
2. **OEM + generic fallback**: If no manufacturer data, generic equipment-type checklist served. Client can upgrade later.
3. **Client-editable**: Templates are AI-generated defaults. PUT endpoint allows customization.
4. **Version tracking**: `version` column increments on edits. Original AI-generated version preserved.
5. **Template reuse**: Same OEM template shared across identical equipment (all Carrier 30HXC0800 units share one template).

## Related Documentation

- [Routine Inspection & Maintenance](45-routine-inspection-maintenance.md) — Phase 55 inspection workflow
- [Service Feedback System](service-feedback-system.md) — Technician feedback after work orders
- [SIMBIOT Concept Connector](../07-integrations/simbiot-concept-connector.md) — Equipment ingestion
