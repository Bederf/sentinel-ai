"""
PII Redaction Guard for SENTINEL BMS Platform.

Protects sensitive personal information before LLM processing.
Compliant with POPIA (South Africa) and GDPR.

Ported from AimTheLaw pii_guard.py - core PII detection and redaction
adapted for BMS context (building occupant data, technician details).

NOT registered as middleware - used as a utility service by AI chat
and other services that process user-provided text.

Features:
- South African ID number detection and redaction (Luhn validation)
- Email address redaction
- Phone number redaction (SA formats: +27, 0XX)
- Credit card number detection
- Reversible redaction for restoration

FSR Domain: 4.12 - Data Privacy (POPIA compliance)
"""

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class RedactionResult:
    """Result of PII redaction operation."""

    redacted_text: str
    redaction_map: Dict[str, str]  # Maps placeholders back to original values
    pii_found: List[str]  # Types of PII detected
    redaction_count: int


class PIIGuard:
    """PII detection and redaction for POPIA compliance.

    South African specific patterns:
    - ID numbers (13 digits with Luhn checksum validation)
    - Phone numbers (+27 format and local 0XX formats)
    - Email addresses
    - Credit card numbers
    """

    def __init__(self):
        """Initialize PII patterns."""
        self.patterns = self._build_patterns()

    def _build_patterns(self) -> Dict[str, re.Pattern]:
        """Build regex patterns for PII detection."""
        return {
            # South African ID number: 13 digits (YYMMDDGSSSCAZ)
            "sa_id": re.compile(r"\b\d{13}\b"),
            # South African phone numbers
            "phone_sa": re.compile(
                r"\+27\s?\d{2}\s?\d{3}\s?\d{4}|"  # +27 12 345 6789
                r"0\d{2}\s?\d{3}\s?\d{4}|"  # 012 345 6789
                r"\b0\d{9}\b"  # 0123456789
            ),
            # Email addresses
            "email": re.compile(
                r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
            ),
            # Credit card numbers (basic pattern, 13-19 digits with separators)
            "credit_card": re.compile(
                r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4,7}\b"
            ),
        }

    def redact(
        self,
        text: str,
        preserve_types: Optional[List[str]] = None,
    ) -> RedactionResult:
        """Redact PII from text with reversible mapping.

        Args:
            text: Text to redact
            preserve_types: PII types to NOT redact (e.g., ["email"])

        Returns:
            RedactionResult with redacted text and restoration map
        """
        redacted_text = text
        redaction_map = {}
        pii_found: set = set()
        redaction_count = 0

        preserve_types = preserve_types or []

        for pii_type, pattern in self.patterns.items():
            if pii_type in preserve_types:
                continue

            matches = list(pattern.finditer(redacted_text))

            for match in matches:
                original_value = match.group(0)

                # Validate SA ID number
                if pii_type == "sa_id" and not self._validate_sa_id(original_value):
                    continue

                placeholder = self._create_placeholder(pii_type, original_value)
                redaction_map[placeholder] = original_value
                redacted_text = redacted_text.replace(original_value, placeholder, 1)
                pii_found.add(pii_type)
                redaction_count += 1

        return RedactionResult(
            redacted_text=redacted_text,
            redaction_map=redaction_map,
            pii_found=list(pii_found),
            redaction_count=redaction_count,
        )

    def restore(self, redacted_text: str, redaction_map: Dict[str, str]) -> str:
        """Restore original PII values from redacted text.

        Args:
            redacted_text: Text with PII placeholders
            redaction_map: Mapping from placeholders to original values

        Returns:
            Original text with PII restored
        """
        restored_text = redacted_text
        for placeholder, original_value in redaction_map.items():
            restored_text = restored_text.replace(placeholder, original_value)
        return restored_text

    def _create_placeholder(self, pii_type: str, original_value: str) -> str:
        """Create unique placeholder for PII value."""
        value_hash = hashlib.md5(original_value.encode()).hexdigest()[:8]
        return f"[{pii_type.upper()}_{value_hash}]"

    def _validate_sa_id(self, id_number: str) -> bool:
        """Validate South African ID number using Luhn algorithm.

        SA ID format: YYMMDDGSSSCAZ
        - YYMMDD: Date of birth
        - G: Gender (0-4 female, 5-9 male)
        - SSS: Sequence number
        - C: Citizenship (0 SA, 1 non-SA)
        - A: Usually 8 or 9
        - Z: Checksum digit (Luhn)

        Args:
            id_number: 13-digit ID number string

        Returns:
            True if valid SA ID number
        """
        if not id_number.isdigit() or len(id_number) != 13:
            return False

        try:
            # Validate date components
            month = int(id_number[2:4])
            day = int(id_number[4:6])

            if not (1 <= month <= 12):
                return False
            if not (1 <= day <= 31):
                return False

            # Luhn algorithm checksum validation
            digits = [int(d) for d in id_number]
            checksum = digits[-1]

            total = 0
            for i in range(12):
                digit = digits[i]
                if i % 2 == 0:
                    digit *= 2
                    if digit > 9:
                        digit -= 9
                total += digit

            calculated_checksum = (10 - (total % 10)) % 10
            return checksum == calculated_checksum

        except (ValueError, IndexError):
            return False

    def scan_for_pii(self, text: str) -> Dict[str, Any]:
        """Scan text for PII without redacting.

        Args:
            text: Text to scan

        Returns:
            Dict with PII detection results
        """
        findings = {}

        for pii_type, pattern in self.patterns.items():
            matches = pattern.findall(text)
            if matches:
                if pii_type == "sa_id":
                    matches = [m for m in matches if self._validate_sa_id(m)]
                if matches:
                    findings[pii_type] = {
                        "count": len(matches),
                        "examples": [
                            self._mask_pii(m) for m in matches[:3]
                        ],
                    }

        return {
            "pii_found": list(findings.keys()),
            "total_count": sum(f["count"] for f in findings.values()),
            "findings": findings,
            "compliant": len(findings) == 0,
        }

    def _mask_pii(self, value: str) -> str:
        """Mask PII value for safe logging (show first/last chars only)."""
        if len(value) <= 4:
            return "***"
        return f"{value[:2]}...{value[-2:]}"


