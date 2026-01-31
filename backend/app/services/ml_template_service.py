"""ML data collection template service for Phase 41.

Provides equipment and service-specific templates for ML data collection,
including required items, prompts, and validation rules.

Context-aware prompts use diagnostic information from the original alert
to ask targeted questions rather than open-ended ones.
"""

import json
from typing import Dict, Any, Optional, List
from pathlib import Path


# Root cause options by equipment type for confirmation prompts
ROOT_CAUSE_OPTIONS = {
    "fcu": {
        "fcu_valve_stuck": [
            "Actuator motor failed",
            "Actuator jammed mechanically",
            "Control signal issue (0-10V)",
            "Power supply issue (24VAC)",
            "Valve seized/corroded",
            "Other"
        ],
        "fcu_fan_failure": [
            "Motor bearing failure",
            "Motor winding burned",
            "Capacitor failed",
            "Fan blade damaged",
            "VSD/speed controller fault",
            "Other"
        ]
    },
    "vav": {
        "vav_damper_stuck": [
            "Actuator failed",
            "Damper blade jammed",
            "Linkage disconnected",
            "Controller fault",
            "Other"
        ]
    },
    "ahu": {
        "ahu_supply_high": [
            "Chiller not running",
            "CHW valve stuck closed",
            "Coil fouled/blocked",
            "Filter blocked (high DP)",
            "VSD fault",
            "Other"
        ]
    },
    "generator": {
        "gen_no_start": [
            "Battery dead/weak",
            "Starter motor failed",
            "Fuel solenoid stuck",
            "Controller fault",
            "Safety interlock active",
            "Other"
        ]
    }
}


