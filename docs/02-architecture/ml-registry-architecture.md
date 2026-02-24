---
title: "ML Registry Architecture - Database-Driven Configuration"
type: "technical-reference"
status: "active"
version: "1.0.0"
created: "2026-02-12"
updated: "2026-02-23"
author: "SENTINEL Development Team"
tags: ["ml", "registry", "database", "async", "architecture", "phase-68-03"]
domain: "ai-ml"
audience: ["developers", "devops", "data-scientists"]
complexity: "advanced"
estimated_read_time: 25
---

# ML Registry Architecture — Database-Driven Configuration

**Phase 68-03 deliverable:** Supabase-driven ML model registry replacing hardcoded configurations. Enables multi-site deployment with graceful degradation for equipment without trained models.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Equipment Discovery                       │
│                   (SIMBIOT BMS Ingestion)                    │
└────────────────────┬────────────────────────────────────────┘
                     │ equipment_code: S002-CHILLER-B1-001
                     │ equipment.type: CHILLER (extracted)
                     ▼
┌─────────────────────────────────────────────────────────────┐
│          NiagaraMLInference Service (Async)                 │
│                                                             │
│  1. get_prediction_with_confidence()                        │
│     ├─ Extract type from code                              │
│     ├─ Query registry: is_model_available()?               │
│     ├─ Fetch equipment data                                │
│     ├─ Prepare features (7-day history)                    │
│     ├─ Run inference (simulated or model-based)            │
│     └─ Check confidence vs threshold                       │
└────────────────────┬────────────────────────────────────────┘
                     │ await registry.get_model(type)
                     │ await registry.get_threshold_value(type, tier)
                     ▼
┌─────────────────────────────────────────────────────────────┐
│       ModelRegistryDB Service (Async, Cached)              │
│                                                             │
│  Lazy-loaded singleton with 1-hour TTL caching            │
│  ├─ get_model(equipment_type)                             │
│  ├─ get_thresholds(equipment_type)                        │
│  ├─ get_threshold_value(equipment_type, tier)             │
│  ├─ is_model_available(equipment_type)                    │
│  └─ get_all_active_models()                               │
└────────────────────┬────────────────────────────────────────┘
                     │ Supabase MCP queries
                     ├─ SELECT FROM ml_models WHERE equipment_type=? AND status='active'
                     ├─ SELECT FROM model_thresholds WHERE equipment_type=?
                     │ (Cached for 1 hour)
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Supabase PostgreSQL                            │
│                                                             │
│  ml_models:                                                │
│  ├─ id: UUID (PK)                                         │
│  ├─ model_id: TEXT UNIQUE                                 │
│  ├─ equipment_type: TEXT (INDEX)                          │
│  ├─ model_path: TEXT                                      │
│  ├─ r_squared_avg: FLOAT                                  │
│  ├─ status: active|inactive|degraded|disabled|unavailable │
│  └─ registered_at: TIMESTAMP                              │
│                                                             │
│  model_thresholds:                                         │
│  ├─ id: UUID (PK)                                         │
│  ├─ equipment_type: TEXT UNIQUE (INDEX)                   │
│  ├─ tier2_confidence_min: FLOAT [0.0-1.0]                │
│  ├─ tier3_confidence_min: FLOAT [0.0-1.0]                │
│  ├─ status: active|disabled                               │
│  └─ reason: TEXT                                          │
└─────────────────────────────────────────────────────────────┘
```

---

## Key Components

### 1. ModelRegistryDB Service (`backend/app/ml/models/model_registry_db.py`)

**Purpose:** Async database-driven registry with local caching.

```python
class ModelRegistryDB:
    CACHE_TTL_SECONDS = 3600  # 1 hour
    CACHE_MODELS = True
    CACHE_THRESHOLDS = True

    async def get_model(equipment_type: str) -> Optional[ModelConfig]:
        """Get active LSTM/autoencoder model for equipment type."""

    async def get_thresholds(equipment_type: str) -> Optional[ThresholdConfig]:
        """Get Tier 2/3 confidence thresholds for equipment type."""

    async def get_threshold_value(equipment_type: str, tier: int) -> Optional[float]:
        """Get specific tier threshold (2 or 3)."""

    async def is_model_available(equipment_type: str) -> bool:
        """Check if model exists and is active."""
