"""Canonical SENTINEL Point Model for SIMBIOT Semantic Ingestion Pipeline.

Phase 162A: Foundation Layer

This model represents the standardized, validated data structure that all SENTINEL
services consume. It preserves provenance while providing semantic consistency,
safety classification, and automation eligibility information.

Design Principles:
1. Preserve Provenance: Never lose connection to original BMS data
2. Semantic Consistency: Standardized naming and classification
3. Safety First: Explicit safety classification and control boundaries
4. Future-Proof: Support for validation, autonomy tiers, and trust scoring
5. Integration Ready: Designed to work with existing control policy system
"""

from dataclasses import dataclass
from typing import Any, Optional, List, Dict
from datetime import datetime
from enum import Enum


class SafetyClass(str, Enum):
    """Safety classification determining automation eligibility."""

    LOW = "LOW"  # Monitor/presentation only (e.g., temperature sensors)
    MEDIUM = "MEDIUM"  # Supervised control (e.g., setpoint adjustments)
    HIGH = "HIGH"  # Critical safety - no autonomous writes (e.g., emergency stops)


class AutonomyTier(str, Enum):
    """Automation eligibility tiers based on trust and validation."""

    OBSERVE_ONLY = "OBSERVE_ONLY"  # Monitoring only, no suggestions
    SHADOW_DRY_RUN = "SHADOW_DRY_RUN"  # Log would-be actions, no execution
    SHADOW_LIVE = "SHADOW_LIVE"  # Suggest actions, show predicted outcomes
    SUPERVISED = "SUPERVISED"  # Suggest + request human approval
    AUTOMATIC = "AUTOMATIC"  # Full autonomy within control envelope


class OperationalStatus(str, Enum):
    """Current operational state of the point."""

    NORMAL = "normal"  # Operating within expected parameters
    FAULT = "fault"  # Detected fault condition
    OVERRIDE = "override"  # Manual override active
    MAINTENANCE = "maintenance"  # Under maintenance
    UNKNOWN = "unknown"  # State cannot be determined


class DataType(str, Enum):
    """Standardized data types for processing and validation."""

    FLOAT = "float"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    STRING = "string"
    UNKNOWN = "unknown"


class PointType(str, Enum):
    """Canonical point types for routing and validation."""

    ANALOG_INPUT = "analog_input"
    ANALOG_OUTPUT = "analog_output"
    BINARY_INPUT = "binary_input"
    BINARY_OUTPUT = "binary_output"
    MULTI_STATE = "multi_state"


@dataclass
class ControlEnvelope:
    """Operational constraints and safety boundaries for writable points.

    These constraints are enforced by the Control Policy Engine before any
    autonomous write operations are attempted.
    """

    # Value constraints - physical/operational bounds
    bounds: Optional[Dict[str, float]] = None  # {"min": 0.0, "max": 100.0}

    # Temporal constraints - rate limiting and cooldowns
    min_cooldown_seconds: Optional[int] = None  # Minimum time between writes
    max_daily_writes: Optional[int] = None  # Maximum writes per 24 hours

    # Rate limits - prevent sudden changes
    ramp_limits: Optional[Dict[str, float]] = None  # {"max_per_second": 5.0, "max_per_minute": 30.0}

    # Safety overrides - explicit control restrictions
    writable_override: bool = True  # Can be written (when False, read-only)
    monitor_only: bool = False  # Never write, monitoring only
    requires_manual_approval: bool = False  # Human approval required for writes
    alarm_on_change: bool = False  # Trigger alarm on any value change

    # Verification requirements
    requires_verification: bool = False  # Must verify write succeeded
    verification_timeout_seconds: int = 30  # Time to wait for verification
    rollback_on_failure: bool = True  # Auto-rollback failed writes


@dataclass
class TrustProfile:
    """Quantitative trust metrics for automation eligibility.

    Trust must be earned through stability and successful operations
    before autonomous control is permitted.
    """

    stable_days: float = 0.0  # Days with stable, reliable data
    validation_runs: int = 0  # Number of successful validations
    successful_actions: int = 0  # Number of successful control actions
    control_trust_score: float = 0.0  # Composite trust score (0.0 - 1.0)


@dataclass
class Provenance:
    """Complete data lineage information for audit and debugging.

    This immutable record preserves the connection to the original
    BMS source system, enabling forensic analysis and compliance.
    """

    source_system: str  # "BACnet", "Modbus", "Desigo Optic", etc.
    site_id: str  # Site identifier
    device_id: str  # Source device identifier
    equipment_id: str  # Equipment identifier
    original_point_name: str  # Original name in source system
    original_object_type: str  # Original object/type in source system
    original_instance: int  # Original instance/address in source system
    ingestion_timestamp: datetime  # When data was first ingested


