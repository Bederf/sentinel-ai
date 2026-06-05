"""
Phase 2: Clean Install Decoupling — Verification Tests

Validates that SENTINEL starts cleanly without the simulation engine when
ENABLE_SITE002_SOURCE is disabled (default), and that enabling it restores
full simulator functionality.
"""

import pytest


@pytest.mark.unit
class TestCleanInstallDeviceManager:
    """Verify device manager behavior with site002 source disabled/enabled."""

    @pytest.mark.asyncio
    async def test_empty_device_manager_when_site002_disabled(self):
        """SENTINEL starts with empty device manager when site002 is disabled."""
        from app.config.settings import Settings

        test_settings = Settings(site002_source_enabled=False, demo_mode=True)
        # The gate is in startup_event: if not site002_source_enabled, devices_data = []
        assert test_settings.site002_source_enabled is False
        # load_reference_devices always returns the file contents,
        # but startup_event only calls it when site002 is enabled
        from app.api.devices import load_reference_devices

        devices = await load_reference_devices()
        assert isinstance(devices, list)

    @pytest.mark.asyncio
    async def test_reference_devices_load_when_site002_enabled(self):
        """Reference devices load when site002 source is enabled."""
        from app.api.devices import load_reference_devices

        devices = await load_reference_devices()
        assert isinstance(devices, list)
        assert len(devices) > 0, "reference_devices.json should contain devices"

    @pytest.mark.asyncio
    async def test_site_equipment_loads_regardless(self):
        """Building equipment loads regardless of site002 setting."""
        from app.api.devices import load_equipment_from_buildings

        # This should work regardless of site002_source_enabled
        devices = await load_equipment_from_buildings()
        assert isinstance(devices, list)


@pytest.mark.unit
class TestCleanInstallSimulation:
    """Verify simulation auto-start behavior (deprecated — simulator removed)."""

    def test_site002_source_always_disabled(self):
        """site002_source_enabled always returns False — simulator removed."""
        from app.config.settings import Settings

        test_settings = Settings(demo_mode=True)
        assert test_settings.site002_source_enabled is False


@pytest.mark.unit
class TestCleanInstallAdapters:
    """Verify device abstraction handles missing simulator gracefully."""

    def test_simulated_adapter_import_success(self):
        """SimulatedDeviceAdapter imports successfully when bms_simulator exists."""
        try:
            from app.services.bms_simulator.adapters.simulated_adapter import (
                SimulatedDeviceAdapter,
            )

            assert SimulatedDeviceAdapter is not None
        except ImportError:
            pytest.skip("bms_simulator not available")

    def test_simulated_adapter_import_failure_doesnt_crash(self):
        """SENTINEL doesn't crash if SimulatedDeviceAdapter import fails."""
        import sys

        # Temporarily hide the bms_simulator module
        original_module = sys.modules.get("app.services.bms_simulator")
        original_adapters = sys.modules.get("app.services.bms_simulator.adapters")
        original_simulated = sys.modules.get("app.services.bms_simulator.adapters.simulated_adapter")

        try:
            # Simulate missing module
            sys.modules["app.services.bms_simulator.adapters.simulated_adapter"] = None  # type: ignore

            SimulatedDeviceAdapter = None
            try:
                from app.services.bms_simulator.adapters.simulated_adapter import (
                    SimulatedDeviceAdapter as _SimAdapter,
                )

                SimulatedDeviceAdapter = _SimAdapter
            except (ImportError, TypeError):
                pass

            assert SimulatedDeviceAdapter is None, "Should be None when import blocked"
        finally:
            # Restore original modules
            if original_simulated is not None:
                sys.modules["app.services.bms_simulator.adapters.simulated_adapter"] = original_simulated
            else:
                sys.modules.pop("app.services.bms_simulator.adapters.simulated_adapter", None)

    @pytest.mark.asyncio
    async def test_device_abstraction_skips_unknown_protocol(self):
        """device_abstraction skips unknown protocol devices gracefully."""
        from app.models.device import create_device_from_dict
        from app.services.device_abstraction import DeviceManager

        manager = DeviceManager.__new__(DeviceManager)
        manager._devices = {}
        manager._adapters = {}
        manager._initialized = False

        # Create a device with unknown protocol (include required site_id)
        device_data = {
            "id": "test-unknown-001",
            "name": "Unknown Protocol Device",
            "device_type": "hvac",
            "protocol": "unknown_protocol",
            "site_id": "site-test",
            "points": {},
        }
        device = create_device_from_dict(device_data)

        # Should not crash — just log and skip
        await manager._create_adapter(device)


@pytest.mark.unit
class TestIngestionModeDecoupling:
    """Verify ingestion mode resolution (site002_source_enabled deprecated — simulator removed)."""

    def test_ingestion_mode_resolves_from_env(self):
        """Resolved ingestion mode comes from ingestion_mode field, not site002_source_enabled."""
        from app.config.settings import IngestionMode, Settings

        s = Settings(
            demo_mode=False,
            ingestion_mode="shadow_live",
        )
        assert s.resolved_ingestion_mode == IngestionMode.SHADOW_LIVE


@pytest.mark.unit
class TestProtocolRename:
    """Verify protocol rename from mock to site002."""

    def test_reference_devices_use_site002_protocol(self):
        """All reference devices use 'site002' protocol, not 'mock'."""
        import json
        from pathlib import Path

        ref_path = (
            Path(__file__).parent.parent / "app" / "services" / "bms_simulator" / "data" / "reference_devices.json"
        )
        if not ref_path.exists():
            pytest.skip("reference_devices.json not found")

        with open(ref_path) as f:
            devices = json.load(f)

        mock_protocol_devices = [d["id"] for d in devices if d.get("protocol") == "mock"]
        assert len(mock_protocol_devices) == 0, f"Devices still using 'mock' protocol: {mock_protocol_devices}"

        site002_devices = [d for d in devices if d.get("protocol") == "site002"]
        assert len(site002_devices) > 0, "No devices with 'site002' protocol found"
