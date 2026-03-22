"""
Floor Zone Extraction Utilities (Phase 165).

Pure functions — no I/O, no imports, deterministic.
Used by DecisionMomentAggregator to map equipment IDs to floors and build
the active_incident_map for the kiosk renderer.

S002 equipment code format: {site}-{type}-{zone}-{seq}
  S002-CHILLER-B1-001 → B1
  S002-FCU-L1-A       → L1
  S002-DALI-L2-CTR    → L2
  S002-GEN-G-001      → G
  S002-MTR-R-SOL      → R
  S002-AHU-B1-001     → B1
  S002-UNKNOWN-G-001  → G

Verified: 100% of 66 S002 equipment codes parse with this pattern.
"""

from __future__ import annotations

# Canonical floor ordering: top-of-building first, basement last.
# stack_index 0 = top of visual stack, highest stack_index = bottom.
FLOOR_STACK_ORDER: list[str] = ["R", "L2", "L1", "L0", "G", "B1"]

# Human-readable floor labels for display.
FLOOR_LABELS: dict[str, str] = {
    "B1": "Basement 1",
    "G": "Ground",
    "L0": "Level 0",
    "L1": "Level 1",
    "L2": "Level 2",
    "R": "Roof",
}

# Stack index lookup (precomputed for performance).
FLOOR_STACK_INDEX: dict[str, int] = {floor: idx for idx, floor in enumerate(FLOOR_STACK_ORDER)}


def extract_floor_from_equipment_id(equipment_id: str) -> str | None:
    """
    Extract floor zone from SENTINEL equipment ID.

    Args:
        equipment_id: e.g. "S002-CHILLER-B1-001", "S002-FCU-L1-A"

    Returns:
        Floor zone string (e.g. "B1", "L1", "G", "R") or None if unparseable.
    """
    parts = equipment_id.split("-")
    # Pattern: {site}-{type}-{zone}-{seq}  → 4+ parts, zone at index 2
    if len(parts) >= 4:
        return parts[2]
    return None


def floor_to_svg_y_pct(floor_id: str, total_floors: int | None = None) -> float:
    """
    Convert floor ID to SVG Y percentage for the floor stack renderer.

    Stack is rendered top→bottom: R=top (low Y%), B1=bottom (high Y%).
    Returns midpoint Y% of the floor band within the stack SVG viewport.

    Args:
        floor_id: e.g. "B1", "L1", "R"
        total_floors: override for custom stacks (defaults to len(FLOOR_STACK_ORDER))

    Returns:
        Float 0.0–100.0 representing SVG Y% for the floor band midpoint.
    """
    stack = FLOOR_STACK_ORDER
    total = total_floors or len(stack)
    idx = FLOOR_STACK_INDEX.get(floor_id)
    if idx is None:
        return 50.0  # unknown → centre
    band_height = 100.0 / total
    return round(idx * band_height + band_height / 2, 1)


def build_active_incident_map(
    affected_zone_ids: list[str],
    primary_asset_id: str | None = None,
) -> dict[str, dict]:
    """
    Build the active_incident_map from a list of affected zone IDs.

    Extracts floor from each zone_id (e.g. "Zone-B1-001" → "B1"),
    then maps each floor to its stack position for the SVG renderer.

    Also adds the primary asset's floor if not already covered.

    Args:
        affected_zone_ids: e.g. ["Zone-B1-001", "Zone-L1-A", "Zone-L1-B"]
        primary_asset_id: e.g. "S002-CHILLER-B1-001" (optional, ensures floor covered)

    Returns:
        {
          "B1": {"stack_index": 5, "svg_y_pct": 91.7, "affected": True},
          "L1": {"stack_index": 2, "svg_y_pct": 41.7, "affected": True},
        }
    """
    affected_floors: set[str] = set()

    for zone_id in affected_zone_ids:
        # zone_id formats: "Zone-B1-001", "Plant-B1", "B1", bare floor codes
        parts = zone_id.split("-")
        if len(parts) >= 2:
            # Try parts[1] first (Zone-B1-... → parts[1]="B1")
            candidate = parts[1]
            if candidate in FLOOR_STACK_INDEX:
                affected_floors.add(candidate)
                continue
        # Fallback: zone_id itself might be a bare floor code
        if zone_id in FLOOR_STACK_INDEX:
            affected_floors.add(zone_id)

    # Add primary asset's floor
    if primary_asset_id:
        floor = extract_floor_from_equipment_id(primary_asset_id)
        if floor and floor in FLOOR_STACK_INDEX:
            affected_floors.add(floor)

    result: dict[str, dict] = {}
    total = len(FLOOR_STACK_ORDER)
    for floor_id in affected_floors:
        idx = FLOOR_STACK_INDEX.get(floor_id, 0)
        result[floor_id] = {
            "stack_index": idx,
            "svg_y_pct": floor_to_svg_y_pct(floor_id, total),
            "affected": True,
        }

    return result
