"""
JSON Equipment Loader — loads equipment from on-disk JSON files.

Site-002 uses JSON files as its equipment source of truth (the simulation IS
the BMS). This loader reads ``backend/app/data/buildings/{site_id}/equipment/*.json``
and returns dicts compatible with ``EquipmentRepository.get_all()`` output.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Where equipment JSON files live, relative to the backend root
_DATA_ROOT = Path(__file__).resolve().parent.parent / "data" / "buildings"

# Map JSON ``equipment_type`` values to the internal simulation type names
# used by LifecycleOrchestrator sensor generators.
JSON_TYPE_ALIASES: dict[str, str] = {
    "lighting_zone": "luminaire",
    "dali_controller": "dali_controller",
    # These are already correct but listed for documentation:
    # "ahu": "ahu",
    # "chiller": "chiller",
    # "fcu": "fcu",
    # "vav": "vav",
    # "bess": "bess",
    # "inverter": "inverter",
    # "generator": "generator",
    # "meter": "meter",
    # "pump": "pump",
    # "ups": "ups",
    # "unknown": "unknown",
}


def _extract_type_from_code(code: str) -> str:
    """Extract equipment type from code middle segment.

    ``S002-AHU-B1-001`` → ``ahu``
    ``S002-DALI_CONTROLLER-B1-001`` → ``dali_controller``
    ``S002-LTG-001`` → ``ltg``
    """
    parts = code.split("-")
    if len(parts) >= 3:
        return parts[1].lower()
    return "unknown"


def load_site_equipment(site_id: str) -> list[dict]:
    """Load equipment from JSON files on disk for a given site.

    Returns a list of dicts with keys compatible with Supabase equipment rows:
    ``code``, ``name``, ``type``, ``device_type``, ``health_score``, ``status``,
    ``points``, ``metadata``, ``site_id``.

    Malformed files are skipped with a warning.
    """
    equip_dir = _DATA_ROOT / site_id / "equipment"
    if not equip_dir.is_dir():
        logger.warning("Equipment directory not found: %s", equip_dir)
        return []

    equipment: list[dict] = []
    for fpath in sorted(equip_dir.glob("*.json")):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Skipping malformed equipment file %s: %s", fpath.name, exc)
            continue

        # Determine type: prefer equipment_type, fall back to code extraction
        raw_type = data.get("equipment_type") or _extract_type_from_code(data.get("id", fpath.stem))
        normalized_type = JSON_TYPE_ALIASES.get(raw_type, raw_type)

        equipment.append(
            {
                "code": data.get("id", fpath.stem),
                "name": data.get("name", fpath.stem),
                "type": normalized_type,
                "device_type": data.get("device_type", "other"),
                "health_score": data.get("health_score", 100),
                "status": data.get("status", "online"),
                "points": data.get("points", {}),
                "metadata": data.get("metadata", {}),
                "site_id": data.get("site_id", site_id),
            }
        )

    logger.info(
        "Loaded %d equipment items from JSON for site %s",
        len(equipment),
        site_id,
    )
    return equipment
