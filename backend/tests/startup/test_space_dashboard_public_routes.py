from app.startup.middleware import _is_public_read_request


def test_space_dashboard_read_routes_are_public():
    assert _is_public_read_request("/api/block-bookings/alerts", "GET") is True
    assert _is_public_read_request("/api/block-bookings/bookings", "GET") is True
    assert _is_public_read_request("/api/space/ghost-findings", "GET") is True
    assert _is_public_read_request("/api/space/focus-sessions", "GET") is True
    assert _is_public_read_request("/api/concierge/rooms/site-002", "GET") is True
    assert _is_public_read_request("/api/occupancy/analytics/hourly-trend", "GET") is True


def test_space_dashboard_mutations_are_not_public():
    assert _is_public_read_request("/api/space/occupancy-event", "POST") is False
    assert _is_public_read_request("/api/block-bookings/alerts/abc/dismiss", "POST") is False
    assert _is_public_read_request("/api/space/findings/abc/inspection-outcome", "POST") is False
