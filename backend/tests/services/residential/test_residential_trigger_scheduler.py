"""Tests for residential recommendation trigger scheduler."""

from __future__ import annotations

from app.services.residential.bridge_scheduler import (
    _get_recommendation_interval,
)


class TestGetRecommendationInterval:
    """Dynamic interval based on SOC and loadshedding."""

    def test_soc_critical_and_shedding_30min(self):
        # SOC < 30% + stage > 0 → 30min
        interval = _get_recommendation_interval("res-123", soc=25.0, ls_stage=2, minutes_to_slot=60)
        assert interval == 30

    def test_soc_30_no_shedding_120min(self):
        # SOC at threshold, no shedding → 120min
        interval = _get_recommendation_interval("res-123", soc=30.0, ls_stage=0, minutes_to_slot=None)
        assert interval == 120

    def test_slot_within_2h_30min(self):
        # Within 2h of slot regardless of SOC → 30min
        interval = _get_recommendation_interval("res-123", soc=80.0, ls_stage=3, minutes_to_slot=90)
        assert interval == 30

    def test_normal_conditions_120min(self):
        # Normal conditions → 120min
        interval = _get_recommendation_interval("res-123", soc=75.0, ls_stage=0, minutes_to_slot=None)
        assert interval == 120

    def test_slot_far_future_120min(self):
        # Slot 3h away → 120min
        interval = _get_recommendation_interval("res-123", soc=50.0, ls_stage=2, minutes_to_slot=200)
        assert interval == 120

    def test_soc_none_defaults_120min(self):
        # SOC unknown → 120min (can't make aggressive decision)
        interval = _get_recommendation_interval("res-123", soc=None, ls_stage=0, minutes_to_slot=None)
        assert interval == 120
