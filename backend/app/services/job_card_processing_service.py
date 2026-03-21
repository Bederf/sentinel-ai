"""Job Card & Service Sheet Processing Orchestrator.

Orchestrates the full pipeline for document photo processing:
1. Classify document type (job card, service sheet, compliance cert)
2. Preprocess image (deskew, denoise, contrast)
3. Extract structured fields via Claude Vision
4. Flatten to text for RAG embedding
5. Link to equipment
6. Store OCR audit trail

Reuses existing OCRService for service sheets; adds job_card and
compliance_certificate extraction templates.
"""

import base64
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.services.model_gateway import model_gateway

logger = logging.getLogger(__name__)

# Document type templates — extraction prompts
EXTRACTION_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "job_card": {
        "fields": [
            "job_number",
            "equipment_code",
            "fault_description",
            "action_taken",
            "parts_used",
            "technician_name",
            "service_date",
            "sign_off",
            "time_on_site",
            "next_action",
        ],
        "prompt": """Analyze this job card / work order photo.

Extract ALL fields visible on the document and return as JSON:
{{
    "job_number": "string (job/WO reference number)",
    "equipment_code": "string (equipment identifier, asset tag, or serial number)",
    "fault_description": "string (reported fault or reason for call-out)",
    "action_taken": "string (what the technician did)",
    "parts_used": ["list of parts/materials used"],
    "technician_name": "string",
    "service_date": "YYYY-MM-DD (date of service)",
    "sign_off": "string (customer/manager signature name if visible)",
    "time_on_site": "string (hours or time range)",
    "next_action": "string (follow-up required, if any)",
    "notes": "string (any additional observations)",
    "overall_confidence": 0.0-1.0
}}

Be thorough. For confidence: 1.0 = clearly legible, 0.5 = partially readable, 0.0 = guessed.""",
    },
    "compliance_certificate": {
        "fields": [
            "certificate_number",
            "equipment_code",
            "inspection_date",
            "expiry_date",
            "inspector_name",
            "compliance_standard",
            "result",
        ],
        "prompt": """Analyze this compliance certificate / inspection report photo.

Extract ALL fields visible and return as JSON:
{{
    "certificate_number": "string",
    "equipment_code": "string (equipment/asset identifier)",
    "inspection_date": "YYYY-MM-DD",
    "expiry_date": "YYYY-MM-DD (if shown)",
    "inspector_name": "string",
    "compliance_standard": "string (e.g. SANS 10142, NFPA 72, etc.)",
    "result": "pass/fail/conditional",
    "issuing_authority": "string (if shown)",
    "notes": "string (conditions, observations)",
    "overall_confidence": 0.0-1.0
}}

Be thorough. For confidence: 1.0 = clearly legible, 0.5 = partially readable, 0.0 = guessed.""",
    },
    "service_sheet": {
        "fields": [
            "equipment_code",
            "service_date",
            "technician",
            "readings",
            "checklists",
            "notes",
        ],
        "prompt": """Analyze this equipment service sheet photo.

Extract ALL fields visible and return as JSON:
{{
    "equipment_code": "string",
    "service_date": "YYYY-MM-DD",
    "technician": "string",
    "readings": {{"field_name": {{"value": "number_or_string", "unit": "string"}}}},
    "checklists": {{"item_name": {{"checked": true/false, "value": "string"}}}},
    "notes": "string (observations or comments)",
    "overall_confidence": 0.0-1.0
}}

Be thorough. For confidence: 1.0 = clearly legible, 0.5 = partially readable, 0.0 = guessed.""",
    },
}


@dataclass
class ProcessingResult:
    """Result of document processing pipeline."""

    status: str  # completed, needs_review, failed
    document_type: str
    extracted_data: Dict[str, Any] = field(default_factory=dict)
    extracted_text: str = ""
    confidence: float = 0.0
    preprocessing_metadata: Dict[str, Any] = field(default_factory=dict)
    equipment_codes: List[str] = field(default_factory=list)
    error: Optional[str] = None


