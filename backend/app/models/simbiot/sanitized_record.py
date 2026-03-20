"""Sanitized Intermediate Record Model for SIMBIOT Ingestion Pipeline.

Phase 162A: Foundation Layer

This model represents data that has been normalized and cleaned but not yet
semantically classified or validated. It sits between RawSourceRecord (source truth)
and CanonicalSentinelPoint (normalized, validated understanding).

Key Principles:
1. NORMALIZED: Standardized formats for names, units, data types
2. CLEANED: Consistent naming conventions and data representations
3. NOT CLASSIFIED: No semantic meaning assigned yet
4. NOT VALIDATED: No quality scores or safety classifications
5. PROVENANCE PRESERVED: Maintains connection to source record
6. WARNINGS COLLECTED: Non-fatal issues flagged for review

Boundary Definition:
- RawSourceRecord: "What the source system sent" (source truth)
- SanitizedIntermediateRecord: "Cleaned and normalized" (standardized format)
- CanonicalSentinelPoint: "What SENTINEL understands" (classified, validated)
"""

from dataclasses import dataclass
from typing import Any, Optional, List, Dict
from datetime import datetime


@dataclass
class SanitizedIntermediateRecord:
    """Normalized and cleaned data ready for semantic classification.

    This record represents the output of the sanitization layer. It contains
    data that has been transformed into consistent formats but has not yet
    been assigned semantic meaning or undergone validation.

    The sanitization process handles:
    - Unit normalization (e.g., "DEG" → "degC")
    - Point name cleaning (e.g., "SAT-1" → "sat_1")
    - Data type standardization
    - Writable flag normalization
    - Warning collection for suspicious patterns
    - Rejection of invalid records
    """

    # ========================================================================
    # SOURCE REFERENCE (Immutable connection to raw record)
    # ========================================================================
    source_record_id: str
    """Unique identifier of the RawSourceRecord this was created from."""

    source_system: str
    """Source system that originally provided this data."""

    site_id: str
    """Site identifier this data belongs to."""

    # ========================================================================
    # NORMALIZED IDENTITY (Cleaned but not yet classified)
    # ========================================================================
    sanitized_name: str
    """Cleaned and normalized point name.
    Examples: 'sat_1', 'bldg1_ah1_sat', 'trane_sat_001', 'space_temp_sensor_42'"""

    normalized_unit: str
    """Standardized unit of measurement.
    Examples: 'degC', '%', 'psi', 'kW', 'cfm', 'ppm'"""

    normalized_data_type: str
    """Standardized data type.
    Values: 'float', 'integer', 'boolean', 'string', 'unknown'"""

    # ========================================================================
    # EQUIPMENT CONTEXT (From source, not yet validated)
    # ========================================================================
    equipment_id: Optional[str] = None
    """Equipment identifier this point belongs to (if determinable)."""

    equipment_type: Optional[str] = None
    """Type of equipment (if determinable from source data)."""

    location_hierarchy: List[str] = None
    """Location path if determinable from source (e.g., ['site-001', 'building-1'])."""

    # ========================================================================
    # TRANSFORMATION METADATA (What happened during sanitization?)
    # ========================================================================
    transformations_applied: List[str] = None
    """List of transformations applied during sanitization.
    Examples: ['unit_normalized', 'name_cleaned', 'type_inferred']"""

    warnings: List[str] = None
    """Non-fatal issues detected during sanitization.
    Examples: ['unusual_unit_format', 'suspicious_name_pattern', 'missing_metadata']"""

    rejection_reason: Optional[str] = None
    """Reason this record was rejected (None if accepted)."""

    is_rejected: bool = False
    """Whether this record failed sanitization and should be quarantined."""

    # ========================================================================
    # AUDIT INFORMATION (When was this created?)
    # ========================================================================
    created_at: datetime = None
    """When this sanitized record was created."""

    updated_at: datetime = None
    """When this sanitized record was last updated."""

    # ========================================================================
    # INITIALIZATION (Setup with sensible defaults)
    # ========================================================================
    def __post_init__(self):
        """Initialize mutable fields while maintaining type safety."""
        if self.location_hierarchy is None:
            object.__setattr__(self, "location_hierarchy", [])
        if self.transformations_applied is None:
            object.__setattr__(self, "transformations_applied", [])
        if self.warnings is None:
            object.__setattr__(self, "warnings", [])
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now())
        if self.updated_at is None:
            object.__setattr__(self, "updated_at", datetime.now())

    # ========================================================================
    # UTILITY METHODS (Helper functions)
    # ========================================================================

    def add_transformation(self, transformation: str):
        """Add a transformation to the applied transformations list."""
        if transformation not in self.transformations_applied:
            self.transformations_applied.append(transformation)

    def add_warning(self, warning: str):
        """Add a warning about non-fatal issues."""
        if warning not in self.warnings:
            self.warnings.append(warning)

    def reject(self, reason: str):
        """Mark this record as rejected with the given reason."""
        self.is_rejected = True
        self.rejection_reason = reason

    def is_valid_for_classification(self) -> bool:
        """Check if this record is valid enough for semantic classification."""
        return (
            not self.is_rejected
            and self.sanitized_name
            and self.normalized_unit != "unknown"
            and len(self.warnings) <= 3  # Allow up to 3 warnings
        )

    def get_sanitization_summary(self) -> Dict[str, Any]:
        """Get a summary of the sanitization process."""
        return {
            "source_record_id": self.source_record_id,
            "sanitized_name": self.sanitized_name,
            "normalized_unit": self.normalized_unit,
            "normalized_data_type": self.normalized_data_type,
            "transformations": self.transformations_applied,
            "warning_count": len(self.warnings),
            "warnings": self.warnings,
            "is_rejected": self.is_rejected,
            "rejection_reason": self.rejection_reason,
        }

    # ========================================================================
    # SERIALIZATION (For storage and transmission)
    # ========================================================================

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "source_record_id": self.source_record_id,
            "source_system": self.source_system,
            "site_id": self.site_id,
            "sanitized_name": self.sanitized_name,
            "normalized_unit": self.normalized_unit,
            "normalized_data_type": self.normalized_data_type,
            "equipment_id": self.equipment_id,
            "equipment_type": self.equipment_type,
            "location_hierarchy": self.location_hierarchy,
            "transformations_applied": self.transformations_applied,
            "warnings": self.warnings,
            "rejection_reason": self.rejection_reason,
            "is_rejected": self.is_rejected,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SanitizedIntermediateRecord":
        """Create from dictionary (for deserialization)."""
        return cls(
            source_record_id=data["source_record_id"],
            source_system=data["source_system"],
            site_id=data["site_id"],
            sanitized_name=data["sanitized_name"],
            normalized_unit=data["normalized_unit"],
            normalized_data_type=data["normalized_data_type"],
            equipment_id=data["equipment_id"],
            equipment_type=data["equipment_type"],
            location_hierarchy=data["location_hierarchy"],
            transformations_applied=data["transformations_applied"],
            warnings=data["warnings"],
            rejection_reason=data["rejection_reason"],
            is_rejected=data["is_rejected"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )
