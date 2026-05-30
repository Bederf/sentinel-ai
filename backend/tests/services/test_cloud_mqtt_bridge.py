from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.residential.schemas import DeviceManifest, EnergySnapshot
from app.services.residential.cloud_mqtt_bridge import CloudToMQTTBridge


def _make_snapshot(site_id: str = "site-test", device_id: str = "dev-001") -> EnergySnapshot:
    from datetime import datetime
    return EnergySnapshot(
        site_id=site_id,
        device_id=device_id,
        timestamp=datetime.utcnow(),
        pv_power_w=1500.0,
        battery_soc_pct=60.0,
        battery_power_w=None,
        grid_power_w=0.0,
        load_power_w=1400.0,
        grid_voltage_v=230.0,
        source_system="solarman",
    )


def _make_adapter(snapshot: EnergySnapshot | None = None) -> MagicMock:
    adapter = MagicMock()
    adapter.authenticate = AsyncMock(return_value=True)
    adapter.discover_devices = AsyncMock(
        return_value=[
            DeviceManifest(
                device_id="dev-001",
                device_name="Inverter",
                device_type="inverter",
                source_system="solarman",
                capabilities=["pv", "grid"],
            )
        ]
    )
    adapter.get_realtime = AsyncMock(return_value=snapshot or _make_snapshot())
    return adapter


# ── register / unregister ─────────────────────────────────────────────────────

def test_register_and_unregister_site():
    bridge = CloudToMQTTBridge()
    adapter = _make_adapter()
    bridge.register_site("site-test", adapter)
    assert "site-test" in bridge._sites
    bridge.unregister_site("site-test")
    assert "site-test" not in bridge._sites


def test_unregister_nonexistent_site_is_idempotent():
    bridge = CloudToMQTTBridge()
    bridge.unregister_site("does-not-exist")  # must not raise


# ── poll_site ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_poll_site_publishes_all_energy_fields():
    bridge = CloudToMQTTBridge()
    adapter = _make_adapter()
    bridge.register_site("site-test", adapter)

    published_topics: list[tuple[str, str, int, bool]] = []

    mock_info = MagicMock()
    mock_info.wait_for_publish = MagicMock()

    mock_client = MagicMock()
    mock_client.publish.side_effect = lambda topic, payload, qos, retain: (
        published_topics.append((topic, payload, qos, retain)) or mock_info
    )
    mock_client.connect = MagicMock()
    mock_client.disconnect = MagicMock()

    with patch("app.services.residential.cloud_mqtt_bridge.mqtt", create=True) as mock_mqtt:
        mock_mqtt.Client.return_value = mock_client
        await bridge.poll_site("site-test")

    topics = [t for t, *_ in published_topics]
    assert "sentinel/site-test/energy/pv_power_w" in topics
    assert "sentinel/site-test/energy/battery_soc_pct" in topics
    assert "sentinel/site-test/energy/battery_power_w" in topics
    assert "sentinel/site-test/energy/grid_power_w" in topics
    assert "sentinel/site-test/energy/load_power_w" in topics
    assert "sentinel/site-test/energy/grid_voltage_v" in topics


@pytest.mark.asyncio
async def test_poll_site_publishes_with_retain_true():
    bridge = CloudToMQTTBridge()
    adapter = _make_adapter()
    bridge.register_site("site-test", adapter)

    retain_flags: list[bool] = []
    mock_info = MagicMock()
    mock_info.wait_for_publish = MagicMock()
    mock_client = MagicMock()
    mock_client.publish.side_effect = lambda topic, payload, qos, retain: (
        retain_flags.append(retain) or mock_info
    )
    mock_client.connect = MagicMock()
    mock_client.disconnect = MagicMock()

    with patch("app.services.residential.cloud_mqtt_bridge.mqtt", create=True) as mock_mqtt:
        mock_mqtt.Client.return_value = mock_client
        await bridge.poll_site("site-test")

    assert all(retain_flags), "All publishes must have retain=True"


@pytest.mark.asyncio
async def test_poll_site_publishes_none_as_json_null():
    bridge = CloudToMQTTBridge()
    snap = _make_snapshot()
    snap.battery_power_w = None
    adapter = _make_adapter(snap)
    bridge.register_site("site-test", adapter)

    payloads: dict[str, str] = {}
    mock_info = MagicMock()
    mock_info.wait_for_publish = MagicMock()
    mock_client = MagicMock()
    mock_client.publish.side_effect = lambda topic, payload, qos, retain: (
        payloads.update({topic: payload}) or mock_info
    )
    mock_client.connect = MagicMock()
    mock_client.disconnect = MagicMock()

    with patch("app.services.residential.cloud_mqtt_bridge.mqtt", create=True) as mock_mqtt:
        mock_mqtt.Client.return_value = mock_client
        await bridge.poll_site("site-test")

    battery_power_payload = payloads.get("sentinel/site-test/energy/battery_power_w")
    assert battery_power_payload == "null", f"Expected 'null', got {battery_power_payload!r}"


@pytest.mark.asyncio
async def test_poll_site_unknown_site_is_noop():
    bridge = CloudToMQTTBridge()
    await bridge.poll_site("nonexistent-site")  # must not raise


@pytest.mark.asyncio
async def test_poll_site_backoff_after_max_failures():
    bridge = CloudToMQTTBridge()
    adapter = MagicMock()
    adapter.authenticate = AsyncMock(side_effect=Exception("Auth down"))
    bridge.register_site("site-test", adapter)

    from app.services.residential.cloud_mqtt_bridge import _MAX_AUTH_FAILURES

    for _ in range(_MAX_AUTH_FAILURES):
        with patch("app.services.residential.cloud_mqtt_bridge.mqtt"):
            await bridge.poll_site("site-test")

    state = bridge._sites["site-test"]
    assert state.auth_failures >= _MAX_AUTH_FAILURES
    assert state.backoff_until > time.monotonic()


@pytest.mark.asyncio
async def test_poll_site_skipped_during_backoff():
    bridge = CloudToMQTTBridge()
    adapter = _make_adapter()
    bridge.register_site("site-test", adapter)
    bridge._sites["site-test"].backoff_until = time.monotonic() + 9999

    with patch("app.services.residential.cloud_mqtt_bridge.mqtt", create=True) as mock_mqtt:
        await bridge.poll_site("site-test")

    adapter.get_realtime.assert_not_called()
