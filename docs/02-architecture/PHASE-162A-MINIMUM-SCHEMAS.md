---
title: "Phase 162A Minimum Viable Schemas"
type: "architecture"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-03-31"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# Phase 162A Minimum Viable Schemas

**Status**: Active Design
**Version**: 1.0
**Date**: 2026-03-19
**Phase**: 162A Foundation Layer

---

## 1. Raw Source Record Schema

**Purpose**: Preserve original BMS data with full provenance
**Location**: `backend/app/models/simbiot/raw_source_record.py`

```python
from dataclasses import dataclass
from typing import Any, Optional
from datetime import datetime

@dataclass(frozen=True)
class RawSourceRecord:
    """Immutable record of raw BMS data with complete provenance."""

    # System identification
    source_system: str  # "BACnet", "Modbus", "Desigo Optic", "Niagara", "MQTT", "OPC UA"
    source_version: str
    adapter_version: str

    # Point identification
    original_point_name: str
    original_object_type: str  # BACnet object type, Modbus register type, etc.
    original_instance: int  # BACnet instance number, Modbus address, etc.

    # Data characteristics
    raw_value: Any  # Exact value from source
    raw_unit: str  # Original unit string
    raw_data_type: str  # "float", "integer", "boolean", "string", "unknown"

    # Temporal information
    source_timestamp: datetime  # Timestamp from source system
    ingestion_timestamp: datetime  # When SIMBIOT received it

    # Connection context
    connection_id: str
    connection_health: str  # "healthy", "degraded", "failed", "reconnecting"

    # Provenance
    site_id: str
    building_id: Optional[str] = None
    device_id: Optional[str] = None

    # Metadata
    metadata: dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            object.__setattr__(self, 'metadata', {})
```

---

## 2. Enriched Intermediate Record Schema

**Purpose**: Transformed data with added context, ready for classification
**Location**: `backend/app/models/simbiot/enriched_record.py`

```python
from dataclasses import dataclass
from typing import Any, Optional, List
from datetime import datetime

@dataclass
class EvidenceRecord:
    """Evidence supporting a classification decision."""
    source: str  # "haystack_id", "point_name", "equipment_type", "metadata", "value_pattern"
    rule: str  # Description of the rule applied
    weight: float  # 0.0 - 1.0
    contribution: float  # Actual contribution to confidence score

@dataclass
class ValidationResult:
    """Result of a validation check."""
    validation_type: str  # "static", "dynamic"
    rule: str  # Name of validation rule
    result: str  # "pass", "warn", "fail"
    value_tested: Any  # The value that was tested
    message: Optional[str] = None  # Additional context
    timestamp: datetime = None

@dataclass
class EnrichedIntermediateRecord:
    """Transformed BMS data with added context, ready for classification."""

    # Source reference (immutable)
    source_record_id: str
    source_system: str
    site_id: str

    # Normalized identity
    sanitized_name: str
    normalized_unit: str
    normalized_data_type: str

    # Equipment context
    equipment_id: Optional[str] = None
    equipment_type: Optional[str] = None
    location_hierarchy: List[str] = None  # ["site-002", "building-1", "floor-2", "zone-north"]

    # Classification evidence
    classification_evidence: List[EvidenceRecord] = None
    classification_confidence: float = 0.0

    # Validation results
    validation_results: List[ValidationResult] = None
    validation_status: str = "pending"  # "pending", "passed", "warning", "failed"

    # Transformation metadata
    transformations_applied: List[str] = None
    created_at: datetime = None
    updated_at: datetime = None

    def __post_init__(self):
        if self.location_hierarchy is None:
            object.__setattr__(self, 'location_hierarchy', [])
        if self.classification_evidence is None:
            object.__setattr__(self, 'classification_evidence', [])
        if self.validation_results is None:
            object.__setattr__(self, 'validation_results', [])
        if self.transformations_applied is None:
            object.__setattr__(self, 'transformations_applied', [])
        if self.created_at is None:
            object.__setattr__(self, 'created_at', datetime.now())
        if self.updated_at is None:
            object.__setattr__(self, 'updated_at', datetime.now())
```

---

## 3. Canonical SENTINEL Point Schema

**Purpose**: Standardized data model for all SENTINEL services
**Location**: `backend/app/models/simbiot/canonical_point.py`

