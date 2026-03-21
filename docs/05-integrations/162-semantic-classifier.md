---
title: "Semantic Control Foundation — Point Classifier & Validation Engine"
type: "architecture"
status: "approved"
version: "1.0.0"
created: "2026-03-21"
updated: "2026-03-21"
author: "Sentinel Development Team"
tags: ["simbiot", "semantic", "classifier", "haystack", "onboarding", "validation", "phase-162"]
domain: "integration"
audience: "developers, architects"
complexity: "intermediate"
estimated_read_time: 12
---

# Semantic control foundation — point classifier & validation engine

## Overview

Phase 162 introduces a **deterministic semantic classifier** that transforms raw BACnet/DALI/Modbus
point names into semantically tagged data with auditable confidence scores. The goal is to enable
**blind site onboarding** (e.g. Site-005) without hardcoded point-name rules, so the same SENTINEL
firmware can be shipped to any building and self-classify its points at discovery time.

The classifier is Haystack-inspired: every point is mapped to a tag from a 47-entry canonical
dictionary. A static validation engine then enforces physical bounds, rate-of-change limits,
template completeness scoring, and tag conflict detection — preventing obviously wrong
classifications from reaching the human review queue.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  SIMBIOT Discovery Layer                                      │
│  (BACnet / DALI / Modbus scan)                               │
└──────────────┬───────────────────────────────────────────────┘
               │ raw point (name, haystack_id, equipment_type,
               │           metadata, value_samples)
               ▼
┌──────────────────────────────────────────────────────────────┐
│  RuleBasedPointClassifier                                     │
│                                                              │
│  For each candidate tag in SemanticDictionary:               │
│    1. Negative-sample guard (fast reject)                    │
│    2. Per-source evidence evaluators:                        │
│       - haystack_id  (glob pattern match)                    │
│       - point_name   (glob pattern match)                    │
│       - equipment_type (exact match)                         │
│       - metadata     (keyword presence in values)            │
│       - value_pattern (numeric range / enum)                 │
│    3. ConfidenceCalculator:                                  │
│       confidence = min(1.0, Σweights / required_evidence)    │
│  Select best-matching tag (highest confidence)               │
└──────────────┬───────────────────────────────────────────────┘
               │ PointClassification (tag, confidence, evidence)
               ▼
┌──────────────────────────────────────────────────────────────┐
│  StaticValidationEngine                                       │
│                                                              │
│  BoundsValidator         — min/max physical bounds           │
│  RateOfChangeValidator   — Δvalue/Δtime limits               │
│  TemplateCompletenessCalculator — weighted point coverage     │
│  TagConflictDetector     — canonical conflict pairs          │
└──────────────┬───────────────────────────────────────────────┘
               │ ValidationReport
               ▼
         Review queue / control layer
