# Equipment Baseline Diagnostic Workflow (Phase 41-03/44/46)

**Purpose:** Establish diagnostic baseline for inherited/legacy equipment to validate repair quotes and enable predictive maintenance through trend analysis.

**Real-World Example:** Gen Set 5 (Mitsubishi S12R-PTA2, 1,100 kW) - Failed after 8 years with R611,820.75 repair quote. Used to validate root cause and negotiate 62% cost reduction to R235K.

**See CLAUDE.md for quick reference. This document covers full technical workflow.**

## Three-Phase Process

**Phase 41-03: External Inspection (30-60 min field visit)**
- Technician captures baseline data without opening equipment
- No invasive procedures, no parts replacement
- Deliverables: 7 phyphox recordings (vibration + audio), manual gauge readings, visual inspection photos

**Phase 44: AI Analysis & Cost-Benefit (1 week analysis)**
- SENTINEL analyzes phyphox FFT signatures to detect failure modes
- Compares current readings to equipment specifications
- Cross-references with equipment failure history (4-year pattern)
- Generates cost-benefit report with repair recommendations
- Output: "Approve quote" vs "Negotiate to X" with data-backed justification

**Phase 46: Post-Repair Validation (after repair completion)**
- Repeat same Phase 41-03 measurements
- Compare pre vs post-repair baselines
- Calculate effectiveness score (target >85%)
- Feed ML models with before/after training data

## Work Order Creation & Notification

Create work order via API:
```bash
POST /api/work-orders/supabase
{
  "equipment_id": "1d57a018-5585-49b7-b13e-7fd001c44fb8",
  "work_type": "diagnostic_assessment",
  "status": "scheduled",
  "priority": "high",
  "title": "Equipment Diagnostic Assessment & Baseline Establishment",
  "description": "Phase 41-03/44/46: Establish diagnostic baseline...",
  "assigned_to": "general",
  "contact": "technician@email.com"
}
```

Response: `WO-2026-0042` created and ready for notification

## Two-Channel Notification (Email + Telegram)

**Email Channel (Detailed Documentation):**
- Recipient: Technician email
- Content: Complete inspection checklist with 9 sections
  - Section 1: Equipment nameplate data (5 min)
  - Section 2: Gauge readings at idle (10 min)
  - Section 3: Gauge readings under load (5 min)
  - Section 4: 6 phyphox vibration recordings (20 min)
  - Section 5: 3 phyphox audio spectrum recordings (20 min)
  - Section 6: Visual inspection & photos (10 min)
  - Section 7: Service history & documentation (5 min)
  - Section 8: Optional specialist samples (fuel/oil analysis)
  - Section 9: Data delivery checklist & file naming conventions
- Attachments: Detailed specifications, file naming guide, critical measurement ranges
- Purpose: Technician reviews offline, uses as reference during field visit

**Telegram Channel (Interactive Collection):**
- Notification: `POST /api/sentry/work-order/notify` triggers Sentry bot message
- Content: Work order number, service record code, equipment details
- Message: "Reply 'done' when inspection complete"
- Purpose: Lightweight notification, entry point for interactive data collection

## Data Collection Flow (Telegram Interactive)

**Step 1: Technician completes inspection using email checklist**
- Records all measurements from Sections 1-7
- Captures phyphox vibration recordings (6 CSV files, 60s each)
- Captures phyphox audio recordings (3 WAV files, 60-120s each)
- Takes 15+ visual inspection photos
- Collects service history documents

**Step 2: Technician replies in Telegram**
```
Technician: "done" or "completed"
↓
Clawd: "Great! Let's collect the data. Send the gauge readings."
```

**Step 3: Interactive data submission via Telegram**
- Clawd prompts for each data item based on equipment type
- Technician submits via Telegram:
  - Text: Gauge readings, observations
  - Files: Phyphox CSV (vibration), WAV (audio), photos (JPEG/PNG)
  - Samples: Oil/fuel samples (photos)
- Each submission automatically classified:
  - CSV files → vibration_recording
  - WAV files → audio_recording
  - Photos → service_sheet, photo_before, photo_after, thermal_image, oil_sample, diesel_sample
  - Service sheet photos → OCR processing (auto-extract gauge readings)

