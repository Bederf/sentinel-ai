---
status: implemented
version: 41-01
date: 2026-01-31
---

# Phase 41-01: Clawd WO Conversation Flow - Implementation

## Overview

Clawd work order conversation flow for ML engineer knowledge capture. When critical equipment alerts occur, Clawd notifies technicians via Telegram in sequential one-by-one prompts, collecting service data (photos, audio, observations) which becomes training data for predictive maintenance models.

## Architecture

```
BMS Alert System
    ↓
Work Order Created
    ↓
bms@company.co.za (Email)
    ↓ (parallel)
Clawd Bot → Telegram Notification
    ↓
Technician replies "done"
    ↓ (sequential prompts)
"📷 Send service sheet photo" ←→ BMS API
    ↓
"🔊 Record engine running (10s)" ←→ Service Record
    ↓
"🛢️ Photo of oil sample" ←→ Supabase Storage
    ↓
All items collected
    ↓
Trigger ML Processing (OCR, Audio Analysis)
    ↓
Store in Training Dataset
```

## Confirmed Workflow

### 1. Fault Alert → WO Creation
- BMS detects fault (e.g., low oil pressure on Generator-001)
- Alert triggers work order creation (manual or automatic)

### 2. Dual Notification (Simultaneous)
- **Email**: technician@company.co.za with WO details
- **Telegram**: Clawd bot sends message to @technician
  ```
  🚨 HIGH PRIORITY WORK ORDER

  Equipment: Generator-001
  Type: Minor Service
  ID: SR-2026-ABC123

  Reply "done" when you complete the service.
  ```

### 3. Technician Performs Service
- Technician goes to equipment location
- **Performs normal service work** (inspections, repairs, maintenance)
- **Does NOT collect ML data** - just does their job
- When finished, replies to Telegram: "done" or "completed"

### 4. Data Collection Workflow Starts (After "done")
Clawd receives "done" → Calls BMS webhook → BMS responds with first prompt:

**Clawd shows technician:**
```
✅ Service completed!

For ML training data, please provide items one by one:

📷 Send a photo of your completed service sheet
```

### 5. Sequential Collection (One-by-One)
- Technician sends service sheet photo
- BMS classifies → Adds to collected items
- BMS responds: "✅ Received! Next: 🔊 Record 10s of engine running"
- Continue through all required items:
  - Service sheet (photo)
  - Audio recording (10-30s)
  - Oil sample (photo)
  - Diesel sample (photo)
  - Observations (optional)

### 6. Completion & ML Processing
- All required items collected → Auto-marked complete
- Triggers ML processing pipeline (Phase 41-02, 41-03)
- Data stored in training dataset

## Implementation Status

### ✅ Backend - Service Record API + Supabase Schema

**Database Schema** (`supabase/migrations/019_service_records.sql`):
- `service_records` - Core service visit records
- `service_readings` - OCR extracted data from service sheets
- `service_attachments` - Photos, audio, documents with metadata
- `service_observations` - Technician text/voice notes
- `ocr_attempts` - Audit trail for OCR accuracy tracking
- `audio_analysis` - Audio features and anomaly detection

**Models** (`backend/app/models/service_record.py`):
- Pydantic models for all entities
- Enum types: ServiceType, ServiceStatus, AttachmentType, SourceType

**API Endpoints** (`backend/app/api/service_records.py`):
```python
POST   /api/service-records              # Create service record
GET    /api/service-records/{id}         # Get with related data
GET    /api/service-records              # List with filters
PATCH  /api/service-records/{id}/status  # Update status
POST   /api/service-records/{id}/reading # Add OCR reading
POST   /api/service-records/{id}/attachment  # Upload file
POST   /api/service-records/{id}/observation # Add note
GET    /api/service-records/{id}/ml-status   # Collection status
POST   /api/service-records/{id}/complete    # Mark complete
GET    /api/template/{eq_type}/{service_type} # Get ML template
```

**Repository** (`backend/app/database/repositories/service_record_repository.py`):
- Full CRUD operations
- Related data fetching (readings, attachments, observations)
- Item collection tracking
- Equipment validation

**ML Templates** (`backend/app/data/ml_data_templates.json`):
- Equipment-specific templates (generator, chiller, pump, AHU, UPS)
- Service type variations (minor/major)
- Required vs optional items per equipment
- Prompt messages with emojis
- Audio duration requirements
- Validation rules (min/max values)

Example template structure:
```json
{
  "generator": {
    "minor": {
      "required": ["service_sheet", "audio_recording", "oil_sample", "diesel_sample"],
      "optional": ["issue_photo", "thermal_image"],
      "prompts": {
        "service_sheet": "📷 Send a photo of your completed service sheet",
        "audio_recording": "🔊 Record 10 seconds of the engine running (hold phone 1m from generator)"
      },
      "audio_duration_seconds": 10
    }
  }
}
```

