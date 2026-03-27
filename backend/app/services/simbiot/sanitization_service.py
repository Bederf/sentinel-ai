"""SIMBIOT Sanitization Service.

Phase 162A: Foundation Layer

This service transforms raw BMS data into normalized, cleaned intermediate records.
It handles format standardization but defers semantic classification and validation
to later pipeline stages.

Responsibilities:
- Unit normalization (e.g., "DEG" → "degC")
- Point name cleaning (e.g., "SAT-1" → "sat_1")
- Data type standardization
- Writable flag normalization
- Warning collection for suspicious patterns
- Rejection of invalid records

Boundary Definition:
- Input: RawSourceRecord (source truth)
- Output: SanitizedIntermediateRecord (normalized format)
- Next Stage: Semantic classification and validation
"""

import re
import logging
from datetime import datetime
from typing import Dict

from app.models.simbiot.raw_source_record import RawSourceRecord
from app.models.simbiot.sanitized_record import SanitizedIntermediateRecord

logger = logging.getLogger(__name__)


class SanitizationService:
    """Core service for normalizing and cleaning raw BMS data."""

    def __init__(self):
        """Initialize the sanitization service."""
        self.sanitized_count = 0
        self.rejected_count = 0
        self.warning_count = 0

    def sanitize(self, raw_record: RawSourceRecord) -> SanitizedIntermediateRecord:
        """Transform raw source record into sanitized intermediate record.

        Args:
            raw_record: RawSourceRecord containing source data

        Returns:
            SanitizedIntermediateRecord with normalized data
        """
        # Create sanitized record with basic provenance
        # Initialize with empty values that will be filled by transformation methods
        source_record_id = (
            f"{raw_record.source_system}_{raw_record.site_id}_"
            f"{raw_record.original_point_name}_{datetime.now().timestamp()}"
        )
        sanitized = SanitizedIntermediateRecord(
            source_record_id=source_record_id,  # Unique ID
            source_system=raw_record.source_system,
            site_id=raw_record.site_id,
            sanitized_name="",  # Will be set by _clean_point_name
            normalized_unit="",  # Will be set by _normalize_unit
            normalized_data_type="",  # Will be set by _normalize_data_type
        )

        # Apply transformations
        self._normalize_unit(raw_record, sanitized)
        self._clean_point_name(raw_record, sanitized)
        self._normalize_data_type(raw_record, sanitized)
        self._normalize_writable_flag(raw_record, sanitized)
        self._extract_context(raw_record, sanitized)

        # Check for rejection conditions
        if self._should_reject(sanitized):
            sanitized.reject("Failed sanitization checks")
            self.rejected_count += 1
        else:
            self.sanitized_count += 1

        self.warning_count += len(sanitized.warnings)

        logger.debug(
            f"Sanitized record {sanitized.source_record_id}: "
            f"{raw_record.original_point_name} → {sanitized.sanitized_name}"
        )

        return sanitized

    def _normalize_unit(self, raw_record: RawSourceRecord, sanitized: SanitizedIntermediateRecord):
        """Normalize unit to standard format."""
        raw_unit = raw_record.raw_unit.upper().strip()

        # Temperature units
        if raw_unit in ["DEG", "DEGREE", "DEGREES", "DEG C", "DEG. C", "°C"]:
            sanitized.normalized_unit = "degC"
            sanitized.add_transformation("unit_normalized_temperature")

        # Percentage
        elif raw_unit in ["%", "PERCENT", "PCT"]:
            sanitized.normalized_unit = "%"
            sanitized.add_transformation("unit_normalized_percentage")

        # Pressure
        elif raw_unit in ["PSI", "LB/IN²", "LB_PER_IN²"]:
            sanitized.normalized_unit = "psi"
            sanitized.add_transformation("unit_normalized_pressure")

        # Power
        elif raw_unit in ["KW", "KILOWATT", "KILOWATTS"]:
            sanitized.normalized_unit = "kW"
            sanitized.add_transformation("unit_normalized_power")

        # Flow
        elif raw_unit in ["CFM", "FT³/MIN"]:
            sanitized.normalized_unit = "cfm"
            sanitized.add_transformation("unit_normalized_flow")

        # Parts per million
        elif raw_unit in ["PPM", "PARTS_PER_MILLION"]:
            sanitized.normalized_unit = "ppm"
            sanitized.add_transformation("unit_normalized_concentration")

        # Volts
        elif raw_unit in ["V", "VOLT", "VOLTS"]:
            sanitized.normalized_unit = "V"
            sanitized.add_transformation("unit_normalized_voltage")

        # Amps
        elif raw_unit in ["A", "AMP", "AMPS"]:
            sanitized.normalized_unit = "A"
            sanitized.add_transformation("unit_normalized_current")

        # Unknown units - preserve but warn
        else:
            sanitized.normalized_unit = raw_unit
            if raw_unit and raw_unit not in ["", "UNKNOWN", "NA"]:
                sanitized.add_warning(f"unknown_unit_format: {raw_unit}")

        # Handle empty/unknown units
        if not sanitized.normalized_unit or sanitized.normalized_unit == "UNKNOWN":
            sanitized.normalized_unit = "unknown"
            sanitized.add_warning("missing_or_invalid_unit")

    def _clean_point_name(self, raw_record: RawSourceRecord, sanitized: SanitizedIntermediateRecord):
        """Clean and normalize point names."""
        original_name = raw_record.original_point_name

        # Common patterns and their replacements
        patterns = [
            (r"\s+", "_"),  # Spaces to underscores
            (r"[\-\.]", "_"),  # Dashes and dots to underscores
            (r"[^\w_]", ""),  # Remove special characters
            (r"_+", "_"),  # Collapse multiple underscores
            (r"^_|_$", ""),  # Remove leading/trailing underscores
        ]

        cleaned_name = original_name
        for pattern, replacement in patterns:
            cleaned_name = re.sub(pattern, replacement, cleaned_name)

        # Convert to lowercase
        cleaned_name = cleaned_name.lower()

        # Handle empty names
        if not cleaned_name:
            cleaned_name = f"unknown_point_{abs(hash(str(original_name)))[:8]}"
            sanitized.add_warning("empty_point_name_after_cleaning")

        sanitized.sanitized_name = cleaned_name
        sanitized.add_transformation("name_cleaned")

        # Check for suspicious patterns
        if len(original_name) > 64:
            sanitized.add_warning("unusually_long_point_name")

        if any(char.isupper() for char in original_name[:10]):
            sanitized.add_warning("mixed_case_point_name")

    def _normalize_data_type(self, raw_record: RawSourceRecord, sanitized: SanitizedIntermediateRecord):
        """Normalize data type to standard format."""
        # Use the raw_value_type from the raw record (already inferred)
        raw_type = raw_record.raw_value_type.lower()

        if raw_type in ["float", "integer", "boolean", "string"]:
            sanitized.normalized_data_type = raw_type
            sanitized.add_transformation("type_normalized")
        else:
            sanitized.normalized_data_type = "unknown"
            sanitized.add_warning(f"unknown_data_type: {raw_type}")

    def _normalize_writable_flag(self, raw_record: RawSourceRecord, sanitized: SanitizedIntermediateRecord):
        """Ensure writable flag is properly normalized."""
        # This is informational - the actual writable status comes from raw record
        # Just ensure it's a proper boolean
        writable = bool(raw_record.writable)

        # Add warning if this seems suspicious for certain point types
        if not writable and "command" in raw_record.original_point_name.lower():
            sanitized.add_warning("command_point_not_writable")

        elif writable and "sensor" in raw_record.original_point_name.lower():
            sanitized.add_warning("sensor_point_marked_writable")

    def _extract_context(self, raw_record: RawSourceRecord, sanitized: SanitizedIntermediateRecord):
        """Extract equipment and location context from raw data."""
        # Equipment ID - try to extract from various sources
        if raw_record.device_id:
            sanitized.equipment_id = raw_record.device_id

        # Equipment type - look for patterns in point name
        point_name_lower = raw_record.original_point_name.lower()
        if "ahu" in point_name_lower:
            sanitized.equipment_type = "AHU"
        elif "fcu" in point_name_lower:
            sanitized.equipment_type = "FCU"
        elif "vav" in point_name_lower:
            sanitized.equipment_type = "VAV"
        elif "chiller" in point_name_lower:
            sanitized.equipment_type = "CHILLER"

        # Location hierarchy - build from available data
        if raw_record.site_id:
            sanitized.location_hierarchy.append(raw_record.site_id)

        if raw_record.building_id:
            sanitized.location_hierarchy.append(raw_record.building_id)

        # Add transformation if we found any context
        if sanitized.equipment_id or sanitized.equipment_type or sanitized.location_hierarchy:
            sanitized.add_transformation("context_extracted")

    def _should_reject(self, sanitized: SanitizedIntermediateRecord) -> bool:
        """Determine if this record should be rejected."""
        # Reject if we have critical warnings
        critical_warnings = ["empty_point_name_after_cleaning", "missing_or_invalid_unit"]

        for warning in sanitized.warnings:
            if warning in critical_warnings:
                return True

        # Reject if name or unit are still unknown
        if not sanitized.sanitized_name or sanitized.sanitized_name.startswith("unknown_"):
            return True

        if sanitized.normalized_unit == "unknown":
            return True

        return False

    def get_metrics(self) -> Dict[str, int]:
        """Get sanitization metrics."""
        return {
            "sanitized_count": self.sanitized_count,
            "rejected_count": self.rejected_count,
            "warning_count": self.warning_count,
            "success_rate": self.sanitized_count / (self.sanitized_count + self.rejected_count)
            if (self.sanitized_count + self.rejected_count) > 0
            else 1.0,
        }

    def reset_metrics(self):
        """Reset counters for monitoring."""
        self.sanitized_count = 0
        self.rejected_count = 0
        self.warning_count = 0
