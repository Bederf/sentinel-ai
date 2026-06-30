"""Site-specific scope rules for live telemetry ingestion."""

from __future__ import annotations

import re


_SITE_002_L3_PATTERNS = (
    re.compile(r"^S002-ZONE-L3(?:-|$)"),
    re.compile(r"^ZONE-L3(?:-|$)"),
    re.compile(r"^ZONE-3\d{2}$"),
    re.compile(r"^S002-(?:AHU|FCU|VAV)-3\d{2}$"),
    re.compile(r"^S002-(?:DALI|LTG|LUM)(?:-[A-Z]+)?-0?3\d{2}$"),
)

_SITE_002_L3_REFERENCE_RE = re.compile(
    r"(?:"
    r"S002-ZONE-L3(?:-|$)|"
    r"\bZONE-L3(?:-|$)|"
    r"\bZONE-3\d{2}\b|"
    r"S002-(?:AHU|FCU|VAV)-3\d{2}\b|"
    r"S002-(?:DALI|LTG|LUM)(?:-[A-Z]+)?-0?3\d{2}\b"
    r")"
)


def is_site_002_out_of_scope_l3(site_id: str | None, equipment_code: str | None) -> bool:
    """Return true for Site 002 L3 references that are outside tenant scope."""
    site = (site_id or "").strip().lower()
    if site not in {"site-002", "s002"}:
        return False

    code = (equipment_code or "").strip().upper()
    if not code:
        return False

    return any(pattern.match(code) for pattern in _SITE_002_L3_PATTERNS)


def contains_site_002_out_of_scope_l3_reference(site_id: str | None, text: str | None) -> bool:
    """Return true when free text contains an out-of-scope Site 002 L3 reference."""
    site = (site_id or "").strip().lower()
    if site not in {"site-002", "s002"}:
        return False

    value = (text or "").strip().upper()
    if not value:
        return False

    return bool(_SITE_002_L3_REFERENCE_RE.search(value))
