"""LLM-based field extraction from OCR text.

Bridge between docling OCR (Phase 181-01) and AssetIDResolver (Phase 180).
Takes raw OCR text and extracts structured fields using model_gateway.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from app.services.model_gateway import model_gateway

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------------- #
# Prompt templates
# -------------------------------------------------------------------------- #

EXTRACTION_PROMPT_TEMPLATE: str = """Analyze this {document_type} text.

Extract the following fields and return as JSON:
{{
    "equipment_description": "string (what the equipment is, its location, type)",
    "equipment_code": "string (asset identifier, equipment tag, or null if not identifiable)",
    "document_date": "string (date in YYYY-MM-DD or null if not shown)",
    "technician_name": "string (name of technician or null)",
    "fault_description": "string (reported fault or reason for call-out)",
    "action_taken": "string (what was done)",
    "overall_confidence": 0.0-1.0 (1.0=clearly legible, 0.5=partial, 0.0=guessed)
}}

Be thorough and precise. For equipment_code, prefer canonical codes like S002-CHILLER-B1-001.
If equipment is not clearly identifiable, return null for equipment_code.
"""

EQUIPMENT_DESCRIPTION_PROMPT: str = """From the text below, extract ONLY the equipment description —
what the equipment is, its type, and its location within the building.

Return a JSON object:
{{
    "equipment_description": "string"
}}

If no equipment can be identified, return:
{{"equipment_description": ""}}"""


# -------------------------------------------------------------------------- #
# Result dataclass
# -------------------------------------------------------------------------- #


@dataclass
class LLMExtractionResult:
    """Structured result from LLM field extraction."""

    equipment_description: str | None = None
    equipment_code: str | None = None
    document_date: str | None = None
    technician_name: str | None = None
    fault_description: str | None = None
    action_taken: str | None = None
    confidence: float = 0.0
    extraction_method: str = "llm"  # llm | rule_based | failed
    raw_response: str = ""

    @classmethod
    def failed(cls, raw_response: str = "") -> LLMExtractionResult:
        """Return a failed extraction result (graceful degradation)."""
        return cls(
            confidence=0.0,
            extraction_method="failed",
            raw_response=raw_response,
        )


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #


class LLMExtractionService:
    """Extract structured fields from raw OCR text using LLM."""

    def __init__(self, db: Any, site_id: str) -> None:
        self.db = db
        self.site_id = site_id
        self._equipment_context: str | None = None

    # ---------------------------------------------------------------------- #
    # Helpers
    # ---------------------------------------------------------------------- #

    @staticmethod
    def _esc(s: str) -> str:
        """
        Escape Jinja2/template braces in user-supplied text to prevent
        format-string injection when text is embedded in a prompt.
        """
        return s.replace("{", "{{").replace("}", "}}")

    def _build_equipment_context(self) -> str:
        """Query equipment table for site and build context string."""
        if self._equipment_context is not None:
            return self._equipment_context

        try:
            rows = self.db.query(
                "SELECT code, type, location FROM equipment WHERE site_id = %s LIMIT 50",
                (self.site_id,),
            ).fetchall()
            if not rows:
                self._equipment_context = ""
                return self._equipment_context

            lines = []
            for r in rows:
                code = r.get("code") or ""
                eq_type = r.get("type") or ""
                loc = r.get("location") or ""
                lines.append(f"  - {code} ({eq_type}){f' — {loc}' if loc else ''}")
            self._equipment_context = "Available equipment at site:\n" + "\n".join(lines)
        except Exception:
            self._equipment_context = ""
        return self._equipment_context

    # ---------------------------------------------------------------------- #
    # Core extraction
    # ---------------------------------------------------------------------- #

    async def extract_fields(
        self,
        raw_text: str,
        document_type: str = "service_report",
        equipment_context: str | None = None,
        gateway: Any | None = None,
    ) -> LLMExtractionResult:
        """
        Extract structured fields from raw OCR text.

        Args:
            raw_text: The raw text extracted from the document (already OCR'd)
            document_type: Type hint for the document (job_card, service_sheet, etc.)
            equipment_context: Optional equipment list override (uses site list if None)
            gateway: Optional model gateway override

        Returns:
            LLMExtractionResult with extracted fields, confidence, and method.
            On failure: extraction_method="failed", confidence=0.0, never raises.
        """
        gw = gateway or model_gateway

        # Escape user-supplied fields to prevent JSON injection
        safe_text = self._esc(raw_text)
        safe_doc_type = self._esc(document_type)
        safe_eq_ctx = self._esc(equipment_context) if equipment_context else self._build_equipment_context()

        prompt = EXTRACTION_PROMPT_TEMPLATE.format(document_type=safe_doc_type)

        if safe_eq_ctx:
            prompt = f"{prompt}\n\n{safe_eq_ctx}"

        prompt = f"{prompt}\n\n--- Document Text ---\n{safe_text}"

        messages = [{"role": "user", "content": prompt}]

        try:
            response_text = await gw.call(
                task_class="medium",
                messages=messages,
            )
        except Exception as exc:
            logger.warning("LLM extraction gateway call failed: %s", exc)
            return LLMExtractionResult.failed()

        if not response_text or not isinstance(response_text, str):
            logger.warning("LLM extraction gateway returned empty response")
            return LLMExtractionResult.failed()

        try:
            fields = json.loads(response_text)
        except json.JSONDecodeError as exc:
            logger.warning("LLM extraction JSON parse failed: %s — raw: %r", exc, response_text[:500])
            return LLMExtractionResult.failed(raw_response=response_text)

        def _str(value: Any) -> str | None:
            if value is None:
                return None
            if isinstance(value, str) and value.strip():
                return value.strip()
            return None

        return LLMExtractionResult(
            equipment_description=_str(fields.get("equipment_description")),
            equipment_code=_str(fields.get("equipment_code")),
            document_date=_str(fields.get("document_date")),
            technician_name=_str(fields.get("technician_name")),
            fault_description=_str(fields.get("fault_description")),
            action_taken=_str(fields.get("action_taken")),
            confidence=float(fields.get("overall_confidence", 0.0)),
            extraction_method="llm",
            raw_response=response_text,
        )

    async def extract_equipment_description(
        self,
        raw_text: str,
        gateway: Any | None = None,
    ) -> str:
        """
        Extract only the equipment_description field from raw text.

        Simplified single-field extraction for the upload pipeline.
        Returns empty string if extraction fails or no equipment found.
        """
        gw = gateway or model_gateway

        safe_text = self._esc(raw_text)
        prompt = f"{EQUIPMENT_DESCRIPTION_PROMPT}\n\n--- Document Text ---\n{safe_text}"
        messages = [{"role": "user", "content": prompt}]

        try:
            response_text = await gw.call(
                task_class="medium",
                messages=messages,
            )
        except Exception as exc:
            logger.warning("Equipment description extraction failed: %s", exc)
            return ""

        if not response_text or not isinstance(response_text, str):
            return ""

        try:
            parsed = json.loads(response_text)
            desc = parsed.get("equipment_description", "")
            return desc.strip() if isinstance(desc, str) else ""
        except json.JSONDecodeError:
            logger.warning("Equipment description JSON parse failed: %r", response_text[:500])
            return ""
