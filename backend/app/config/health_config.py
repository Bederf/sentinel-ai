"""
Health scoring configuration — equipment scoreability by type.

Supabase is the source of truth. This config provides defaults;
runtime overrides can be added to the equipment_type_config table.

Scoreability resolution (in order):
1. Supabase equipment_type_config table (runtime overrides)
2. EQUIPMENT_HEALTH_SCOREABILITY dict (detailed per-type config)
3. MECHANICAL_TYPES frozenset → scoreable
4. PASSIVE_TYPES frozenset → not scoreable
5. Default → scoreable (fail-open for novel equipment types)
"""

MECHANICAL_TYPES = frozenset({
    # HVAC
    "ahu",
    "fcu",
    "vav",
    "chiller",
    "cooling_tower",
    "boiler",
    "pump",
    "heat_exchanger",
    "air_handler",
    # Electrical / power
    "generator",
    "ups",
    "bess",
    "inverter",
    "transfer_switch",
    # Other active
    "compressor",
    "fan",
    "motor",
    # Renewable / electrical generation
    "solar_panel",
    "pv_array",
})

PASSIVE_TYPES = frozenset({
    "dali",
    "dali_controller",
    "dali_zone",
    "lighting",
    "lighting_panel",
    "lighting_zone",
    "lighting_driver",
    "luminaire",
    "meter",
    "submeter",
    "energy_meter",
    "water_meter",
    "sensor",
    "co2_sensor",
    "temp_sensor",
    "humidity_sensor",
    "outdoor_air_sensor",
    "zone_sensor",
    "weather_station",
    "access_control",
    "access_control_server",
    "door",
    "gate",
    "barrier",
    "camera",
    "security_camera",
    "pir",
    "scene_controller",
    "general",
    "weather",
    "zone",
})

EQUIPMENT_HEALTH_SCOREABILITY: dict[str, dict] = {
    # ── Mechanical (rotating/heat-exchange): full 5-factor scoring ──
    "chiller": {"scoreable": True, "method": "age_only", "reason": "mechanical"},
    "ahu": {"scoreable": True, "method": "age_only", "reason": "mechanical"},
    "pump": {"scoreable": True, "method": "age_only", "reason": "mechanical"},
    "generator": {"scoreable": True, "method": "age_only", "reason": "mechanical"},
    "cooling_tower": {"scoreable": True, "method": "age_only", "reason": "mechanical"},
    # ── VAV/FCU: synthetic fallback while awaiting service data ──
    "vav": {"scoreable": True, "method": "synthetic_fallback", "reason": "mechanical"},
    "VAV": {"scoreable": True, "method": "synthetic_fallback", "reason": "mechanical"},
    "FCU": {"scoreable": True, "method": "synthetic_fallback", "reason": "mechanical"},
    "fcu": {"scoreable": True, "method": "synthetic_fallback", "reason": "mechanical"},
    # ── Electrical/power: now scoreable (Phase 226) ──
    "ups": {"scoreable": True, "method": "age_only", "reason": "electrical"},
    "bess": {"scoreable": True, "method": "age_only", "reason": "electrical"},
    "inverter": {"scoreable": True, "method": "age_only", "reason": "electrical"},
    "solar_panel": {"scoreable": True, "method": "age_only", "reason": "renewable"},
    # ── Not health-scoreable: passive / static ──
    "meter": {"scoreable": False, "method": None, "reason": "passive"},
    "zone": {"scoreable": False, "method": None, "reason": "not_a_device"},
    "lighting_zone": {"scoreable": False, "method": None, "reason": "passive"},
    "luminaire": {"scoreable": False, "method": None, "reason": "passive"},
    "dali": {"scoreable": False, "method": None, "reason": "passive"},
    "dali_zone": {"scoreable": False, "method": None, "reason": "passive"},
    "dali_controller": {"scoreable": False, "method": None, "reason": "passive"},
    "zone_sensor": {"scoreable": False, "method": None, "reason": "passive"},
    "outdoor_air_sensor": {"scoreable": False, "method": None, "reason": "passive"},
    "general": {"scoreable": False, "method": None, "reason": "not_a_device"},
    "weather": {"scoreable": False, "method": None, "reason": "external_data_source"},
    "lighting_panel": {"scoreable": False, "method": None, "reason": "passive"},
    "access_control": {"scoreable": False, "method": None, "reason": "passive"},
    "access_control_server": {"scoreable": False, "method": None, "reason": "passive"},
    "lighting_driver": {"scoreable": False, "method": None, "reason": "passive"},
    "scene_controller": {"scoreable": False, "method": None, "reason": "passive"},
    "weather_station": {"scoreable": False, "method": None, "reason": "passive"},
    "water_meter": {"scoreable": False, "method": None, "reason": "passive"},
    "security_camera": {"scoreable": False, "method": None, "reason": "passive"},
}


def is_mechanical(equipment_type: str) -> bool:
    """Check if equipment type is mechanical (eligible for health scoring)."""
    return equipment_type.lower() in MECHANICAL_TYPES


def is_passive(equipment_type: str) -> bool:
    """Check if equipment type is passive (excluded from health scoring)."""
    return equipment_type.lower() in PASSIVE_TYPES


def get_scoreability(equipment_type: str) -> dict:
    """Get scoreability config for an equipment type.

    Resolution order:
    1. Supabase equipment_type_config table (runtime overrides)
    2. EQUIPMENT_HEALTH_SCOREABILITY dict
    3. MECHANICAL_TYPES → scoreable (fail-open for novel mechanical types)
    4. PASSIVE_TYPES → not scoreable
    5. Default → scoreable (fail-open for novel equipment types)
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

    from_cache = EQUIPMENT_HEALTH_SCOREABILITY.get(equipment_type)
    if from_cache is not None:
        return from_cache

    if is_mechanical(equipment_type):
        return {"scoreable": True, "method": "age_only", "reason": "mechanical"}

    if is_passive(equipment_type):
        return {"scoreable": False, "method": None, "reason": "passive"}

    return {"scoreable": True, "method": "age_only", "reason": "unknown_type"}
