"""Connector and ingestion policy enforcement for SIMBIOT.

This module centralizes two building-level rules:

1. Site processing gate:
   When site processing is off, runtime SIMBIOT reads/writes must stop.
2. Module gating:
   When a site module is explicitly inactive, points/equipment for that
   subsystem are ignored even if the upstream BMS exposes them.

Commissioning sessions are allowed to bypass the runtime processing gate so
the onboarding wizard can discover and classify a disconnected building
before activation.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.models.module_registry import ModuleType
from app.services.module_registry_service import module_registry

_EQUIPMENT_TYPE_TO_MODULE: dict[str, ModuleType] = {
    "ahu": ModuleType.HVAC,
    "chiller": ModuleType.HVAC,
    "crac": ModuleType.HVAC,
    "ct": ModuleType.HVAC,
    "cooling_tower": ModuleType.HVAC,
    "fcu": ModuleType.HVAC,
    "hvac": ModuleType.HVAC,
    "pump": ModuleType.HVAC,
    "split": ModuleType.HVAC,
    "theatre_ahu": ModuleType.HVAC,
    "vav": ModuleType.HVAC,
    "dali": ModuleType.LIGHTING,
    "dali_controller": ModuleType.LIGHTING,
    "emergency_luminaire": ModuleType.LIGHTING,
    "light_sensor": ModuleType.LIGHTING,
    "lighting": ModuleType.LIGHTING,
    "lum": ModuleType.LIGHTING,
    "luminaire": ModuleType.LIGHTING,
    "ats": ModuleType.ENERGY,
    "energy": ModuleType.ENERGY,
    "gen": ModuleType.ENERGY,
    "generator": ModuleType.ENERGY,
    "meter": ModuleType.ENERGY,
    "mtr": ModuleType.ENERGY,
    "msb": ModuleType.ENERGY,
    "power": ModuleType.ENERGY,
    "transformer": ModuleType.ENERGY,
    "tx": ModuleType.ENERGY,
    "ups": ModuleType.ENERGY,
    "battery": ModuleType.SOLAR,
    "bess": ModuleType.SOLAR,
    "inv": ModuleType.SOLAR,
    "inverter": ModuleType.SOLAR,
    "pv": ModuleType.SOLAR,
    "solar": ModuleType.SOLAR,
    "flow": ModuleType.WATER,
    "water": ModuleType.WATER,
    "water_meter": ModuleType.WATER,
    "alarm_panel": ModuleType.FIRE,
    "detector": ModuleType.FIRE,
    "fire": ModuleType.FIRE,
    "access": ModuleType.SECURITY,
    "badge": ModuleType.SECURITY,
    "cctv": ModuleType.SECURITY,
    "intrusion": ModuleType.SECURITY,
    "occupancy": ModuleType.SECURITY,
    "security": ModuleType.SECURITY,
}

_KEYWORD_TO_MODULE: dict[str, ModuleType] = {
    "ahu": ModuleType.HVAC,
    "chiller": ModuleType.HVAC,
    "chw": ModuleType.HVAC,
    "cooling tower": ModuleType.HVAC,
    "crac": ModuleType.HVAC,
    "fcu": ModuleType.HVAC,
    "hvac": ModuleType.HVAC,
    "supply air": ModuleType.HVAC,
    "vav": ModuleType.HVAC,
    "dali": ModuleType.LIGHTING,
    "daylight": ModuleType.LIGHTING,
    "lighting": ModuleType.LIGHTING,
    "lum": ModuleType.LIGHTING,
    "luminaire": ModuleType.LIGHTING,
    "scene": ModuleType.LIGHTING,
    "lux": ModuleType.LIGHTING,
    "ats": ModuleType.ENERGY,
    "energy": ModuleType.ENERGY,
    "gen": ModuleType.ENERGY,
    "generator": ModuleType.ENERGY,
    "kwh": ModuleType.ENERGY,
    "kw": ModuleType.ENERGY,
    "meter": ModuleType.ENERGY,
    "power": ModuleType.ENERGY,
    "ups": ModuleType.ENERGY,
    "voltage": ModuleType.ENERGY,
    "solar": ModuleType.SOLAR,
    "pv": ModuleType.SOLAR,
    "bess": ModuleType.SOLAR,
    "battery": ModuleType.SOLAR,
    "inverter": ModuleType.SOLAR,
    "water": ModuleType.WATER,
    "flow": ModuleType.WATER,
    "liters": ModuleType.WATER,
    "smoke": ModuleType.FIRE,
    "fire": ModuleType.FIRE,
    "alarm": ModuleType.FIRE,
    "door": ModuleType.SECURITY,
    "access": ModuleType.SECURITY,
    "badge": ModuleType.SECURITY,
    "cctv": ModuleType.SECURITY,
    "occupancy": ModuleType.SECURITY,
    "security": ModuleType.SECURITY,
}


@dataclass(slots=True)
class SiteConnectorPolicy:
    """Effective connector policy for one site."""

    site_id: str
    processing_enabled: bool
    has_explicit_module_config: bool
    active_modules: frozenset[ModuleType]

    def allows_module(self, module_type: ModuleType | None) -> bool:
        if module_type is None or not self.has_explicit_module_config:
            return True
        return module_type in self.active_modules


async def is_runtime_processing_enabled(site_id: str, *, commissioning: bool = False) -> bool:
    """Return True when runtime connector activity is allowed for a site."""
    if commissioning:
        return True

    from app.api.sites import is_site_processing_enabled

    return await is_site_processing_enabled(site_id)


def get_site_connector_policy(site_id: str) -> SiteConnectorPolicy:
    """Return the current explicit module policy for a site.

    Fail open when a site has no module config yet. That keeps onboarding and
    legacy sites working until a site-specific module set exists.
    """
    config = module_registry.get_site_config(site_id)
    if config is None:
        return SiteConnectorPolicy(
            site_id=site_id,
            processing_enabled=True,
            has_explicit_module_config=False,
            active_modules=frozenset(),
        )

    active_modules = frozenset(module.module_type for module in module_registry.get_active_modules(site_id))
    return SiteConnectorPolicy(
        site_id=site_id,
        processing_enabled=True,
        has_explicit_module_config=True,
        active_modules=active_modules,
    )


def infer_module_from_equipment_type(equipment_type: str | None) -> ModuleType | None:
    """Map a normalized equipment type to a site module when possible."""
    if not equipment_type:
        return None

    normalized = equipment_type.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in _EQUIPMENT_TYPE_TO_MODULE:
        return _EQUIPMENT_TYPE_TO_MODULE[normalized]

    return _EQUIPMENT_TYPE_TO_MODULE.get(normalized.split("_")[-1])


def infer_module_from_identifiers(*values: str | None) -> ModuleType | None:
    """Best-effort module inference from point/device identifiers."""
    tokens = " ".join(value for value in values if value).lower().replace("-", " ").replace("_", " ")
    if not tokens:
        return None

    for keyword, module_type in _KEYWORD_TO_MODULE.items():
        if keyword in tokens:
            return module_type
    return None


def is_point_allowed_for_site(
    site_id: str,
    *,
    device_id: str | None = None,
    point_id: str | None = None,
    point_name: str | None = None,
    equipment_type: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Return True when a point is allowed by the site's explicit module policy."""
    policy = get_site_connector_policy(site_id)
    if not policy.has_explicit_module_config:
        return True

    module_type = infer_module_from_equipment_type(equipment_type)
    if module_type is None:
        metadata = metadata or {}
        module_type = infer_module_from_identifiers(
            equipment_type,
            device_id,
            point_id,
            point_name,
            str(metadata.get("description") or ""),
            str(metadata.get("module_hint") or ""),
        )

    return policy.allows_module(module_type)


