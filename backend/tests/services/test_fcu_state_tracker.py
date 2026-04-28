"""Tests for FCUStateTracker (Phase 1a)."""

from datetime import UTC, datetime, timedelta

from app.services.fcu_state_tracker import (
    FCUStateTracker,
    InMemoryBackend,
)

UTC = UTC
NOW = datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)


def make_tracker(profile: str = "balanced") -> FCUStateTracker:
    """Create a fresh tracker with InMemoryBackend."""
    return FCUStateTracker(active_profile=profile, backend=InMemoryBackend())


def poll(tracker, zone_id, occupancy_pct, room_temp_c, setpoint_c=None, delta_minutes=0):
    """Helper: record a poll at a given offset from NOW."""
    ts = NOW + timedelta(minutes=delta_minutes)
    tracker.record_poll(zone_id, occupancy_pct, room_temp_c, setpoint_c, ts)


class TestOccupancyTransitions:
    """Zone transitions: occupied → empty → records occupancy_end_time."""

    def test_occupied_zone_no_end_time(self):
        tracker = make_tracker()
        poll(tracker, "Zone-201", 80.0, 22.5, 24.0, delta_minutes=0)

        state = tracker.get_state("Zone-201")
        assert state is not None
        assert state.occupancy_pct == 80.0
        assert state.occupancy_end_time is None

    def test_transition_to_empty_records_end_time(self):
        tracker = make_tracker()
        poll(tracker, "Zone-201", 80.0, 22.5, 24.0, delta_minutes=0)
        poll(tracker, "Zone-201", 0.0, 22.5, 24.0, delta_minutes=5)

        state = tracker.get_state("Zone-201")
        assert state is not None
        assert state.occupancy_pct == 0.0
        assert state.occupancy_end_time is not None
        # end_time should be the moment of transition (5 min after start)
        elapsed = (state.timestamp - state.occupancy_end_time).total_seconds() / 60.0
        assert elapsed == 0.0

    def test_remaining_occupied_keeps_previous_end_time(self):
        tracker = make_tracker()
        poll(tracker, "Zone-201", 80.0, 22.5, 24.0, delta_minutes=0)
        poll(tracker, "Zone-201", 0.0, 22.5, 24.0, delta_minutes=5)
        # Becomes occupied again — occupancy_end_time should be cleared (zone no longer empty)
        poll(tracker, "Zone-201", 50.0, 22.5, 24.0, delta_minutes=10)

        state = tracker.get_state("Zone-201")
        assert state.occupancy_pct == 50.0
        assert state.occupancy_end_time is None  # not empty → no end_time


class TestFCUInference:
    """FCU running inference from temperature trends."""

    def test_fcu_running_when_actively_cooling(self):
        tracker = make_tracker()
        poll(tracker, "Zone-201", 0.0, 26.0, 24.0, delta_minutes=0)  # prev
        poll(tracker, "Zone-201", 0.0, 25.2, 24.0, delta_minutes=5)  # delta = -0.8°C → cooling

        state = tracker.get_state("Zone-201")
        assert state.fcu_inferred_running is True

    def test_fcu_running_when_significantly_below_setpoint(self):
        tracker = make_tracker()
        # temp well below setpoint (no previous delta, setpoint alone triggers)
        poll(tracker, "Zone-201", 0.0, 22.5, 24.0, delta_minutes=0)
        poll(tracker, "Zone-201", 0.0, 22.5, 24.0, delta_minutes=5)  # no temp change, but 1.5°C below

        state = tracker.get_state("Zone-201")
        assert state.fcu_inferred_running is True

    def test_fcu_not_running_when_stable_above_setpoint(self):
        tracker = make_tracker()
        poll(tracker, "Zone-201", 0.0, 25.5, 24.0, delta_minutes=0)
        poll(tracker, "Zone-201", 0.0, 25.6, 24.0, delta_minutes=5)  # rising (+0.1°C), not cooling

        state = tracker.get_state("Zone-201")
        assert state.fcu_inferred_running is False

    def test_fcu_not_running_when_at_setpoint_stable(self):
        tracker = make_tracker()
        poll(tracker, "Zone-201", 0.0, 24.2, 24.0, delta_minutes=0)
        poll(tracker, "Zone-201", 0.0, 24.3, 24.0, delta_minutes=5)  # slight rise, at setpoint

        state = tracker.get_state("Zone-201")
        assert state.fcu_inferred_running is False

    def test_no_inference_without_history(self):
        tracker = make_tracker()
        # First poll ever for this zone
        tracker.record_poll("Zone-201", 0.0, 25.0, 24.0, NOW)

        state = tracker.get_state("Zone-201")
        assert state.fcu_inferred_running is False  # no prev temp

    def test_no_inference_without_temp(self):
        tracker = make_tracker()
        poll(tracker, "Zone-201", 0.0, None, 24.0, delta_minutes=0)
        poll(tracker, "Zone-201", 0.0, None, 24.0, delta_minutes=5)

        state = tracker.get_state("Zone-201")
        assert state.fcu_inferred_running is False


