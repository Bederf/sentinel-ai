from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.module_registry import ModuleType
from app.services.niagara.mapping_service import EquipmentMapping
from app.services.niagara.point_classifier import ClassifiedPoint, ConfidenceLevel, PointType
from app.services.simbiot import BmsConnectionConfig, BmsPointDescriptor, BmsWriteRequest
from app.services.simbiot.connection_policy import (
    filter_classified_points_for_site,
    filter_equipment_mappings_for_site,
)
from app.services.simbiot.policy_enforced_bms_adapter import PolicyEnforcedBmsAdapter


@pytest.mark.unit
class TestPolicyEnforcedBmsAdapter:
    @pytest.mark.asyncio
    async def test_blocks_runtime_access_when_site_processing_is_disabled(self):
        inner = MagicMock()
        inner.capabilities = MagicMock()
        inner.connect = AsyncMock()
        inner.disconnect = AsyncMock()

        adapter = PolicyEnforcedBmsAdapter(inner)

        with patch(
            "app.services.simbiot.policy_enforced_bms_adapter.is_runtime_processing_enabled",
            AsyncMock(return_value=False),
        ):
            status = await adapter.connect(BmsConnectionConfig(site_id="site-002", source_type="bacnet"))

        assert status.connected is False
        assert status.status == "blocked"
        inner.connect.assert_not_awaited()

        with pytest.raises(ConnectionError):
            await adapter.discover_devices()

    @pytest.mark.asyncio
    async def test_filters_discovered_points_by_module_policy(self):
        inner = MagicMock()
        inner.capabilities = MagicMock()
        inner.connect = AsyncMock(return_value=MagicMock(connected=True))
        inner.get_status = AsyncMock(return_value=MagicMock())
        inner.disconnect = AsyncMock()
        inner.discover_points = AsyncMock(
            return_value=[
                BmsPointDescriptor(point_id="room_temp", point_name="room_temp", point_type="analog"),
                BmsPointDescriptor(point_id="pv_power_kw", point_name="pv_power_kw", point_type="analog"),
            ]
        )

        adapter = PolicyEnforcedBmsAdapter(inner)

        with (
            patch(
                "app.services.simbiot.policy_enforced_bms_adapter.is_runtime_processing_enabled",
                AsyncMock(return_value=True),
            ),
            patch(
                "app.services.simbiot.policy_enforced_bms_adapter.is_point_allowed_for_site",
                side_effect=[True, False],
            ),
        ):
            await adapter.connect(BmsConnectionConfig(site_id="site-002", source_type="simulation"))
            points = await adapter.discover_points("S002-AHU-L1-001")

        assert [point.point_id for point in points] == ["room_temp"]

    @pytest.mark.asyncio
    async def test_blocks_writes_for_inactive_module_points(self):
        inner = MagicMock()
        inner.capabilities = MagicMock()
        inner.connect = AsyncMock(return_value=MagicMock(connected=True))
        inner.get_status = AsyncMock(return_value=MagicMock())
        inner.disconnect = AsyncMock()
        inner.write_point = AsyncMock(return_value=True)

        adapter = PolicyEnforcedBmsAdapter(inner)

        with (
            patch(
                "app.services.simbiot.policy_enforced_bms_adapter.is_runtime_processing_enabled",
                AsyncMock(return_value=True),
            ),
            patch(
                "app.services.simbiot.policy_enforced_bms_adapter.is_point_allowed_for_site",
                return_value=False,
            ),
        ):
            await adapter.connect(BmsConnectionConfig(site_id="site-002", source_type="simulation"))
            with pytest.raises(PermissionError):
                await adapter.write_point(
                    BmsWriteRequest(
                        device_id="S002-PV-R-001",
                        point_id="pv_power_kw",
                        value=42.0,
                    )
                )

        inner.write_point.assert_not_awaited()


@pytest.mark.unit
class TestConnectionPolicyFilters:
    def test_filters_classified_points_for_explicit_module_config(self):
        hvac_point = ClassifiedPoint(
            original_name="S002-AHU-L1-001.room_temp",
            equipment_type="ahu",
            point_type=PointType.SENSOR,
            confidence=ConfidenceLevel.HIGH,
            instance=1,
        )
        solar_point = ClassifiedPoint(
            original_name="S002-PV-R-001.pv_power_kw",
            equipment_type="solar",
            point_type=PointType.SENSOR,
            confidence=ConfidenceLevel.HIGH,
            instance=2,
        )

        with (
            patch("app.services.simbiot.connection_policy.module_registry.get_site_config", return_value=object()),
            patch(
                "app.services.simbiot.connection_policy.module_registry.get_active_modules",
                return_value=[SimpleNamespace(module_type=ModuleType.HVAC)],
            ),
        ):
            filtered, dropped = filter_classified_points_for_site("site-002", [hvac_point, solar_point])

        assert [point.original_name for point in filtered] == ["S002-AHU-L1-001.room_temp"]
        assert dropped == 1

    def test_filters_equipment_mappings_for_explicit_module_config(self):
        hvac_mapping = EquipmentMapping("S002-AHU-L1-001", "ahu", site_id="site-002")
        solar_mapping = EquipmentMapping("S002-PV-R-001", "solar", site_id="site-002")

        with (
            patch("app.services.simbiot.connection_policy.module_registry.get_site_config", return_value=object()),
            patch(
                "app.services.simbiot.connection_policy.module_registry.get_active_modules",
                return_value=[SimpleNamespace(module_type=ModuleType.HVAC)],
            ),
        ):
            filtered, dropped = filter_equipment_mappings_for_site(
                "site-002",
                {
                    hvac_mapping.equipment_id: hvac_mapping,
                    solar_mapping.equipment_id: solar_mapping,
                },
            )

        assert list(filtered.keys()) == ["S002-AHU-L1-001"]
        assert dropped == ["S002-PV-R-001"]
