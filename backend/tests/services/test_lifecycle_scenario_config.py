from app.services.lifecycle_orchestrator import ARCHIVED_SCENARIOS, SCENARIOS


def test_sentinel_annual_scenario_exposes_demo_mode_default_false():
    scenario = SCENARIOS["sentinel_annual"]

    assert scenario.demo_mode is False


def test_grant_demo_scenarios_are_flagged_demo_mode():
    assert ARCHIVED_SCENARIOS["grant_hvac_only_7day"].demo_mode is True
    assert ARCHIVED_SCENARIOS["grant_hvac_dali_7day"].demo_mode is True
    assert ARCHIVED_SCENARIOS["grant_hvac_dali_ai_7day"].demo_mode is True
