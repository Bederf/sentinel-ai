"""
Fault Urgency Scorer (Phase 164).

Computes urgency for equipment fault incidents — distinct from concierge_urgency.py
which scores rooms for the concierge view.

Formula (v1 — deterministic, no LLM):
  urgency = (severity_component * posture_weight_comfort)
          + (asset_criticality_component * posture_weight_asset)
          + (cost_component * posture_weight_cost)

All components normalised to 0.0–1.0. Final score clamped to 0.0–1.0.

Note: ``criticality`` is not stored in the equipment schema or JSON files —
derive from equipment type code instead (see EQUIPMENT_CRITICALITY mapping below).
"""

from __future__ import annotations

# Severity weights matching event_bus.Importance levels
SEVERITY_WEIGHTS: dict[str, float] = {
    "critical": 1.0,
    "high": 0.75,
    "medium": 0.50,
    "warning": 0.35,
    "low": 0.20,
    "info": 0.05,
}

# Equipment criticality by type code (higher = more critical to building operations).
# criticality not in schema — derive from type (see module docstring).
EQUIPMENT_CRITICALITY: dict[str, float] = {
    "CHILLER": 1.0,  # Loss = full building cooling failure
    "AHU": 0.80,  # Loss = zone HVAC failure
    "FCU": 0.50,  # Loss = room comfort impact
    "VAV": 0.45,
    "GEN": 0.90,  # Loss = power continuity risk
    "UPS": 0.85,
    "PUMP": 0.60,
    "CT": 0.55,  # Cooling tower
    "DALI": 0.30,  # Lighting — lower criticality
    "LUM": 0.25,
    "MTR": 0.40,  # Meter — monitoring loss
    "DEFAULT": 0.50,
}


# Cluster boost factor applied to urgency when equipment is in cluster alert state.
# Configurable via settings; default 1.5× means 50% urgency increase for systemic faults.
CLUSTER_BOOST_FACTOR = 1.5


def _cost_component(fault_type: str, current_hour: int | None) -> float:
    """Return tariff-based cost component (0.0–1.0).

    SA commercial peak: 07:00–10:00 and 17:00–20:00.
    fault_type reserved for future tariff-category overrides.
    """
    if current_hour is None:
        return 0.5  # unknown → moderate
    # Peak hours — highest cost risk
    if 7 <= current_hour < 10 or 17 <= current_hour < 20:
        return 0.9
    # Business hours (occupied) — moderate cost risk
    if 8 <= current_hour < 17:
        return 0.6
    # Off-peak — lower cost risk
    return 0.3


def compute_fault_urgency(
    fault_type: str,
    severity: str,
    equipment_id: str,
    posture_weights: dict[str, float],
    current_hour: int | None = None,
    is_cluster_alert: bool = False,
    cluster_count: int = 1,
) -> tuple[float, dict[str, float]]:
    """Compute urgency score for an equipment fault.

    Args:
        fault_type: e.g. "thermal_drift_exceeded", "chiller_fault", "comm_loss"
        severity: "critical" | "high" | "medium" | "warning" | "low" | "info"
        equipment_id: e.g. "S002-CHILLER-B1-001" — type extracted from code
        posture_weights: {"comfort": 0.70, "cost": 0.15, "asset": 0.15}
        current_hour: 0-23 local hour, or None if unknown
        is_cluster_alert: True if equipment has >= 3 occurrences in 90-day window
        cluster_count: Running count of occurrences in window (used for cluster boost)

    Returns:
        (urgency_score, urgency_components)
        urgency_components keys: "comfort", "asset_risk", "cost"
    """
    # Extract equipment type from ID (e.g. S002-CHILLER-B1-001 → CHILLER)
    parts = equipment_id.split("-")
    eq_type = parts[1].upper() if len(parts) >= 2 else "DEFAULT"

    # Severity → comfort component (weighted by comfort posture)
    sev_weight = SEVERITY_WEIGHTS.get(severity.lower(), 0.5)
    comfort_component = sev_weight * posture_weights.get("comfort", 0.70)

    # Equipment criticality → asset risk component
    criticality = EQUIPMENT_CRITICALITY.get(eq_type, EQUIPMENT_CRITICALITY["DEFAULT"])
    asset_component = criticality * posture_weights.get("asset", 0.15)

    # Tariff exposure → cost component
    cost_raw = _cost_component(fault_type, current_hour)
    cost_component = cost_raw * posture_weights.get("cost", 0.15)

    urgency_score = min(1.0, comfort_component + asset_component + cost_component)

    # Cluster boost: systemic faults (3+ occurrences in 90-day window) get urgency multiplier
    if is_cluster_alert and cluster_count >= 3:
        urgency_score = min(1.0, urgency_score * CLUSTER_BOOST_FACTOR)

    components = {
        "comfort": round(comfort_component, 3),
        "asset_risk": round(asset_component, 3),
        "cost": round(cost_component, 3),
    }

    return round(urgency_score, 3), components


# ---------------------------------------------------------------------------
# Alert text templates — plain language, no LLM required.
# Placeholders: {asset_id}, {zone_count}, {zones}
# ---------------------------------------------------------------------------

ALERT_TEMPLATES: dict[str, str] = {
    "chiller_fault": "Chiller {asset_id} fault detected. Cooling loss likely across {zone_count} zone(s).",
    "thermal_drift_exceeded": "Temperature drift on {asset_id}. Comfort threshold at risk in {zones}.",
    "comm_loss": "Communication lost with {asset_id}. Monitoring interrupted — manual check required.",
    "high_vibration": "High vibration detected on {asset_id}. Mechanical failure risk elevated.",
    "low_refrigerant": "Low refrigerant pressure on {asset_id}. Cooling capacity reduced.",
    "power_anomaly": "Power anomaly on {asset_id}. Check supply and protection devices.",
    "filter_pressure_high": "High filter differential pressure on {asset_id}. Airflow restricted in {zones}.",
    "co2_limit_exceeded": "CO\u2082 threshold exceeded in {zones}. Ventilation response required on {asset_id}.",
    "generator_fault": "Generator {asset_id} fault. Backup power availability compromised.",
    "ups_fault": "UPS {asset_id} fault. Critical load continuity at risk.",
    "pump_fault": "Pump {asset_id} fault. Fluid distribution to {zones} affected.",
    "DEFAULT": "Fault detected on {asset_id}. Requires investigation.",
}


def build_alert_text(
    fault_type: str,
    asset_id: str,
    affected_zone_ids: list[str] | None = None,
) -> str:
    """Build plain-language alert text from fault type and asset context.

    Falls back to DEFAULT template if fault_type not in registry.
    Never raises — always returns a string.
    """
    template = ALERT_TEMPLATES.get(fault_type, ALERT_TEMPLATES["DEFAULT"])
    zone_count = len(affected_zone_ids) if affected_zone_ids else 0
    zones_str = ", ".join(affected_zone_ids[:3]) if affected_zone_ids else "affected areas"
    if affected_zone_ids and len(affected_zone_ids) > 3:
        zones_str += f" (+{len(affected_zone_ids) - 3} more)"
    try:
        return template.format(
            asset_id=asset_id,
            zone_count=zone_count,
            zones=zones_str,
        )
    except KeyError:
        return ALERT_TEMPLATES["DEFAULT"].format(asset_id=asset_id, zone_count=0, zones="")