```

## Semantic dictionary

The dictionary lives at `backend/app/data/simbiot/semantic_dictionary.json` and contains **47 tags**
across eight equipment domains:

| Domain | Count | Examples |
|--------|-------|---------|
| HVAC | 15 | `supply_air_temperature_sensor`, `chw_valve_position_actuator` |
| Lighting | 5 | `dali_dimming_level_actuator`, `occupancy_sensor` |
| Energy | 8 | `active_power_meter`, `power_factor_meter` |
| Fire | 5 | `smoke_detector`, `suppression_system_status` |
| Water | 2 | `cold_water_flow_meter`, `hot_water_temperature_sensor` |
| Security | 4 | `access_control_door_status`, `cctv_motion_trigger` |
| Solar/BESS | 3 | `solar_irradiance_sensor`, `bess_state_of_charge` |
| IAQ / building-wide | 5 | `co2_concentration_sensor`, `ambient_temperature_sensor` |

Each tag entry specifies:
- `safety_class` — `LOW`, `MEDIUM`, or `HIGH` (gates control actions downstream)
- `classification_rules` — list of `{source, pattern, weight}` entries
- `required_evidence` — denominator for the confidence formula
- `negative_samples` — point-name patterns that must not match
- `control_envelope` — optional min/max/step for writable tags
- `validation_bounds` — physical min/max and rate-of-change limits

## Confidence scoring

```
confidence = min(1.0, Σ(matched_evidence.weight) / required_evidence)
```

| Level | Range | Meaning |
|-------|-------|---------|
| HIGH | ≥ 0.7 | Sufficient evidence for autonomous processing |
| MEDIUM | 0.4 – 0.69 | Needs human review before control actions |
| LOW | < 0.4 | Likely wrong match; hold for re-discovery |

The denominator `required_evidence` is defined per tag in the dictionary, not a global constant.
This means sensors with few distinguishing features can still reach HIGH confidence with fewer
evidence sources than, say, a fire suppression actuator.

## Safety class gating

| Safety class | Classification control implication |
|---|---|
| `LOW` | Can be acted on automatically at HIGH confidence |
| `MEDIUM` | Requires operator approval before first write |
| `HIGH` | Always requires sign-off; never auto-controlled |

Safety class is inherited from the matched SemanticTag and forwarded to the `PointClassification`
model so downstream control layers can enforce the correct gate without re-querying the dictionary.

## Static validation

Validation runs automatically after every classification inside `RuleBasedPointClassifier`. The
`StaticValidationEngine` orchestrates four checks:

### Bounds validator

Compares the point's current or sample value against the tag's `validation_bounds.min` and
`validation_bounds.max`. Produces a `BOUNDS_VIOLATION` error if outside range.

### Rate-of-change validator

Requires at least two time-stamped value samples. The rate is compared against
`validation_bounds.rate_limit`. Severity is controlled by `alarm_if_exceeded`:
- `False` → warning (advisory)
- `True` → error (blocks control actions)

### Template completeness calculator

Computes a weighted coverage score for an equipment batch (not a single point):

```
score = (Σ critical_weight_matched + Σ important_weight_matched) / (Σ all_weights)
```

Weights: critical = 0.7, important = 0.3. Optional points do not affect score.

| Grade | Score |
|-------|-------|
| A | ≥ 0.9 |
| B | 0.75 – 0.89 |
| C | 0.6 – 0.74 |
| D | 0.4 – 0.59 |
| F | < 0.4 |

A `DATA_QUALITY_TOO_LOW` error is raised when score < 0.3, blocking any control decisions for
the equipment until missing critical points are resolved.

### Tag conflict detection

Three canonical conflict pairs are enforced:
- `supply_air_temperature_sensor` ↔ `return_air_temperature_sensor`
- `chw_supply_temperature_sensor` ↔ `chw_return_temperature_sensor`
- `dali_dimming_level_actuator` ↔ `occupancy_sensor`

Both tags being assigned to the same physical point triggers a `TAG_CONFLICT` error.

## Source files

| File | Purpose |
|------|---------|
| `backend/app/data/simbiot/semantic_dictionary.json` | Canonical 47-tag dictionary |
| `backend/app/models/semantic_tag.py` | `SemanticTag`, `EvidenceSource`, `SafetyClass` Pydantic models |
| `backend/app/services/simbiot/semantic_dictionary.py` | `SemanticDictionaryService` |
| `backend/app/models/point_classification.py` | `PointClassification`, `EvidenceRecord`, `BatchClassificationResult` |
| `backend/app/services/simbiot/classifiers/base_classifier.py` | `BasePointClassifier` ABC |
| `backend/app/services/simbiot/classifiers/confidence_calculator.py` | Weighted evidence formula |
| `backend/app/services/simbiot/classifiers/rule_based_classifier.py` | Full classifier with 5 evidence evaluators |
| `backend/app/models/validation_errors.py` | `ValidationErrorCategory`, `ValidationError`, `ValidationReport` |
| `backend/app/services/simbiot/validators/bounds_validator.py` | Physical bounds check |
| `backend/app/services/simbiot/validators/template_completeness.py` | Weighted completeness scoring |
| `backend/app/services/simbiot/validators/validation_engine.py` | Orchestrates all validators |
| `backend/app/api/semantic_classification.py` | FastAPI router (4 endpoints) |

## Test coverage

| Suite | Tests | Status |
|-------|-------|--------|
| `test_semantic_dictionary.py` | 11 | PASS |
| `test_semantic_classifier.py` | 17 | PASS |
| `test_static_validation.py` | 27 | PASS |
| **Total** | **55** | **PASS** |

## Related documents

- [SIMBIOT Universal Adapter Pattern](simbiot-universal-adapter-pattern.md) — overall onboarding architecture
- [Semantic Classification API](../03-api-reference/semantic-classification-api.md) — REST endpoint reference
- [Niagara BMS Connection Wizard](../04-features/niagara-connection-wizard.md) — wizard that will consume classifier output
- [Device Abstraction Layer](../02-architecture/device-abstraction-layer.md) — protocol-agnostic interface
