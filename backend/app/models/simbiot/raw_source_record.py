"""Raw Source Record Model for SIMBIOT Ingestion Pipeline.

Phase 162A: Foundation Layer

This model captures the EXACT state of data as received from source BMS systems,
preserving all original naming, units, data types, and metadata without any
normalization or transformation. This immutable record serves as the single source
of truth for provenance and enables forensic analysis, debugging, and compliance.

Key Principles:
1. IMMUTABLE: Once created, never modified (frozen=True)
2. EXACT COPY: Preserves source system data exactly as received
3. NO NORMALIZATION: No unit conversion, name cleaning, or type coercion
4. COMPLETE PROVENANCE: Tracks source system, connection state, and timestamps
5. SOURCE TRUTH: The definitive record of "what the BMS actually said"

Boundary with Canonical Model:
- RawSourceRecord: "What the source system sent" (source truth)
- CanonicalSentinelPoint: "What SENTINEL understands" (normalized, validated)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services.simbiot.bms_adapter import BmsConnectionStatus, BmsPointValue


@dataclass(frozen=True)
class RawSourceRecord:
    """Immutable record of raw BMS data with complete provenance.

    This model preserves the exact state of data as received from source systems.
    It is the foundation of the SIMBIOT ingestion pipeline and serves as the
    single source of truth for all provenance, audit, and debugging purposes.

    Every field in this record represents EXACTLY what the source system provided,
    without any normalization, transformation, or interpretation.
    """

    # ========================================================================
    # SYSTEM IDENTIFICATION (Where did this data come from?)
    # ========================================================================
    source_system: str
    """The source BMS system that generated this data.
    Examples: 'BACnet', 'Modbus', 'Desigo Optic', 'Niagara', 'MQTT', 'OPC UA'"""

    source_version: str
    """Version of the source system or protocol."""

    adapter_version: str
    """Version of the SIMBIOT adapter that ingested this data."""

    # ========================================================================
    # POINT IDENTIFICATION (How is this point identified in the source?)
    # ========================================================================
    original_point_name: str
    """The EXACT point name as it appears in the source system.
    Examples: 'SAT-1', 'BLDG1_AH1_SAT', 'Trane-SAT-001', 'SPACE-TEMP-SENSOR-42'"""

    original_object_type: str
    """The source system's object/type classification.
    BACnet: 'analog-input', 'binary-value', 'multi-state-input'
    Modbus: 'holding-register', 'coil', 'input-register'
    Other: Vendor-specific type identifiers"""

    original_instance: int
    """The source system's addressing/instance identifier.
    BACnet: Instance number
    Modbus: Register/coil address
    Other: Vendor-specific instance identifiers"""

    # ========================================================================
    # DATA CHARACTERISTICS (What did the source actually send?)
    # ========================================================================
    raw_value: Any
    """The EXACT value received from the source system, without any transformation.
    No unit conversion, no type coercion, no rounding, no scaling."""

    raw_unit: str
    """The EXACT unit string as provided by the source system.
    Examples: 'DEG', 'Deg. C', '°C', '%', 'PSI', 'kW', 'CFM', '' (empty), 'unknown'"""

    raw_value_type: str
    """The data type inferred from the raw value.
    Determined by Python type inspection, not source metadata.
    Values: 'float', 'integer', 'boolean', 'string', 'unknown'"""

    writable: bool
    """Whether this point is writable according to the source system.
    This reflects the source system's capability, not SENTINEL's policy."""

    # ========================================================================
    # TEMPORAL INFORMATION (When did this happen?)
    # ========================================================================
    source_timestamp: datetime
    """The timestamp as provided by the source system.
    May be None if source doesn't provide timestamps."""

    ingestion_timestamp: datetime
    """When SIMBIOT received and recorded this data.
    This is the definitive timestamp for audit purposes."""

    # ========================================================================
    # CONNECTION CONTEXT (What was the system state?)
    # ========================================================================
    connection_id: str
    """Unique identifier for the connection/adapter that sourced this data."""

    connection_health: str
    """Health status of the connection at ingestion time.
    Values: 'healthy', 'degraded', 'failed', 'reconnecting', 'unknown'"""

    # ========================================================================
    # METADATA (What else did the source tell us?)
    # ========================================================================
    metadata: dict[str, Any]
    """All additional attributes provided by the source system.
    This is a catch-all for any source-specific metadata that doesn't fit
    into the standardized fields above."""

    # ========================================================================
    # PROVENANCE (Where in the building is this from?)
    # ========================================================================
    site_id: str
    """Site identifier this data belongs to."""

    building_id: str | None = None
    """Building identifier within the site (if applicable)."""

    device_id: str | None = None
    """Device identifier that this point belongs to."""

    # ========================================================================
    # INITIALIZATION (Setup with sensible defaults)
    # ========================================================================
    def __post_init__(self):
        """Initialize the metadata field while maintaining immutability."""
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})

    # ========================================================================
    # FACTORY METHODS (Convenient creation from existing structures)
    # ========================================================================

    @classmethod
    def from_bms_point_value(
        cls,
        bms_point: BmsPointValue,
        connection_status: BmsConnectionStatus,
        source_system: str,
        adapter_version: str,
    ) -> RawSourceRecord:
        """Create RawSourceRecord from existing BMS adapter structures.

        This factory method provides convenient integration with the existing
        SIMBIOT BMS adapter ecosystem.

        Args:
            bms_point: BmsPointValue from adapter
            connection_status: BmsConnectionStatus from adapter
            source_system: Source system name
            adapter_version: SIMBIOT adapter version

        Returns:
            RawSourceRecord with data from adapter structures
        """
        return cls(
            source_system=source_system,
            source_version="1.0",  # Would typically come from adapter config
            adapter_version=adapter_version,
            original_point_name=bms_point.point_id,
            original_object_type=bms_point.metadata.get("object_type", "unknown"),
            original_instance=bms_point.metadata.get("instance", 0),
            raw_value=bms_point.value,
            raw_unit=bms_point.unit or "unknown",
            raw_value_type=cls._infer_data_type(bms_point.value),
            writable=bms_point.metadata.get("writable", False),
            source_timestamp=bms_point.timestamp if bms_point.timestamp else datetime.now(),
            ingestion_timestamp=datetime.now(),
            connection_id=connection_status.metadata.get("connection_id", "unknown"),
            connection_health=connection_status.status,
            site_id=connection_status.site_id,
            building_id=bms_point.metadata.get("building_id"),
            device_id=bms_point.device_id,
            metadata={
                "quality": bms_point.quality,
                "adapter_metadata": bms_point.metadata,
                "connection_metadata": connection_status.metadata,
            },
        )

    # ========================================================================
    # UTILITY METHODS (Helper functions for working with raw data)
    # ========================================================================

    @staticmethod
    def _infer_data_type(value: Any) -> str:
        """Infer data type from raw value using Python type inspection.

        This method determines the most appropriate type classification
        based on the actual Python type of the value.

        Args:
            value: The raw value to inspect

        Returns:
            String representing the data type
        """
        if isinstance(value, float):
            return "float"
        elif isinstance(value, int):
            return "integer"
        elif isinstance(value, bool):
            return "boolean"
        elif isinstance(value, str):
            return "string"
        elif value is None:
            return "unknown"
        else:
            # For any other type, return the type name
            return type(value).__name__.lower()

    def get_provenance_summary(self) -> dict[str, str]:
        """Get a summary of provenance information for logging/debugging.

        Returns:
            Dictionary with key provenance information
        """
        return {
            "source_system": self.source_system,
            "site_id": self.site_id,
            "device_id": self.device_id or "unknown",
            "original_point_name": self.original_point_name,
            "ingestion_timestamp": self.ingestion_timestamp.isoformat(),
        }

    def is_source_data_valid(self) -> bool:
        """Check if the source data appears valid (basic sanity check).

        This performs minimal validation to catch obvious issues like
        None values where they shouldn't be, without interpreting the data.

        Returns:
            True if data appears valid, False if there are obvious issues
        """
        # Basic field presence checks
        if not self.original_point_name:
            return False
        if not self.source_system:
            return False
        if not self.site_id:
            return False

        # These checks are very permissive since we want to preserve
        # even "invalid" source data for audit purposes
        return True

    # ========================================================================
    # SERIALIZATION (For storage and transmission)
    # ========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary representation suitable for JSON serialization
        """
        return {
            "source_system": self.source_system,
            "source_version": self.source_version,
            "adapter_version": self.adapter_version,
            "original_point_name": self.original_point_name,
            "original_object_type": self.original_object_type,
            "original_instance": self.original_instance,
            "raw_value": self.raw_value,
            "raw_unit": self.raw_unit,
            "raw_value_type": self.raw_value_type,
            "writable": self.writable,
            "source_timestamp": self.source_timestamp.isoformat() if self.source_timestamp else None,
            "ingestion_timestamp": self.ingestion_timestamp.isoformat(),
            "connection_id": self.connection_id,
            "connection_health": self.connection_health,
            "site_id": self.site_id,
            "building_id": self.building_id,
            "device_id": self.device_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RawSourceRecord:
        """Create from dictionary (for deserialization).

        Args:
            data: Dictionary containing raw source record data

        Returns:
            RawSourceRecord instance
        """
        return cls(
            source_system=data["source_system"],
            source_version=data["source_version"],
            adapter_version=data["adapter_version"],
            original_point_name=data["original_point_name"],
            original_object_type=data["original_object_type"],
            original_instance=data["original_instance"],
            raw_value=data["raw_value"],
            raw_unit=data["raw_unit"],
            raw_value_type=data["raw_value_type"],
            writable=data["writable"],
            source_timestamp=datetime.fromisoformat(data["source_timestamp"])
            if data["source_timestamp"]
            else datetime.now(),
            ingestion_timestamp=datetime.fromisoformat(data["ingestion_timestamp"]),
            connection_id=data["connection_id"],
            connection_health=data["connection_health"],
            site_id=data["site_id"],
            building_id=data["building_id"],
            device_id=data["device_id"],
            metadata=data["metadata"],
        )
