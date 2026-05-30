from __future__ import annotations

from app.adapters.residential.base import ResidentialEnergyAdapter
from app.adapters.residential.solarman import SolarmanAdapter
from app.adapters.residential.victron_vrm import VictronVRMAdapter

SUPPORTED_PLATFORMS: dict[str, dict] = {
    "solarman": {
        "name": "SOLARMAN Smart",
        "adapter_class": SolarmanAdapter,
        "brands": ["Deye", "Sofar", "Ginlong", "SOLIS"],
    },
    "victron": {
        "name": "Victron VRM",
        "adapter_class": VictronVRMAdapter,
        "brands": ["Victron Energy"],
    },
}


def build_adapter(platform: str, site_config: dict, **kwargs) -> ResidentialEnergyAdapter:
    """Instantiate the correct adapter for the given platform.

    Raises ValueError for unknown platforms — never returns None.
    """
    if platform not in SUPPORTED_PLATFORMS:
        raise ValueError(
            f"Unsupported platform '{platform}'. "
            f"Supported: {list(SUPPORTED_PLATFORMS)}"
        )
    cls = SUPPORTED_PLATFORMS[platform]["adapter_class"]
    return cls(site_config=site_config, **kwargs)