### ✅ ML Template Service

**Service** (`backend/app/services/ml_template_service.py`):
- Template loading and validation
- Dynamic prompt generation (one-by-one)
- Progress tracking
- Missing item detection
- **Context-aware prompts** for breakdown repairs
- **NLP extraction** from comprehensive responses

Key methods:
```python
get_template(equipment_type, service_type)  # Get full template
get_next_prompt(eq_type, service_type, collected_items)  # Next prompt
validate_collected_items(eq_type, service_type, items)  # Check completion
get_missing_items(eq_type, service_type, collected_items)  # What's missing
list_equipment_types()  # All supported types

# Context-aware methods (NEW)
get_context_aware_prompt(eq_type, service_type, diagnostic_context, collected, step)
get_breakdown_flow(eq_type, diagnostic_context)  # Ordered breakdown steps
extract_info_from_response(eq_type, context, response_text)  # NLP extraction
```

### ✅ Context-Aware Prompts (Breakdown Repairs)

When dispatching from an alert, Clawd already knows the detected fault. Instead of asking open-ended questions, the system uses **context-aware prompts** with pre-filled options.

**Diagnostic Context** (`backend/app/models/service_record.py`):
```python
class DiagnosticContext(BaseModel):
    fault_type: str          # e.g., "fcu_valve_stuck"
    fault_code: str          # e.g., "E04"
    fault_description: str   # e.g., "FCU valve stuck at 15%"
    original_reading: float  # e.g., 25.0 (temp was 25°C)
    setpoint: float          # e.g., 21.0
    deviation: float         # e.g., 4.0
    faulty_equipment: str    # e.g., "FCU-L10-03"
    zone_id: str             # e.g., "Zone-L10-C"
    recommended_actions: List[str]
    parts_required: List[str]
    severity: str            # critical, warning, info
```

**Breakdown Flow** (context-aware steps):
1. `fault_confirmation` - Confirm detected fault (choice: yes/no/different)
2. `root_cause` - Select from equipment-specific options
3. `repair_action` - Select from recommended actions
4. `parts_replaced` - Photo of replacement part
5. `verification_reading` - Confirm repair worked (compare to original)

**Example Conversation**:
```
Clawd: FCU-L10-03 repair complete - thanks!
       We detected: FCU valve stuck at 15% (E04)
       Did you confirm this was the issue?
       □ Yes, confirmed
       □ No, different issue
       □ Partially - multiple issues

Tech: Yes, confirmed

Clawd: What was the root cause?
       □ Actuator motor failed
       □ Actuator jammed mechanically
       □ Control signal issue (0-10V)
       □ Power supply issue (24VAC)

Tech: Actuator motor failed

Clawd: Photo of replacement part label?

Tech: [photo]

Clawd: Zone temp now? (was 25.0°C, setpoint 21.0°C)

Tech: 21.5

Clawd: Service record complete!
```

### ✅ Comprehensive Response Handling

If the technician provides all info in one message, the system extracts it and skips answered steps:

**Input**: "Yes actuator motor failed, replaced Belimo LMV-D3, zone now 21.5C"

**Extraction**:
```python
{
    "fault_confirmation": "confirmed",
    "root_cause": "Actuator motor failed",
    "repair_action": "Replaced component",
    "parts_info": "Belimo LMV-D3",
    "verification_reading": 21.5
}
```

**Response**:
```
Clawd: Got it! (fault confirmed, root cause: Actuator motor failed,
       part: Belimo LMV-D3, temp: 21.5°C)

       Just need a photo of the replacement part label
```

This respects technician time while capturing complete ML training data.

### ✅ Clawd Integration Layer

**Work Order Notifier** (`backend/app/services/clawd_integration/work_order_notifier.py`):
- Sends WO notifications to Clawd
- Handles technician replies
- Manages sequential data collection flow
- File classification (auto-detects service_sheet, oil_sample, etc.)
- Tracks collected items
- Triggers ML processing when complete

Key flow:
1. `notify_technician()` - Send Telegram notification
2. `handle_technician_reply()` - Process "done" or file upload
3. `_classify_attachment()` - Determine attachment type from file
4. `get_collection_status()` - Report what's still needed

**Webhook API** (`backend/app/api/clawd_webhooks.py`):
```python
POST   /api/clawd/work-order/response      # Handle tech replies
GET    /api/clawd/work-order/status/{code}  # Get collection status
POST   /api/clawd/work-order/notify         # Send WO notification
POST   /api/clawd/work-order/complete/{code}  # Mark complete
```

Protected with `X-Clawd-Secret` header for security.

## Data Flow

### 1. WO Assignment

