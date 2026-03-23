"""Municipal invoice OCR fallback service.

Provides OCR-based extraction for scanned municipal PDFs. This is used as a
fallback by ``MunicipalPdfExtractionService`` when native text extraction is
weak or low confidence.
"""

from __future__ import annotations

import io
import logging
import re
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class MunicipalInvoiceOCRService:
    """Extract municipal invoice fields from scanned PDFs via OCR."""

    def parse_invoice(self, pdf_path: str) -> dict[str, Any]:
        """Parse invoice fields using OCR.

        Returns a dict compatible with ``MunicipalPdfExtractionService``
        output shape so the fallback can merge results safely.
        """
        ocr_text = self._extract_ocr_text(pdf_path)
        if not ocr_text.strip():
            return {"raw_text": "", "confidence": 0.0}

        parsed = self._extract_fields(ocr_text)
        parsed["raw_text"] = ocr_text
        # OCR is noisier than native extraction; keep conservative default.
        parsed.setdefault("confidence", self._score_confidence(parsed, default=0.5))
        parsed["ocr_used"] = True
        return parsed

    def _extract_ocr_text(self, pdf_path: str) -> str:
        """Render PDF pages and run Tesseract OCR."""
        try:
            import fitz  # PyMuPDF
            import pytesseract
            from PIL import Image
        except Exception as exc:
            logger.warning("Municipal OCR dependencies unavailable: %s", exc)
            return ""

        try:
            text_parts: list[str] = []
            doc = fitz.open(pdf_path)
            for page in doc:
                # 2x zoom improves OCR quality while keeping memory reasonable.
                pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
                image = Image.open(io.BytesIO(pix.tobytes("png")))
                text_parts.append(pytesseract.image_to_string(image, lang="eng"))
            return "\n".join(text_parts)
        except Exception as exc:
            # Includes missing tesseract binary, unreadable files, etc.
            logger.info("Municipal OCR failed for %s: %s", pdf_path, exc)
            return ""

    def _extract_fields(self, text: str) -> dict[str, Any]:
        return {
            "account_number": self._find_first(text, r"Account\s*(Number|No)\s*[:#]?\s*(\d{6,15})"),
            "invoice_number": self._find_first(text, r"Invoice\s*(Number|No)\s*[:#]?\s*([A-Z0-9-]{6,20})"),
            "total_amount_zar": self._find_number(text, r"Total\s*(Amount|Due)?\s*[:#]?\s*R?\s*([\d,]+\.\d{2})"),
            "consumption_kwh": self._find_number(text, r"Consumption\s*[:#]?\s*([\d,]+\.?\d*)\s*kWh"),
            "demand_kva": self._find_number(text, r"Demand\s*[:#]?\s*([\d,]+\.?\d*)\s*kVA"),
            "is_estimated": bool(re.search(r"estimated|estimate", text, re.IGNORECASE)),
            "is_back_billed": bool(re.search(r"back\s*-?\s*billed|backbilling|back billing", text, re.IGNORECASE)),
            **self._extract_billing_period(text),
        }

    def _extract_billing_period(self, text: str) -> dict[str, Any]:
        match = re.search(
            r"(\d{2}[\/\-\s][A-Za-z]{3}[\/\-\s]\d{4}|\d{2}/\d{2}/\d{4})\s*(to|-)\s*(\d{2}[\/\-\s][A-Za-z]{3}[\/\-\s]\d{4}|\d{2}/\d{2}/\d{4})",
            text,
            re.IGNORECASE,
        )
        if not match:
            return {}

        return {
            "billing_period_start": self._parse_date(match.group(1)),
            "billing_period_end": self._parse_date(match.group(3)),
        }

    def _parse_date(self, value: str) -> str:
        for fmt in ("%d %b %Y", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(value.strip(), fmt).date().isoformat()
            except Exception:
                continue
        return value

    def _find_first(self, text: str, pattern: str) -> str | None:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(match.lastindex or 1)
        return None

    def _find_number(self, text: str, pattern: str) -> float | None:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return None
        value = match.group(match.lastindex or 1).replace(",", "")
        try:
            return float(value)
        except Exception:
            return None

    def _score_confidence(self, parsed: dict[str, Any], default: float = 0.5) -> float:
        fields = [
            "account_number",
            "invoice_number",
            "billing_period_start",
            "billing_period_end",
            "total_amount_zar",
        ]
        found = sum(1 for field in fields if parsed.get(field))
        score = round(found / len(fields), 2)
        return score if score > 0 else default
