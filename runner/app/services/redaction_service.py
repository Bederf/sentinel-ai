"""RedactionService — POPIA-compliant PII redaction for runner output.

Adapted from backend/app/middleware/pii_guard.py for the RLM Runner.
SA-specific patterns: ID numbers, phone numbers, emails, credit cards, account numbers.

IMPORTANT: Redacts OUTPUT only (spec Section 9.1).
Raw evidence is preserved unredacted for audit purposes.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PII pattern definitions (SA-specific, POPIA-required)
# ---------------------------------------------------------------------------

_PATTERNS: dict[str, re.Pattern[str]] = {
    # SA ID numbers: 13 digits (YYMMDDGSSSCAZ), clean or with optional spaces/dashes
    # MUST be checked before phone to avoid phone pattern consuming ID sub-sequences
    "ID": re.compile(
        r"\b\d{2}[\s-]?\d{2}[\s-]?\d{2}[\s-]?\d{4}[\s-]?\d{3}\b"
    ),
    # SA phone numbers: +27 and 0XX formats (mobile: 06/07/08, landline: 01/02/03)
    "PHONE": re.compile(
        r"\+27\s?\d{2}\s?\d{3}\s?\d{4}"  # +27 72 123 4567
        r"|(?<!\d)0[1-8]\d\s?\d{3}\s?\d{4}(?!\d)"  # 072 123 4567 (not inside longer number)
    ),
    # Email addresses
    "EMAIL": re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    ),
    # Account/customer numbers: ACC-XXXX, CUST-XXXX patterns
    "ACCT": re.compile(
        r"\b(?:ACC|ACCT|CUST|CUSTOMER)[-_]?\d{4,}\b",
        re.IGNORECASE,
    ),
    # Credit card numbers: 13-19 digits with optional spaces/dashes, basic pattern
    "CC": re.compile(
        r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{1,7}\b"
    ),
}

# Fields in ResultSchema that are NON-PII metadata — never redacted
_METADATA_FIELDS: frozenset[str] = frozenset({
    "status",
    "confidence",
    "confidence_label",
    "scoring",
    "model_name",
    "model_provider",
    "trajectory",
    "needs_deeper_run",
    "steps",
    "files_read",
    "bytes_read",
    "elapsed_s",
})


def _validate_sa_id(raw: str) -> bool:
    """Validate a South African ID number using Luhn algorithm.

    SA ID format: YYMMDDGSSSCAZ
    - YYMMDD: Date of birth
    - G: Gender (0-4 female, 5-9 male)
    - SSS: Sequence
    - C: Citizenship (0 SA, 1 non-SA)
    - A: Usually 8 or 9
    - Z: Checksum (Luhn)
    """
    digits_only = re.sub(r"[\s-]", "", raw)
    if not digits_only.isdigit() or len(digits_only) != 13:
        return False

    try:
        month = int(digits_only[2:4])
        day = int(digits_only[4:6])
        if not (1 <= month <= 12):
            return False
        if not (1 <= day <= 31):
            return False

        # Luhn checksum
        digits = [int(d) for d in digits_only]
        total = 0
        for i in range(12):
            d = digits[i]
            if i % 2 == 0:
                d *= 2
                if d > 9:
                    d -= 9
            total += d

        expected = (10 - (total % 10)) % 10
        return digits[12] == expected
    except (ValueError, IndexError):
        return False


def _luhn_check(number_str: str) -> bool:
    """Generic Luhn algorithm check for credit card numbers."""
    digits_only = re.sub(r"[\s-]", "", number_str)
    if not digits_only.isdigit() or len(digits_only) < 13:
        return False

    digits = [int(d) for d in digits_only]
    digits.reverse()
    total = 0
    for i, d in enumerate(digits):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


class RedactionService:
    """Redacts PII from runner output for POPIA compliance.

    Numbering resets per redact() call:
      [REDACTED-ID-001], [REDACTED-PHONE-001], etc.
    """

    def redact(self, text: str) -> str:
        """Replace all PII matches with numbered placeholder tokens.

        Numbering resets per call.
        """
        counters: dict[str, int] = {}

        for pii_type, pattern in _PATTERNS.items():
            matches = list(pattern.finditer(text))
            for match in matches:
                raw = match.group(0)

                # Validate SA ID (skip false positives)
                if pii_type == "ID" and not _validate_sa_id(raw):
                    continue

                # Validate credit card via Luhn
                if pii_type == "CC" and not _luhn_check(raw):
                    continue

                count = counters.get(pii_type, 0) + 1
                counters[pii_type] = count
                placeholder = f"[REDACTED-{pii_type}-{count:03d}]"
                text = text.replace(raw, placeholder, 1)

        return text

    def redact_result(self, result: dict[str, Any]) -> dict[str, Any]:
        """Deep-walk a result dict and redact string values in PII-bearing fields.

        Redacts: summary, findings[], anomalies[].description,
                 timeline[].description, recommended_actions[].
        Does NOT redact metadata fields: status, confidence, trajectory,
                                         needs_deeper_run.
        """
        out = dict(result)

        # Redact top-level summary
        if "summary" in out and isinstance(out["summary"], str):
            out["summary"] = self.redact(out["summary"])

        # Redact findings list
        if "findings" in out and isinstance(out["findings"], list):
            out["findings"] = [
                self.redact(f) if isinstance(f, str) else f
                for f in out["findings"]
            ]

        # Redact anomalies — walk each dict's description
        if "anomalies" in out and isinstance(out["anomalies"], list):
            out["anomalies"] = [
                self._redact_dict_field(a, "description") for a in out["anomalies"]
            ]

        # Redact timeline — walk each dict's description
        if "timeline" in out and isinstance(out["timeline"], list):
            out["timeline"] = [
                self._redact_dict_field(t, "description") for t in out["timeline"]
            ]

        # Redact recommended_actions list
        if "recommended_actions" in out and isinstance(out["recommended_actions"], list):
            out["recommended_actions"] = [
                self.redact(a) if isinstance(a, str) else a
                for a in out["recommended_actions"]
            ]

        return out

    def _redact_dict_field(self, d: Any, field: str) -> Any:
        """Redact a specific field within a dict, if present."""
        if not isinstance(d, dict):
            return d
        out = dict(d)
        if field in out and isinstance(out[field], str):
            out[field] = self.redact(out[field])
        return out


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

redaction_service = RedactionService()
