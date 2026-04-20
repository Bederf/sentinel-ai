"""
Checklist Generator Service - Generates OEM-specific inspection checklists using Claude AI.

Phase 66: OEM-Specific Checklist Generation
Plan 01: Checklist Generation Foundation

This service generates equipment-specific inspection and maintenance checklists
tailored to manufacturer and model specifications. Generated checklists are
stored in Supabase for reuse across identical equipment.
"""

import json
import logging
import re
from typing import Any

from app.config.settings import settings
from app.services.model_gateway import model_gateway

logger = logging.getLogger(__name__)


class ChecklistGeneratorService:
    """Generates OEM-specific inspection and maintenance checklists using Claude AI.

    Features:
    - Generates 3 template variants per equipment: routine, preventive, annual
    - OEM-specific tolerances, tools, PPE, and safety requirements
    - Demo mode returns pre-built templates without Claude API calls
    - Idempotent: checks for existing templates before generating
    - Stores generated templates in Supabase via ChecklistTemplateRepository
    """

    def __init__(self):
        """Initialize with settings and lazy repository."""
        self._repo = None

    @property
    def repo(self):
        """Lazy-init repository to avoid import-time Supabase connection."""
        if self._repo is None:
            try:
                from app.database.repositories.checklist_template_repository import (
                    get_checklist_template_repository,
                )

                self._repo = get_checklist_template_repository()
            except Exception as e:
                logger.warning(f"Could not initialize checklist template repository: {e}")
        return self._repo

    async def generate_checklists(
        self,
        equipment_type: str,
        manufacturer: str,
        model: str,
        capacity: str = None,
        additional_specs: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Generate OEM-specific inspection/maintenance checklists.

        Generates 3 template variants:
        - routine_inspection (weekly/monthly)
        - preventive_maintenance (quarterly)
        - annual_major_service (annual)

        Checks for existing templates first to avoid duplicate generation.

        Args:
            equipment_type: Equipment type (e.g., 'chiller', 'ahu').
            manufacturer: Manufacturer name (e.g., 'Carrier', 'York').
            model: Model identifier (e.g., '30HXC0800').
            capacity: Optional capacity string (e.g., '800kW').
            additional_specs: Optional additional specifications dict.

        Returns:
            List of generated template dicts (up to 3).
        """
        # Check if OEM templates already exist
        if self.repo:
            existing = self.repo.get_oem_template(equipment_type, manufacturer, model)
            if existing:
                logger.info(f"OEM templates already exist for {manufacturer} {model} {equipment_type}")
                # Return all variants for this OEM
                all_templates = self.repo.get_templates_for_equipment_type(equipment_type)
                oem_templates = [t for t in all_templates if manufacturer.lower() in t.get("template_name", "").lower()]
                if oem_templates:
                    return oem_templates

        # Local simulator mode: return pre-built templates
        if settings.site002_source_enabled:
            return self._generate_demo_templates(equipment_type, manufacturer, model, capacity)

        # Build and call Claude API
        prompt = self._build_prompt(equipment_type, manufacturer, model, capacity, additional_specs)

        try:
            response_text = await model_gateway.call(
                task_class="medium",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=settings.claude_max_tokens,
                source="checklist_generation",
            )

            templates = self._parse_response(response_text, equipment_type, manufacturer, model)

            # Store in Supabase
            stored_templates = []
            if self.repo and templates:
                for template in templates:
                    result = self.repo.upsert_template(template)
                    if result:
                        stored_templates.append(result)

            return stored_templates if stored_templates else templates

        except Exception as e:
            logger.error(f"Claude API checklist generation failed: {e}")
            # Fall back to seeded templates on API failure
            return self._generate_demo_templates(equipment_type, manufacturer, model, capacity)

    async def generate_for_equipment(self, equipment_code: str) -> list[dict[str, Any]]:
        """Generate checklists for equipment by looking up its metadata.

        Args:
            equipment_code: Equipment code (e.g., 'S002-CHILLER-B1-001').

        Returns:
            List of generated template dicts, or empty list if no metadata.
        """
        try:
            from app.database.repositories.equipment_repository import EquipmentRepository

            equip_repo = EquipmentRepository()
            equipment = equip_repo.get_by_code(equipment_code)

            if not equipment:
                logger.warning(f"Equipment not found: {equipment_code}")
                return []

            # Extract manufacturer/model from metadata or equipment fields
            metadata = equipment.get("metadata", {}) or {}
            manufacturer = metadata.get("manufacturer") or equipment.get("manufacturer") or ""
            model = metadata.get("model") or equipment.get("model") or ""
            equipment_type = equipment.get("equipment_type", "").lower()
            capacity = metadata.get("capacity") or metadata.get("capacity_kw")

            if not manufacturer:
                logger.warning(f"No manufacturer data for {equipment_code}, skipping checklist generation")
                return []

            return await self.generate_checklists(
                equipment_type=equipment_type,
                manufacturer=manufacturer,
                model=model,
                capacity=str(capacity) if capacity else None,
            )

        except Exception as e:
            logger.error(f"Failed to generate checklists for {equipment_code}: {e}")
            return []

    def _build_prompt(
        self,
        equipment_type: str,
        manufacturer: str,
        model: str,
        capacity: str = None,
        additional_specs: dict[str, Any] | None = None,
    ) -> str:
        """Build Claude prompt for checklist generation.

        Args:
            equipment_type: Equipment type.
            manufacturer: Manufacturer name.
            model: Model identifier.
            capacity: Optional capacity string.
            additional_specs: Optional additional specs.

        Returns:
            Formatted prompt string.
        """
        specs_text = ""
        if capacity:
            specs_text += f"\nCapacity: {capacity}"
        if additional_specs:
            for key, value in additional_specs.items():
                specs_text += f"\n{key}: {value}"

        return (
            f"You are a building maintenance expert specializing in "
            f"commercial HVAC, electrical, and mechanical systems. "
            f"Generate inspection checklists for the following "
            f"equipment:\n\n"
            f"Equipment Type: {equipment_type}\n"
            f"Manufacturer: {manufacturer}\n"
            f"Model: {model}{specs_text}\n\n"
            f"Generate exactly 3 inspection template variants as a "
            f"JSON array. Each template should be tailored to "
            f"{manufacturer} {model} specifications with OEM-specific "
            f"tolerances where applicable.\n"
            f"""

**Template variants required:**
1. **routine_inspection** - Weekly/monthly routine checks (15-45 min)
2. **preventive_maintenance** - Quarterly preventive maintenance (60-120 min)
3. **annual_major_service** - Annual comprehensive service (120-240 min)

**Each template must have this exact structure:**
```json
{{
  "template_name": "{manufacturer} {model} [Inspection Type Name]",
  "equipment_type": "{equipment_type}",
  "inspection_type": "routine|preventive|annual",
  "frequency_type": "weekly|monthly|quarterly|annual",
  "estimated_duration_minutes": <number>,
  "required_tools": ["tool1", "tool2"],
  "required_skills": ["skill1", "skill2"],
  "safety_requirements": ["requirement1"],
  "ppe_required": ["ppe1", "ppe2"],
  "checklist_items": [
    {{
      "category": "Category Name",
      "item_id": "unique_snake_case_id",
      "question": "Human-readable question or instruction",
      "item_type": "checklist|measurement|visual_inspection",
      "options": [{{"label": "Display text", "value": "ok|warning|critical"}}],
      "parameter_name": "for_measurement_items_only",
      "unit": "measurement_unit",
      "tolerance_min": <number>,
      "tolerance_max": <number>,
      "required": true|false,
      "photos_required": true|false
    }}
  ]
}}
```

**Rules for checklist_items:**
- For `item_type: "checklist"`: include `options` array with ok/warning/critical values. Omit tolerance fields.
- For `item_type: "measurement"`: include `parameter_name`, `unit`, `tolerance_min`, `tolerance_max`. Omit `options`.
- For `item_type: "visual_inspection"`: set `photos_required: true`. Omit `options` and tolerance fields.
- Use {manufacturer}-specific tolerance ranges from manufacturer documentation where possible.
- Include 8-15 items per template, grouped by category.
- Categories should be specific to {equipment_type} (e.g., Compressor, Refrigerant, Oil System for chillers).
- Each `item_id` must be unique within the template (use snake_case).

Respond with ONLY the JSON array of 3 templates. No markdown, no explanation, just valid JSON."""
        )

    def _parse_response(
        self,
        response_text: str,
        equipment_type: str,
        manufacturer: str,
        model: str,
    ) -> list[dict[str, Any]]:
        """Parse Claude response into template dicts.

        Handles markdown code blocks and validates required fields.

        Args:
            response_text: Raw Claude API response text.
            equipment_type: Equipment type for fallback metadata.
            manufacturer: Manufacturer for fallback metadata.
            model: Model for fallback metadata.

        Returns:
            List of validated template dicts.
        """
        # Strip markdown code blocks if present
        text = response_text.strip()
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude JSON response: {e}")
            # Try to extract JSON array from response
            match = re.search(r"\[[\s\S]*\]", text)
            if match:
                try:
                    parsed = json.loads(match.group())
                except json.JSONDecodeError:
                    logger.error("Regex JSON extraction also failed")
                    return []
            else:
                return []

        if not isinstance(parsed, list):
            parsed = [parsed]

        # Validate and enrich templates
        valid_templates = []
        for template in parsed:
            if not isinstance(template, dict):
                continue

            # Ensure required fields
            template.setdefault("equipment_type", equipment_type)
            template.setdefault("version", 1)
            template.setdefault("is_active", True)
            template.setdefault("created_by", "ai_generator")

            if not template.get("template_name"):
                template["template_name"] = f"{manufacturer} {model} {equipment_type} Inspection"

            if not template.get("checklist_items"):
                logger.warning(f"Template '{template.get('template_name')}' has no checklist_items, skipping")
                continue

            valid_templates.append(template)

        logger.info(f"Parsed {len(valid_templates)} valid templates from Claude response")
        return valid_templates

    def _generate_demo_templates(
        self,
        equipment_type: str,
        manufacturer: str,
        model: str,
        capacity: str = None,
    ) -> list[dict[str, Any]]:
        """Generate pre-built seeded templates without Claude API.

        Used when DEMO_MODE=true or as fallback on API failure.

        Args:
            equipment_type: Equipment type.
            manufacturer: Manufacturer name.
            model: Model identifier.
            capacity: Optional capacity string.

        Returns:
            List of 3 seeded template dicts.
        """
        capacity_text = f" ({capacity})" if capacity else ""
        base_name = f"{manufacturer} {model}{capacity_text}"

        templates = [
            {
                "template_name": f"{base_name} Routine Inspection",
                "equipment_type": equipment_type,
                "inspection_type": "routine",
                "frequency_type": "weekly",
                "estimated_duration_minutes": 30,
                "version": 1,
                "is_active": True,
                "created_by": "ai_generator_demo",
                "required_tools": ["Multimeter", "Vibration meter", "IR thermometer"],
                "required_skills": [equipment_type, "general_inspection"],
                "safety_requirements": ["Lock-out/Tag-out before internal inspection"],
                "ppe_required": ["Safety glasses", "Hearing protection", "Steel-toe boots"],
                "checklist_items": [
                    {
                        "category": "General",
                        "item_id": "visual_check",
                        "question": (
                            f"Visual inspection of {manufacturer} {model} - check for leaks, damage, unusual noise"
                        ),
                        "item_type": "checklist",
                        "options": [
                            {"label": "No issues", "value": "ok"},
                            {"label": "Minor concerns", "value": "warning"},
                            {"label": "Major issues", "value": "critical"},
                        ],
                        "required": True,
                        "photos_required": False,
                    },
                    {
                        "category": "General",
                        "item_id": "nameplate_photo",
                        "question": f"Photograph {manufacturer} nameplate and current readings",
                        "item_type": "visual_inspection",
                        "required": False,
                        "photos_required": True,
                    },
                    {
                        "category": "Operating Parameters",
                        "item_id": "operating_temp",
                        "question": f"Operating temperature ({manufacturer} spec)",
                        "item_type": "measurement",
                        "parameter_name": "operating_temperature",
                        "unit": "°C",
                        "tolerance_min": 5.0,
                        "tolerance_max": 45.0,
                        "required": True,
                        "photos_required": False,
                    },
                    {
                        "category": "Operating Parameters",
                        "item_id": "vibration_level",
                        "question": "Vibration level at bearing housing",
                        "item_type": "measurement",
                        "parameter_name": "vibration_rms",
                        "unit": "mm/s",
                        "tolerance_min": 0.0,
                        "tolerance_max": 4.5,
                        "required": True,
                        "photos_required": False,
                    },
                    {
                        "category": "Electrical",
                        "item_id": "supply_voltage",
                        "question": "Supply voltage (all phases)",
                        "item_type": "measurement",
                        "parameter_name": "supply_voltage",
                        "unit": "V",
                        "tolerance_min": 380.0,
                        "tolerance_max": 420.0,
                        "required": True,
                        "photos_required": False,
                    },
                    {
                        "category": "Electrical",
                        "item_id": "motor_current",
                        "question": "Motor running current",
                        "item_type": "measurement",
                        "parameter_name": "motor_current",
                        "unit": "A",
                        "tolerance_min": 0.0,
                        "tolerance_max": 100.0,
                        "required": True,
                        "photos_required": False,
                    },
                    {
                        "category": "Safety",
                        "item_id": "safety_devices",
                        "question": "Safety devices and interlocks operational",
                        "item_type": "checklist",
                        "options": [
                            {"label": "All functional", "value": "ok"},
                            {"label": "Partial function", "value": "warning"},
                            {"label": "Safety device failed", "value": "critical"},
                        ],
                        "required": True,
                        "photos_required": False,
                    },
                ],
            },
            {
                "template_name": f"{base_name} Preventive Maintenance",
                "equipment_type": equipment_type,
                "inspection_type": "preventive",
                "frequency_type": "quarterly",
                "estimated_duration_minutes": 90,
                "version": 1,
                "is_active": True,
                "created_by": "ai_generator_demo",
                "required_tools": [
                    "Multimeter",
                    "Vibration meter",
                    "IR thermometer",
                    "Torque wrench",
                    "Filter set",
                ],
                "required_skills": [equipment_type, "preventive_maintenance"],
                "safety_requirements": [
                    "Lock-out/Tag-out required",
                    "Permit to work for electrical isolation",
                ],
                "ppe_required": [
                    "Safety glasses",
                    "Hearing protection",
                    "Steel-toe boots",
                    "Gloves",
                ],
                "checklist_items": [
                    {
                        "category": "Pre-Maintenance",
                        "item_id": "pre_maint_visual",
                        "question": f"Pre-maintenance visual inspection of {manufacturer} {model}",
                        "item_type": "visual_inspection",
                        "required": True,
                        "photos_required": True,
                    },
                    {
                        "category": "Filters",
                        "item_id": "filter_condition",
                        "question": "Air/oil filter condition and replacement",
                        "item_type": "checklist",
                        "options": [
                            {"label": "Clean / replaced", "value": "ok"},
                            {"label": "Dirty but serviceable", "value": "warning"},
                            {"label": "Blocked / damaged", "value": "critical"},
                        ],
                        "required": True,
                        "photos_required": False,
                    },
                    {
                        "category": "Belts & Bearings",
                        "item_id": "belt_tension",
                        "question": "Belt tension and condition",
                        "item_type": "checklist",
                        "options": [
                            {"label": "Correct tension, no wear", "value": "ok"},
                            {"label": "Slight wear or loose", "value": "warning"},
                            {"label": "Cracked/frayed/broken", "value": "critical"},
                        ],
                        "required": True,
                        "photos_required": False,
                    },
                    {
                        "category": "Belts & Bearings",
                        "item_id": "bearing_temp",
                        "question": "Bearing temperature (IR thermometer)",
                        "item_type": "measurement",
                        "parameter_name": "bearing_temperature",
                        "unit": "°C",
                        "tolerance_min": 20.0,
                        "tolerance_max": 70.0,
                        "required": True,
                        "photos_required": False,
                    },
                    {
                        "category": "Electrical",
                        "item_id": "insulation_resistance",
                        "question": "Motor insulation resistance (Megger test)",
                        "item_type": "measurement",
                        "parameter_name": "insulation_resistance",
                        "unit": "MΩ",
                        "tolerance_min": 1.0,
                        "tolerance_max": 1000.0,
                        "required": True,
                        "photos_required": False,
                    },
                    {
                        "category": "Connections",
                        "item_id": "electrical_connections",
                        "question": "Electrical connections - tightness and condition",
                        "item_type": "checklist",
                        "options": [
                            {"label": "All secure", "value": "ok"},
                            {"label": "Loose connections found", "value": "warning"},
                            {"label": "Burnt/damaged terminals", "value": "critical"},
                        ],
                        "required": True,
                        "photos_required": False,
                    },
                    {
                        "category": "Post-Maintenance",
                        "item_id": "post_maint_test",
                        "question": "Post-maintenance functional test - unit starts and runs normally",
                        "item_type": "checklist",
                        "options": [
                            {"label": "Normal operation", "value": "ok"},
                            {"label": "Minor issues noted", "value": "warning"},
                            {"label": "Failed to start / abnormal", "value": "critical"},
                        ],
                        "required": True,
                        "photos_required": False,
                    },
                ],
            },
            {
                "template_name": f"{base_name} Annual Major Service",
                "equipment_type": equipment_type,
                "inspection_type": "annual",
                "frequency_type": "annual",
                "estimated_duration_minutes": 180,
                "version": 1,
                "is_active": True,
                "created_by": "ai_generator_demo",
                "required_tools": [
                    "Multimeter",
                    "Vibration analyzer",
                    "IR thermometer",
                    "Torque wrench",
                    "Pressure gauge set",
                    "Refrigerant recovery unit",
                ],
                "required_skills": [
                    equipment_type,
                    "major_service",
                    "refrigerant_handling",
                ],
                "safety_requirements": [
                    "Lock-out/Tag-out required",
                    "Permit to work for electrical and mechanical isolation",
                    "Refrigerant handling certification required",
                ],
                "ppe_required": [
                    "Safety glasses",
                    "Hearing protection",
                    "Steel-toe boots",
                    "Chemical-resistant gloves",
                    "Face shield",
                ],
                "checklist_items": [
                    {
                        "category": "Pre-Service",
                        "item_id": "annual_pre_inspection",
                        "question": f"Full pre-service documentation of {manufacturer} {model} condition",
                        "item_type": "visual_inspection",
                        "required": True,
                        "photos_required": True,
                    },
                    {
                        "category": "Mechanical",
                        "item_id": "vibration_analysis",
                        "question": "Comprehensive vibration analysis - all bearings",
                        "item_type": "measurement",
                        "parameter_name": "vibration_overall",
                        "unit": "mm/s",
                        "tolerance_min": 0.0,
                        "tolerance_max": 4.5,
                        "required": True,
                        "photos_required": False,
                    },
                    {
                        "category": "Mechanical",
                        "item_id": "alignment_check",
                        "question": "Shaft alignment verification",
                        "item_type": "checklist",
                        "options": [
                            {"label": "Within tolerance", "value": "ok"},
                            {"label": "Minor misalignment", "value": "warning"},
                            {"label": "Requires realignment", "value": "critical"},
                        ],
                        "required": True,
                        "photos_required": False,
                    },
                    {
                        "category": "Electrical",
                        "item_id": "annual_insulation",
                        "question": "Motor insulation resistance (all phases)",
                        "item_type": "measurement",
                        "parameter_name": "insulation_resistance_annual",
                        "unit": "MΩ",
                        "tolerance_min": 2.0,
                        "tolerance_max": 2000.0,
                        "required": True,
                        "photos_required": False,
                    },
                    {
                        "category": "Electrical",
                        "item_id": "contactor_condition",
                        "question": "Contactor and starter condition",
                        "item_type": "checklist",
                        "options": [
                            {"label": "Good condition", "value": "ok"},
                            {"label": "Pitting visible", "value": "warning"},
                            {"label": "Replace required", "value": "critical"},
                        ],
                        "required": True,
                        "photos_required": False,
                    },
                    {
                        "category": "Controls",
                        "item_id": "control_calibration",
                        "question": "Sensor and control calibration verification",
                        "item_type": "checklist",
                        "options": [
                            {"label": "All calibrated", "value": "ok"},
                            {"label": "Minor drift", "value": "warning"},
                            {"label": "Requires recalibration", "value": "critical"},
                        ],
                        "required": True,
                        "photos_required": False,
                    },
                    {
                        "category": "Safety",
                        "item_id": "annual_safety_test",
                        "question": "All safety devices tested and certified",
                        "item_type": "checklist",
                        "options": [
                            {"label": "All passed", "value": "ok"},
                            {"label": "Adjustment needed", "value": "warning"},
                            {"label": "Safety device failed", "value": "critical"},
                        ],
                        "required": True,
                        "photos_required": False,
                    },
                    {
                        "category": "Post-Service",
                        "item_id": "annual_post_photo",
                        "question": f"Post-service condition photos of {manufacturer} {model}",
                        "item_type": "visual_inspection",
                        "required": True,
                        "photos_required": True,
                    },
                ],
            },
        ]

        # Store seeded templates in Supabase if available
        if self.repo:
            for template in templates:
                try:
                    self.repo.upsert_template(template)
                except Exception as e:
                    logger.warning(f"Could not store seeded template in Supabase: {e}")

        return templates


# ============================================================================
# Singleton Factory
# ============================================================================

_instance: ChecklistGeneratorService | None = None


def get_checklist_generator_service() -> ChecklistGeneratorService:
    """Get singleton instance of ChecklistGeneratorService.

    Returns:
        ChecklistGeneratorService instance.
    """
    global _instance
    if _instance is None:
        _instance = ChecklistGeneratorService()
    return _instance
