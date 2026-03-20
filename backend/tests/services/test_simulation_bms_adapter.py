from app.services.simbiot.bms_adapter import BmsConnectionConfig, BmsWriteRequest
from app.services.simbiot.simulation_bms_adapter import SimulationBmsAdapter
from app.services.simulation_store import get_simulation_store


class TestSimulationBmsAdapter:
    async def test_discovers_devices_and_points_from_simulation_store(self):
        site_id = "site-sim-adapter-001"
        store = get_simulation_store(site_id)
        store.reset()
        store.update_equipment_state("S001-FCU-201", {"health_score": 88.5, "status": "online"})
        store.write_sensor_readings(
            [
                {
                    "equipment_code": "S001-FCU-201",
                    "point_name": "room_temp",
                    "value": 22.4,
                    "timestamp": "2026-03-16T08:00:00Z",
                    "site_id": site_id,
                },
                {
                    "equipment_code": "S001-FCU-201",
                    "point_name": "room_temp",
                    "value": 22.8,
                    "timestamp": "2026-03-16T09:00:00Z",
                    "site_id": site_id,
                },
                {
                    "equipment_code": "S001-FCU-201",
                    "point_name": "fan_status",
                    "value": True,
                    "timestamp": "2026-03-16T09:00:00Z",
                    "site_id": site_id,
                },
            ]
        )

        adapter = SimulationBmsAdapter()
        await adapter.connect(BmsConnectionConfig(site_id=site_id, source_type="simulation"))

        devices = await adapter.discover_devices()
        points = await adapter.discover_points("S001-FCU-201")
        room_temp = await adapter.read_point("S001-FCU-201", "room_temp")

        assert {device.device_id for device in devices} == {"S001-FCU-201"}
        assert {point.point_id for point in points} >= {"room_temp", "fan_status", "health_score", "status"}
        assert room_temp.value == 22.8
        assert room_temp.metadata["source"] == "sensor_readings"

        store.reset()

    async def test_write_point_persists_command_override(self):
        site_id = "site-sim-adapter-002"
        store = get_simulation_store(site_id)
        store.reset()
        store.update_equipment_state("S002-AHU-B1-001", {"health_score": 91.0, "status": "online"})

        adapter = SimulationBmsAdapter()
        await adapter.connect(BmsConnectionConfig(site_id=site_id, source_type="simulation"))

        success = await adapter.write_point(
            BmsWriteRequest(
                device_id="S002-AHU-B1-001",
                point_id="supply_temp_setpoint",
                value=13.5,
                priority=14,
                user="tester",
            )
        )
        written_value = await adapter.read_point("S002-AHU-B1-001", "supply_temp_setpoint")
        points = await adapter.discover_points("S002-AHU-B1-001")

        assert success is True
        assert written_value.value == 13.5
        assert written_value.metadata["source"] == "command_override"
        assert any(point.point_id == "supply_temp_setpoint" and point.writable for point in points)

        store.reset()