```python
from dataclasses import dataclass
from typing import Any, Optional, List, Dict
from datetime import datetime
from enum import Enum

class SafetyClass(str, Enum):
    LOW = "LOW"      # Monitor/presentation only
    MEDIUM = "MEDIUM" # Supervised control (human in loop)
    HIGH = "HIGH"    # Critical safety - no autonomous writes

class AutonomyTier(str, Enum):
    OBSERVE_ONLY = "OBSERVE_ONLY"      # Monitoring only
    SHADOW_DRY_RUN = "SHADOW_DRY_RUN"  # Log would-be actions
    SHADOW_LIVE = "SHADOW_LIVE"        # Suggest actions
    SUPERVISED = "SUPERVISED"          # Human approval required
    AUTOMATIC = "AUTOMATIC"            # Full autonomy

class OperationalStatus(str, Enum):
    NORMAL = "normal"
    FAULT = "fault"
    OVERRIDE = "override"
    MAINTENANCE = "maintenance"
    UNKNOWN = "unknown"

@dataclass
class ControlEnvelope:
    """Operational constraints for writable points."""

    # Value constraints
    bounds: Optional[Dict[str, float]] = None  # {"min": 0, "max": 100}

    # Temporal constraints
    min_cooldown_seconds: Optional[int] = None
    max_daily_writes: Optional[int] = None

    # Safety overrides
    writable_override: bool = True
    monitor_only: bool = False
    requires_manual_approval: bool = False
    alarm_on_change: bool = False

@dataclass
class TrustProfile:
    """Quantitative trust metrics for automation eligibility."""
    stable_days: float = 0.0
    validation_runs: int = 0
    successful_actions: int = 0
    control_trust_score: float = 0.0

@dataclass
class Provenance:
    """Complete data lineage information."""
    source_system: str
    site_id: str
    device_id: str
    equipment_id: str
    original_point_name: str
    original_object_type: str
    original_instance: int
    ingestion_timestamp: datetime

@dataclass
class CanonicalSentinelPoint:
    """Standardized SENTINEL point model for all downstream services."""

    # Provenance (immutable)
    source_provenance: Provenance

    # Identity (normalized)
    canonical_name: str
    canonical_point_type: str  # "analog_input", "analog_output", "binary_input", "binary_output", "multi_state"
    semantic_tag: str

    # Context
    equipment_id: str
    equipment_type: str
    location_hierarchy: List[str]

    # Data characteristics
    unit: str
    data_type: str  # "float", "integer", "boolean", "string"
    writable: bool = False

    # Quality & validation
    data_quality_score: float = 0.0  # 0.0 - 1.0
    validation_status: str = "pending"  # "pending", "passed", "warning", "failed", "quarantined"
    last_validation_timestamp: Optional[datetime] = None
    last_valid_value_timestamp: Optional[datetime] = None

    # Safety & control
    safety_class: SafetyClass = SafetyClass.LOW
    control_envelope: ControlEnvelope = None
    automation_tier: AutonomyTier = AutonomyTier.OBSERVE_ONLY

    # Operational state
    current_value: Any = None
    current_value_timestamp: Optional[datetime] = None
    operational_status: OperationalStatus = OperationalStatus.UNKNOWN

    # Classification metadata
    classification_confidence: float = 0.0
    classification_evidence: List[Dict[str, Any]] = None

    # Trust & eligibility
    trust_profile: TrustProfile = None

    # Audit information
    created_at: datetime = None
    updated_at: datetime = None
    version: str = "1.0"

    def __post_init__(self):
        if self.control_envelope is None:
            object.__setattr__(self, 'control_envelope', ControlEnvelope())
        if self.classification_evidence is None:
            object.__setattr__(self, 'classification_evidence', [])
        if self.trust_profile is None:
            object.__setattr__(self, 'trust_profile', TrustProfile())
        if self.created_at is None:
            object.__setattr__(self, 'created_at', datetime.now())
        if self.updated_at is None:
            object.__setattr__(self, 'updated_at', datetime.now())
```

---

## 4. Autonomy Tier Decision Matrix

**Purpose**: Determine automation eligibility based on quantitative metrics
**Location**: `backend/app/services/simbiot/autonomy_decision.py`

### Decision Matrix

| **Tier** | **Requirements** | **Behavior** |
|-----------|------------------|--------------|
| OBSERVE_ONLY | Default for unknown/low-confidence points | Log decisions, no suggestions |
| SHADOW_DRY_RUN | `template_completeness >= 0.70` AND `stable_days >= 2` | Log would-be actions, no execution |
| SHADOW_LIVE | `classification_confidence >= 0.85` AND `data_quality_score >= 0.85` AND `stable_days >= 7` AND `successful_actions >= 5` | Suggest actions, show predictions |
| SUPERVISED | `classification_confidence >= 0.90` AND `data_quality_score >= 0.90` AND `stable_days >= 14` AND `successful_actions >= 20` | Suggest + request human approval |
| AUTOMATIC | `classification_confidence >= 0.95` AND `data_quality_score >= 0.95` AND `stable_days >= 30` AND `successful_actions >= 50` | Suggest + execute automatically |

### Safety Class Overrides

