"""Registry and factory for SIMBIOT BMS adapters."""

from __future__ import annotations

from typing import Type

from .bms_adapter import BmsAdapter
from .policy_enforced_bms_adapter import PolicyEnforcedBmsAdapter

_BMS_ADAPTERS: dict[str, Type[BmsAdapter]] = {}

# Vendor/source aliases map onto concrete adapter implementations.
_ADAPTER_ALIASES: dict[str, str] = {
    "simulation": "simulation",
    "simulated": "simulation",
    "bacnet": "bacnet",
    "niagara": "bacnet",
    "desigo": "bacnet",
    "metasys": "bacnet",
    "honeywell": "bacnet",
    "schneider": "bacnet",
    "trend": "bacnet",
    "generic": "bacnet",
    "obix": "obix",
}


def register_bms_adapter(adapter_type: str, adapter_cls: Type[BmsAdapter]) -> None:
    """Register a concrete BMS adapter implementation."""
    _BMS_ADAPTERS[adapter_type.lower()] = adapter_cls


def resolve_bms_adapter_type(
    adapter_type: str | None = None,
    bms_vendor: str | None = None,
    device_ip: str | None = None,
) -> str:
    """Resolve a requested adapter or vendor to a concrete adapter type."""
    requested = adapter_type or bms_vendor or ("simulation" if device_ip == "simulation" else "bacnet")
    return _ADAPTER_ALIASES.get(requested.lower(), requested.lower())


def create_bms_adapter(
    adapter_type: str | None = None,
    bms_vendor: str | None = None,
    device_ip: str | None = None,
) -> BmsAdapter:
    """Create a concrete BMS adapter instance."""
    _register_default_adapters()
    resolved = resolve_bms_adapter_type(adapter_type=adapter_type, bms_vendor=bms_vendor, device_ip=device_ip)
    adapter_cls = _BMS_ADAPTERS.get(resolved)
    if adapter_cls is None:
        raise ValueError(f"No BMS adapter registered for '{resolved}'")
    return PolicyEnforcedBmsAdapter(adapter_cls())


def _register_default_adapters() -> None:
    """Register built-in adapters once."""
    if _BMS_ADAPTERS:
        return

    from .bacnet_bms_adapter import BacnetBmsAdapter
    from .simulation_bms_adapter import SimulationBmsAdapter

    register_bms_adapter("bacnet", BacnetBmsAdapter)
    register_bms_adapter("simulation", SimulationBmsAdapter)