```

**Caching Strategy:**
- **MODELS_CACHE**: Dict[equipment_type → ModelConfig], TTL 1 hour
- **THRESHOLDS_CACHE**: Dict[equipment_type → ThresholdConfig], TTL 1 hour
- Reduces Supabase queries during burst traffic
- Auto-expires, forcing refresh at most once per hour

### 2. NiagaraMLInference Service (`backend/app/services/niagara_ml_inference.py`)

**Purpose:** Async inference engine using database registry.

**Key Methods:**

```python
async def get_prediction_with_confidence(
    equipment_code: str,
    min_confidence: float = 0.70,
    tier: int = 2
) -> Optional[Dict[str, Any]]:
    """Generate prediction with confidence score for equipment."""

    # Flow:
    # 1. Extract equipment type from code
    # 2. Query registry: is model available?
    # 3. If no model: return None (graceful degradation)
    # 4. If model exists: prepare features, run inference
    # 5. Check confidence vs threshold
    # 6. Return prediction or None
```

**Graceful Degradation:**
- No model available → returns None (no error)
- Threshold=1.0 (impossible to meet) → recommendations blocked
- System continues normally with rules fallback

### 3. Supabase Tables

#### ml_models

Stores trained model metadata and paths.

```sql
CREATE TABLE ml_models (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  model_id TEXT UNIQUE NOT NULL,           -- e.g., "lstm_chiller_20260209_212308"
  model_type TEXT NOT NULL,                 -- "lstm", "autoencoder", "classifier"
  equipment_type TEXT NOT NULL,             -- "chiller", "ahu", "vav"
  model_path TEXT NOT NULL,                 -- Full path to .h5 file
  scaler_path TEXT,                         -- Optional feature scaler
  r_squared_avg FLOAT,                      -- Overall R² score
  status TEXT CHECK (status IN ('active', 'inactive', 'degraded', 'disabled', 'unavailable')),
  registered_at TIMESTAMP DEFAULT now(),
  INDEX idx_equipment_type (equipment_type),
  INDEX idx_status (status),
  INDEX idx_active (equipment_type, status) WHERE status='active'
);
```

**Current Data (Production):**

| equipment_type | model_id | r_squared_avg | status |
|---|---|---|---|
| chiller | lstm_chiller_20260209_212308 | 0.6065 | active |
| ahu | lstm_ahu_20260209_213006 | 0.4915 | active |
| fcu | lstm_fcu_20260209_214416 | 0.4236 | active |
| ups | lstm_ups_20260209_215037 | 0.4144 | active |
| generator | lstm_generator_20260209_213751 | 0.3710 | active |
| vav | lstm_vav_20260209_215713 | 0.3171 | disabled |

**Classifier Models (v25.0):**

Registered in `registry.json` (file-based, not Supabase). Random Forest classifiers for fault type prediction:

| equipment_type | model_id | cv_accuracy | n_classes | status |
|---|---|---|---|---|
| chiller | classifier_chiller_20260223_* | 0.608 | 6 | active |
| ahu | classifier_ahu_20260223_* | 0.667 | 6 | active |
| generator | classifier_generator_20260223_* | 0.542 | 6 | active |
| fcu | classifier_fcu_20260223_* | 0.717 | 5 | active |
| ups | classifier_ups_20260223_* | 0.508 | 5 | active |

#### model_thresholds

Stores confidence thresholds (per equipment type, not per site/building).

```sql
CREATE TABLE model_thresholds (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  equipment_type TEXT UNIQUE NOT NULL,      -- e.g., "chiller"
  tier2_confidence_min FLOAT NOT NULL,      -- Advisory: 0.70 (default)
  tier3_confidence_min FLOAT NOT NULL,      -- Auto-execute: 0.85 (default)
  status TEXT CHECK (status IN ('active', 'disabled')),
  reason TEXT,                              -- Why these thresholds
  INDEX idx_equipment_type (equipment_type),
  CONSTRAINT tier2_less_than_tier3 CHECK (tier2_confidence_min <= tier3_confidence_min)
);
```

**Current Configuration (23 Equipment Types):**

**Active (6 types):**
- CHILLER, AHU, FCU, UPS: tier2=0.70, tier3=0.85
- GENERATOR: tier2=0.85, tier3=0.95 (elevated for safety)
- DALI: tier2=0.70, tier3=0.85 (placeholder)

**Disabled (17 types):**
- All others: tier2=1.0, tier3=1.0 (impossible to meet)
- Gracefully blocks recommendations until model trained

---

## Confidence Tiers Explained

### Tier 2: Advisory Recommendations
- Shown to user for approval
- Minimum confidence: 0.70 (standard), 0.85 (elevated for critical equipment)
- **Flow:** Confidence ≥ tier2 → **Show recommendation** → User approves → Create work order

### Tier 3: Auto-Execute (Future)
- Applied automatically when conditions right
- Minimum confidence: 0.85 (standard), 0.95 (elevated)
- **Not yet implemented:** Currently all recommendations require approval
- **Future:** Will enable autonomous control for non-critical equipment

---

## Equipment Type Extraction

Equipment codes follow Two-Tier naming (Phase 078):

**Format 1: Office/Zone Equipment**
```
S002-VAV-101
├─ S002: Site code
├─ VAV: Equipment type (INDEX 1)
└─ 101: Zone ID

