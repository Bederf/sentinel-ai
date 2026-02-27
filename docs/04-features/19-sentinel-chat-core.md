---
status: implemented
version: 19
date: 2026-01-29
---

# Phase 19: SENTINEL Chat Core - Technician AI Assistant

## Overview

Mobile-first AI chat interface for field technicians with guided fault diagnosis, photo recognition, and structured troubleshooting flows. Integrates with the fault code database (Phase 18) to provide instant equipment diagnosis and parts sourcing.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  TechnicianChat Component (Mobile-First UI)                     │
│  - Message bubbles (text, diagnosis, suggestions, vision)       │
│  - Quick action buttons                                         │
│  - Photo capture with camera API                                │
│  - Inline diagnosis flows                                       │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌──────────────────────────┐    ┌──────────────────────────┐
│  Equipment Lookup API    │    │  Vision API              │
│  /api/equipment-lookup   │    │  /api/vision             │
│  - Fault code diagnosis  │    │  - Component ID          │
│  - Parts search          │    │  - Model plate OCR       │
│  - Natural language      │    │  - Damage assessment     │
└──────────────────────────┘    └──────────────────────────┘
              │                               │
              ▼                               ▼
┌──────────────────────────┐    ┌──────────────────────────┐
│  Diagnosis Flow API      │    │  Claude Vision API       │
│  /api/diagnosis          │    │  (Multimodal analysis)   │
│  - Guided checklists     │    │                          │
│  - State machine         │    │                          │
└──────────────────────────┘    └──────────────────────────┘
```

## Components

### TechnicianChat

**Location:** `frontend/src/components/TechnicianChat.tsx` (456+ lines)

Mobile-first AI chat interface with:

- **Message Types:**
  - `text` - Plain text messages
  - `diagnosis` - Structured fault code responses
  - `suggestions` - Troubleshooting suggestions
  - `guided-flow` - Inline diagnosis checklist
  - `vision` - Photo analysis results
  - `photo` - User-uploaded photos
  - `error` - Error messages

- **Mobile Optimizations:**
  - Fixed input at bottom with iOS safe area
  - 85% max-width messages on mobile, 75% on desktop
  - Touch-friendly tap targets (min 44x44px)
  - Auto-scroll to latest message

- **Quick Actions:**
  - "Carrier E4" - Common fault lookup
  - "ABB VSD fault" - VSD troubleshooting
  - "Chiller noise" - Keyword search
  - "Start Guided Diagnosis" - Launch checklist

### DiagnosisFlow

**Location:** `frontend/src/components/DiagnosisFlow.tsx` (433 lines)

Step-by-step guided diagnosis with:

- Visual progress indicator with percentage
- Checkpoint questions in styled cards
- Quick response buttons for common answers
- Custom text input for detailed observations
- Completed steps summary
- Mobile-optimized layout

**Props:**
```typescript
interface DiagnosisFlowProps {
  initialQuery: string;      // Query to start diagnosis
  onComplete?: (summary) => void;
  onClose?: () => void;
  sessionId?: string;        // For resuming
}
```

### PhotoCapture

**Location:** `frontend/src/components/PhotoCapture.tsx` (304 lines)

Camera integration for component identification:

- `capture="environment"` for mobile rear camera
- File input fallback for desktop
- Image preview modal before sending
- Canvas-based compression (max 1920px, 0.85 quality)
- Base64 encoding for API transport
- 5MB file size limit

## Backend Services

### DiagnosisFlowEngine

**Location:** `backend/app/services/technician_chat.py` (295 lines)

State machine for guided diagnosis:

```python
class DiagnosisState(Enum):
    IDENTIFYING = "identifying"
    CHECKING = "checking"
    ANALYZING = "analyzing"
    RESOLVING = "resolving"
    COMPLETE = "complete"
```

**Session Persistence:** DiagnosisFlow sessions are persisted via Redis (write-through) with a 1-hour TTL. This means:

- **Restart resilience:** Sessions survive backend restarts — technicians don't lose diagnosis progress mid-flow
- **Write-through pattern:** Every state change (new checkpoint response, state transition) writes to both in-memory and Redis
- **Graceful degradation:** If Redis is unavailable, sessions fall back to in-memory-only (lost on restart)
- **Serialization:** `DiagnosisFlow.to_dict()`/`from_dict()` handle full roundtrip including checkpoints, collected info, and fault info
- **Key format:** `bms:diagnosis:{session_id}`

**Pre-defined Checklists:**

| Fault | Checkpoints | Equipment |
|-------|-------------|-----------|
| E4 | 6 | Chillers (oil pressure) |
| E1 | 5 | Chillers (high pressure) |
| E3 | 4 | Chillers (low pressure) |
| FAULT_001 | 4 | VSDs (communication) |
| U4 | 3 | Daikin (Modbus error) |

**Key Methods:**
```python
start_diagnosis(session_id, query) -> dict
process_response(session_id, step_id, response) -> dict
get_flow_state(session_id) -> dict
end_diagnosis(session_id) -> dict
```

### VisionService

**Location:** `backend/app/services/vision_service.py` (373 lines)

Claude Vision integration for photo analysis:

| Method | Description |
|--------|-------------|
| `analyze_image()` | General image analysis |
| `identify_component()` | Equipment type identification |
| `read_model_plate()` | OCR for manufacturer/model/serial |
| `diagnose_damage()` | Damage assessment with severity |
| `read_error_display()` | Fault codes from LED/LCD |

**Response Structure:**
```typescript
interface VisionData {
  success: boolean;
  components?: Array<{
    name: string;
    manufacturer?: string;
    model?: string;
    condition?: string;
    confidence?: number;
  }>;
  issues?: Array<{
    type: string;
    severity: string;
    description?: string;
    recommendation?: string;
  }>;
  fault_codes?: string[];
  manufacturer?: string;
  model?: string;
  serial?: string;
  maintenance_priority?: string;
}
```

## API Endpoints

### Diagnosis API

**Base URL:** `/api/diagnosis`

```bash
# Start diagnosis session
POST /api/diagnosis/start
{"query": "Carrier chiller E4 fault"}

