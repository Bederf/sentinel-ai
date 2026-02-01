---
status: implemented
version: 41-02
date: 2026-02-01
---

# Phase 41-02: Service Sheet OCR - Implementation

## Overview

3-stage OCR pipeline for processing service sheet photos submitted via Clawd. Uses Claude Vision API for extraction, validates against equipment-specific templates, and enables technician corrections with full audit trail. All extracted data feeds into the ML training dataset.

## Architecture

```
Technician uploads service sheet photo (via Clawd Telegram)
    ↓
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 1: Claude Vision OCR                                     │
│  - Send photo to Claude Vision API (claude-sonnet-4-20250514)   │
│  - Extract raw text + structured data                           │
│  - Calculate per-field confidence scores (0.0-1.0)              │
│  - Status: processing → stage1_complete                         │
└─────────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 2: Template Validation                                   │
│  - Load template for equipment_type + service_type              │
│  - Type coercion (string → float/int/bool/enum)                 │
│  - Range validation (e.g., battery 10-32V, hour_meter 0-100k)   │
│  - Collect validation issues with severity levels               │
│  - Status: stage1_complete → stage2_complete                    │
└─────────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 3: AI Enhancement + Correction Flow                      │
│  - If validation issues: prompt tech for corrections via Clawd  │
│  - AI fills in missing fields from context                      │
│  - Track corrections with audit trail                           │
│  - Status: stage2_complete → completed/needs_review             │
└─────────────────────────────────────────────────────────────────┘
    ↓
Store in service_readings table (linked to equipment_id)
    ↓
Ready for ML training (Phase 43)
```

## Implementation Status

### ✅ OCR Service (3-Stage Pipeline)

**Service** (`backend/app/services/ocr_service.py` - 472 lines):

```python
class OCRService:
    """3-stage OCR pipeline for service sheet photos."""

    async def process_service_sheet(
        self,
        image_data: bytes,
        equipment_id: str,
        service_type: str,
        service_record_id: str,
        media_type: str = "image/jpeg"
    ) -> Dict[str, Any]:
        """
        Main entry point - runs full 3-stage pipeline.

        Returns:
            {
                "status": "completed" | "needs_review" | "failed",
                "extracted_data": {...},
                "validated_data": {...},
                "pipeline_info": {
                    "stage1_confidence": 0.85,
                    "stage2_validation_score": 0.9,
                    "stage3_enhanced": True,
                    "issues": [...]
                }
            }
        """
```

**Key Methods:**

| Method | Purpose |
|--------|---------|
| `process_service_sheet()` | Main entry - runs full pipeline |
| `_stage1_ocr_extraction()` | Claude Vision API call |
| `_stage2_template_validation()` | Template-based validation |
| `_stage3_ai_enhancement()` | Gap filling and status determination |
| `_coerce_type()` | Type coercion (number, boolean, enum) |
| `_find_extracted_value()` | Find value in nested OCR response |
| `_determine_final_status()` | Based on confidence and issues |

**Design Patterns:**
- Duplicate processing prevention via `_currently_processing` set
- Memory cleanup with `gc.collect()` after each processing
- Graceful fallback (Stage 3 failure returns Stage 2 data)
- Confidence scoring per field (0.0-1.0)

### ✅ OCR Correction Handler

**Handler** (`backend/app/services/clawd_integration/ocr_correction_handler.py` - 235 lines):

```python
class OCRCorrectionHandler:
    """Handles technician corrections for OCR-extracted data via Clawd."""

    async def start_correction_flow(
        self,
        service_record_id: str,
        pipeline_result: Dict[str, Any],
        telegram_user_id: str
    ) -> Dict[str, Any]:
        """Start correction flow for a service record needing review."""

    async def process_correction_response(
        self,
        service_record_id: str,
        response: str
    ) -> Dict[str, Any]:
        """Process technician's correction response."""
```

**Correction Tracking:**
```python
{
    "field": "hour_meter",
    "value": "1247.5",
    "confidence": 1.0,  # Human-verified
    "was_corrected": True,
    "corrected_from": "12475",  # Original OCR value
    "corrected_by": "@jsmith",
    "corrected_at": "2026-02-01T10:30:00Z"
}
```

### ✅ OCR API Endpoints

**Router** (`backend/app/api/ocr.py` - 256 lines):

```bash
# Process service sheet photo
POST /api/ocr/process
  - Multipart file upload
  - Form fields: equipment_id, service_type, service_record_id

POST /api/ocr/process-base64
  - JSON body with base64-encoded image
  - Fields: image_data, media_type, equipment_id, service_type, service_record_id

# Processing status
GET /api/ocr/status/{service_record_id}
  - Returns: status, corrections_pending (if needs_review)

# Correction flow
POST /api/ocr/correction/{service_record_id}
  - Form field: correction (the corrected value)
  - Returns: next prompt or completion

POST /api/ocr/correction/{service_record_id}/start
  - JSON body: pipeline_result, telegram_user_id
  - Starts correction flow

GET /api/ocr/correction/{service_record_id}/status
  - Returns pending corrections count and fields

POST /api/ocr/correction/{service_record_id}/cancel
  - Cancels correction session, returns partial data
```

