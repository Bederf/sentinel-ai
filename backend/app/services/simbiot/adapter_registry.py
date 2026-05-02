"""Registry and factory for SIMBIOT BMS adapters."""

from __future__ import annotations

from .bms_adapter import BmsAdapter
from .modbus_bms_adapter import ModbusBmsAdapter
from .obix_bms_adapter import ObixBmsAdapter
from .policy_enforced_bms_adapter import PolicyEnforcedBmsAdapter

_BMS_ADAPTERS: dict[str, type[BmsAdapter]] = {}

# Vendor/source aliases map onto concrete adapter implementations.
_ADAPTER_ALIASES: dict[str, str] = {
    "bacnet": "bacnet",
    "niagara": "obix",
    "desigo": "bacnet",
    "metasys": "bacnet",
    "honeywell": "bacnet",
    "schneider": "bacnet",
    "trend": "bacnet",
    "generic": "bacnet",
    "obix": "obix",
    "modbus": "modbus",
}


def register_bms_adapter(adapter_type: str, adapter_cls: type[BmsAdapter]) -> None:
    """Register a concrete BMS adapter implementation."""
    _BMS_ADAPTERS[adapter_type.lower()] = adapter_cls


def resolve_bms_adapter_type(
    adapter_type: str | None = None,
    bms_vendor: str | None = None,
    device_ip: str | None = None,  # noqa: ARG001 - reserved for future discovery use
) -> str:
    """Resolve a requested adapter or vendor to a concrete adapter type."""
    requested = adapter_type or bms_vendor or "bacnet"
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

    register_bms_adapter("bacnet", BacnetBmsAdapter)
    register_bms_adapter("obix", ObixBmsAdapter)
    register_bms_adapter("modbus", ModbusBmsAdapter)