def filter_classified_points_for_site(site_id: str, classified_points: Iterable[Any]) -> tuple[list[Any], int]:
    """Drop classified points for modules that are explicitly inactive."""
    policy = get_site_connector_policy(site_id)
    if not policy.has_explicit_module_config:
        return list(classified_points), 0

    filtered: list[Any] = []
    dropped = 0

    for point in classified_points:
        equipment_type = getattr(point, "equipment_type", None)
        original_name = getattr(point, "original_name", None)
        standardized_name = getattr(point, "standardized_name", None)
        original_description = getattr(point, "original_description", None)
        point_category = getattr(point, "point_category", None)
        module_type = infer_module_from_equipment_type(equipment_type) or infer_module_from_identifiers(
            equipment_type,
            original_name,
            standardized_name,
            original_description,
            point_category,
        )
        if policy.allows_module(module_type):
            filtered.append(point)
        else:
            dropped += 1

    return filtered, dropped


def filter_equipment_mappings_for_site(site_id: str, mappings: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Drop equipment mappings for modules that are explicitly inactive."""
    policy = get_site_connector_policy(site_id)
    if not policy.has_explicit_module_config:
        return dict(mappings), []

    filtered: dict[str, Any] = {}
    dropped: list[str] = []

    for equipment_id, mapping in mappings.items():
        if equipment_id == "UNASSIGNED":
            filtered[equipment_id] = mapping
            continue

        equipment_type = getattr(mapping, "equipment_type", None)
        metadata = getattr(mapping, "metadata", {}) or {}
        module_type = infer_module_from_equipment_type(equipment_type) or infer_module_from_identifiers(
            equipment_id,
            equipment_type,
            str(metadata.get("bms_original_id") or ""),
        )
        if policy.allows_module(module_type):
            filtered[equipment_id] = mapping
        else:
            dropped.append(equipment_id)

    return filtered, dropped