class JobCardProcessingService:
    """Orchestrates photo → OCR → structured data → RAG text pipeline."""

    def __init__(self):
        pass  # Provider selection handled by model_gateway

    async def process_document(
        self,
        image_data: bytes,
        media_type: str,
        site_id: str,
        document_type: str = "auto",
        work_order_id: Optional[str] = None,
        equipment_id: Optional[str] = None,
    ) -> ProcessingResult:
        """Process a document image through the full pipeline.

        Args:
            image_data: Raw image bytes
            media_type: MIME type (image/jpeg, image/png)
            site_id: Site identifier
            document_type: "job_card", "service_sheet", "compliance_certificate", or "auto"
            work_order_id: Optional WO to link to
            equipment_id: Optional equipment code to associate

        Returns:
            ProcessingResult with extracted data and text
        """
        try:
            # Step 1: Preprocess image
            from app.services.image_preprocessing_service import get_image_preprocessor

            preprocessor = get_image_preprocessor()
            processed_image, preprocess_meta = preprocessor.preprocess(image_data, media_type)

            # Step 2: Auto-classify if needed
            if document_type == "auto":
                document_type = await self._classify_document_type(processed_image, media_type)
                logger.info("Auto-classified document as: %s", document_type)

            # Step 3: Extract structured fields
            extracted_data, confidence = await self._extract_fields(
                processed_image, media_type, document_type, equipment_id
            )

            if not extracted_data:
                return ProcessingResult(
                    status="failed",
                    document_type=document_type,
                    error="No data extracted from image",
                    preprocessing_metadata=preprocess_meta,
                )

            # Step 4: Flatten to text for RAG
            extracted_text = self._flatten_to_text(extracted_data, document_type)

            # Step 5: Collect equipment codes from extraction
            equipment_codes = []
            eq_code = extracted_data.get("equipment_code", "")
            if eq_code:
                equipment_codes.append(eq_code)

            # Determine status based on confidence
            status = "completed" if confidence >= 0.6 else "needs_review"

            return ProcessingResult(
                status=status,
                document_type=document_type,
                extracted_data=extracted_data,
                extracted_text=extracted_text,
                confidence=confidence,
                preprocessing_metadata=preprocess_meta,
                equipment_codes=equipment_codes,
            )

        except Exception as e:
            logger.error("Document processing failed: %s", e, exc_info=True)
            return ProcessingResult(
                status="failed",
                document_type=document_type,
                error=str(e),
            )

    async def _classify_document_type(self, image_data: bytes, media_type: str) -> str:
        """Classify document type using Vision API via model_gateway."""
        try:
            image_b64 = base64.b64encode(image_data).decode()
            result_text = await model_gateway.call(
                task_class="light",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "What type of document is this? Reply with EXACTLY one of: "
                                    "job_card, service_sheet, compliance_certificate, general_document"
                                ),
                            },
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_b64,
                                },
                            },
                        ],
                    }
                ],
                max_tokens=100,
            )
            result = result_text.strip().lower()
            # Normalize response
            for valid_type in ["job_card", "service_sheet", "compliance_certificate"]:
                if valid_type in result:
                    return valid_type
            return "job_card"  # Default
        except Exception as e:
            logger.warning("Document classification failed: %s, defaulting to job_card", e)
            return "job_card"

    async def _extract_fields(
        self,
        image_data: bytes,
        media_type: str,
        document_type: str,
        equipment_context: Optional[str] = None,
    ) -> tuple[Dict[str, Any], float]:
        """Extract structured fields using Claude Vision with type-specific template."""
        template = EXTRACTION_TEMPLATES.get(document_type, EXTRACTION_TEMPLATES["job_card"])
        prompt = template["prompt"]

        if equipment_context:
            prompt = f"Equipment context: {equipment_context}\n\n{prompt}"

        try:
            image_b64 = base64.b64encode(image_data).decode()
            response_text = await model_gateway.call(
                task_class="light",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_b64,
                                },
                            },
                        ],
                    }
                ],
                max_tokens=4000,
            )
            json_match = re.search(r"\{[\s\S]*\}", response_text)
            if json_match:
                data = json.loads(json_match.group())
                confidence = data.pop("overall_confidence", 0.7)
                return data, float(confidence)

            logger.warning("Could not parse JSON from extraction response")
            return {}, 0.0

        except json.JSONDecodeError as e:
            logger.error("JSON parse error during extraction: %s", e)
            return {}, 0.0
        except Exception as e:
            logger.error("Field extraction failed: %s", e)
            return {}, 0.0

    def _flatten_to_text(self, extracted_data: Dict[str, Any], document_type: str) -> str:
        """Convert structured extracted data to readable prose for RAG embedding."""
        parts = []

        if document_type == "job_card":
            if extracted_data.get("job_number"):
                parts.append(f"Job Card {extracted_data['job_number']}.")
            if extracted_data.get("equipment_code"):
                parts.append(f"Equipment: {extracted_data['equipment_code']}.")
            if extracted_data.get("service_date"):
                parts.append(f"Date: {extracted_data['service_date']}.")
            if extracted_data.get("fault_description"):
                parts.append(f"Fault: {extracted_data['fault_description']}.")
            if extracted_data.get("action_taken"):
                parts.append(f"Action: {extracted_data['action_taken']}.")
            if extracted_data.get("parts_used"):
                parts_list = extracted_data["parts_used"]
                if isinstance(parts_list, list):
                    parts.append(f"Parts: {', '.join(str(p) for p in parts_list)}.")
                else:
                    parts.append(f"Parts: {parts_list}.")
            if extracted_data.get("technician_name"):
                parts.append(f"Technician: {extracted_data['technician_name']}.")
            if extracted_data.get("time_on_site"):
                parts.append(f"Time on site: {extracted_data['time_on_site']}.")
            if extracted_data.get("next_action"):
                parts.append(f"Follow-up: {extracted_data['next_action']}.")

        elif document_type == "compliance_certificate":
            if extracted_data.get("certificate_number"):
                parts.append(f"Compliance Certificate {extracted_data['certificate_number']}.")
            if extracted_data.get("equipment_code"):
                parts.append(f"Equipment: {extracted_data['equipment_code']}.")
            if extracted_data.get("inspection_date"):
                parts.append(f"Inspection date: {extracted_data['inspection_date']}.")
            if extracted_data.get("expiry_date"):
                parts.append(f"Expires: {extracted_data['expiry_date']}.")
            if extracted_data.get("compliance_standard"):
                parts.append(f"Standard: {extracted_data['compliance_standard']}.")
            if extracted_data.get("result"):
                parts.append(f"Result: {extracted_data['result']}.")
            if extracted_data.get("inspector_name"):
                parts.append(f"Inspector: {extracted_data['inspector_name']}.")

        elif document_type == "service_sheet":
            if extracted_data.get("equipment_code"):
                parts.append(f"Service Sheet for {extracted_data['equipment_code']}.")
            if extracted_data.get("service_date"):
                parts.append(f"Date: {extracted_data['service_date']}.")
            if extracted_data.get("technician"):
                parts.append(f"Technician: {extracted_data['technician']}.")
            readings = extracted_data.get("readings", {})
            if readings and isinstance(readings, dict):
                reading_parts = []
                for name, val in readings.items():
                    if isinstance(val, dict):
                        reading_parts.append(f"{name}: {val.get('value', '?')} {val.get('unit', '')}")
                    else:
                        reading_parts.append(f"{name}: {val}")
                if reading_parts:
                    parts.append(f"Readings: {'; '.join(reading_parts)}.")

        # Add notes for all types
        if extracted_data.get("notes"):
            parts.append(f"Notes: {extracted_data['notes']}.")

        return " ".join(parts)


# Singleton
_service: Optional[JobCardProcessingService] = None


def get_job_card_service() -> JobCardProcessingService:
    global _service
    if _service is None:
        _service = JobCardProcessingService()
    return _service
