"""Maintenance gap detector — identifies equipment cohorts sharing a maintenance gap.

Phase 227 — detects clusters of 3+ equipment of the same type where:
- health_score <= 65 (age-based fallback range, degraded enough to warrant attention)
- last_maintenance_date IS NULL (definitive maintenance gap signal)

Generates a single grouped recommendation instead of N individual ones.
Runs on an hourly cadence via background_scheduler.
"""

from __future__ import annotations

import logging
from uuid import NAMESPACE_URL, uuid5

logger = logging.getLogger(__name__)

# Minimum cohort size to produce a grouped gap recommendation
MIN_COHORT_SIZE = 3


def detect_maintenance_gaps(site_id: str) -> list[dict]:
    """Query equipment for maintenance gap cohorts and return gap group dicts.

    Args:
        site_id: Site code (e.g. ``"site-002"``).

    Returns:
        List of gap group dicts, one per equipment type with match.
        Each dict has the fields needed to create a grouped recommendation::

            {
                "equipment_type": "vav",
                "member_count": 7,
                "member_ids": [uuid, ...],       # equipment UUIDs
                "member_codes": ["S002-VAV-001", ...],
                "avg_health_score": 62.0,
                "site_id": "site-002",
                "detection": "age_based_fallback",
            }
    """
    from app.database.repositories.equipment_repository import EquipmentRepository
    from app.database.supabase_client import get_supabase_client

    client = get_supabase_client()

    # Resolve site code → UUID
    sites_resp = client.table("sites").select("id").eq("code", site_id).execute()
    if not sites_resp.data:
        logger.warning("Maintenance gap detector: site %s not found", site_id)
        return []
    site_uuid = sites_resp.data[0]["id"]

    # Fetch candidate equipment: low health + no maintenance + scorable type
    repo = EquipmentRepository()
    candidates = repo.get_maintenance_gap_candidates(site_uuid=site_uuid, health_threshold=65)

    if not candidates:
        return []

    # Group by equipment type
    by_type: dict[str, list[dict]] = {}
    for eq in candidates:
        eq_type = eq.get("type", "").lower()
        by_type.setdefault(eq_type, []).append(eq)

    gaps: list[dict] = []
    for eq_type, members in by_type.items():
        if len(members) < MIN_COHORT_SIZE:
            continue

        scores = [m.get("health_score") or 0 for m in members]
        avg_health = round(sum(scores) / len(scores), 1) if scores else 0.0

        gaps.append(
            {
                "equipment_type": eq_type,
                "member_count": len(members),
                "member_ids": [m["id"] for m in members if m.get("id")],
                "member_codes": [m["code"] for m in members if m.get("code")],
                "avg_health_score": avg_health,
                "site_id": site_id,
                "detection": "age_based_fallback",
            }
        )

    return gaps


def build_gap_recommendation_id(site_id: str, equipment_type: str) -> str:
    """Deterministic recommendation ID for upsert dedup.

    Uses UUID v5 on a stable namespace so the same gap produces the same ID
    across runs — the cockpit fusion layer will update rather than accumulate.
    """
    return str(uuid5(NAMESPACE_URL, f"{site_id}/{equipment_type}_maintenance_gap"))