class TestWasteCandidates:
    """Waste candidate detection."""

    def test_zone_empty_beyond_threshold_with_fcu_running(self):
        tracker = make_tracker("balanced")  # 10-min threshold
        poll(tracker, "Zone-201", 80.0, 22.5, 24.0, delta_minutes=0)
        poll(tracker, "Zone-201", 0.0, 22.0, 24.0, delta_minutes=5)
        # After 5 min: still below threshold (10 min for balanced)
        assert tracker.get_minutes_since_zone_emptied("Zone-201") == 0.0
        # FCU still running (temp converging)
        poll(tracker, "Zone-201", 0.0, 21.5, 24.0, delta_minutes=10)  # 5 min empty, delta=-0.5
        # At exactly 10 min threshold
        poll(tracker, "Zone-201", 0.0, 21.5, 24.0, delta_minutes=15)  # 10 min empty

        candidates = tracker.get_waste_candidates()
        assert len(candidates) == 1
        assert candidates[0].equipment_id == "S002-FCU-201"
        assert candidates[0].opportunity_type == "fcu_post_occupancy"
        assert candidates[0].minutes_elapsed >= 10.0

    def test_zone_empty_below_threshold_not_yet_a_waste(self):
        tracker = make_tracker("balanced")
        poll(tracker, "Zone-201", 0.0, 22.5, 24.0, delta_minutes=0)
        poll(tracker, "Zone-201", 0.0, 22.0, 24.0, delta_minutes=5)  # 5 min empty, threshold=10

        candidates = tracker.get_waste_candidates()
        assert len(candidates) == 0

    def test_zone_occupied_not_a_waste_candidate(self):
        tracker = make_tracker()
        poll(tracker, "Zone-201", 80.0, 25.0, 24.0, delta_minutes=0)
        poll(tracker, "Zone-201", 80.0, 24.5, 24.0, delta_minutes=5)

        assert tracker.get_waste_candidates() == []

    def test_zone_empty_fcu_not_running_not_a_waste(self):
        tracker = make_tracker()
        poll(tracker, "Zone-201", 80.0, 26.0, 24.0, delta_minutes=0)
        # Zone empties, temp rises (FCU off) — no waste
        poll(tracker, "Zone-201", 0.0, 26.5, 24.0, delta_minutes=5)
        poll(tracker, "Zone-201", 0.0, 27.0, 24.0, delta_minutes=10)

        candidates = tracker.get_waste_candidates()
        assert len(candidates) == 0

    def test_zone_never_emptied_not_a_waste(self):
        tracker = make_tracker()
        poll(tracker, "Zone-201", 80.0, 22.0, 24.0, delta_minutes=0)
        poll(tracker, "Zone-201", 50.0, 22.5, 24.0, delta_minutes=5)

        assert tracker.get_waste_candidates() == []