@dataclass
class ClassificationEvidence:
    """Evidence supporting semantic classification decisions."""

    source: str  # "haystack_id", "point_name", "equipment_type", etc.
    rule: str  # Description of classification rule applied
    weight: float  # Rule weight (0.0 - 1.0)
    contribution: float  # Actual contribution to confidence score


@dataclass
class CanonicalSentinelPoint:
    """Standardized SENTINEL point model consumed by all downstream services.

    This model represents the culmination of the SIMBIOT ingestion pipeline:
    raw data → sanitization → semantic mapping → validation → safety classification.

    All SENTINEL services (analytics, recommendations, control) consume this
    canonical model, ensuring consistent data semantics across the platform.
    """

    # ========================================================================
    # PROVENANCE (Immutable - preserves connection to source)
    # ========================================================================
    source_provenance: Provenance
    """Complete data lineage information for audit and debugging."""

    # ========================================================================
    # IDENTITY (Normalized - standardized across all systems)
    # ========================================================================
    canonical_name: str
    """Standardized point name (e.g., 'supply_air_temperature')."""

    canonical_point_type: PointType
    """Standardized point type for routing and validation."""

    semantic_tag: str
    """Haystack-inspired semantic classification (e.g., 'supply_air_temperature_sensor')."""

    # ========================================================================
    # CONTEXT (Operational - where and what this point represents)
    # ========================================================================
    equipment_id: str
    """Equipment identifier this point belongs to."""

    equipment_type: str
    """Type of equipment (AHU, CHILLER, FCU, etc.)."""

    location_hierarchy: List[str]
    """Location path (e.g., ['site-002', 'building-1', 'floor-2', 'zone-north'])."""

    # ========================================================================
    # DATA CHARACTERISTICS (Processing - how to handle this data)
    # ========================================================================
    unit: str
    """Normalized unit of measurement (e.g., 'degC', '%', 'kW')."""

    data_type: DataType
    """Standardized data type for processing."""

    writable: bool = False
    """Whether this point can be written to (when True, subject to control policies)."""

    # ========================================================================
    # QUALITY & VALIDATION (Reliability - can we trust this data?)
    # ========================================================================
    data_quality_score: float = 0.0
    """Telemetry reliability score (0.0 - 1.0)."""

    validation_status: str = "pending"
    """Current validation state: 'pending', 'passed', 'warning', 'failed', 'quarantined'."""

    last_validation_timestamp: Optional[datetime] = None
    """When validation was last performed."""

    last_valid_value_timestamp: Optional[datetime] = None
    """When a valid value was last received."""

    # ========================================================================
    # SAFETY & CONTROL (Automation - what can we do with this point?)
    # ========================================================================
    safety_class: SafetyClass = SafetyClass.LOW
    """Safety classification determining maximum automation eligibility."""

    control_envelope: ControlEnvelope = None
    """Operational constraints and safety boundaries."""

    autonomy_tier: AutonomyTier = AutonomyTier.OBSERVE_ONLY
    """Current automation eligibility tier."""

    # ========================================================================
    # OPERATIONAL STATE (Real-time - current status and value)
    # ========================================================================
    current_value: Any = None
    """Current value of the point."""

    current_value_timestamp: Optional[datetime] = None
    """When current value was last updated."""

    operational_status: OperationalStatus = OperationalStatus.UNKNOWN
    """Current operational state."""

    # ========================================================================
    # CLASSIFICATION (Semantics - how was this point classified?)
    # ========================================================================
    classification_confidence: float = 0.0
    """Confidence in semantic classification (0.0 - 1.0)."""

    classification_evidence: List[ClassificationEvidence] = None
    """Evidence supporting the classification decision."""

    # ========================================================================
    # TRUST & ELIGIBILITY (Automation - has this point earned trust?)
    # ========================================================================
    trust_profile: TrustProfile = None
    """Quantitative trust metrics for automation eligibility."""

    # ========================================================================
    # AUDIT INFORMATION (Change tracking)
    # ========================================================================
    created_at: datetime = None
    """When this canonical point record was created."""

    updated_at: datetime = None
    """When this canonical point record was last updated."""

    version: str = "1.0"
    """Schema version for migration compatibility."""

    # ========================================================================
    # INITIALIZATION (Setup default values)
    # ========================================================================
    def __post_init__(self):
        """Initialize mutable fields while maintaining type safety."""
        if self.control_envelope is None:
            object.__setattr__(self, "control_envelope", ControlEnvelope())
        if self.classification_evidence is None:
            object.__setattr__(self, "classification_evidence", [])
        if self.trust_profile is None:
            object.__setattr__(self, "trust_profile", TrustProfile())
        if self.location_hierarchy is None:
            object.__setattr__(self, "location_hierarchy", [])
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now())
        if self.updated_at is None:
            object.__setattr__(self, "updated_at", datetime.now())

    # ========================================================================
    # UTILITY METHODS (Helper functions)
    # ========================================================================

    def is_control_eligible(self) -> bool:
        """Determine if this point is eligible for any form of control."""
        return (
            self.writable
            and self.safety_class != SafetyClass.HIGH
            and self.autonomy_tier != AutonomyTier.OBSERVE_ONLY
            and not self.control_envelope.monitor_only
        )

    def is_automatic_eligible(self) -> bool:
        """Determine if this point is eligible for automatic control."""
        return (
            self.is_control_eligible()
            and self.autonomy_tier == AutonomyTier.AUTOMATIC
            and self.data_quality_score >= 0.90
            and self.classification_confidence >= 0.90
        )

    def get_safety_override_reason(self) -> Optional[str]:
        """Get reason if safety constraints prevent control."""
        if self.safety_class == SafetyClass.HIGH:
            return "HIGH safety class - no autonomous control permitted"
        if self.control_envelope.monitor_only:
            return "Control envelope set to monitor-only mode"
        if not self.writable:
            return "Point is not writable"
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "source_provenance": {
                "source_system": self.source_provenance.source_system,
                "site_id": self.source_provenance.site_id,
                "device_id": self.source_provenance.device_id,
                "equipment_id": self.source_provenance.equipment_id,
                "original_point_name": self.source_provenance.original_point_name,
                "original_object_type": self.source_provenance.original_object_type,
                "original_instance": self.source_provenance.original_instance,
                "ingestion_timestamp": self.source_provenance.ingestion_timestamp.isoformat(),
            },
            "canonical_name": self.canonical_name,
            "canonical_point_type": self.canonical_point_type.value,
            "semantic_tag": self.semantic_tag,
            "equipment_id": self.equipment_id,
            "equipment_type": self.equipment_type,
            "location_hierarchy": self.location_hierarchy,
            "unit": self.unit,
            "data_type": self.data_type.value,
            "writable": self.writable,
            "data_quality_score": self.data_quality_score,
            "validation_status": self.validation_status,
            "safety_class": self.safety_class.value,
            "autonomy_tier": self.autonomy_tier.value,
            "operational_status": self.operational_status.value,
            "current_value": self.current_value,
            "classification_confidence": self.classification_confidence,
            "trust_profile": {
                "stable_days": self.trust_profile.stable_days,
                "validation_runs": self.trust_profile.validation_runs,
                "successful_actions": self.trust_profile.successful_actions,
                "control_trust_score": self.trust_profile.control_trust_score,
            },
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CanonicalSentinelPoint":
        """Create from dictionary (for deserialization)."""
        provenance_data = data["source_provenance"]
        provenance = Provenance(
            source_system=provenance_data["source_system"],
            site_id=provenance_data["site_id"],
            device_id=provenance_data["device_id"],
            equipment_id=provenance_data["equipment_id"],
            original_point_name=provenance_data["original_point_name"],
            original_object_type=provenance_data["original_object_type"],
            original_instance=provenance_data["original_instance"],
            ingestion_timestamp=datetime.fromisoformat(provenance_data["ingestion_timestamp"]),
        )

        trust_profile = TrustProfile(
            stable_days=data["trust_profile"]["stable_days"],
            validation_runs=data["trust_profile"]["validation_runs"],
            successful_actions=data["trust_profile"]["successful_actions"],
            control_trust_score=data["trust_profile"]["control_trust_score"],
        )

        return cls(
            source_provenance=provenance,
            canonical_name=data["canonical_name"],
            canonical_point_type=PointType(data["canonical_point_type"]),
            semantic_tag=data["semantic_tag"],
            equipment_id=data["equipment_id"],
            equipment_type=data["equipment_type"],
            location_hierarchy=data["location_hierarchy"],
            unit=data["unit"],
            data_type=DataType(data["data_type"]),
            writable=data["writable"],
            data_quality_score=data["data_quality_score"],
            validation_status=data["validation_status"],
            safety_class=SafetyClass(data["safety_class"]),
            autonomy_tier=AutonomyTier(data["autonomy_tier"]),
            operational_status=OperationalStatus(data["operational_status"]),
            current_value=data["current_value"],
            classification_confidence=data["classification_confidence"],
            trust_profile=trust_profile,
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            version=data["version"],
        )