```python
# BMS alert triggers WO
WO assigned to technician → bms@company.co.za

# Parallel notification to Clawd
await work_order_notifier.notify_technician({
    "work_order_id": "wo-123",
    "equipment_id": "eq-123",
    "equipment_name": "Generator-001",
    "service_type": "minor",
    "technician_id": "@jsmith",
    "technician_name": "John Smith"
})
```

**Clawd notification message:**
```
🚨 HIGH PRIORITY WORK ORDER

Equipment: Generator-001 (Sandton Generator #1)
Type: Minor Service
ID: SR-2026-ABC123

Problem: Low oil pressure alarm

Reply "done" when you complete the service.
```

### 2. Technician Replies "done"

Technician completes service → Telegram reply "done"

Clawd webhook calls BMS:
```
POST /api/clawd/work-order/response
{
  "service_record_code": "SR-2026-ABC123",
  "telegram_user_id": "@jsmith",
  "message_type": "text",
  "content": "done"
}
```

BMS responds:
```json
{
  "success": true,
  "type": "ready_for_collection",
  "next_prompt": "📷 Send a photo of your completed service sheet",
  "collected_items": []
}
```

Clawd shows next prompt to technician.

### 3. Sequential Collection

Technician sends service sheet photo → BMS classifies → Add to items → Next prompt:

```
BMS: "Got service sheet! 🔊 Record 10s of engine running (hold phone 1m)"
```

Continue until all required items collected.

### 4. Completion

All items collected → Auto-mark complete:
```json
{
  "is_complete": true,
  "collected_items": ["service_sheet", "audio_recording", "oil_sample", "diesel_sample"],
  "missing_items": [],
  "progress": "4/4",
  "completion_percentage": 100
}
```

Trigger ML processing pipeline (Phase 41-02, 41-03).

## Data Model

### Service Record

```json
{
  "id": "uuid",
  "code": "SR-2026-ABC123",
  "work_order_id": "uuid",
  "equipment_id": "uuid",
  "building_id": "uuid",
  "service_type": "minor",
  "technician_id": "@jsmith",
  "technician_name": "John Smith",
  "telegram_chat_id": "123456789",
  "status": "data_collection",
  "current_prompt": null,
  "items_collected": ["service_sheet", "audio_recording"],
  "created_at": "2026-01-31T10:00:00Z"
}
```

Status flow: `notified` → `in_progress` → `data_collection` → `complete` → `closed`

### Service Reading (OCR)

```json
{
  "id": "uuid",
  "service_record_id": "uuid",
  "reading_type": "hour_meter",
  "value": "1247.5",
  "unit": "hours",
  "numeric_value": 1247.5,
  "source": "ocr",
  "confidence": 0.95
}
```

### Service Attachment

```json
{
  "id": "uuid",
  "service_record_id": "uuid",
  "attachment_type": "service_sheet",
  "file_path": "supabase://service_records/uuid/service_sheet/filename.jpg",
  "file_name": "generator_service.jpg",
  "file_size_bytes": 2048576,
  "mime_type": "image/jpeg",
  "extracted_data": {},  # OCR results
  "analysis_status": "completed"
}
```

## Supported Equipment Types

All 19 equipment types in Sandton building are supported:

### HVAC Equipment

| Equipment | Service Types | Required Items (Minor) | Audio Duration |
|-----------|--------------|------------------------|----------------|
| FCU | minor, major, breakdown | Service sheet, filter, valve operation | 10s |
| VAV | minor, breakdown | Service sheet, damper operation, airflow | 10s |
| AHU | minor, major, breakdown | Service sheet, filter, belt, motor audio | 15s |
| Sensor | minor, breakdown | Calibration check, reading comparison | - |
| Chiller | minor, major, breakdown | Service sheet, compressor audio, sight glass | 30s / 60s |
| Pump | minor, major, breakdown | Service sheet, pump audio, bearing temp | 15s |

### Generator Equipment

| Equipment | Service Types | Required Items (Minor) | Audio Duration |
|-----------|--------------|------------------------|----------------|
| Generator | minor, major, breakdown | Service sheet, audio, oil sample, diesel sample | 10s / 30s |
| Generator Group | minor | Sync test, load sharing check | - |
| Diesel Tank | minor | Tank level, fuel sample, leak inspection | - |

### Energy Centre Equipment

| Equipment | Service Types | Required Items (Minor) |
|-----------|--------------|------------------------|
| MV Incomer | minor | Insulation test, contact inspection |
| Transformer | minor, major | Oil/winding temp, load reading, DGA |
| LV Switchboard | minor | Thermal scan, breaker operation |
| ATS | minor, breakdown | Transfer test, contact inspection |
| UPS | minor, major | Battery test, load reading |
| Power Meter | minor | Accuracy check, CT connection |
| PFC Bank | minor | Capacitor check, contactor operation |
| Feeder | minor | Thermal scan, load reading |