**Step 4: Progress tracking**
```
Clawd: "✓ RPM recorded, ✓ Oil pressure recorded, ✓ Vibration file received
        Missing: 2 audio files, 5 photos
        Progress: 65% complete
        Send next audio file..."
```

**Step 5: Completion**
```
Clawd: "All data collected! Service record complete.
        SENTINEL is analyzing... Check dashboard tomorrow
        for Phase 44 cost-benefit analysis."
```

## Clawd Bot API Endpoints

**Send work order notification:**
```python
POST /api/sentry/work-order/notify
Headers: X-Sentry-Secret: sentry-bms-phase-41
Body: {
  "work_order_id": "uuid",
  "equipment_id": "uuid",
  "equipment_name": "Gen Set 5 (Mitsubishi S12R-PTA2, 1,100 kW)",
  "criticality": "HIGH",
  "service_type": "diagnostic_assessment",
  "technician_id": "email",
  "technician_name": "Technician Name",
  "description": "Phase 41-03 external inspection..."
}
Response: {"success": true, "service_record_code": "SR-2026-ABC123"}
```

**Handle technician response (text/photo/audio/file):**
```python
POST /api/sentry/work-order/response
Headers: X-Sentry-Secret: sentry-bms-phase-41
Body: {
  "service_record_code": "SR-2026-ABC123",
  "telegram_user_id": "123456789",
  "message_type": "text|photo|audio|file",
  "content": {...}
}
Response: {"success": true, "next_prompt": "...", "collected_items": [...]}
```

**Get data collection status:**
```python
GET /api/sentry/work-order/status/{service_record_code}
Response: {
  "status": "DATA_COLLECTION",
  "collected_items": ["rpm", "oil_pressure", "vibration_engine_block"],
  "missing_items": ["vibration_fuel_pump", "audio_engine_bay"],
  "progress": [3, 7],
  "completion_percentage": 43
}
```

**Mark service record complete:**
```python
POST /api/sentry/work-order/complete/{service_record_code}
Response: {"success": true, "ml_processing_initiated": true}
```

## Supabase Tables

**service_records table:**
- `code`: SR-2026-ABC123 (auto-generated)
- `work_order_id`: Links to work order
- `equipment_id`: Links to equipment
- `service_type`: "diagnostic_assessment" or "breakdown"
- `status`: NOTIFIED → DATA_COLLECTION → COMPLETE
- `items_collected`: ["rpm", "oil_pressure", "vibration_engine_block", ...]
- `attachments`: Relation to attachment metadata (phyphox files, photos)
- `confirmed_fault`: Root cause identified (e.g., "fuel_cavitation")
- `actual_repair`: Repair performed (if applicable)
- `diagnostic_context`: Alert/prediction context for breakdown repairs

**service_record_attachments table:**
- `service_record_id`: Links to service record
- `attachment_type`: vibration_recording, audio_recording, service_sheet, photo_before, etc.
- `file_path`: Cloud storage path
- `file_name`: Original filename with date (GEN5_BASELINE_VIBRATION_ENGINE_BLOCK_IDLE_20260212.csv)
- `file_size_bytes`: Size for quota tracking
- `mime_type`: image/jpeg, audio/wav, text/csv, etc.
- `analysis_status`: pending → in_progress → complete
- `analysis_result`: FFT peaks, cavitation detection, bearing wear indicators, etc.

## Phase 44 AI Analysis Pipeline

**Automatic FFT Analysis (When baseline complete):**

1. Extract frequency domain from phyphox vibration CSV files
2. Detect failure signatures:
   - **Fuel cavitation:** 200-400 Hz peaks + low fuel pressure correlation
   - **Bearing wear:** BPFO/BPFI/BSF/FTF frequencies (equipment-specific)
   - **Governor hunting:** 2-5 Hz oscillation pattern in RPM
   - **Detonation/knock:** 5-10 kHz peaks + timing irregularity
   - **Engine vibration:** Low-frequency knocking (0.5-2 kHz)