class TestProfileThresholds:
    """Profile threshold awareness."""

    def test_cost_saving_faster_threshold(self):
        """cost_saving=5min vs balanced=10min same conditions → different results."""
        # cost_saving profile: 5 min threshold
        cs_tracker = make_tracker("cost_saving")
        poll(cs_tracker, "Zone-201", 80.0, 22.5, 24.0, delta_minutes=0)
        poll(cs_tracker, "Zone-201", 0.0, 22.0, 24.0, delta_minutes=5)  # transition at 5 min
        poll(cs_tracker, "Zone-201", 0.0, 21.8, 24.0, delta_minutes=12)  # 7 min empty (12-5=7)

        cs_candidates = cs_tracker.get_waste_candidates()
        assert len(cs_candidates) == 1  # past 5 min threshold

        # balanced profile: 10 min threshold
        bal_tracker = make_tracker("balanced")
        poll(bal_tracker, "Zone-201", 80.0, 22.5, 24.0, delta_minutes=0)
        poll(bal_tracker, "Zone-201", 0.0, 22.0, 24.0, delta_minutes=5)
        poll(bal_tracker, "Zone-201", 0.0, 21.8, 24.0, delta_minutes=12)  # same 7 min empty

        bal_candidates = bal_tracker.get_waste_candidates()
        assert len(bal_candidates) == 0  # below 10 min threshold

    def test_comfort_slower_threshold(self):
        """comfort=15min threshold catches fewer candidates than balanced."""
        comfort_tracker = make_tracker("comfort")
        poll(comfort_tracker, "Zone-201", 80.0, 22.5, 24.0, delta_minutes=0)
        poll(comfort_tracker, "Zone-201", 0.0, 22.0, 24.0, delta_minutes=10)
        poll(comfort_tracker, "Zone-201", 0.0, 21.8, 24.0, delta_minutes=12)  # 12 min elapsed

        comfort_candidates = comfort_tracker.get_waste_candidates()
        assert len(comfort_candidates) == 0  # below 15 min threshold


class TestZoneToFCUMapping:
    """Zone-to-FCU equipment ID mapping."""

    def test_zone_201_maps_to_s002_fcu_201(self):
        tracker = make_tracker()
        # Zone must transition occupied→empty to record occupancy_end_time
        poll(tracker, "Zone-201", 80.0, 26.0, 24.0, delta_minutes=0)  # zone occupied
        poll(tracker, "Zone-201", 0.0, 26.0, 24.0, delta_minutes=5)  # transition to empty
        poll(tracker, "Zone-201", 0.0, 22.0, 24.0, delta_minutes=15)  # delta=-4.0°C → FCU running

        candidates = tracker.get_waste_candidates()
        assert len(candidates) == 1
        assert candidates[0].equipment_id == "S002-FCU-201"

    def test_zone_001_maps_to_s002_fcu_001(self):
        tracker = make_tracker()
        # Zone-001 → S002-FCU-001 (zero-padded to 3 digits, consistent with Zone-201 → S002-FCU-201)
        poll(tracker, "Zone-001", 80.0, 26.0, 24.0, delta_minutes=0)
        poll(tracker, "Zone-001", 0.0, 26.0, 24.0, delta_minutes=5)
        poll(tracker, "Zone-001", 0.0, 22.0, 24.0, delta_minutes=15)

        candidates = tracker.get_waste_candidates()
        assert len(candidates) == 1
        assert candidates[0].equipment_id == "S002-FCU-001"


