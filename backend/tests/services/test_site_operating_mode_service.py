from app.services.site_operating_mode_service import resolve_site_operating_mode


def test_resolve_site_operating_mode_defaults_from_active_profile():
    assert resolve_site_operating_mode("site-012") == "cost_saving"


def test_resolve_site_operating_mode_accepts_sentinel_style_site_ids():
    assert resolve_site_operating_mode("S012") == "cost_saving"


def test_resolve_site_operating_mode_prefers_explicit_mode_over_profile():
    assert resolve_site_operating_mode("site-012") == "cost_saving"


def test_resolve_site_operating_mode_defaults_to_comfort_for_missing_site():
    assert resolve_site_operating_mode("site-missing") == "comfort"