Extraction: parts[1].upper() = "VAV"
```

**Format 2: Plant/Infrastructure Equipment**
```
S002-CHILLER-B1-001
├─ S002: Site code
├─ CHILLER: Equipment type (INDEX 1)
├─ B1: Location (basement)
└─ 001: Sequence

Extraction: parts[1].upper() = "CHILLER"
```

**Format 3: Hospital Format (Site 005)**
```
site-005-UMH-AHU-B1-LAUN.fan
├─ site-005: Site prefix
├─ UMH: Hospital code
├─ AHU: Equipment type (INDEX 3)
├─ B1: Location
└─ LAUN.fan: Zone & point suffix

Extraction: parts[3].upper() = "AHU"
```

**Extraction Function** (`PL/pgSQL`):

```sql
CREATE FUNCTION extract_equipment_type(code TEXT) RETURNS TEXT AS $$
BEGIN
  DECLARE
    parts TEXT[];
  BEGIN
    parts := string_to_array(code, '-');

    -- Format 1/2: S002-TYPE-... → index 2 (1-indexed)
    IF parts[1] ~ '^S\d{3}$' THEN
      IF array_length(parts, 1) >= 2 THEN
        RETURN UPPER(parts[2]);
      END IF;
    END IF;

    -- Format 3: site-005-UMH-TYPE-... → index 4 (1-indexed)
    IF parts[1] = 'site' AND array_length(parts, 1) >= 4 THEN
      RETURN UPPER(parts[4]);
    END IF;

    RETURN UPPER(code);
  EXCEPTION WHEN OTHERS THEN
    RETURN code;
  END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;
```

---

## Async/Await Pattern

All registry queries are async to prevent blocking:

```python
# Backend API Handler (Async)
@router.get("/api/predictions/{equipment_code}")
async def predict_equipment(equipment_code: str):
    inference_service = get_ml_inference()

    # Non-blocking registry lookup
    prediction = await inference_service.get_prediction_with_confidence(
        equipment_code,
        min_confidence=0.70,
        tier=2
    )

    return {"prediction": prediction}
```

---

## Graceful Degradation Examples

### Scenario 1: Equipment with Active Model
```
Equipment: S002-CHILLER-B1-001
Type: CHILLER (found in equipment.type column)

Query: registry.get_model("chiller")
Result: ModelConfig(status='active', r_squared=0.6065, model_path="/opt/.../chiller_lstm_20260209_212308.h5")

Query: registry.get_threshold_value("chiller", tier=2)
Result: 0.70

Inference: confidence = 0.75 (calculated from health score + alerts)
Check: 0.75 >= 0.70? YES
Outcome: ✅ RECOMMENDATION SHOWN
```

### Scenario 2: Equipment without Trained Model
```
Equipment: site-005-UMH-LIFT-B1-001
Type: LIFT (patient transport elevator)

