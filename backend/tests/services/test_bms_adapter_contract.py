from app.services.simbiot.bms_adapter import (
    BmsAdapter,
    BmsAdapterCapabilities,
    BmsConnectionConfig,
    BmsConnectionStatus,
    BmsDeviceDescriptor,
    BmsPointDescriptor,
    BmsPointValue,
    BmsWriteRequest,
)


class FakeBmsAdapter(BmsAdapter):
    @property
    def adapter_id(self) -> str:
        return "fake"

    @property
    def capabilities(self) -> BmsAdapterCapabilities:
        return BmsAdapterCapabilities()

    async def connect(self, config: BmsConnectionConfig) -> BmsConnectionStatus:
        return BmsConnectionStatus(
            connected=True,
            site_id=config.site_id,
            source_type=config.source_type,
            status="connected",
        )

    async def disconnect(self) -> None:
        return None

    async def get_status(self) -> BmsConnectionStatus:
        return BmsConnectionStatus(
            connected=True,
            site_id="site-002",
            source_type="fake",
            status="connected",
        )

    async def discover_devices(self) -> list[BmsDeviceDescriptor]:
        return [BmsDeviceDescriptor(device_id="dev-1", display_name="Device 1", protocol="fake")]

    async def discover_points(self, device_id: str) -> list[BmsPointDescriptor]:
        return [BmsPointDescriptor(point_id="p1", point_name="temp", point_type="analog", unit="C")]

    async def read_point(self, device_id: str, point_id: str) -> BmsPointValue:
        return BmsPointValue(device_id=device_id, point_id=point_id, value=21.5, unit="C")

    async def write_point(self, request: BmsWriteRequest) -> bool:
        return True


class TestBmsAdapterContract:
    async def test_default_bulk_read_delegates_to_single_point_reads(self):
        adapter = FakeBmsAdapter()

        values = await adapter.read_points("dev-1", ["p1", "p2"])

        assert [value.point_id for value in values] == ["p1", "p2"]
        assert all(value.device_id == "dev-1" for value in values)

    async def test_default_subscription_methods_fail_closed(self):
        adapter = FakeBmsAdapter()

        try:
            await adapter.subscribe_points("dev-1", ["p1"])
        except NotImplementedError as exc:
            assert "does not support subscriptions" in str(exc)
        else:
            raise AssertionError("Expected subscribe_points to reject unsupported subscriptions")
