"""
Health scoring configuration — equipment scoreability by type.

Supabase is the source of truth. This config provides defaults;
runtime overrides can be added to the equipment_type_config table.
"""

EQUIPMENT_HEALTH_SCOREABILITY: dict[str, dict] = {
    # ── Large serviceable: age-only baselines ──
    "chiller":        {"scoreable": True, "method": "age_only", "reason": None},
    "ahu":            {"scoreable": True, "method": "age_only", "reason": None},
    "pump":           {"scoreable": True, "method": "age_only", "reason": None},
    "generator":      {"scoreable": True, "method": "age_only", "reason": None},
    "cooling_tower":  {"scoreable": True, "method": "age_only", "reason": None},
    "ups":            {"scoreable": True, "method": "age_only", "reason": None},
    "bess":           {"scoreable": True, "method": "age_only", "reason": None},

    # ── Energy equipment: add to service history, age-only baselines ──
    "inverter":       {"scoreable": True, "method": "age_only", "reason": None},
    "meter":          {"scoreable": True, "method": "age_only", "reason": None},
    "zone":           {"scoreable": True, "method": "age_only", "reason": None},

    # ── VAV/FCU: synthetic fallback while awaiting service data ──
    "vav":            {"scoreable": True, "method": "synthetic_fallback", "reason": None},
    "VAV":            {"scoreable": True, "method": "synthetic_fallback", "reason": None},
    "FCU":            {"scoreable": True, "method": "synthetic_fallback", "reason": None},
    "fcu":            {"scoreable": True, "method": "synthetic_fallback", "reason": None},

    # ── Not health-scoreable (separate scorecards) ──
    "lighting_zone":  {"scoreable": False, "method": None, "reason": "availability_only"},
    "luminaire":      {"scoreable": False, "method": None, "reason": "availability_only"},
    "dali":           {"scoreable": False, "method": None, "reason": "control_status_only"},
    "dali_zone":      {"scoreable": False, "method": None, "reason": "control_status_only"},
    "dali_controller":{"scoreable": False, "method": None, "reason": "control_status_only"},
    "zone_sensor":    {"scoreable": False, "method": None, "reason": "signal_quality_only"},
    "outdoor_air_sensor":{"scoreable": False, "method": None, "reason": "signal_quality_only"},
    "general":        {"scoreable": False, "method": None, "reason": "not_a_device"},
    "weather":        {"scoreable": False, "method": None, "reason": "external_data_source"},
}


def get_scoreability(equipment_type: str) -> dict:
    """Get scoreability config for an equipment type.

    Checks Supabase equipment_type_config table first for runtime overrides.
    Falls back to hardcoded defaults. Unknown types default to non-scoreable.
    """
    try:
        from app.database.supabase_client import get_supabase_client

        supabase = get_supabase_client()
        override = (
            supabase.table("equipment_type_config")
            .select("scoreable,scoring_method,reason")
            .eq("equipment_type", equipment_type)
            .limit(1)
            .execute()
        )
        if override.data:
            return {
                "scoreable": override.data[0]["scoreable"],
                "method": override.data[0].get("scoring_method"),
                "reason": override.data[0].get("reason"),
            }
    except Exception:
        pass

    return EQUIPMENT_HEALTH_SCOREABILITY.get(
        equipment_type,
        {"scoreable": False, "method": None, "reason": "unknown_type"},
    )
