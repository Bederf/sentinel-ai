"""Equipment label helpers for operator-facing text.

Internal asset IDs remain unchanged in persisted references. These helpers only
shape text shown to operators, technicians, and FM users.
"""

from __future__ import annotations

import re

_BASEMENT_RE = re.compile(r"^B0+(\d+)$", re.IGNORECASE)


def operator_equipment_label(equipment_code: str | None) -> str:
    """Return the operator-facing equipment label.

    Tier-2 plant assets are stored with a sequence suffix, e.g.
    ``S002-CHILLER-B1-001``. Operators should see the logical asset label
    ``S002-CHILLER-B1``; the sequenced code remains an internal reference.
    """
    code = str(equipment_code or "").strip()
    if not code:
        return ""

    parts = code.split("-")
    if len(parts) >= 4 and parts[-1].isdigit() and len(parts[-1]) == 3:
        parts = parts[:-1]

    return "-".join(_normalise_zone_part(part) for part in parts)


def internal_asset_reference(equipment_code: str | None) -> str | None:
    """Return the internal asset reference when it differs from operator label."""
    code = str(equipment_code or "").strip()
    if not code:
        return None
    label = operator_equipment_label(code)
    return code if code != label else None


def format_operator_equipment_reference(equipment_code: str | None) -> str:
    """Return ``operator label`` plus internal reference when useful."""
    label = operator_equipment_label(equipment_code)
    internal_ref = internal_asset_reference(equipment_code)
    if internal_ref:
        return f"{label} (internal asset: {internal_ref})"
    return label


def _normalise_zone_part(part: str) -> str:
    match = _BASEMENT_RE.match(part)
    if match:
        return f"B{match.group(1)}"
    return part