### ✅ Clawd Webhook Integration

**Endpoints** (`backend/app/api/clawd_webhooks.py`):

```bash
# Service sheet photo upload from Telegram
POST /api/clawd/ocr/process-service-sheet
  - JSON body: service_record_id, equipment_id, service_type,
               telegram_user_id, image_data (base64), media_type
  - Returns: prompt (for correction) or extracted_data

# Correction submission from Telegram
POST /api/clawd/ocr/correction
  - JSON body: service_record_id, correction
  - Returns: next prompt or completion

# Check OCR status
GET /api/clawd/ocr/status/{service_record_id}
```

## Data Flow

### 1. Photo Upload (via Clawd)

```
Technician sends service sheet photo in Telegram
    ↓
Clawd bot receives photo → Encodes to base64
    ↓
POST /api/clawd/ocr/process-service-sheet
{
    "service_record_id": "SR-2026-ABC123",
    "equipment_id": "gen-001",
    "service_type": "minor",
    "telegram_user_id": "@jsmith",
    "image_data": "base64...",
    "media_type": "image/jpeg"
}
```

### 2. OCR Processing

```python
# Stage 1: Claude Vision extraction
response = await client.messages.create(
    model="claude-sonnet-4-20250514",
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": extraction_prompt},
            {"type": "image", "source": {"type": "base64", ...}}
        ]
    }]
)

# Extracted structure
{
    "equipment_code": "GEN-001",
    "service_date": "2026-02-01",
    "hour_meter": {"value": 1247, "confidence": 0.95},
    "readings": {
        "battery_voltage": {"value": 24.5, "unit": "V", "confidence": 0.92},
        "oil_pressure": {"value": 45, "unit": "psi", "confidence": 0.88}
    },
    "checklists": {
        "oil_level": {"checked": True, "value": "good", "confidence": 0.98}
    }
}
```

### 3. Template Validation

```python
# Load template
template = ml_template_service.get_template("generator", "minor")

# Validate each field
for item in template["required_items"]:
    value = find_extracted_value(extracted, item["id"])

    # Type coercion
    if item["type"] == "number":
        value = float(value)

        # Range validation
        if value < item["validation"]["min"]:
            issues.append({
                "field": item["id"],
                "message": f"Value {value} below minimum",
                "severity": "error"
            })
```

### 4. Correction Flow (if needed)

```
API returns needs_review status
    ↓
Clawd shows: "⚠️ Battery voltage not detected. Please type the value:"
    ↓
Technician replies: "24.5"
    ↓
POST /api/clawd/ocr/correction
{
    "service_record_id": "SR-2026-ABC123",
    "correction": "24.5"
}
    ↓
System validates, stores with was_corrected=true
    ↓
Next prompt or completion
```

### 5. Data Storage

```python
# Stored in service_readings table
{
    "id": "uuid",
    "service_record_id": "SR-2026-ABC123",
    "reading_name": "battery_voltage",
    "reading_value": "24.5",
    "reading_unit": "V",
    "numeric_value": 24.5,
    "ocr_confidence": 0.92,
    "was_corrected": False,
    "corrected_from": None,
    "source": "ocr"
}
```

## Extraction Prompt

Claude Vision receives equipment context for better extraction:

```
Analyze this equipment service worksheet image.

Equipment Type: generator
Asset Name: Generator-001
Service Type: minor

Extract ALL fields you can find and return as JSON with this structure:
{
    "equipment_code": "string (from form header)",
    "service_date": "YYYY-MM-DD",
    "technician": "string",
    "hour_meter": number,
    "readings": {
        "field_name": {"value": number_or_string, "unit": "string", "confidence": 0.0-1.0},
        ...
    },
    "checklists": {
        "item_name": {"checked": true/false, "value": "good/low/critical", "confidence": 0.0-1.0},
        ...
    },
    "samples": [
        {"type": "oil/diesel/coolant", "taken": true/false, "sample_id": "string"},
        ...
    ],
    "notes": "any observations or comments",
    "overall_confidence": 0.0-1.0
}

Be thorough - extract every reading, checkbox, and note visible on the form.
For confidence scores: 1.0 = clearly legible, 0.5 = partially readable, 0.0 = guessed/unclear.
```

## Type Coercion

The validation stage performs automatic type coercion:

