# Service Records Database Schema

## Overview

The service records schema supports the **Phase 41-03/44/46 Equipment Baseline Diagnostic Workflow** for capturing, analyzing, and validating equipment condition assessments.

**Primary Use Case:** Gen Set 5 baseline diagnostic (WO-2026-0042 → SR-2026-ABC123)

## Core Tables

### 1. service_records
Stores baseline diagnostic inspection sessions linked to work orders.

**Purpose:** Track the complete lifecycle of a diagnostic assessment from notification through analysis.

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `code` | TEXT | Service record code (e.g., "SR-2026-ABC123", unique) |
| `work_order_id` | UUID | Link to work order (WO-2026-0042) |
| `equipment_id` | UUID | Link to equipment (S002-GEN-B1-005) |
| `building_id` | UUID | Link to building/site |
| `service_type` | TEXT | One of: `minor`, `major`, `breakdown`, `callout` |
| `status` | TEXT | One of: `notified`, `in_progress`, `data_collection`, `complete`, `closed` |
| `technician_id` | TEXT | Telegram ID or email of assigned technician |
| `technician_name` | TEXT | Full name for reference |
| `started_at` | TIMESTAMP | When technician started work |
| `completed_at` | TIMESTAMP | When all data was collected |
| `current_prompt` | TEXT | Current step in collection flow (for breakdown service) |
| `items_collected` | JSONB | Array of collected items: `["rpm", "oil_pressure", "vibration_engine_block", ...]` |
| `created_at` | TIMESTAMP | Record creation time |
| `updated_at` | TIMESTAMP | Last modification time |

**Constraints:**
```sql
service_type IN ('minor', 'major', 'breakdown', 'callout')
status IN ('notified', 'in_progress', 'data_collection', 'complete', 'closed')
code UNIQUE
```

**Example Record:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "code": "SR-2026-ABC123",
  "work_order_id": "8fdfe233-7bdb-4244-acd9-289b82a5aa1d",
  "equipment_id": "1d57a018-5585-49b7-b13e-7fd001c44fb8",
  "building_id": "7e7c1500-d9b2-4b43-b7cf-650648816b21",
  "service_type": "breakdown",
  "status": "data_collection",
  "technician_id": "ntaote.moshoeshoe@fnb.co.za",
  "technician_name": "Ntaote Moshoeshoe",
  "items_collected": ["rpm", "oil_pressure", "fuel_pressure", "vibration_engine_block"],
  "current_prompt": "audio_engine_bay",
  "started_at": "2026-02-12T10:30:00Z",
  "completed_at": null,
  "created_at": "2026-02-12T10:00:00Z",
  "updated_at": "2026-02-12T10:45:00Z"
}
```

---

### 2. service_attachments
Stores metadata for files uploaded during baseline diagnostic inspection.

**Purpose:** Track all files (phyphox recordings, photos, samples) with analysis status and results.

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `service_record_id` | UUID | Link to service record |
| `attachment_type` | TEXT | Type of attachment (see constraints) |
| `file_name` | TEXT | Original filename (e.g., "GEN5_BASELINE_VIBRATION_ENGINE_BLOCK_IDLE_20260212.csv") |
| `file_path` | TEXT | Cloud storage path (s3://...) |
| `file_size_bytes` | INTEGER | File size for quota tracking |
| `mime_type` | TEXT | MIME type (text/csv, audio/wav, image/jpeg, etc.) |
| `extracted_data` | JSONB | OCR or FFT analysis results |
| `analysis_status` | TEXT | One of: `pending`, `completed`, `failed` |
| `created_at` | TIMESTAMP | Upload time |

**Constraints:**
```sql
attachment_type IN (
  'service_sheet',
  'audio_recording',
  'oil_sample',
  'diesel_sample',
  'thermal_image',
  'issue_photo',
  'before_photo',
  'after_photo',
  'load_test_video',
  'oil_analysis_report'
)
analysis_status IN ('pending', 'completed', 'failed')
```

**Example Record:**
```json
{
  "id": "f1e2d3c4-b5a6-7890-1234-567890abcdef",
  "service_record_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "attachment_type": "audio_recording",
  "file_name": "GEN5_BASELINE_AUDIO_ENGINE_BAY_FULL_CYCLE_20260212.wav",
  "file_path": "s3://sentinel-storage/service-records/SR-2026-ABC123/GEN5_BASELINE_AUDIO_ENGINE_BAY_FULL_CYCLE_20260212.wav",
  "file_size_bytes": 1234567,
  "mime_type": "audio/wav",
  "analysis_status": "pending",
  "extracted_data": null,
  "created_at": "2026-02-12T11:00:00Z"
}
```

---

### 3. Related Analysis Tables

#### sensor_recordings
Stores vibration data extracted from phyphox CSV files.

| Field | Description |
|-------|-------------|
| `attachment_id` | Link to service_attachments |
| `frequency_hz` | Frequency value (Hz) |
| `amplitude` | Vibration amplitude (m/s² or normalized) |
| `timestamp` | When reading was taken |

**Purpose:** FFT analysis for cavitation, bearing wear, governor hunting detection.

#### audio_analysis
Stores audio frequency analysis results.

| Field | Description |
|-------|-------------|
| `attachment_id` | Link to service_attachments |
| `service_record_id` | Link to service_records |
| `frequency_range` | Frequency band analyzed (200-400 Hz, 5-10 kHz, etc.) |
| `amplitude_db` | Signal strength in dB |
| `anomaly_detected` | Boolean: cavitation, knock, grinding detected? |
| `confidence` | Confidence score (0-1) |

**Purpose:** Detect cavitation hiss, engine knock, detonation, bearing grinding.

#### ocr_attempts
Stores OCR processing results for service sheet photos.

| Field | Description |
|-------|-------------|
| `attachment_id` | Link to service_attachments |
| `service_record_id` | Link to service_records |
| `raw_text` | OCR output before validation |
| `validated_text` | Corrected text after technician review |
| `extracted_fields` | JSON of parsed gauge readings |
| `confidence_score` | OCR confidence (0-1) |
| `status` | pending_review, approved, rejected |

**Purpose:** Auto-extract gauge readings from handwritten or printed service sheets.

#### service_observations
Stores textual observations and notes from technician.

| Field | Description |
|-------|-------------|
| `service_record_id` | Link to service_records |
| `observation_type` | Category: fault_confirmation, repair_action, verification_reading, general_note |
| `content` | Text content |
| `created_at` | Timestamp |

**Purpose:** Store technician's textual descriptions, confirmations, repair notes.

#### service_readings
Stores manual gauge readings captured during inspection.

| Field | Description |
|-------|-------------|
| `service_record_id` | Link to service_records |
| `reading_type` | rpm, oil_pressure, fuel_pressure, oil_temp, coolant_temp, ac_voltage, frequency, etc. |
| `value` | Numeric value |
| `unit` | rpm, psi, celsius, volts, hz, etc. |
| `baseline_value` | Expected/spec value for comparison |
| `deviation_percent` | % difference from baseline |

**Purpose:** Store baseline measurements for trend analysis and degradation detection.

---

## Data Flow for Gen Set 5

```
WO-2026-0042 (Work Order)
    ↓