Query: registry.get_model("lift")
Result: None (no trained model)

Query: registry.get_threshold_value("lift", tier=2)
Result: 1.0 (disabled threshold)

Inference: (skipped, no model)
Check: confidence < 1.0 (always true)
Outcome: ⏸️ NO RECOMMENDATION SHOWN (graceful)
         Use rule-based predictions instead

Later when model trained:
  1. Add to ml_models table: status='active'
  2. Update threshold: tier2=0.70
  3. Cache expires in 1 hour
  4. Next prediction uses new model
  5. RECOMMENDATIONS AUTOMATICALLY ENABLED ✅
```

---

## Performance Characteristics

### Latency (per prediction)

| Operation | Time | Notes |
|---|---|---|
| Extract equipment type | ~1ms | String parsing |
| Query registry (cache hit) | ~0.1ms | In-memory dict lookup |
| Query registry (cache miss) | ~50-100ms | Supabase round-trip |
| Prepare features | ~10-20ms | 7-day history aggregation |
| Run inference (simulated) | ~1-2ms | Math operations |
| Check threshold | ~0.1ms | Float comparison |
| **Total (cache hit)** | **~12-24ms** | Typical case |
| **Total (cache miss)** | **~60-130ms** | Hourly worst case |

### Cache Efficiency

- **Cache TTL:** 1 hour (configurable in settings)
- **Typical hit rate:** 95%+ (equipment types don't change hourly)
- **Memory usage:** ~1KB per equipment type in cache (~23KB total)
- **Supabase query reduction:** 98%+ (from hourly recheck)

### Scalability

- **Equipment types:** 23 (current), supports unlimited
- **Threshold configurations:** 1 per type (global)
- **Model versions:** Multiple per type, only 1 active (via UNIQUE constraint)
- **Multi-site:** Global tables shared across all sites
- **Connections:** Async non-blocking, supports 1000s concurrent predictions

---

## Deployment Checklist

- [x] ml_models table created with indexes
- [x] model_thresholds table created with constraints
- [x] 23 equipment types configured
- [x] 6 ML models registered (CHILLER, AHU, FCU, UPS, GENERATOR, DALI)
- [x] ModelRegistryDB service deployed
- [x] NiagaraMLInference refactored (async)
- [x] Equipment types extracted from codes (migration 068)
- [x] Cache TTL configured (1 hour default)
- [x] Supabase indexes created for performance
- [x] Graceful degradation verified (threshold=1.0 blocks recommendations)
- [x] 5 Random Forest classifiers trained and registered (v25.0)
- [x] Fault classification wired into anomaly detection pipeline (v25.0)
- [x] Classifier included in /train/all and retraining scheduler (v25.0)
- [x] Documentation updated (v25.0)
- [ ] Monitoring & alerting setup (model performance metrics)

---

## Future Enhancements

### Phase 69+

1. **Automated Model Registration:** Training pipeline auto-updates ml_models table
2. **A/B Testing:** Multiple active models per type, gradual rollout
3. **Tier 3 Auto-Execute:** Autonomous control for equipment without critical thresholds
4. **Federated Learning:** Train models across multiple buildings
5. **Model Performance Tracking:** Prediction accuracy monitoring in Supabase
6. **Dynamic Thresholds:** Adjust tier2/tier3 based on deployment environment (dev/staging/prod)

---

## References

- [NiagaraMLInference Service](../../backend/app/services/niagara_ml_inference.py)
- [ModelRegistryDB Service](../../backend/app/ml/models/model_registry_db.py)
- [ML Predictions API](../03-api-reference/ml-predictions-api.md)
- [Equipment Type Mapping](./ml-models-equipment-mapping.md)
- [Two-Tier Equipment System](../04-features/equipment-naming-system.md)
- [Migration 067: ML Model Registry](../../supabase/migrations/067_ml_model_registry.sql)
- [Migration 068: Equipment Type Extraction](../../supabase/migrations/068_fix_equipment_types.sql)