# Global PII guard instance
pii_guard = PIIGuard()


# =============================================================================
# Utility Functions
# =============================================================================


def redact_request_pii(
    request_data: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """Redact PII from request data before LLM processing.

    Args:
        request_data: Request payload dict

    Returns:
        Tuple of (redacted_data, redaction_map)
    """
    import json

    data_str = json.dumps(request_data)
    result = pii_guard.redact(data_str)
    redacted_data = json.loads(result.redacted_text)

    if result.pii_found:
        logger.info(
            f"Redacted {result.redaction_count} PII instances: {result.pii_found}"
        )

    return redacted_data, result.redaction_map


def restore_response_pii(
    response_data: Dict[str, Any], redaction_map: Dict[str, str]
) -> Dict[str, Any]:
    """Restore PII in response data after LLM processing.

    Args:
        response_data: Response payload dict
        redaction_map: Redaction map from redact_request_pii

    Returns:
        Response data with PII restored
    """
    import json

    data_str = json.dumps(response_data)
    restored_str = pii_guard.restore(data_str, redaction_map)
    return json.loads(restored_str)


def validate_pii_compliance(text: str, raise_on_pii: bool = False) -> bool:
    """Check if text is PII-compliant (no sensitive data).

    Args:
        text: Text to validate
        raise_on_pii: Raise exception if PII found

    Returns:
        True if compliant (no PII found)

    Raises:
        ValueError: If PII found and raise_on_pii=True
    """
    scan_result = pii_guard.scan_for_pii(text)

    if not scan_result["compliant"]:
        msg = (
            f"PII detected: {scan_result['pii_found']} "
            f"({scan_result['total_count']} instances)"
        )
        if raise_on_pii:
            raise ValueError(msg)
        logger.warning(msg)
        return False

    return True
