"""SIMBIOT integration contracts and adapters."""

from .bms_adapter import (
    BmsAdapter,
    BmsAdapterCapabilities,
    BmsConnectionConfig,
    BmsConnectionStatus,
    BmsDeviceDescriptor,
    BmsPointDescriptor,
    BmsPointValue,
    BmsSubscription,
    BmsWriteRequest,
)
from .adapter_registry import create_bms_adapter, register_bms_adapter, resolve_bms_adapter_type
from .bacnet_bms_adapter import BacnetBmsAdapter
from .connection_policy import (
    SiteConnectorPolicy,
    filter_classified_points_for_site,
    filter_equipment_mappings_for_site,
    get_site_connector_policy,
    infer_module_from_equipment_type,
    infer_module_from_identifiers,
    is_point_allowed_for_site,
    is_runtime_processing_enabled,
)
from .policy_enforced_bms_adapter import PolicyEnforcedBmsAdapter
from .simulation_bms_adapter import SimulationBmsAdapter

__all__ = [
    "BmsAdapter",
    "BmsAdapterCapabilities",
    "BmsConnectionConfig",
    "BmsConnectionStatus",
    "BmsDeviceDescriptor",
    "BmsPointDescriptor",
    "BmsPointValue",
    "BmsSubscription",
    "BmsWriteRequest",
    "create_bms_adapter",
    "register_bms_adapter",
    "resolve_bms_adapter_type",
    "BacnetBmsAdapter",
    "PolicyEnforcedBmsAdapter",
    "SimulationBmsAdapter",
    "SiteConnectorPolicy",
    "filter_classified_points_for_site",
    "filter_equipment_mappings_for_site",
    "get_site_connector_policy",
    "infer_module_from_equipment_type",
    "infer_module_from_identifiers",
    "is_point_allowed_for_site",
    "is_runtime_processing_enabled",
]
