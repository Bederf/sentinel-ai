"""Holistic optimization evaluator — unifies telemetry and runs all module rules."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid5, NAMESPACE_URL

from app.models.module_registry import ModuleType
from app.services.module_registry_service import module_registry
from app.services.optimization.rules import ALL_RULES

logger = logging.getLogger(__name__)

# ── Helpers ──────────────────────────────────────────────────────────


def _dedup_key(site_id: str, rule_name: str, target: str = "") -> str:
    """Deterministic UUID for upsert dedup — same site+rule+target always same ID."""
    raw = f"{site_id}/{rule_name}/{target}"
    return str(uuid5(NAMESPACE_URL, raw))


# ── Profile gate ─────────────────────────────────────────────────────


def _target_profile(site_id: str) -> str:
    """Return the active optimization profile for a site.

    Defaults to "balanced" if no profile is configured.
    """
    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        site = client.table("sites").select("optimization_status").eq("code", site_id).maybe_single().execute()
        if site.data and site.data.get("optimization_status"):
            return site.data["optimization_status"]
    except Exception:
        pass
    return "balanced"


# ── Telemetry collector ──────────────────────────────────────────────


def _collect_telemetry(site_id: str) -> dict[str, dict[str, Any]]:
    """Collect telemetry from all active modules for a site.

    Returns a dict keyed by module type, e.g.::

        {
            "hvac": {"zone_temp": 22.5, "outdoor_temp": 17.0, ...},
            "solar": {"pv_power_kw": 45.2, "bess_soc": 78, ...},
            ...
        }
    """
    snapshot: dict[str, dict[str, Any]] = {}

    # Start with unified module telemetry
    unified = module_registry.get_unified_telemetry(site_id)
    modules_data = unified.get("modules", {}) if unified else {}
    for module_type, mod_data in modules_data.items():
        if isinstance(mod_data, dict):
            snapshot[module_type] = {
                k: v
                for k, v in mod_data.items()
                if k not in ("status", "health_score", "last_telemetry", "capabilities", "ai_features")
            }

    # Append site-level aggregates (occupancy, total power, etc.)
    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        agg = (
            client.table("equipment_sensor_readings")
            .select("point_name, value, recorded_at")
            .eq("site_id", site_id)
            .order("recorded_at", desc=True)
            .limit(200)
            .execute()
        )
        if agg.data:
            for row in agg.data:
                pn = row.get("point_name", "")
                if pn:
                    snapshot.setdefault("site_aggregate", {})[pn] = row.get("value")
    except Exception:
        pass

    return snapshot


# ── Main evaluator ───────────────────────────────────────────────────


def evaluate(site_id: str) -> list[dict[str, Any]]:
    """Run all optimization rules for a site against its unified telemetry.

    Returns a list of recommendation dicts ready for the recommendations table.
    Each recommendation includes a deterministic ``id`` for upsert-on-conflict
    dedup, preventing duplicates across evaluation cycles.
    """
    profile = _target_profile(site_id)
    telemetry = _collect_telemetry(site_id)

    if not telemetry:
        logger.debug("Optimizer: no telemetry for %s", site_id)
        return []

    recommendations: list[dict[str, Any]] = []

    for rule in ALL_RULES:
        # Profile gate: skip rules that don't match the site profile
        if profile != "balanced" and rule.profile != "balanced" and rule.profile != profile:
            continue

        # Module gate: skip rules whose module is not active for this site
        try:
            mt = ModuleType(rule.module)
            if not module_registry.is_module_active(site_id, mt):
                continue
        except (ValueError, KeyError):
            continue

        try:
            rec = rule.evaluate(telemetry)
        except Exception as e:
            logger.warning("Optimizer rule '%s' failed for %s: %s", rule.name, site_id, e)
            continue

        if rec is None:
            continue

        target = rec.get("target_equipment", "")
        recommendations.append(
            {
                "id": _dedup_key(site_id, rule.name, target),
                "site_id": site_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "action_type": "optimization",
                "risk_level": "medium",
                "target_equipment": target,
                "action": rec.get("action", {}),
                "reason": rec.get("reason", ""),
                "expected_impact": rec.get("expected_impact", {}),
                "confidence": "medium",
                "confidence_score": rec.get("confidence", 0.7),
                "profile": "holistic_optimizer",
                "multi_objective_score": 0.0,
                "status": "pending",
                "requires_approval": True,
                "shadow_mode": False,
                "metadata": {
                    "module": rule.module,
                    "rule": rule.name,
                    "profile": rule.profile,
                },
            }
        )

    if recommendations:
        logger.info("Optimizer: %d recommendations for %s", len(recommendations), site_id)

    return recommendations
