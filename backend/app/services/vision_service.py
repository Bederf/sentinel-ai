"""
Vision Service - AI-powered image analysis for equipment identification.

Uses Claude's multimodal vision capabilities to:
- Identify equipment components from photos
- Read model/serial plates (OCR)
- Assess visible damage or wear
- Extract fault codes from error displays
"""

import base64
import logging
from dataclasses import dataclass

import anthropic

from app.config.settings import settings
from app.services.ai_usage_tracker import usage_tracker

logger = logging.getLogger(__name__)


@dataclass
class IdentifiedComponent:
    """A component identified in an image."""

    name: str
    manufacturer: str | None = None
    model: str | None = None
    condition: str | None = None
    confidence: float = 0.0


@dataclass
class DetectedIssue:
    """An issue detected in equipment image."""

    type: str
    severity: str  # low, medium, high, critical
    location: str | None = None
    recommendation: str | None = None


@dataclass
class ModelPlateInfo:
    """Information extracted from equipment model plate."""

    manufacturer: str | None = None
    model: str | None = None
    serial: str | None = None
    year: str | None = None
    refrigerant: str | None = None
    capacity: str | None = None
    voltage: str | None = None
    raw_text: str | None = None


class VisionService:
    """AI vision service using Claude multimodal capabilities."""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.claude_model

    def _encode_image(self, image_data: bytes) -> str:
        """Encode image bytes to base64."""
        return base64.b64encode(image_data).decode("utf-8")

    def _create_vision_message(self, image_data: bytes, media_type: str, prompt: str) -> str:
        """Send image to Claude and get response."""
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=1500,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": self._encode_image(image_data),
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )
            try:
                u = message.usage
                usage_tracker.record(
                    provider="anthropic",
                    model=self.model,
                    input_tokens=getattr(u, "input_tokens", 0),
                    output_tokens=getattr(u, "output_tokens", 0),
                    source="vision_analysis",
                )
            except Exception:
                pass  # Never break vision for tracking
            return message.content[0].text
        except Exception as e:
            logger.error(f"Vision API error: {e}")
            raise

    def analyze_image(self, image_data: bytes, media_type: str = "image/jpeg", prompt: str | None = None) -> dict:
        """
        General image analysis.

        Args:
            image_data: Raw image bytes
            media_type: MIME type (image/jpeg, image/png, etc.)
            prompt: Custom analysis prompt

        Returns:
            Analysis result with text description
        """
        default_prompt = """Analyze this HVAC/building equipment image.
Describe what you see, identify any components, and note any visible issues.
Be specific about manufacturers, models, and conditions if visible."""

        analysis = self._create_vision_message(image_data, media_type, prompt or default_prompt)

        return {"analysis": analysis, "success": True}

    def identify_component(self, image_data: bytes, media_type: str = "image/jpeg", context: str | None = None) -> dict:
        """
        Identify equipment component from image.

        Args:
            image_data: Raw image bytes
            media_type: MIME type
            context: Optional context (e.g., "chiller room", "AHU")

        Returns:
            Identified components with confidence
        """
        context_str = f" Context: {context}." if context else ""
        prompt = f"""Identify the HVAC/building equipment component in this image.{context_str}

Provide a JSON response with this structure:
{{
    "components": [
        {{
            "name": "component name",
            "manufacturer": "manufacturer if visible",
            "model": "model number if visible",
            "condition": "observed condition",
            "confidence": 0.0-1.0
        }}
    ],
    "equipment_type": "overall equipment type (chiller, AHU, VSD, etc.)",
    "notes": "any additional observations"
}}

Only output valid JSON, no markdown formatting."""

        response = self._create_vision_message(image_data, media_type, prompt)

        # Try to parse JSON response
        try:
            import json

            # Clean up response if needed
            clean_response = response.strip()
            if clean_response.startswith("```"):
                clean_response = clean_response.split("```")[1]
                if clean_response.startswith("json"):
                    clean_response = clean_response[4:]
            result = json.loads(clean_response)
            result["success"] = True
            return result
        except json.JSONDecodeError:
            # Return raw response if JSON parsing fails
            return {"success": True, "components": [], "notes": response, "parse_error": True}

    def read_model_plate(self, image_data: bytes, media_type: str = "image/jpeg") -> dict:
        """
        Extract information from equipment model/serial plate.

        Args:
            image_data: Raw image bytes
            media_type: MIME type

        Returns:
            Extracted plate information (manufacturer, model, serial, etc.)
        """
        prompt = """This image shows an equipment model plate or nameplate.
Extract all visible information and provide a JSON response:

{
    "manufacturer": "brand/manufacturer name",
    "model": "model number",
    "serial": "serial number",
    "year": "manufacture year if visible",
    "refrigerant": "refrigerant type if visible",
    "capacity": "cooling/heating capacity if visible",
    "voltage": "electrical specifications if visible",
    "other_specs": {},
    "raw_text": "all text visible on the plate"
}

If any field is not visible, use null. Only output valid JSON, no markdown."""

        response = self._create_vision_message(image_data, media_type, prompt)

        # Try to parse JSON response
        try:
            import json

            clean_response = response.strip()
            if clean_response.startswith("```"):
                clean_response = clean_response.split("```")[1]
                if clean_response.startswith("json"):
                    clean_response = clean_response[4:]
            result = json.loads(clean_response)
            result["success"] = True
            return result
        except json.JSONDecodeError:
            return {"success": True, "raw_text": response, "parse_error": True}

    def diagnose_damage(
        self, image_data: bytes, media_type: str = "image/jpeg", equipment_context: str | None = None
    ) -> dict:
        """
        Assess visible damage or wear in equipment image.

        Args:
            image_data: Raw image bytes
            media_type: MIME type
            equipment_context: Context about the equipment

        Returns:
            Detected issues with severity and recommendations
        """
        context_str = f"Equipment context: {equipment_context}\n\n" if equipment_context else ""
        prompt = f"""{context_str}Analyze this HVAC/building equipment image for visible damage, wear, or issues.

Provide a JSON response:
{{
    "overall_condition": "good/fair/poor/critical",
    "issues": [
        {{
            "type": "issue type (leak, corrosion, damage, wear, etc.)",
            "severity": "low/medium/high/critical",
            "location": "where on the equipment",
            "description": "detailed description",
            "recommendation": "suggested action"
        }}
    ],
    "maintenance_priority": "immediate/soon/routine/none",
    "notes": "additional observations"
}}

If no issues are visible, return an empty issues array. Only output valid JSON."""

        response = self._create_vision_message(image_data, media_type, prompt)

        try:
            import json

            clean_response = response.strip()
            if clean_response.startswith("```"):
                clean_response = clean_response.split("```")[1]
                if clean_response.startswith("json"):
                    clean_response = clean_response[4:]
            result = json.loads(clean_response)
            result["success"] = True
            return result
        except json.JSONDecodeError:
            return {"success": True, "issues": [], "notes": response, "parse_error": True}

    def read_error_display(
        self, image_data: bytes, media_type: str = "image/jpeg", manufacturer: str | None = None
    ) -> dict:
        """
        Extract fault codes from equipment error display screen.

        Args:
            image_data: Raw image bytes
            media_type: MIME type
            manufacturer: Known manufacturer for context

        Returns:
            Extracted fault codes with interpretation
        """
        mfr_str = f"This is a {manufacturer} display. " if manufacturer else ""
        prompt = f"""{mfr_str}This image shows an equipment control panel or error display.
Extract any fault codes, error messages, or status indicators.

Provide a JSON response:
{{
    "fault_codes": ["list of fault codes visible"],
    "error_messages": ["any text error messages"],
    "status_indicators": {{
        "power": "on/off/unknown",
        "alarm": "active/inactive/unknown",
        "run_mode": "running/stopped/standby/unknown"
    }},
    "display_values": {{
        "temperature": "value if visible",
        "pressure": "value if visible",
        "other": "any other readings"
    }},
    "raw_text": "all text visible on display"
}}

Only output valid JSON, no markdown formatting."""

        response = self._create_vision_message(image_data, media_type, prompt)

        try:
            import json

            clean_response = response.strip()
            if clean_response.startswith("```"):
                clean_response = clean_response.split("```")[1]
                if clean_response.startswith("json"):
                    clean_response = clean_response[4:]
            result = json.loads(clean_response)
            result["success"] = True
            return result
        except json.JSONDecodeError:
            return {"success": True, "fault_codes": [], "raw_text": response, "parse_error": True}


# Singleton instance
_vision_service: VisionService | None = None


def get_vision_service() -> VisionService:
    """Get or create singleton VisionService instance."""
    global _vision_service
    if _vision_service is None:
        _vision_service = VisionService()
    return _vision_service