| **Safety Class** | **Maximum Allowed Tier** | **Rationale** |
|------------------|-------------------------|---------------|
| LOW | AUTOMATIC | Monitor/presentation points |
| MEDIUM | SUPERVISED | Control points requiring oversight |
| HIGH | OBSERVE_ONLY | Critical safety systems |

### Decision Function

```python
def calculate_autonomy_tier(
    point: CanonicalSentinelPoint,
    template_completeness: float
) -> AutonomyTier:
    """Calculate autonomy tier based on trust metrics and safety class."""

    # Safety class override - takes precedence over all other factors
    if point.safety_class == SafetyClass.HIGH:
        return AutonomyTier.OBSERVE_ONLY

    # Template completeness gate
    if template_completeness < 0.70:
        return AutonomyTier.OBSERVE_ONLY

    # Classification confidence gate
    if point.classification_confidence < 0.70:
        return AutonomyTier.OBSERVE_ONLY

    # Data quality gate
    if point.data_quality_score < 0.70:
        return AutonomyTier.OBSERVE_ONLY

    # Trust history requirements
    trust = point.trust_profile

    if (trust.stable_days >= 30 and
        trust.validation_runs >= 1000 and
        trust.successful_actions >= 50 and
        point.classification_confidence >= 0.95 and
        point.data_quality_score >= 0.95):
        return AutonomyTier.AUTOMATIC

    elif (trust.stable_days >= 14 and
          trust.validation_runs >= 500 and
          trust.successful_actions >= 20 and
          point.classification_confidence >= 0.90 and
          point.data_quality_score >= 0.90):
        return AutonomyTier.SUPERVISED

    elif (trust.stable_days >= 7 and
          trust.validation_runs >= 100 and
          trust.successful_actions >= 5 and
          point.classification_confidence >= 0.85 and
          point.data_quality_score >= 0.85):
        return AutonomyTier.SHADOW_LIVE

    elif trust.stable_days >= 2:
        return AutonomyTier.SHADOW_DRY_RUN

    else:
        return AutonomyTier.OBSERVE_ONLY
```

---

## 5. First Implementation Task

**Task**: Create Raw Source Record Model and Basic Ingestion Service
**Files**: 2 files maximum

### File 1: Raw Source Record Model
**Location**: `backend/app/models/simbiot/raw_source_record.py`

```python
"""Raw source record model for SIMBIOT ingestion pipeline.

Phase 162A: Foundation Layer - Task 1
"""

from dataclasses import dataclass
from typing import Any, Optional
from datetime import datetime


@dataclass(frozen=True)
class RawSourceRecord:
    """Immutable record of raw BMS data with complete provenance.

    This model preserves the exact state of data as received from source systems,
    enabling forensic analysis, debugging, and compliance auditing.
    """

    # System identification
    source_system: str  # "BACnet", "Modbus", "Desigo Optic", "Niagara", "MQTT", "OPC UA"
    source_version: str
    adapter_version: str

    # Point identification
    original_point_name: str
    original_object_type: str  # BACnet object type, Modbus register type, etc.
    original_instance: int  # BACnet instance number, Modbus address, etc.

    # Data characteristics
    raw_value: Any  # Exact value from source
    raw_unit: str  # Original unit string
    raw_data_type: str  # "float", "integer", "boolean", "string", "unknown"

    # Temporal information
    source_timestamp: datetime  # Timestamp from source system
    ingestion_timestamp: datetime  # When SIMBIOT received it

    # Connection context
    connection_id: str
    connection_health: str  # "healthy", "degraded", "failed", "reconnecting"

    # Provenance
    site_id: str
    building_id: Optional[str] = None
    device_id: Optional[str] = None

    # Metadata
    metadata: dict[str, Any] = None

    def __post_init__(self):
        """Initialize mutable fields while maintaining immutability."""
        if self.metadata is None:
            object.__setattr__(self, 'metadata', {})

    @classmethod
    def from_bms_point(
        cls,
        bms_point: 'BmsPointValue',
        connection_status: 'BmsConnectionStatus',
        adapter_version: str
    ) -> 'RawSourceRecord':
        """Create RawSourceRecord from existing BMS adapter structures."""
        return cls(
            source_system=connection_status.source_type,
            source_version="1.0",  # Would come from adapter
            adapter_version=adapter_version,
            original_point_name=bms_point.point_id,
            original_object_type=bms_point.metadata.get('object_type', 'unknown'),
            original_instance=bms_point.metadata.get('instance', 0),
            raw_value=bms_point.value,
            raw_unit=bms_point.unit or 'unknown',
            raw_data_type=cls._infer_data_type(bms_point.value),
            source_timestamp=bms_point.timestamp or datetime.now(),
            ingestion_timestamp=datetime.now(),
            connection_id=connection_status.metadata.get('connection_id', 'unknown'),
            connection_health=connection_status.status,
            site_id=connection_status.site_id,
            building_id=bms_point.metadata.get('building_id'),
            device_id=bms_point.device_id,
            metadata={
                'quality': bms_point.quality,
                'adapter_metadata': bms_point.metadata
            }
        )

    @staticmethod
    def _infer_data_type(value: Any) -> str:
        """Infer data type from raw value."""
        if isinstance(value, (int, float)):
            return 'float' if isinstance(value, float) else 'integer'
        elif isinstance(value, bool):
            return 'boolean'
        elif isinstance(value, str):
            return 'string'
        else:
            return 'unknown'
```