### DALI Lighting Equipment

| Equipment | Service Types | Required Items (Minor) |
|-----------|--------------|------------------------|
| DALI Controller | minor, breakdown | Communication test, addressing check |
| Luminaire Group | minor, breakdown | Operation test, dimming test |
| Daylight Sensor | minor | Calibration check, reading verification |
| Occupancy Sensor | minor, breakdown | Detection test, sensitivity check |

## Testing

### API Tests

```bash
# Create service record
python -m pytest tests/api/test_service_records.py::test_create_service_record -v

# Test ML template service
python -m pytest tests/services/test_ml_template_service.py -v

# Test Clawd webhooks
python -m pytest tests/api/test_clawd_webhooks.py -v
```

### Manual Testing

**Create service record:**
```bash
curl -X POST http://localhost:9095/api/service-records \
  -H "Content-Type: application/json" \
  -d '{
    "work_order_id": "123e4567-e89b-12d3-a456-426614174000",
    "equipment_id": "456e4567-e89b-12d3-a456-426614174000",
    "building_id": "789e4567-e89b-12d3-a456-426614174000",
    "service_type": "minor",
    "technician_id": "@jsmith",
    "technician_name": "John Smith"
  }'
```

**Get ML status:**
```bash
curl http://localhost:9095/api/service-records/SR-2026-ABC123/ml-status
```

**Add attachment:**
```bash
curl -X POST http://localhost:9095/api/service-records/{id}/attachment \
  -F "attachment_type=service_sheet" \
  -F "file=@/path/to/service_sheet.jpg"
```

**Simulate Clawd webhook:**
```bash
curl -X POST http://localhost:9095/api/clawd/work-order/response \
  -H "X-Clawd-Secret: clawd-bms-phase-41" \
  -H "Content-Type: application/json" \
  -d '{
    "service_record_code": "SR-2026-ABC123",
    "telegram_user_id": "@jsmith",
    "message_type": "text",
    "content": "done"
  }'
```

## Security

- Clawd webhook endpoints require `X-Clawd-Secret` header
- File uploads validated by MIME type
- Equipment access checked via repository
- Audit trail logged for all changes

## Next Steps (Phase 41-02 & 41-03)

**Phase 41-02:** Service Sheet OCR
- Claude Vision API integration
- Reading extraction (hour meter, battery voltage, pressures)
- Validation rules and alerts
- Training data storage

**Phase 41-03:** Audio Analysis
- librosa feature extraction
- Bearing fault detection (MFCC analysis)
- Knock detection algorithms
- Confidence scoring

## Files Reference

**Backend:**
- `supabase/migrations/019_service_records.sql` - Database schema
- `backend/app/models/service_record.py` - Pydantic models (includes DiagnosticContext)
- `backend/app/api/service_records.py` - REST API endpoints
- `backend/app/api/alerts.py` - Alert creation and dispatch endpoints
- `backend/app/database/repositories/service_record_repository.py` - Data access
- `backend/app/services/ml_template_service.py` - Template management + context-aware prompts
- `backend/app/services/zone_diagnostics.py` - Zone fault analysis and root cause
- `backend/app/data/ml_data_templates.json` - Equipment templates (19 types)
- `backend/app/services/clawd_integration/work_order_notifier.py` - Clawd integration + comprehensive response handling
- `backend/app/services/clawd_integration/alert_notifier.py` - Send alerts to Telegram
- `backend/app/api/clawd_webhooks.py` - Webhook endpoints
- `backend/app/main.py` - Router inclusion

**Clawd Side** (`/home/bederf/clawd`):
- `tools/wo_notifier.py` - Send WO notifications to BMS
- `tools/wo_conversation_handler.py` - Handle technician replies
- `tools/clawd_ai_bridge.py` - Route WO conversations
- Gmail skill - Email notifications to technicians

## Usage Example

```python
from app.services.clawd_integration.work_order_notifier import work_order_notifier

# When critical alert occurs
await work_order_notifier.notify_technician({
    "work_order_id": wo.id,
    "equipment_id": equipment.id,
    "building_id": building.id,
    "equipment_name": "Generator-001",
    "criticality": "HIGH",
    "service_type": "minor",
    "technician_id": "@jsmith",
    "technician_name": "John Smith",
    "description": "Low oil pressure alarm"
})

# Clawd handles sequential collection
# All data stored in service record
# Trigger ML processing when complete
```

## Status

✅ **IMPLEMENTED** - All components ready for integration testing

Dependencies:
- Clawd bot at `/home/bederf/clawd` (external)
- Telegram notification system
- Supabase storage for files