SR-2026-ABC123 (Service Record)
    ├─ status: notified → in_progress → data_collection → complete
    └─ Attachments (9 files):
        ├─ GEN5_BASELINE_VIBRATION_ENGINE_BLOCK_IDLE.csv
        │  ├─ service_attachments row
        │  ├─ sensor_recordings (FFT analysis)
        │  └─ analysis_status: pending → completed
        │
        ├─ GEN5_BASELINE_AUDIO_ENGINE_BAY_FULL_CYCLE.wav
        │  ├─ service_attachments row
        │  ├─ audio_analysis (detect cavitation hiss)
        │  └─ analysis_status: pending → completed
        │
        ├─ GEN5_BASELINE_PHOTO_FUEL_SYSTEM_01.jpg
        │  ├─ service_attachments row
        │  └─ extracted_data: null (photo, not text)
        │
        └─ [6 more attachments...]

Service Readings:
    ├─ RPM: 1500 (baseline), 1500 (current), 0% deviation
    ├─ Oil Pressure: 42 PSI (baseline), 38 PSI (current), -9.5% deviation
    ├─ Fuel Pressure: 24 PSI (baseline), 18 PSI (current), -25% deviation ← ALARM
    └─ [more readings...]

Service Observations:
    ├─ Fault Confirmation: "Yes, fuel pump cavitation suspected"
    ├─ Root Cause: "Fuel pressure dropped 25%, audio shows cavitation signature"
    └─ Repair Action: "Replace fuel system + governor controller"

Phase 44 AI Analysis (Automatic):
    ├─ FFT Analysis on vibration files
    ├─ Audio Frequency Analysis
    ├─ Trend vs Baseline Comparison
    ├─ Root Cause: 92% confidence = FUEL CAVITATION
    └─ Cost-Benefit Report: R235K vs R611K (save R376K)
```

---

## Indexes

```sql
-- Query by service record code
idx_service_records_code (code)

-- Query by equipment
idx_service_records_equipment (equipment_id)

-- Query by work order
idx_service_records_wo (work_order_id)

-- Query by status for workflow
idx_service_records_status (status)

-- Query by technician
idx_service_records_tech (technician_id)

-- Query attachments by type (vibration, audio, photo)
idx_service_attachments_type (attachment_type)

-- Query analysis status for processing
idx_service_attachments_analysis_status (analysis_status)