class MLTemplateService:
    """Service for managing ML data collection templates."""

    def __init__(self, templates_path: Optional[str] = None):
        """Initialize template service.

        Args:
            templates_path: Path to templates JSON file. Defaults to
                app/data/ml_data_templates.json
        """
        if templates_path is None:
            # Default path relative to backend/app
            self.templates_path = Path(__file__).parent.parent / "data" / "ml_data_templates.json"
        else:
            self.templates_path = Path(templates_path)

        self._templates = None

    def _load_templates(self) -> Dict[str, Any]:
        """Load templates from JSON file."""
        if self._templates is None:
            with open(self.templates_path, 'r') as f:
                self._templates = json.load(f)
        return self._templates

    def get_template(self, equipment_type: str, service_type: str) -> Optional[Dict[str, Any]]:
        """Get template for equipment type and service type.

        Args:
            equipment_type: Equipment type (generator, chiller, pump, ahu, ups)
            service_type: Service type (minor, major, breakdown, callout)

        Returns:
            Template dictionary with required items, prompts, and rules,
            or None if not found

        Example:
            >>> template = template_service.get_template("generator", "minor")
            >>> print(template["required"])
            ['service_sheet', 'audio_recording', 'oil_sample', 'diesel_sample']
        """
        templates = self._load_templates()

        # Normalize inputs
        equipment_type = equipment_type.lower()
        service_type = service_type.lower()

        # Get equipment templates
        equipment_templates = templates.get(equipment_type)
        if not equipment_templates:
            return None

        # Get service-specific template
        template = equipment_templates.get(service_type)
        if not template:
            # Fallback to minor service if major not defined
            if service_type == "major":
                template = equipment_templates.get("minor")

        return template

    def get_next_prompt(self, equipment_type: str, service_type: str, collected_items: list) -> Optional[str]:
        """Get the next prompt for data collection.

        Args:
            equipment_type: Equipment type
            service_type: Service type
            collected_items: List of already collected items

        Returns:
            Next prompt string, or None if all items collected
        """
        template = self.get_template(equipment_type, service_type)
        if not template:
            return None

        # Find first required item not yet collected
        for item in template.get("required", []):
            if item not in collected_items:
                return template.get("prompts", {}).get(item)

        # All required items collected, check optional items
        for item in template.get("optional", []):
            if item not in collected_items:
                return template.get("prompts", {}).get(item)

        return None

    def get_missing_items(self, equipment_type: str, service_type: str, collected_items: list) -> list:
        """Get list of missing required items.

        Args:
            equipment_type: Equipment type
            service_type: Service type
            collected_items: List of already collected items

        Returns:
            List of missing required item keys
        """
        template = self.get_template(equipment_type, service_type)
        if not template:
            return []

        missing = []
        for item in template.get("required", []):
            if item not in collected_items:
                missing.append(item)

        return missing

    def validate_collected_items(self, equipment_type: str, service_type: str, collected_items: list) -> Dict[str, Any]:
        """Validate collected items against template.

        Args:
            equipment_type: Equipment type
            service_type: Service type
            collected_items: List of collected items

        Returns:
            Validation result with status, missing items, and progress
        """
        template = self.get_template(equipment_type, service_type)
        if not template:
            return {
                "is_complete": False,
                "missing_items": [],
                "progress": "0/0",
                "error": "Template not found"
            }

        required_items = template.get("required", [])
        missing_items = [item for item in required_items if item not in collected_items]

        is_complete = len(missing_items) == 0
        progress = f"{len(collected_items)}/{len(required_items)}"

        return {
            "is_complete": is_complete,
            "missing_items": missing_items,
            "progress": progress,
            "completion_percentage": (len(collected_items) / len(required_items) * 100) if required_items else 0
        }

    def get_validation_rules(self, equipment_type: str, service_type: str) -> Dict[str, Any]:
        """Get validation rules for readings.

        Args:
            equipment_type: Equipment type
            service_type: Service type

        Returns:
            Dictionary of validation rules by reading type
        """
        template = self.get_template(equipment_type, service_type)
        if not template:
            return {}

        return template.get("validation_rules", {})

    def get_audio_config(self, equipment_type: str, service_type: str) -> Optional[Dict[str, Any]]:
        """Get audio recording configuration.

        Args:
            equipment_type: Equipment type
            service_type: Service type

        Returns:
            Audio config with duration_seconds, or None if audio not required
        """
        template = self.get_template(equipment_type, service_type)
        if not template:
            return None

        config = {}
        if "audio_duration_seconds" in template:
            config["duration_seconds"] = template["audio_duration_seconds"]
        if "audio_recording" in template.get("required", []) or "audio_recording" in template.get("optional", []):
            config["required"] = "audio_recording" in template.get("required", [])
            return config

        return None

    def list_equipment_types(self) -> list:
        """List all supported equipment types."""
        templates = self._load_templates()
        return list(templates.keys())

    def list_service_types(self, equipment_type: str) -> list:
        """List service types for an equipment type."""
        templates = self._load_templates()
        equipment_templates = templates.get(equipment_type.lower())
        if not equipment_templates:
            return []
        return list(equipment_templates.keys())

    def get_context_aware_prompt(
        self,
        equipment_type: str,
        service_type: str,
        diagnostic_context: Optional[Dict[str, Any]],
        collected_items: List[str],
        current_step: str
    ) -> Dict[str, Any]:
        """Generate context-aware prompt based on diagnostic context.

        Instead of asking open-ended questions, uses the known fault
        information to ask targeted confirmation questions.

        Args:
            equipment_type: Equipment type (fcu, vav, etc.)
            service_type: Service type (breakdown, minor, etc.)
            diagnostic_context: Original alert/diagnosis context
            collected_items: Already collected items
            current_step: Current data collection step

        Returns:
            Dict with prompt text, options (if applicable), and type
        """
        # If no diagnostic context, fall back to standard prompts
        if not diagnostic_context:
            standard_prompt = self.get_next_prompt(equipment_type, service_type, collected_items)
            return {
                "prompt": standard_prompt,
                "type": "open_text",
                "options": None
            }

        fault_type = diagnostic_context.get("fault_type", "")
        fault_description = diagnostic_context.get("fault_description", "")
        faulty_equipment = diagnostic_context.get("faulty_equipment", "")
        original_reading = diagnostic_context.get("original_reading")
        setpoint = diagnostic_context.get("setpoint")
        zone_id = diagnostic_context.get("zone_id", "")

        # Step 1: Confirm the detected fault
        if current_step == "fault_confirmation":
            return {
                "prompt": f"{faulty_equipment} repair complete - thanks!\n\nWe detected: {fault_description}\n\nDid you confirm this was the issue?",
                "type": "choice",
                "options": ["Yes, confirmed", "No, different issue", "Partially - multiple issues"]
            }

        # Step 2: Root cause selection (context-aware options)
        if current_step == "root_cause":
            options = ROOT_CAUSE_OPTIONS.get(equipment_type, {}).get(fault_type, [])
            if not options:
                # Generic options if no specific ones defined
                options = [
                    "Mechanical failure",
                    "Electrical failure",
                    "Control/signal issue",
                    "Wear and tear",
                    "Environmental factors",
                    "Other"
                ]
            return {
                "prompt": "What was the root cause?",
                "type": "choice",
                "options": options
            }

        # Step 3: Repair action (pre-filled from recommendations)
        if current_step == "repair_action":
            recommended = diagnostic_context.get("recommended_actions", [])
            if recommended:
                options = recommended[:4]  # Max 4 options
                if "Other repair" not in options:
                    options.append("Other repair")
                return {
                    "prompt": "What repair did you perform?",
                    "type": "choice",
                    "options": options
                }
            return {
                "prompt": "What repair did you perform?",
                "type": "open_text",
                "options": None
            }

        # Step 4: Parts replaced (suggest from parts_required)
        if current_step == "parts_replaced":
            parts = diagnostic_context.get("parts_required", [])
            if parts:
                return {
                    "prompt": f"Parts suggested: {', '.join(parts)}\n\nPhoto of replacement part label?",
                    "type": "photo",
                    "options": None
                }
            return {
                "prompt": "Photo of replacement part label?",
                "type": "photo",
                "options": None
            }

        # Step 5: Verification reading (compare to original)
        if current_step == "verification_reading":
            if original_reading and setpoint:
                return {
                    "prompt": f"Zone temp now? (was {original_reading}°C, setpoint {setpoint}°C)",
                    "type": "numeric",
                    "options": None,
                    "validation": {"min": 15, "max": 35, "unit": "°C"}
                }
            return {
                "prompt": "Current reading after repair?",
                "type": "numeric",
                "options": None
            }

        # Default: fall back to standard prompt
        standard_prompt = self.get_next_prompt(equipment_type, service_type, collected_items)
        return {
            "prompt": standard_prompt,
            "type": "open_text",
            "options": None
        }

    def get_breakdown_flow(self, equipment_type: str, diagnostic_context: Optional[Dict[str, Any]]) -> List[str]:
        """Get the ordered flow of steps for breakdown data collection.

        Args:
            equipment_type: Equipment type
            diagnostic_context: Original diagnostic context

        Returns:
            List of step names in order
        """
        # If we have diagnostic context, use context-aware flow
        if diagnostic_context and diagnostic_context.get("fault_type"):
            return [
                "fault_confirmation",  # Confirm detected fault
                "root_cause",          # Select root cause from options
                "repair_action",       # What was done
                "parts_replaced",      # Photo of parts
                "verification_reading" # Confirm repair worked
            ]

        # Otherwise use standard breakdown flow
        return [
            "fault_description",
            "root_cause",
            "diagnostic_steps",
            "repair_action",
            "parts_replaced"
        ]

    def extract_info_from_response(
        self,
        equipment_type: str,
        diagnostic_context: Optional[Dict[str, Any]],
        response_text: str
    ) -> Dict[str, Any]:
        """Extract structured information from a free-form technician response.

        If technician provides comprehensive info in one message, extract all
        relevant fields and skip steps that are already answered.

        Args:
            equipment_type: Equipment type
            diagnostic_context: Original diagnostic context
            response_text: Technician's response text

        Returns:
            Dict with extracted fields and remaining steps
        """
        import re

        extracted = {}
        response_lower = response_text.lower()

        # Check for fault confirmation
        confirmation_positive = ["yes", "confirmed", "correct", "that's right", "exactly"]
        confirmation_negative = ["no", "different", "wrong", "not that"]

        if any(word in response_lower for word in confirmation_positive):
            extracted["fault_confirmation"] = "confirmed"
        elif any(word in response_lower for word in confirmation_negative):
            extracted["fault_confirmation"] = "different"

        # Check for root cause mentions
        fault_type = diagnostic_context.get("fault_type", "") if diagnostic_context else ""
        root_cause_options = ROOT_CAUSE_OPTIONS.get(equipment_type, {}).get(fault_type, [])

        for option in root_cause_options:
            # Check if any key words from the option appear in response
            option_words = option.lower().split()
            if any(word in response_lower for word in option_words if len(word) > 3):
                extracted["root_cause"] = option
                break

        # Check for repair actions
        repair_keywords = {
            "replaced": "Replaced component",
            "fixed": "Repaired in place",
            "adjusted": "Adjusted settings",
            "cleaned": "Cleaned component",
            "reset": "Reset/restarted",
            "rewired": "Rewired connections"
        }
        for keyword, action in repair_keywords.items():
            if keyword in response_lower:
                extracted["repair_action"] = action
                break

        # Extract part numbers/models
        part_patterns = [
            r"belimo\s+[\w-]+",
            r"siemens\s+[\w-]+",
            r"honeywell\s+[\w-]+",
            r"trane\s+[\w-]+",
            r"carrier\s+[\w-]+",
            r"[A-Z]{2,4}[-\s]?\d{2,4}[-\s]?\w*",  # Generic model pattern
        ]
        for pattern in part_patterns:
            match = re.search(pattern, response_text, re.IGNORECASE)
            if match:
                extracted["parts_info"] = match.group(0)
                break

        # Extract temperature readings
        temp_pattern = r"(\d{1,2}(?:\.\d)?)\s*(?:°|degrees?|deg|c\b)"
        temp_matches = re.findall(temp_pattern, response_lower)
        if temp_matches:
            # Take the last temperature mentioned (likely the current reading)
            extracted["verification_reading"] = float(temp_matches[-1])

        # Determine which steps are still needed
        flow = self.get_breakdown_flow(equipment_type, diagnostic_context)
        completed_steps = []

        step_field_map = {
            "fault_confirmation": "fault_confirmation",
            "root_cause": "root_cause",
            "repair_action": "repair_action",
            "verification_reading": "verification_reading"
        }

        for step, field in step_field_map.items():
            if field in extracted:
                completed_steps.append(step)

        # Parts always needs photo - text mention isn't enough
        remaining_steps = [s for s in flow if s not in completed_steps]

        # If parts were mentioned in text, still need photo but acknowledge the info
        if "parts_info" in extracted and "parts_replaced" in remaining_steps:
            extracted["parts_mentioned"] = extracted["parts_info"]

        return {
            "extracted": extracted,
            "completed_steps": completed_steps,
            "remaining_steps": remaining_steps,
            "needs_photo": "parts_replaced" in remaining_steps,
            "all_text_complete": len([s for s in remaining_steps if s != "parts_replaced"]) == 0
        }