# Response
{
  "session_id": "diag-abc123",
  "state": "checking",
  "check": {
    "id": "oil_level",
    "question": "Check oil sight glass - what level?",
    "options": ["Full", "3/4", "1/2", "1/4 or less"]
  },
  "progress": {"current": 1, "total": 6, "percent": 16}
}

# Submit checkpoint response
POST /api/diagnosis/respond
{"session_id": "diag-abc123", "step_id": "oil_level", "response": "1/4 or less"}

# Get session state
GET /api/diagnosis/{session_id}

# End session and get summary
DELETE /api/diagnosis/{session_id}

# Get checklist for fault code
GET /api/diagnosis/checklists/{fault_code}
```

### Vision API

**Base URL:** `/api/vision`

```bash
# General image analysis
POST /api/vision/analyze
Content-Type: application/json
{"image": "base64...", "media_type": "image/jpeg"}

# Component identification
POST /api/vision/component
{"image": "base64...", "context": "HVAC equipment room"}

# Model plate OCR
POST /api/vision/model-plate
{"image": "base64..."}

# Damage assessment
POST /api/vision/diagnose
{"image": "base64...", "equipment_type": "compressor"}

# Error display reading
POST /api/vision/error-display
{"image": "base64...", "manufacturer": "Carrier"}

# File upload (multipart)
POST /api/vision/upload
Content-Type: multipart/form-data
```

## User Experience

### Fault Code Lookup Flow

```
User: "Carrier chiller E4 fault"

SENTINEL: 🔴 CRITICAL: E4 - Low Oil Pressure

Compressor oil pressure has dropped below safe threshold.

**Probable Causes:**
• Low oil level (high) - Check sight glass
• Oil pump failure (medium) - Test pump pressure
• Oil filter blocked (medium) - Check filter DP

**Immediate Actions:**
1. Shut down compressor immediately
2. Verify oil pressure with mechanical gauge
3. Check oil level and condition

**Parts:**
• Oil filter: Carrier 30XA-OILF-001
  Carrier SA: +27 11 207 2000

[Start Guided Diagnosis]
```

### Guided Diagnosis Flow

```
User: [Taps "Start Guided Diagnosis"]

SENTINEL: Starting E4 diagnosis for Carrier chiller...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Step 1 of 6 (16%)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Check the oil sight glass - what level do you see?

[Full] [3/4 or more] [1/2] [1/4 or less]

User: [Taps "1/4 or less"]

SENTINEL: ⚠️ Oil level is critically low.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Step 2 of 6 (33%)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Is the chiller currently running?

[Running with fault] [Shut down] [Running normally]
```

### Photo Analysis Flow

```
User: [Taps camera icon, takes photo of model plate]

SENTINEL: 📷 Analyzing image...

✅ Model Plate Identified

**Equipment Details:**
• Manufacturer: Carrier
• Model: 30XA-262
• Serial: 2819F40234
• Year: 2018

**Detected Components:**
• Compressor nameplate (95% confidence)
• Rating label (87% confidence)

Would you like me to look up fault codes for this model?

[Yes, show common faults] [No thanks]
```

## Navigation

Access TechnicianChat via sidebar:
- **Nav Item:** "Tech Chat" with Wrench icon
- **View ID:** `"technician"`
- **Required Module:** `maintenance` (gated via `TechnicianPortalGated`)
- **Route:** Sidebar selection → `TechnicianPortalGated` → `TechnicianChat`

## Files Reference

### Frontend

| File | Lines | Description |
|------|-------|-------------|
| `TechnicianChat.tsx` | 900+ | Main chat component |
| `DiagnosisFlow.tsx` | 433 | Guided checklist |
| `PhotoCapture.tsx` | 304 | Camera integration |

### Backend

| File | Lines | Description |
|------|-------|-------------|
| `technician_chat.py` | 295 | Diagnosis state machine |
| `vision_service.py` | 373 | Claude Vision integration |
| `diagnosis.py` | 203 | Diagnosis REST API |
| `vision.py` | 296 | Vision REST API |

### Modified

- `frontend/src/components/Sidebar.tsx` - Added technician nav
- `frontend/src/App.tsx` - Added routing
- `frontend/src/lib/api.ts` - Added API methods
- `backend/app/main.py` - Added routers

## Status

✅ **IMPLEMENTED** - Phase 19 (3/4 plans complete)

- 19-01: TechnicianChat mobile UI ✓
- 19-02: Guided diagnosis flows ✓
- 19-03: Photo recognition ✓
- 19-04: Job integration (pending)

## Dependencies

- Phase 18: Fault Code Database (fault lookups)
- Claude Vision API (photo analysis)
- ANTHROPIC_API_KEY environment variable