### File 2: Basic Ingestion Service
**Location**: `backend/app/services/simbiot/ingestion_service.py`

```python
"""Basic ingestion service for SIMBIOT pipeline.

Phase 162A: Foundation Layer - Task 1
"""

from typing import List, Optional
from datetime import datetime
import logging

from app.models.simbiot.raw_source_record import RawSourceRecord
from app.services.simbiot.bms_adapter import BmsPointValue, BmsConnectionStatus

logger = logging.getLogger(__name__)


class SimbiotIngestionService:
    """Core ingestion service for raw BMS data."""

    def __init__(self, adapter_version: str = "1.0.0"):
        self.adapter_version = adapter_version
        self.ingested_count = 0
        self.error_count = 0

    def ingest_from_adapter(
        self,
        point_values: List[BmsPointValue],
        connection_status: BmsConnectionStatus
    ) -> List[RawSourceRecord]:
        """Ingest raw data from BMS adapter into SIMBIOT pipeline."""
        records = []

        for point_value in point_values:
            try:
                record = self._create_raw_record(point_value, connection_status)
                records.append(record)
                self.ingested_count += 1

                logger.debug(
                    f"Ingested point {point_value.point_id} from {connection_status.source_type}"
                )

            except Exception as e:
                self.error_count += 1
                logger.error(
                    f"Failed to ingest point {point_value.point_id}: {e}",
                    exc_info=True
                )
                continue

        logger.info(
            f"Ingestion batch complete: {len(records)} records created, "
            f"{self.error_count} errors encountered"
        )

        return records

    def _create_raw_record(
        self,
        point_value: BmsPointValue,
        connection_status: BmsConnectionStatus
    ) -> RawSourceRecord:
        """Create raw source record from adapter data."""
        return RawSourceRecord.from_bms_point(
            point_value,
            connection_status,
            self.adapter_version
        )

    def get_health_metrics(self) -> dict:
        """Get ingestion health metrics."""
        return {
            'total_ingested': self.ingested_count,
            'total_errors': self.error_count,
            'success_rate':
                self.ingested_count / (self.ingested_count + self.error_count)
                if (self.ingested_count + self.error_count) > 0 else 1.0
        }

    def reset_metrics(self):
        """Reset counters for monitoring."""
        self.ingested_count = 0
        self.error_count = 0
```

---

## Decision Gates for Phase 162A

### Gate 1: Raw Source Record Validation
**Criteria**:
- ✅ RawSourceRecord model created with all required fields
- ✅ Immutability enforced (frozen=True)
- ✅ Integration with existing BmsPointValue structure
- ✅ Comprehensive provenance tracking
- ✅ Unit tests for model creation and validation

### Gate 2: Basic Ingestion Service
**Criteria**:
- ✅ Ingestion service handles adapter data correctly
- ✅ Error handling and logging implemented
- ✅ Health metrics tracking
- ✅ Integration tests with mock adapter data
- ✅ Performance acceptable (<100ms per point)

### Gate 3: Schema Completeness
**Criteria**:
- ✅ All three schemas defined (Raw, Enriched, Canonical)
- ✅ Enums properly defined (SafetyClass, AutonomyTier)
- ✅ Type hints complete and correct
- ✅ Documentation strings present
- ✅ Schema validation tests passing

### Gate 4: Autonomy Decision Logic
**Criteria**:
- ✅ Decision matrix clearly defined
- ✅ Safety class overrides implemented
- ✅ Quantitative thresholds set appropriately
- ✅ Unit tests for all decision paths
- ✅ Edge cases handled (boundary conditions)

---

## Next Steps

1. **Implement Task 1**: Create the two files above
2. **Write unit tests**: Test model creation, validation, and basic ingestion
3. **Integrate with existing adapters**: Connect to BACnet and simulation adapters
4. **Add monitoring**: Prometheus metrics for ingestion pipeline
5. **Proceed to Task 2**: Enriched record transformation service

---

## References

- **Phase 162 Planning**: `.planning/phases/162-semantic-control-foundation/`
- **SIMBIOT Architecture**: `docs/02-architecture/SIMBIOT-SEMANTIC-INGESTION-ARCHITECTURE.md`
- **Existing Adapters**: `backend/app/services/simbiot/bms_adapter.py`
- **Control Policy**: `backend/app/models/control_policy.py`
