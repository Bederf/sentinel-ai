"""
Checklist Service - Manages inspection checklist templates and measurement recording.

Phase 55: Routine Inspection & Maintenance
Plan 02: Checklist Templates and Measurement Service

This service provides:
- Template loading from JSON with caching
- Template lookup by equipment type and inspection type
- Completion status calculation with critical/warning/ok counts
- Measurement preparation for database storage
- Measurement type inference from parameter names
"""

from typing import List, Dict, Any, Optional
from pathlib import Path
import json
import logging

from app.database.repositories.checklist_template_repository import (
    get_checklist_template_repository,
)

logger = logging.getLogger(__name__)


class ChecklistService:
    """
    Service for managing inspection checklist templates and processing inspection responses.

    Features:
    - Lazy loading and caching of templates from JSON
    - Template lookup by ID, equipment type, or inspection type
    - Completion status calculation from responses
    - Measurement record preparation for database storage
    - Measurement type inference from parameter names
    """

    def __init__(self):
        """Initialize ChecklistService with template path and lazy Supabase repo."""
        self._templates_cache: Optional[Dict[str, Any]] = None
        self._templates_path = Path(__file__).parent.parent / "data" / "inspection_checklist_templates.json"
        self._repo = None  # Lazy-init Supabase repository

    @property
    def repo(self):
        """Lazy-init Supabase repository. Returns None if unavailable."""
        if self._repo is None:
            try:
                self._repo = get_checklist_template_repository()
            except Exception:
                self._repo = None
        return self._repo

    def _load_templates(self) -> Dict[str, Any]:
        """
        Load templates from JSON file with caching.

        Returns:
            Dict mapping template_id to template data.

        Raises:
            FileNotFoundError: If templates file doesn't exist.
            json.JSONDecodeError: If templates file is invalid JSON.
        """
        if self._templates_cache is None:
            logger.info(f"Loading checklist templates from {self._templates_path}")
            with open(self._templates_path, 'r') as f:
                data = json.load(f)
                self._templates_cache = data.get("templates", {})
                logger.info(f"Loaded {len(self._templates_cache)} checklist templates")
        return self._templates_cache

    def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """
        Get checklist template by ID.

        Tries Supabase first, falls back to JSON file.

        Args:
            template_id: Unique template identifier (UUID or JSON key like 'chiller_weekly')

        Returns:
            Template dict or None if not found.
        """
        # Try Supabase first
        if self.repo:
            try:
                result = self.repo.get_template(template_id)
                if result:
                    return result
            except Exception as e:
                logger.warning(f"Supabase template lookup failed: {e}")

        # Fall back to JSON
        templates = self._load_templates()
        return templates.get(template_id)

    def get_templates_by_equipment_type(self, equipment_type: str) -> List[Dict[str, Any]]:
        """
        Get all templates for an equipment type.

        Tries Supabase first, falls back to JSON file.

        Args:
            equipment_type: Equipment type (e.g., 'chiller', 'ahu', 'generator')

        Returns:
            List of matching template dicts.
        """
        # Try Supabase first
        if self.repo:
            try:
                results = self.repo.get_templates_for_equipment_type(equipment_type)
                if results:
                    return results
            except Exception as e:
                logger.warning(f"Supabase equipment type lookup failed: {e}")

        # Fall back to JSON
        templates = self._load_templates()
        return [
            t for t in templates.values()
            if t.get("equipment_type") == equipment_type
        ]

    def get_template_for_inspection(
        self,
        equipment_type: str,
        inspection_type: str = "routine"
    ) -> Optional[Dict[str, Any]]:
        """
        Get best matching template for equipment and inspection type.

        Tries Supabase first with exact match, falls back to JSON best-match.

        Args:
            equipment_type: Equipment type (e.g., 'chiller', 'ahu')
            inspection_type: Inspection type (e.g., 'routine', 'preventive')

        Returns:
            Matching template dict or None if no match.
        """
        # Try Supabase first for exact match
        if self.repo:
            try:
                results = self.repo.get_templates_for_equipment_type(equipment_type)
                if results:
                    matching = [
                        t for t in results
                        if t.get("inspection_type") == inspection_type
                    ]
                    if matching:
                        return matching[0]
                    # Return first Supabase result as fallback
                    return results[0]
            except Exception as e:
                logger.warning(f"Supabase inspection template lookup failed: {e}")

        # Fall back to JSON-based lookup
        templates = self._get_json_templates_by_equipment_type(equipment_type)

        if not templates:
            logger.warning(f"No templates found for equipment_type={equipment_type}")
            return None

        # Prefer exact inspection_type match, fall back to first template
        matching = [t for t in templates if t.get("inspection_type") == inspection_type]

        if matching:
            return matching[0]

        # Fall back to first available template for this equipment type
        logger.info(
            f"No exact match for inspection_type={inspection_type}, "
            f"using first available template for {equipment_type}"
        )
        return templates[0]

    def _get_json_templates_by_equipment_type(self, equipment_type: str) -> List[Dict[str, Any]]:
        """Get templates from JSON file only (no Supabase).

        Used as internal fallback when Supabase is unavailable.
        """
        templates = self._load_templates()
        return [
            t for t in templates.values()
            if t.get("equipment_type") == equipment_type
        ]

    def get_oem_template(
        self,
        equipment_type: str,
        manufacturer: str,
        model: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get OEM-specific template by manufacturer.

        Only available via Supabase (OEM templates are AI-generated
        and stored in the database, not in JSON files).

        Args:
            equipment_type: Equipment type (e.g., 'chiller').
            manufacturer: Manufacturer name (e.g., 'Carrier').
            model: Optional model for more specific matching.

        Returns:
            OEM-specific template dict or None if not found.
        """
        if self.repo:
            try:
                return self.repo.get_oem_template(equipment_type, manufacturer, model)
            except Exception as e:
                logger.warning(f"Supabase OEM template lookup failed: {e}")
        return None  # No OEM fallback in JSON

    def list_all_templates(self) -> List[Dict[str, Any]]:
        """
        List all available templates with summary info.

        Merges Supabase templates with JSON templates, deduplicating by name.

        Returns:
            List of template summaries with id, name, equipment_type, item_count.
        """
        results = []
        seen_names = set()

        # Try Supabase first
        if self.repo:
            try:
                supabase_templates = self.repo.list_all_templates()
                for t in supabase_templates:
                    name = t.get("template_name", "")
                    seen_names.add(name.lower())
                    results.append({
                        "template_id": t.get("id"),
                        "template_name": name,
                        "equipment_type": t.get("equipment_type"),
                        "inspection_type": t.get("inspection_type"),
                        "estimated_duration_minutes": t.get("estimated_duration_minutes"),
                        "item_count": len(t.get("checklist_items", [])),
                        "source": "supabase",
                    })
            except Exception as e:
                logger.warning(f"Supabase template listing failed: {e}")

        # Add JSON templates not already in Supabase
        templates = self._load_templates()
        for t in templates.values():
            name = t.get("template_name", "")
            if name.lower() not in seen_names:
                results.append({
                    "template_id": t.get("template_id"),
                    "template_name": name,
                    "equipment_type": t.get("equipment_type"),
                    "inspection_type": t.get("inspection_type"),
                    "estimated_duration_minutes": t.get("estimated_duration_minutes"),
                    "item_count": len(t.get("checklist_items", [])),
                    "source": "json",
                })

        return results

    def calculate_completion_status(
        self,
        template: Dict[str, Any],
        responses: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calculate inspection completion status from responses.

        Args:
            template: Template dict containing checklist_items
            responses: Dict mapping item_id to response value
                - For checklist items: response is string ('ok', 'warning', 'critical')
                - For measurement items: response is dict {'value': float, 'notes': str}
                - For visual_inspection: response is dict {'notes': str, 'photo_url': str}

        Returns:
            Dict with completion statistics:
            - total_items: Total checklist items
            - completed_items: Items with responses
            - completion_percentage: Percentage complete
            - critical_count: Items marked critical
            - warning_count: Items marked warning
            - ok_count: Items marked ok or within tolerance
            - failed_tolerances: Measurement items outside tolerance
            - overall_status: 'critical', 'warning', or 'ok'
        """
        items = template.get("checklist_items", [])
        total_items = len(items)
        completed_items = 0
        critical_count = 0
        warning_count = 0
        ok_count = 0
        failed_tolerances = 0

        for item in items:
            item_id = item.get("item_id")
            response = responses.get(item_id)

            if response is None:
                continue

            completed_items += 1
            item_type = item.get("item_type")

            # Checklist items (multiple choice)
            if item_type == "checklist":
                if response == "critical":
                    critical_count += 1
                elif response == "warning":
                    warning_count += 1
                elif response == "ok":
                    ok_count += 1

            # Measurement items (numerical with tolerances)
            elif item_type == "measurement":
                value = response.get("value") if isinstance(response, dict) else response
                min_tol = item.get("tolerance_min")
                max_tol = item.get("tolerance_max")

                if value is not None and min_tol is not None and max_tol is not None:
                    try:
                        value = float(value)
                        if min_tol <= value <= max_tol:
                            ok_count += 1
                        else:
                            failed_tolerances += 1
                    except (ValueError, TypeError):
                        # Invalid value, count as failed
                        failed_tolerances += 1

            # Visual inspection items (always ok if completed with notes/photo)
            elif item_type == "visual_inspection":
                ok_count += 1

        # Determine overall status
        if critical_count > 0:
            overall_status = "critical"
        elif warning_count > 0 or failed_tolerances > 0:
            overall_status = "warning"
        else:
            overall_status = "ok"

        return {
            "total_items": total_items,
            "completed_items": completed_items,
            "completion_percentage": round((completed_items / total_items * 100), 1) if total_items > 0 else 0.0,
            "critical_count": critical_count,
            "warning_count": warning_count,
            "ok_count": ok_count,
            "failed_tolerances": failed_tolerances,
            "overall_status": overall_status
        }

    def prepare_measurements_for_db(
        self,
        template: Dict[str, Any],
        responses: Dict[str, Any],
        task_id: str
    ) -> List[Dict[str, Any]]:
        """
        Convert checklist responses to measurement records for database.

        Only processes measurement-type items from responses.

        Args:
            template: Template dict containing checklist_items
            responses: Dict mapping item_id to response value
                - For measurement items: {'value': float, 'notes': str, 'measured_at': str}
            task_id: Inspection task ID for linking measurements

        Returns:
            List of measurement record dicts ready for database insertion:
            - task_id: Inspection task ID
            - element_id: Equipment element ID (if applicable)
            - measurement_type: Inferred type (vibration, temperature, etc.)
            - parameter_name: Parameter identifier
            - value: Measured value
            - unit: Measurement unit
            - is_within_tolerance: Boolean tolerance check result
            - tolerance_min/max: Tolerance bounds
            - notes: Optional technician notes
            - measured_at: ISO timestamp
        """
        measurements = []

        for item in template.get("checklist_items", []):
            if item.get("item_type") != "measurement":
                continue

            item_id = item.get("item_id")
            response = responses.get(item_id)

            if response is None:
                continue

            # Handle both dict and direct value responses
            if isinstance(response, dict):
                value = response.get("value")
                notes = response.get("notes")
                measured_at = response.get("measured_at")
            else:
                value = response
                notes = None
                measured_at = None

            if value is None:
                continue

            try:
                value = float(value)
            except (ValueError, TypeError):
                logger.warning(f"Invalid measurement value for {item_id}: {value}")
                continue

            min_tol = item.get("tolerance_min")
            max_tol = item.get("tolerance_max")

            # Determine if within tolerance
            is_within_tolerance = None
            if min_tol is not None and max_tol is not None:
                is_within_tolerance = min_tol <= value <= max_tol

            measurements.append({
                "task_id": task_id,
                "element_id": item.get("element_id"),  # May be None
                "measurement_type": self._infer_measurement_type(item),
                "parameter_name": item.get("parameter_name"),
                "value": value,
                "unit": item.get("unit"),
                "is_within_tolerance": is_within_tolerance,
                "tolerance_min": min_tol,
                "tolerance_max": max_tol,
                "notes": notes,
                "measured_at": measured_at
            })

        return measurements

    def _infer_measurement_type(self, item: Dict[str, Any]) -> str:
        """
        Infer measurement type from parameter name and item context.

        Args:
            item: Checklist item dict with parameter_name

        Returns:
            Measurement type string: 'vibration', 'temperature', 'pressure',
            'electrical', 'flow', 'level', or 'general'
        """
        param = item.get("parameter_name", "").lower()

        # Vibration measurements
        if "vibration" in param or "vib" in param:
            return "vibration"

        # Temperature measurements
        if "temp" in param:
            return "temperature"

        # Pressure measurements
        if "pressure" in param or "press" in param or "_dp" in param:
            return "pressure"

        # Current/Amperage
        if "current" in param or "amp" in param:
            return "electrical"

        # Voltage
        if "voltage" in param or "volt" in param:
            return "electrical"

        # Flow
        if "flow" in param or "airflow" in param:
            return "flow"

        # Level
        if "level" in param:
            return "level"

        # Position
        if "position" in param:
            return "position"

        # Default
        return "general"

    def validate_response_format(
        self,
        template: Dict[str, Any],
        responses: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate response format against template requirements.

        Args:
            template: Template dict containing checklist_items
            responses: Dict mapping item_id to response value

        Returns:
            Dict with validation results:
            - is_valid: Boolean overall validity
            - missing_required: List of missing required item IDs
            - invalid_items: List of items with invalid response format
            - errors: List of error message strings
        """
        items = template.get("checklist_items", [])
        missing_required = []
        invalid_items = []
        errors = []

        for item in items:
            item_id = item.get("item_id")
            item_type = item.get("item_type")
            is_required = item.get("required", False)
            response = responses.get(item_id)

            # Check required fields
            if is_required and response is None:
                missing_required.append(item_id)
                errors.append(f"Required item '{item_id}' is missing")
                continue

            if response is None:
                continue

            # Validate response format by item type
            if item_type == "checklist":
                valid_values = [opt.get("value") for opt in item.get("options", [])]
                if response not in valid_values:
                    invalid_items.append(item_id)
                    errors.append(
                        f"Item '{item_id}' has invalid value '{response}'. "
                        f"Valid values: {valid_values}"
                    )

            elif item_type == "measurement":
                if isinstance(response, dict):
                    value = response.get("value")
                else:
                    value = response

                if value is not None:
                    try:
                        float(value)
                    except (ValueError, TypeError):
                        invalid_items.append(item_id)
                        errors.append(
                            f"Item '{item_id}' has non-numeric value: {value}"
                        )

            elif item_type == "visual_inspection":
                if item.get("photos_required") and isinstance(response, dict):
                    if not response.get("photo_url") and not response.get("photo_urls"):
                        invalid_items.append(item_id)
                        errors.append(
                            f"Item '{item_id}' requires photo but none provided"
                        )

        return {
            "is_valid": len(missing_required) == 0 and len(invalid_items) == 0,
            "missing_required": missing_required,
            "invalid_items": invalid_items,
            "errors": errors
        }

    def reload_templates(self) -> int:
        """
        Force reload of templates from file.

        Useful for development or when templates are updated.

        Returns:
            Number of templates loaded.
        """
        self._templates_cache = None
        templates = self._load_templates()
        logger.info(f"Reloaded {len(templates)} checklist templates")
        return len(templates)


# ============================================================================
# Singleton Factory
# ============================================================================

_checklist_service_instance: Optional[ChecklistService] = None


def get_checklist_service() -> ChecklistService:
    """
    Get singleton instance of ChecklistService.

    Returns:
        ChecklistService instance.
    """
    global _checklist_service_instance
    if _checklist_service_instance is None:
        _checklist_service_instance = ChecklistService()
    return _checklist_service_instance
