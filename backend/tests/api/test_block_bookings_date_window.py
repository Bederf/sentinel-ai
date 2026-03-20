from app.api.block_bookings import _default_booking_window


class _Status:
    def __init__(self, running: bool, simulated_time: str | None):
        self.running = running
        self.simulated_time = simulated_time


def test_default_booking_window_uses_simulated_date(monkeypatch):
    def _fake_status(_site_id: str):
        return _Status(True, "2024-10-10T01:00:00")

    monkeypatch.setattr("app.api.lifecycle_simulation.get_site_simulation_status_sync", _fake_status)

    start, end = _default_booking_window("site-002")

    assert start.isoformat() == "2024-10-10"
    assert end.isoformat() == "2024-11-07"


def test_default_booking_window_falls_back_to_today(monkeypatch):
    def _fake_status(_site_id: str):
        return _Status(False, None)

    monkeypatch.setattr("app.api.lifecycle_simulation.get_site_simulation_status_sync", _fake_status)

    start, end = _default_booking_window("site-002")

    assert (end - start).days == 28