class TestGetMinutesSinceZoneEmptied:
    """get_minutes_since_zone_emptied API."""

    def test_returns_none_if_zone_never_emptied(self):
        tracker = make_tracker()
        poll(tracker, "Zone-201", 80.0, 22.0, 24.0, delta_minutes=0)

        assert tracker.get_minutes_since_zone_emptied("Zone-201") is None

    def test_returns_none_for_unknown_zone(self):
        tracker = make_tracker()
        assert tracker.get_minutes_since_zone_emptied("Zone-999") is None

    def test_returns_elapsed_minutes(self):
        tracker = make_tracker()
        poll(tracker, "Zone-201", 80.0, 22.0, 24.0, delta_minutes=0)
        poll(tracker, "Zone-201", 0.0, 22.0, 24.0, delta_minutes=5)
        # At delta_minutes=15, zone has been empty for 10 min
        poll(tracker, "Zone-201", 0.0, 22.0, 24.0, delta_minutes=15)

        elapsed = tracker.get_minutes_since_zone_emptied("Zone-201")
        assert elapsed is not None
        assert elapsed >= 10.0


class TestUpdateProfile:
    """update_profile API."""

    def test_update_profile_accepted(self):
        tracker = make_tracker("balanced")
        tracker.update_profile("cost_saving")

        # Verify threshold changed — temp above setpoint, cooling
        poll(tracker, "Zone-201", 80.0, 26.0, 24.0, delta_minutes=0)
        poll(tracker, "Zone-201", 0.0, 25.2, 24.0, delta_minutes=5)  # transition at 5 min; delta=-0.8 → FCU running
        poll(tracker, "Zone-201", 0.0, 21.5, 24.0, delta_minutes=12)  # 7 min empty (12-5=7); delta=-3.7 → FCU running

        # cost_saving=5 min, at 7 min elapsed should be a candidate
        candidates = tracker.get_waste_candidates()
        assert len(candidates) == 1


class TestConfidenceScoring:
    """Confidence tiers based on how far past threshold."""

    def test_high_confidence_far_past_threshold(self):
        tracker = make_tracker("balanced")  # 10 min threshold
        poll(tracker, "Zone-201", 80.0, 22.5, 24.0, delta_minutes=0)
        poll(tracker, "Zone-201", 0.0, 22.0, 24.0, delta_minutes=5)
        # At 30 min elapsed (3x threshold) → 0.95 confidence
        poll(tracker, "Zone-201", 0.0, 21.5, 24.0, delta_minutes=35)

        candidates = tracker.get_waste_candidates()
        assert len(candidates) == 1
        assert candidates[0].confidence == 0.95

    def test_medium_confidence_15x_threshold(self):
        tracker = make_tracker("balanced")
        poll(tracker, "Zone-201", 80.0, 22.5, 24.0, delta_minutes=0)
        poll(tracker, "Zone-201", 0.0, 22.0, 24.0, delta_minutes=5)
        # At 15 min elapsed (1.5x threshold) → 0.80 confidence
        poll(tracker, "Zone-201", 0.0, 21.5, 24.0, delta_minutes=20)

        candidates = tracker.get_waste_candidates()
        assert len(candidates) == 1
        assert candidates[0].confidence == 0.80

    def test_low_confidence_at_threshold(self):
        tracker = make_tracker("balanced")
        poll(tracker, "Zone-201", 80.0, 22.5, 24.0, delta_minutes=0)
        poll(tracker, "Zone-201", 0.0, 22.0, 24.0, delta_minutes=5)
        poll(tracker, "Zone-201", 0.0, 21.5, 24.0, delta_minutes=15)  # just past 10 min

        candidates = tracker.get_waste_candidates()
        assert len(candidates) == 1
        assert candidates[0].confidence == 0.65


class TestEstimatedSavingKwh:
    """estimated_saving_kwh field (optional, set when BESS rules added in Phase 1b)."""

    def test_waste_opportunity_defaults_to_none(self):
        tracker = make_tracker()
        poll(tracker, "Zone-201", 80.0, 22.5, 24.0, delta_minutes=0)
        poll(tracker, "Zone-201", 0.0, 22.0, 24.0, delta_minutes=5)
        poll(tracker, "Zone-201", 0.0, 21.5, 24.0, delta_minutes=20)

        candidates = tracker.get_waste_candidates()
        assert candidates[0].estimated_saving_kwh is None