| Target Type | Coercion Logic |
|-------------|----------------|
| `number` | Strip non-numeric chars, convert to float, validate min/max |
| `boolean` | Match "yes", "true", "checked", "☑", "✓", "1", "x" → True |
| `enum` | Exact match first, then fuzzy substring match |
| `text` | Default - keep as string |

**Range Validation Examples:**
```python
{
    "battery_voltage": {"min": 10, "max": 32},      # Volts
    "hour_meter": {"min": 0, "max": 100000},        # Hours
    "oil_pressure": {"min": 20, "max": 80},         # PSI
    "coolant_temp": {"min": 60, "max": 100}         # Celsius
}
```

## Confidence Scoring

| Score | Meaning | Action |
|-------|---------|--------|
| 0.9-1.0 | Clearly legible | Accept automatically |
| 0.7-0.9 | Mostly clear | Accept with flag |
| 0.5-0.7 | Partially readable | Needs review |
| 0.0-0.5 | Guessed/unclear | Requires correction |

**Final Status Determination:**
```python
def _determine_final_status(ocr_confidence, validation_score, issues):
    error_count = len([i for i in issues if i["severity"] == "error"])

    if error_count > 0:
        return "needs_review"
    elif validation_score < 0.7 or ocr_confidence < 0.6:
        return "needs_review"
    else:
        return "completed"
```

## Testing

### API Tests

```bash
# Test OCR service import
python -c "from app.services.ocr_service import OCRService; print('OK')"

# Test correction handler
python -c "from app.services.clawd_integration.ocr_correction_handler import OCRCorrectionHandler; print('OK')"

# Full unit tests
pytest tests/services/test_ocr_service.py -v
pytest tests/services/test_ocr_correction_handler.py -v
```

### Manual Testing

**Process service sheet (multipart upload):**
```bash
curl -X POST http://localhost:9095/api/ocr/process \
  -F "file=@/path/to/service_sheet.jpg" \
  -F "equipment_id=gen-001" \
  -F "service_type=minor" \
  -F "service_record_id=SR-2026-TEST"
```

**Process service sheet (base64):**
```bash
curl -X POST http://localhost:9095/api/ocr/process-base64 \
  -H "Content-Type: application/json" \
  -d '{
    "image_data": "base64...",
    "media_type": "image/jpeg",
    "equipment_id": "gen-001",
    "service_type": "minor",
    "service_record_id": "SR-2026-TEST"
  }'
```

**Check status:**
```bash
curl http://localhost:9095/api/ocr/status/SR-2026-TEST
```

**Submit correction:**
```bash
curl -X POST http://localhost:9095/api/ocr/correction/SR-2026-TEST \
  -F "correction=24.5"
```

### Clawd Integration Test

```bash
# Simulate Clawd photo upload
curl -X POST http://localhost:9095/api/clawd/ocr/process-service-sheet \
  -H "Content-Type: application/json" \
  -d '{
    "service_record_id": "SR-2026-TEST",
    "equipment_id": "gen-001",
    "service_type": "minor",
    "telegram_user_id": "@jsmith",
    "image_data": "base64...",
    "media_type": "image/jpeg"
  }'
```

## Security

- Clawd webhook endpoints protected with `X-Clawd-Secret` header
- File uploads validated by MIME type (image/* only)
- Equipment ID validated against database
- Audit trail for all corrections

## Files Reference

**Created:**
- `backend/app/services/ocr_service.py` - 3-stage OCR pipeline (472 lines)
- `backend/app/services/clawd_integration/ocr_correction_handler.py` - Correction flow (235 lines)
- `backend/app/api/ocr.py` - REST API endpoints (256 lines)

**Modified:**
- `backend/app/main.py` - Added OCR router
- `backend/app/api/clawd_webhooks.py` - Added OCR webhook endpoints

**Dependencies:**
- `backend/app/data/ml_data_templates.json` - Equipment templates (23 types)
- `backend/app/services/ml_template_service.py` - Template loading
- `backend/app/database/repositories/equipment_repository.py` - Equipment lookup

## Pattern Reference

Based on `/opt/aimthelaw/backendv2/app/services/receipt_service.py`:
- 3-stage architecture (OCR → Validation → Enhancement)
- Status tracking at each stage
- Confidence scoring per field
- Validation issue collection with severity
- Graceful fallback on stage failure
- Memory cleanup with `gc.collect()`
- Duplicate prevention with `_currently_processing` set

## Next Steps

**Phase 41-03:** Data Validation & Quality Checks
- Cross-validate OCR readings against expected ranges
- Detect anomalies in extracted data
- Quality scoring for ML training data
- Feedback loop for OCR accuracy improvement

## Status

✅ **IMPLEMENTED** - Ready for integration testing

Dependencies:
- Claude Vision API (via ANTHROPIC_API_KEY)
- Clawd bot at `/home/bederf/clawd`
- ML templates in `ml_data_templates.json`