-- Query by service record for UI display
idx_service_attachments_record (service_record_id)
```

---

## Common Queries

### Get a service record with all attachments
```sql
SELECT sr.*, COUNT(sa.id) AS attachment_count
FROM service_records sr
LEFT JOIN service_attachments sa ON sr.id = sa.service_record_id
WHERE sr.code = 'SR-2026-ABC123'
GROUP BY sr.id;
```

### Get all pending analysis
```sql
SELECT sa.id, sa.file_name, sa.analysis_status
FROM service_attachments sa
WHERE sa.analysis_status = 'pending'
ORDER BY sa.created_at DESC;
```

### Get data collection progress
```sql
SELECT
  sr.code,
  sr.technician_name,
  array_length(sr.items_collected, 1) AS items_collected_count,
  COUNT(sa.id) AS total_attachments,
  COUNT(CASE WHEN sa.analysis_status = 'completed' THEN 1 END) AS analyzed_count
FROM service_records sr
LEFT JOIN service_attachments sa ON sr.id = sa.service_record_id
WHERE sr.status = 'data_collection'
GROUP BY sr.id;
```

### Get equipment baseline for trend analysis
```sql
SELECT
  sr.code,
  sr.equipment_id,
  sr.created_at,
  sr.items_collected,
  sr.status,
  COUNT(sa.id) AS file_count
FROM service_records sr
LEFT JOIN service_attachments sa ON sr.id = sa.service_record_id
WHERE sr.equipment_id = '1d57a018-5585-49b7-b13e-7fd001c44fb8'
AND sr.status = 'complete'
ORDER BY sr.created_at DESC;
```

---

## Views

### service_records_with_details
Combines service records with equipment and work order information.

```sql
SELECT
  sr.code,
  sr.work_order_code,
  sr.equipment_code,
  sr.equipment_name,
  sr.equipment_type,
  sr.service_type,
  sr.status,
  sr.technician_name,
  sr.created_at,
  sr.completed_at
FROM service_records_with_details;
```

### attachment_statistics
Shows attachment counts and analysis status by service record.

```sql
SELECT
  sr.code,
  total_attachments,
  vibration_files,
  audio_files,
  photo_files,
  total_size_bytes,
  analyzed_count,
  pending_count
FROM attachment_statistics;
```

---

## RLS Policies

**Read Access:**
- Authenticated users can view service records and attachments for their equipment
- Based on equipment → building relationship

**Write Access:**
- System (backend service) can create and update records
- Technician data submitted via Telegram is stored by backend service

**Delete Access:**
- Cascade delete: When service record deleted, all attachments deleted

---

## Storage

### Local Development
- **Database:** PostgreSQL (Supabase, port 55322)
- **File Storage:** S3-compatible (minio or AWS S3)
- **Path Pattern:** `s3://sentinel-storage/service-records/{SR-CODE}/{filename}`

### Example File Paths
```
s3://sentinel-storage/service-records/SR-2026-ABC123/GEN5_BASELINE_VIBRATION_ENGINE_BLOCK_IDLE_20260212.csv
s3://sentinel-storage/service-records/SR-2026-ABC123/GEN5_BASELINE_AUDIO_ENGINE_BAY_FULL_CYCLE_20260212.wav
s3://sentinel-storage/service-records/SR-2026-ABC123/GEN5_BASELINE_PHOTO_FUEL_SYSTEM_01_20260212.jpg
```

---

## API Integration

### Backend Services
- **WorkOrderNotifier:** Creates service records and sends notifications
- **SentryWebhook:** Receives Telegram uploads, stores attachments
- **OCRService:** Processes service sheet photos, extracts gauge readings
- **AudioAnalysis:** FFT analysis of phyphox recordings for cavitation/knock detection
- **SensorAnalysis:** Analyzes vibration patterns for bearing wear, governor hunting

### API Endpoints
- `POST /api/sentry/work-order/notify` - Create service record
- `POST /api/sentry/work-order/response` - Receive attachment
- `GET /api/sentry/work-order/status/{SR-CODE}` - Track progress
- `POST /api/sentry/ocr/process-service-sheet` - OCR analysis
- `GET /api/service-records/{equipment_id}` - Get baseline history

---

## Performance

**Typical Baseline Assessment:**
- 9 files (6 CSV + 3 WAV + photos): ~50-100 MB
- Service record creation: <100ms
- Attachment insertion: <50ms per file
- FFT analysis: 2-5s per vibration file
- Audio analysis: 1-2s per audio file
- Total Phase 44 analysis: 30-60s for all files
- Cost-benefit report generation: <5s

**Storage Scaling:**
- 1 service record: ~50MB (compressed)
- 100 generators with yearly baseline: ~5GB/year
- Archive retention: 7 years = ~35GB per site

---

## Future Enhancements

1. **Compression:** Compress CSV/WAV files before S3 upload (50-70% reduction)
2. **Partitioning:** Partition `service_records` by creation month for large deployments
3. **Archive:** Move >1 year old records to S3 Glacier for cost savings
4. **Real-time:** WebSocket updates for technician progress tracking
5. **Mobile App:** Native app for Telegram-free file uploads
6. **Video Support:** Store load test video recordings for equipment analysis
7. **Comparison Reports:** Auto-generate before/after comparison for Phase 46
