from __future__ import annotations

from app.adapters.residential.base import ResidentialEnergyAdapter
from app.adapters.residential.solarman import SolarmanAdapter
from app.adapters.residential.victron_vrm import VictronVRMAdapter

SUPPORTED_PLATFORMS: dict[str, dict] = {
    "solarman": {
        "name": "SOLARMAN Smart",
        "adapter_class": SolarmanAdapter,
        "connection_type": "cloud_poll",
        "brands": ["Deye", "Sofar", "Ginlong", "SOLIS"],
    },
    "victron": {
        "name": "Victron VRM",
        "adapter_class": VictronVRMAdapter,
        "connection_type": "cloud_poll",
        "brands": ["Victron Energy"],
    },
    "home_assistant": {
        "name": "Home Assistant",
        "gateway_class": None,  # filled in after import to avoid circular
        "connection_type": "simbiot_gateway",
        "brands": ["Any HA-supported inverter"],
    },
}


def _lazy_load_ha_gateway():
    from app.gateways.home_assistant import HomeAssistantGateway

    return HomeAssistantGateway


SUPPORTED_PLATFORMS["home_assistant"]["gateway_class"] = _lazy_load_ha_gateway


def build_adapter(platform: str, site_config: dict, **kwargs) -> ResidentialEnergyAdapter:
    """Instantiate the correct adapter for the given platform.

    Raises ValueError for unknown platforms — never returns None.
    """
    if platform not in SUPPORTED_PLATFORMS:
        raise ValueError(f"Unsupported platform '{platform}'. Supported: {list(SUPPORTED_PLATFORMS)}")
    cfg = SUPPORTED_PLATFORMS[platform]
    if cfg.get("connection_type") == "simbiot_gateway":
        raise ValueError(
            f"Platform '{platform}' uses a SIMBIOT gateway, not an adapter. "
            "Use start_ha_gateway() from bridge_scheduler instead."
        )
    cls = cfg["adapter_class"]
    return cls(site_config=site_config, **kwargs)


def get_gateway_class(platform: str):
    """Return the gateway class for a platform, or None if it uses an adapter."""
    if platform not in SUPPORTED_PLATFORMS:
        return None
    return SUPPORTED_PLATFORMS[platform].get("gateway_class")


def is_simbiot_gateway(platform: str) -> bool:
    """True if this platform uses a SIMBIOT gateway (not a cloud polling adapter)."""
    return SUPPORTED_PLATFORMS.get(platform, {}).get("connection_type") == "simbiot_gateway"