3. Cross-reference with Mitsubishi S12R-PTA2 specifications:
   - Fuel pressure: 20-30 PSI (baseline: 24 PSI) → 18 PSI = cavitation risk
   - Oil pressure: 30-60 PSI (baseline: 42 PSI) → 38 PSI = acceptable aging
   - RPM stability: ±5 rpm (baseline: ±3 rpm) → ±20 rpm = hunting
   - Oil temperature: 80-95°C (baseline: 87°C) → 94°C = acceptable rise

4. Analyze 4-year failure pattern:
   - 2023: Speed controller fail (governor issue emerges)
   - 2024: Fuel pump leak + cavitation begins
   - 2025: Injectors blocked (consequence of fuel starvation)
   - 2026: Full failure
   - **Pattern:** Fuel cavitation → governor stress → mechanical wear (cascading failure)

5. Generate cost-benefit report:
   - **Root cause confidence:** 85%+ = Approve recommendation, 60-85% = Request clarification, <60% = Get 2nd opinion
   - **Repair scenarios:** Full quote vs targeted repairs vs alternative approaches
   - **Data-backed counter-offer:** "Quote includes R300K engine work not supported by baseline"
   - **Timeline:** Analysis complete within 24-48 hours of baseline submission

## Example: Gen Set 5 Analysis Output

```
PHASE 44 COST-BENEFIT ANALYSIS REPORT
Service Record: SR-2026-ABC123
Date: 2026-02-13
Equipment: Gen Set 5 (S002-GEN-B1-005)

═══════════════════════════════════════════════════════════

ROOT CAUSE ANALYSIS (Confidence: 92%)

PRIMARY ISSUE: Fuel System Cavitation
- Evidence: Audio FFT shows 200-400 Hz cavitation hiss
- Baseline (2018): Fuel pressure 24 PSI, clean audio spectrum
- Current (2026): Fuel pressure 18 PSI, cavitation signature present
- Supporting: 4-year trend shows pressure decline 24→18 PSI over 2 years

═══════════════════════════════════════════════════════════

SUPPLIER QUOTE ANALYSIS

Diesel Electric Quote: R611,820.75
├─ Fuel system overhaul: R300K ✅ JUSTIFIED (cavitation confirmed)
├─ Engine rebuild: R180K ❌ NOT JUSTIFIED (bearing wear is minor)
├─ Governor replacement: R60K ✅ JUSTIFIED (hunting confirmed)
├─ Injector replacement: R40K ⚠️ PARTIAL (symptom, not root cause)
└─ Miscellaneous: R31K ❓ UNCLEAR (not itemized)

═══════════════════════════════════════════════════════════

SENTINEL COUNTER-OFFER: R235K
├─ Fuel system complete overhaul: R180K (not R300K, targeted replacement)
├─ Governor controller replacement: R35K (not R60K, different brand)
├─ Injector cleanup/replacement: R15K (attempt cleaning first)
└─ Labor + miscellaneous: R5K
TOTAL: R235K
SAVINGS: R376,820 (62% reduction)

═══════════════════════════════════════════════════════════

RECOMMENDATION: Counter-offer R235K. If supplier refuses,
authorize full R611K. Your baseline data proves
engine work is not required TODAY.
```

## Related Files

**Backend:**
- Sentry integration: `backend/app/services/clawd_integration/`
- Work order API: `backend/app/api/work_orders.py`
- Sentry webhooks: `backend/app/api/clawd_webhooks.py`
- Service record repository: `backend/app/database/repositories/service_record_repository.py`
- OCR service: `backend/app/services/ocr_service.py`

**Documentation:**
- `.planning/GENSET5_BASELINE_DATA_REQUIREMENTS.md` - Technician inspection checklist
- `.planning/EQUIPMENT_ONBOARDING_BASELINE_STRATEGY.md` - Strategic approach
- `.planning/GENSET5_EXTERNAL_INSPECTION_QUICK.md` - 30-min external inspection protocol
- `.planning/GENSET5_PHASE44_AI_ANALYSIS.md` - Cost-benefit analysis framework
