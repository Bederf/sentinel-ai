"""
OCR Service for Service Sheet Processing (Phase 41-02)

Implements a 3-stage OCR pipeline for service sheet photos:
1. Stage 1: Claude Vision OCR extraction
2. Stage 2: Template validation against equipment-specific rules
3. Stage 3: AI enhancement and correction flow

Pattern reference: /opt/aimthelaw/backendv2/app/services/receipt_service.py
"""

import base64
import gc
import json
import logging
import re
from typing import Any

import anthropic

from app.config.settings import settings
from app.database.repositories.equipment_repository import EquipmentRepository
from app.services.ai_usage_tracker import usage_tracker

logger = logging.getLogger(__name__)


class OCRService:
    """
    3-stage OCR pipeline for service sheet photos.

    Stage 1: Claude Vision extraction
    Stage 2: Template validation
    Stage 3: AI enhancement + corrections

    Pattern from: /opt/aimthelaw/backendv2/app/services/receipt_service.py
    """

    def __init__(self):
        self.client = anthropic.Anthropic()
        self.equipment_repo = EquipmentRepository()
        self._currently_processing: set[str] = set()

    async def process_service_sheet(
        self,
        image_data: bytes,
        equipment_id: str,
        service_type: str,
        service_record_id: str,
        media_type: str = "image/jpeg",
    ) -> dict[str, Any]:
        """
        Main entry point - runs full 3-stage pipeline.

        Args:
            image_data: Raw image bytes
            equipment_id: Equipment identifier
            service_type: Type of service (minor, major, breakdown)
            service_record_id: Unique service record ID
            media_type: Image MIME type

        Returns:
            {
                "status": "completed" | "needs_review" | "failed",
                "extracted_data": {...},
                "validated_data": {...},
                "pipeline_info": {
                    "stage1_confidence": 0.85,
                    "stage2_validation_score": 0.9,
                    "stage3_enhanced": True,
                    "issues": [...]
                }
            }
        """
        # Prevent duplicate processing
        if service_record_id in self._currently_processing:
            logger.warning(f"Service sheet {service_record_id} already processing")
            return {"status": "processing", "message": "Already being processed"}

        self._currently_processing.add(service_record_id)

        try:
            # Stage 1: OCR extraction
            stage1_result = await self._stage1_ocr_extraction(image_data, equipment_id, service_type, media_type)

            if not stage1_result.get("success"):
                return {
                    "status": "failed",
                    "error": stage1_result.get("error", "OCR extraction failed"),
                    "pipeline_info": {"stage1_confidence": 0.0},
                }

            # Stage 2: Template validation
            stage2_result = await self._stage2_template_validation(stage1_result["data"], equipment_id, service_type)

            # Stage 3: AI enhancement (fill gaps, handle corrections)
            stage3_result = await self._stage3_ai_enhancement(stage2_result, equipment_id, service_type)

            # Determine final status
            final_status = self._determine_final_status(
                stage1_result.get("confidence", 0),
                stage2_result.get("validation_score", 0),
                stage2_result.get("issues", []),
            )

            return {
                "status": final_status,
                "extracted_data": stage1_result["data"],
                "validated_data": stage3_result.get("final_data", stage2_result["data"]),
                "pipeline_info": {
                    "stage1_confidence": stage1_result.get("confidence", 0),
                    "stage2_validation_score": stage2_result.get("validation_score", 0),
                    "stage3_enhanced": stage3_result.get("enhanced", False),
                    "issues": stage2_result.get("issues", []),
                },
            }

        except Exception as e:
            logger.error(f"OCR pipeline error: {e}", exc_info=True)
            return {"status": "failed", "error": str(e)}
        finally:
            self._currently_processing.discard(service_record_id)
            gc.collect()  # Memory cleanup after processing

    async def _stage1_ocr_extraction(
        self, image_data: bytes, equipment_id: str, service_type: str, media_type: str
    ) -> dict[str, Any]:
        """Stage 1: Extract structured data from service sheet using Claude Vision."""
        logger.info(f"Stage 1: Starting OCR extraction for equipment {equipment_id}")

        try:
            # Get equipment context for better prompting
            equipment = self.equipment_repo.get_by_id(equipment_id)
            equipment_type = equipment.get("type", "unknown") if equipment else "unknown"
            equipment_name = equipment.get("name", equipment_id) if equipment else equipment_id

            prompt = f"""Analyze this equipment service worksheet image.

Equipment Type: {equipment_type}
Asset Name: {equipment_name}
Service Type: {service_type}

Extract ALL fields you can find and return as JSON with this structure:
{{
    "equipment_code": "string (from form header)",
    "service_date": "YYYY-MM-DD",
    "technician": "string",
    "hour_meter": number,
    "readings": {{
        "field_name": {{"value": number_or_string, "unit": "string", "confidence": 0.0-1.0}},
        ...
    }},
    "checklists": {{
        "item_name": {{"checked": true/false, "value": "good/low/critical", "confidence": 0.0-1.0}},
        ...
    }},
    "samples": [
        {{"type": "oil/diesel/coolant", "taken": true/false, "sample_id": "string"}},
        ...
    ],
    "notes": "any observations or comments",
    "overall_confidence": 0.0-1.0
}}

Be thorough - extract every reading, checkbox, and note visible on the form.
For confidence scores: 1.0 = clearly legible, 0.5 = partially readable, 0.0 = guessed/unclear."""

            # Encode image to base64
            image_b64 = base64.b64encode(image_data).decode()

            response = self.client.messages.create(
                model=settings.claude_model,
                max_tokens=4000,
                temperature=0.1,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image",
                                "source": {"type": "base64", "media_type": media_type, "data": image_b64},
                            },
                        ],
                    }
                ],
            )

            try:
                u = response.usage
                usage_tracker.record(
                    provider="anthropic",
                    model=settings.claude_model,
                    input_tokens=getattr(u, "input_tokens", 0),
                    output_tokens=getattr(u, "output_tokens", 0),
                    source="ocr_extraction",
                )
            except Exception:
                pass  # Never break OCR for tracking

            # Parse JSON response
            response_text = response.content[0].text

            # Try to extract JSON from response (may be wrapped in markdown)
            json_match = re.search(r"\{[\s\S]*\}", response_text)
            if json_match:
                data = json.loads(json_match.group())
                confidence = data.get("overall_confidence", 0.7)
                logger.info(f"Stage 1 complete: confidence={confidence:.2f}")
                return {"success": True, "data": data, "confidence": confidence}
            else:
                logger.warning("Could not parse JSON from Claude response")
                return {"success": False, "error": "Invalid response format"}

        except json.JSONDecodeError as e:
            logger.error(f"Stage 1 JSON parse error: {e}")
            return {"success": False, "error": f"JSON parse error: {e!s}"}
        except Exception as e:
            logger.error(f"Stage 1 OCR failed: {e}")
            return {"success": False, "error": str(e)}

    async def _stage2_template_validation(
        self, extracted_data: dict[str, Any], equipment_id: str, service_type: str
    ) -> dict[str, Any]:
        """Stage 2: Validate extracted data against equipment template."""
        logger.info(f"Stage 2: Validating against template for {equipment_id}")

        from app.services.ml_template_service import MLTemplateService

        template_service = MLTemplateService()

        # Get equipment type
        equipment = self.equipment_repo.get_by_id(equipment_id)
        equipment_type = equipment.get("type", "generator") if equipment else "generator"

        # Load template for this equipment + service type
        template = template_service.get_template(equipment_type, service_type)

        if not template:
            logger.warning(f"No template for {equipment_type}/{service_type}")
            return {
                "data": extracted_data,
                "validation_score": 0.5,
                "issues": [{"field": "_template", "message": "No template found", "severity": "warning"}],
            }

        validated_data = {}
        issues = []

        # Get validation rules from template
        validation_rules = template.get("validation_rules", {})

        # Validate readings from extracted data
        for rule_name, rule in validation_rules.items():
            value = self._find_extracted_value(extracted_data, rule_name)
            confidence = self._find_confidence(extracted_data, rule_name)

            if value is None and rule.get("required", False):
                issues.append(
                    {"field": rule_name, "message": f"Missing required field: {rule_name}", "severity": "error"}
                )
            elif value is not None:
                # Type coercion and validation
                try:
                    coerced = self._coerce_type(value, "number", rule)
                    validated_data[rule_name] = {
                        "value": coerced,
                        "confidence": confidence,
                        "unit": rule.get("unit", ""),
                        "valid": True,
                    }
                except ValueError as e:
                    issues.append({"field": rule_name, "message": str(e), "severity": "error", "raw_value": value})

        # Copy other extracted data that doesn't have validation rules
        for key in ["equipment_code", "service_date", "technician", "hour_meter", "notes"]:
            if key in extracted_data and key not in validated_data:
                validated_data[key] = extracted_data[key]

        # Copy checklists and samples
        if "checklists" in extracted_data:
            validated_data["checklists"] = extracted_data["checklists"]
        if "samples" in extracted_data:
            validated_data["samples"] = extracted_data["samples"]

        # Calculate validation score
        total_rules = len(validation_rules)
        error_count = len([i for i in issues if i["severity"] == "error"])
        validation_score = max(0.0, 1.0 - (error_count / max(total_rules, 1)))

        logger.info(f"Stage 2 complete: score={validation_score:.2f}, {len(issues)} issues")

        return {
            "data": validated_data,
            "validation_score": validation_score,
            "issues": issues,
            "template_used": f"{equipment_type}/{service_type}",
        }

    def _find_extracted_value(self, data: dict[str, Any], field_name: str) -> Any:
        """Find a value in extracted data by field name."""
        # Check top-level
        if field_name in data:
            return data[field_name]

        # Check readings
        readings = data.get("readings", {})
        if field_name in readings:
            reading = readings[field_name]
            if isinstance(reading, dict):
                return reading.get("value")
            return reading

        # Check checklists
        checklists = data.get("checklists", {})
        if field_name in checklists:
            checklist = checklists[field_name]
            if isinstance(checklist, dict):
                return checklist.get("value") or checklist.get("checked")
            return checklist

        return None

    def _find_confidence(self, data: dict[str, Any], field_name: str) -> float:
        """Find confidence score for a field."""
        # Check readings
        readings = data.get("readings", {})
        if field_name in readings:
            reading = readings[field_name]
            if isinstance(reading, dict):
                return reading.get("confidence", 0.7)

        # Check checklists
        checklists = data.get("checklists", {})
        if field_name in checklists:
            checklist = checklists[field_name]
            if isinstance(checklist, dict):
                return checklist.get("confidence", 0.7)

        return 0.7  # Default confidence

    def _coerce_type(self, value: Any, target_type: str, validation: dict) -> Any:
        """Coerce extracted value to target type with validation."""
        if target_type == "number":
            # Extract numeric value
            if isinstance(value, (int, float)):
                num = float(value)
            else:
                cleaned = re.sub(r"[^0-9.\-]", "", str(value))
                num = float(cleaned) if cleaned else 0.0

            # Range validation
            if "min" in validation and num < validation["min"]:
                raise ValueError(f"Value {num} below minimum {validation['min']}")
            if "max" in validation and num > validation["max"]:
                raise ValueError(f"Value {num} above maximum {validation['max']}")

            return num

        elif target_type == "boolean":
            if isinstance(value, bool):
                return value
            value_str = str(value).lower()
            return value_str in ["yes", "true", "checked", "good", "ok", "pass", "1", "x"]

        elif target_type == "enum":
            valid_values = validation.get("values", [])
            value_lower = str(value).lower()
            for v in valid_values:
                if v.lower() == value_lower:
                    return v
            # Fuzzy match
            for v in valid_values:
                if v.lower() in value_lower or value_lower in v.lower():
                    return v
            raise ValueError(f"Value '{value}' not in allowed values: {valid_values}")

        return str(value)  # Default to string

    async def _stage3_ai_enhancement(
        self, stage2_result: dict[str, Any], equipment_id: str, service_type: str
    ) -> dict[str, Any]:
        """Stage 3: AI enhancement to fill gaps and suggest corrections."""
        logger.info("Stage 3: Starting AI enhancement")

        issues = stage2_result.get("issues", [])

        # If no issues, return Stage 2 data as-is
        if not issues:
            return {"final_data": stage2_result["data"], "enhanced": False, "corrections_needed": []}

        try:
            # Build context for AI to fill gaps
            error_fields = [i["field"] for i in issues if i["severity"] == "error"]

            # AI can try to infer missing values from context
            enhanced_data = stage2_result["data"].copy()

            for field in error_fields:
                # Check if raw value exists but failed validation
                raw = next((i.get("raw_value") for i in issues if i["field"] == field), None)
                if raw:
                    # Store raw value with low confidence for manual review
                    enhanced_data[field] = {
                        "value": raw,
                        "confidence": 0.3,  # Low confidence for AI-corrected
                        "needs_verification": True,
                    }

            return {"final_data": enhanced_data, "enhanced": True, "corrections_needed": error_fields}

        except Exception as e:
            logger.warning(f"Stage 3 enhancement failed: {e}, using Stage 2 data")
            return {
                "final_data": stage2_result["data"],
                "enhanced": False,
                "corrections_needed": [i["field"] for i in issues if i["severity"] == "error"],
            }

    def _determine_final_status(self, ocr_confidence: float, validation_score: float, issues: list[dict]) -> str:
        """Determine final status based on pipeline results."""
        error_count = len([i for i in issues if i["severity"] == "error"])

        if error_count > 0 or validation_score < 0.7 or ocr_confidence < 0.6:
            return "needs_review"
        else:
            return "completed"


# Singleton instance
_ocr_service: OCRService | None = None


def get_ocr_service() -> OCRService:
    """Get singleton OCR service instance."""
    global _ocr_service
    if _ocr_service is None:
        _ocr_service = OCRService()
    return _ocr_service
