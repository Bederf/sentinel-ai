"""Municipal PDF extraction service.

Extracts text from PDFs using PyMuPDF/pdfplumber and applies lightweight
regex-based field extraction. Falls back to OCR if text extraction fails.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class MunicipalPdfExtractionService:
    """Extract invoice text and basic fields from PDF files."""

    async def parse_invoice(self, pdf_path: Path) -> Dict[str, Any]:
        text = self._extract_text(pdf_path)
        if not text or len(text.strip()) < 200:
            logger.info("PDF text extraction weak; attempting OCR fallback")
            ocr = await self._fallback_ocr(pdf_path)
            if ocr:
                return ocr
            return {"raw_text": text or "", "confidence": 0.0}

        parsed = self._extract_fields(text)
        parsed["raw_text"] = text
        parsed["confidence"] = self._score_confidence(parsed)
        if parsed["confidence"] < 0.6 or self._missing_core_fields(parsed):
            logger.info("Low confidence PDF parse; attempting OCR fallback")
            ocr = await self._fallback_ocr(pdf_path)
            if ocr:
                return {**parsed, **ocr, "confidence": max(parsed["confidence"], ocr.get("confidence", 0.0))}
        return parsed

    def _extract_text(self, pdf_path: Path) -> str:
        # Try PyMuPDF
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(pdf_path)
            text = "\n".join(page.get_text("text") for page in doc)
            if text and len(text.strip()) > 50:
                return text
        except Exception as exc:
            logger.debug("PyMuPDF extraction failed: %s", exc)

        # Try pdfplumber
        try:
            import pdfplumber

            text_parts = []
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    text_parts.append(page.extract_text() or "")
            text = "\n".join(text_parts)
            return text
        except Exception as exc:
            logger.debug("pdfplumber extraction failed: %s", exc)

        return ""

    async def _fallback_ocr(self, pdf_path: Path) -> Optional[Dict[str, Any]]:
        try:
            from app.services.municipal_ocr_service import MunicipalInvoiceOCRService

            ocr_service = MunicipalInvoiceOCRService()
            result = ocr_service.parse_invoice(str(pdf_path))
            if hasattr(result, "__await__"):
                result = await result
            if isinstance(result, dict):
                result.setdefault("confidence", result.get("confidence", 0.0))
                return result
        except Exception as exc:
            logger.info("OCR fallback unavailable: %s", exc)
        return None

    def _extract_fields(self, text: str) -> Dict[str, Any]:
        return {
            "account_number": self._find_first(text, r"Account\s*(Number|No)\s*[:#]?\s*(\d{6,15})"),
            "invoice_number": self._find_first(text, r"Invoice\s*(Number|No)\s*[:#]?\s*([A-Z0-9-]{6,20})"),
            "total_amount_zar": self._find_currency(text, r"Total\s*(Amount|Due)?\s*[:#]?\s*R?\s*([\d,]+\.\d{2})"),
            "consumption_kwh": self._find_number(text, r"Consumption\s*[:#]?\s*([\d,]+\.?\d*)\s*kWh"),
            "demand_kva": self._find_number(text, r"Demand\s*[:#]?\s*([\d,]+\.?\d*)\s*kVA"),
            "is_estimated": bool(re.search(r"estimated|estimate", text, re.IGNORECASE)),
            "is_back_billed": bool(re.search(r"back\s*-?\s*billed|backbilling|back billing", text, re.IGNORECASE)),
            **self._extract_billing_period(text),
        }

    def _extract_billing_period(self, text: str) -> Dict[str, Any]:
        # Example formats: "01 Jan 2026 to 31 Jan 2026" or "01/01/2026 - 31/01/2026"
        match = re.search(
            r"(\d{2}[\/\-\s][A-Za-z]{3}[\/\-\s]\d{4}|\d{2}/\d{2}/\d{4})\s*(to|-)\s*(\d{2}[\/\-\s][A-Za-z]{3}[\/\-\s]\d{4}|\d{2}/\d{2}/\d{4})",
            text,
            re.IGNORECASE,
        )
        if not match:
            return {}

        start_raw = match.group(1)
        end_raw = match.group(3)
        return {
            "billing_period_start": self._parse_date(start_raw),
            "billing_period_end": self._parse_date(end_raw),
        }

    def _parse_date(self, value: str) -> str:
        for fmt in ("%d %b %Y", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(value.strip(), fmt).date().isoformat()
            except Exception:
                continue
        return value

    def _find_first(self, text: str, pattern: str) -> Optional[str]:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(match.lastindex or 1)
        return None

    def _find_number(self, text: str, pattern: str) -> Optional[float]:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(match.lastindex or 1).replace(",", "")
            try:
                return float(value)
            except Exception:
                return None
        return None

    def _find_currency(self, text: str, pattern: str) -> Optional[float]:
        return self._find_number(text, pattern)

    def _score_confidence(self, parsed: Dict[str, Any]) -> float:
        fields = [
            "account_number",
            "invoice_number",
            "billing_period_start",
            "billing_period_end",
            "total_amount_zar",
        ]
        found = sum(1 for f in fields if parsed.get(f))
        return round(found / len(fields), 2)

    def _missing_core_fields(self, parsed: Dict[str, Any]) -> bool:
        core = ["account_number", "invoice_number", "total_amount_zar"]
        return any(not parsed.get(field) for field in core)
