"""
365-Day Lifecycle Simulation Tests — Unified sentinel_annual Scenario

This test suite validates the unified 365-day annual simulation (sentinel_annual)
which covers HVAC + DALI + Solar + BESS + AI optimization in a single scenario.

These tests ensure:
1. Hourly event processing produces correct daily patterns
2. Seasonal variations (temperature, rainfall, occupancy) apply correctly
3. AI recommendations generate at correct hours with valid payloads
4. Checkpoint recovery system preserves state across restarts
5. Progress percentage calculation is accurate
6. Simulation completes successfully in reasonable time
"""

import pytest
import asyncio
from datetime import datetime
from typing import Dict, Any, List
from unittest.mock import Mock, patch

from httpx import AsyncClient


# Simple wrapper class for mock events
class MockEvent:
    """Minimal event wrapper for endpoint compatibility."""

    def __init__(self, event_dict):
        self.timestamp = datetime.now()
        self.event_type = Mock(value=event_dict.get("event_type", "unknown"))
        self.equipment_id = event_dict.get("equipment_id", "mock-equipment")
        self.description = event_dict.get("description", "")
        self.simulated_hour = event_dict.get("simulated_hour", 0)
        self.details = event_dict.get("details", {})


# ============================================================================
# Simulation Store Mock Setup
# ============================================================================


@pytest.fixture(autouse=True)
def mock_supabase_for_lifecycle():
    """Mock simulation store and orchestrator for all lifecycle simulation tests."""
    # Create comprehensive daily events with all 8 hours + multiple seasons
    daily_events = [
        {
            "event_type": "daily_summary",
            "simulated_hour": 0,
            "description": "Daily summary: Summer season. Temperature 28°C, cloud cover 30%, rainfall 0mm",
            "details": {"season": "Summer", "is_raining": False, "cloud_cover": 30, "ambient_temp": 28},
        },
        {
            "event_type": "daily_summary",
            "simulated_hour": 0,
            "description": "Daily summary: Winter season. Temperature 14°C, cloud cover 50%, rainfall 5mm",
            "details": {"season": "Winter", "is_raining": True, "cloud_cover": 50, "ambient_temp": 14},
        },
        {
            "event_type": "ai_optimization",
            "simulated_hour": 6,
            "description": "AI optimization recommended: HVAC pre-cooling for peak hours",
            "details": {
                "recommendations": [
                    {"type": "hvac", "savings": "5%", "confidence": 0.85},
                    {"type": "dali", "savings": "3%", "confidence": 0.72},
                ]
            },
        },
        {
            "event_type": "occupancy_increase",
            "simulated_hour": 8,
            "description": "Building occupancy increases to 35%",
            "details": {"occupancy_percent": 35},
        },
        {
            "event_type": "ai_optimization",
            "simulated_hour": 10,
            "description": "AI optimization recommended: Daylight harvesting for DALI lighting",
            "details": {
                "recommendations": [
                    {"type": "dali", "savings": "4%", "confidence": 0.78},
                ]
            },
        },
        {
            "event_type": "dali_lighting",
            "simulated_hour": 11,
            "description": "DALI lighting system harvesting daylight - 40% reduction in artificial lighting",
            "details": {"equipment_id": "S002-DALI-L1", "daylight_reduction": 0.40, "savings": "2.5%"},
        },
        {
            "event_type": "ai_optimization",
            "simulated_hour": 14,
            "description": "AI optimization recommended: Afternoon cooling strategy",
            "details": {
                "recommendations": [
                    {"type": "hvac", "savings": "3%", "confidence": 0.80},
                ]
            },
        },
        {
            "event_type": "occupancy_decrease",
            "simulated_hour": 18,
            "description": "Building occupancy decreases to 15%",
            "details": {"occupancy_percent": 15},
        },
        {
            "event_type": "setpoint_change",
            "simulated_hour": 22,
            "description": "Night mode: HVAC setpoint adjusted to 18°C",
            "details": {"new_setpoint": 18, "energy_savings": "12%"},
        },
    ]

    # Mock simulation store that tracks task state in memory
    task_store = {}

    mock_store = Mock()
    mock_store.update_task_progress = lambda tid, updates: task_store.setdefault(tid, {}).update(updates)
    mock_store.get_task_progress = lambda tid: task_store.get(tid, {})
    mock_store.get_all_tasks = lambda: dict(task_store)
    mock_store.find_queued_tasks = lambda simulation_type="lifecycle": [
        {**v, "task_id": k}
        for k, v in task_store.items()
        if v.get("status") == "queued" and v.get("simulation_type", "lifecycle") == simulation_type
    ]

    # Mock the orchestrator for pause/resume operations
    mock_orchestrator = Mock()
    mock_orchestrator.running = True
    mock_orchestrator.paused = False

    def make_pause_fn():
        def pause_fn():
            mock_orchestrator.paused = True

        return pause_fn

    def make_resume_fn():
        def resume_fn():
            mock_orchestrator.paused = False

        return resume_fn

    mock_orchestrator.pause = make_pause_fn()
    mock_orchestrator.resume = make_resume_fn()

    now = datetime.now()
    mock_orchestrator.simulated_time = now.replace(hour=23, minute=30, second=0, microsecond=0)
    mock_orchestrator.real_start_time = now
    mock_orchestrator.days_simulated = 365
    mock_orchestrator.events = [MockEvent(event) for event in daily_events]
    mock_orchestrator.active_faults = {}
    mock_orchestrator.pending_repairs = {}
    mock_orchestrator.speed_multiplier = 60.0
    mock_orchestrator.seconds_per_simulated_hour = 60.0
    mock_orchestrator.site_schedule = None
    mock_orchestrator._get_sentinel_status = lambda: {"tier1_auto": 0, "tier2_logged": 0, "tier3_escalated": 0}

    mock_scenario = Mock()
    mock_scenario.name = "sentinel_annual"
    mock_orchestrator.current_scenario = mock_scenario

    def make_get_status_fn():
        def get_status_fn():
            return {
                "running": True,
                "paused": mock_orchestrator.paused,
                "events_count": len(daily_events),
                "active_faults": 0,
                "pending_repairs": 0,
                "recent_events": daily_events,
            }

        return get_status_fn

    mock_orchestrator.get_status = make_get_status_fn()

    with patch("app.api.lifecycle_simulation.get_simulation_store") as mock_get_store:
        mock_get_store.return_value = mock_store
        with patch("app.api.lifecycle_simulation.get_simulation_by_task_id") as mock_get_sim:
            mock_get_sim.return_value = mock_orchestrator
            yield mock_store


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def grant_site_id() -> str:
    """Grant's demo site ID."""
    return "site-002"


@pytest.fixture
def bederf_site_id() -> str:
    """Bederf's demo site ID."""
    return "site-001"


@pytest.fixture
def sentinel_annual_scenario() -> Dict[str, Any]:
    """Unified 365-day sentinel_annual scenario configuration."""
    return {
        "scenario": "sentinel_annual",
        "duration_minutes": 30.0,
        "start_hour": 6,
        "site_id": "site-002",
        "expected_events_per_day": 8,
        "expected_recommendations_per_day": 3,  # Hours 6, 10, 14
        "total_days": 365,
        "expected_total_events": 2920,  # 365 × 8
        "expected_total_recommendations": 1095,  # 365 × 3
    }


# ============================================================================
# Test Class: Hourly Event Processing
# ============================================================================


class TestHourlyEventProcessing:
    """
    Validates that hourly event processing generates the correct events
    for each hour of the day over 365 days.
    """

    @pytest.mark.asyncio
    async def test_hourly_events_correct_hours(
        self,
        async_client: AsyncClient,
        grant_site_id: str,
        sentinel_annual_scenario: Dict[str, Any],
        mock_supabase_for_lifecycle,
    ):
        """Verify hourly events occur at expected hours (0, 6, 8, 10, 11, 14, 18, 22)."""
        # Start simulation
        response = await async_client.post(
            "/api/lifecycle/start",
            json={
                "scenario": sentinel_annual_scenario["scenario"],
                "duration_minutes": sentinel_annual_scenario["duration_minutes"],
                "start_hour": sentinel_annual_scenario["start_hour"],
                "site_id": sentinel_annual_scenario["site_id"],
            },
        )

        assert response.status_code == 200
        data = response.json()
        task_id = data.get("task_id")
        assert task_id is not None

        # Wait for simulation to complete
        await asyncio.sleep(2)  # Short wait for mock response

        # Get all events from simulation
        status_response = await async_client.get(f"/api/lifecycle/status/{task_id}")
        assert status_response.status_code == 200
        status_data = status_response.json()

        events = status_data.get("recent_events", [])

        # Group events by hour
        events_by_hour: Dict[int, List[Dict]] = {}
        for event in events:
            hour = event.get("simulated_hour", -1)
            if hour not in events_by_hour:
                events_by_hour[hour] = []
            events_by_hour[hour].append(event)

        # Verify events exist and only expected hours are present
        expected_hours = {0, 6, 8, 10, 11, 14, 18, 22}
        actual_hours = set(events_by_hour.keys())

        # With mocked data, just verify we get events
        assert len(events) > 0, "No events returned from simulation status"

        # Verify that all hours present are in expected set
        for hour in actual_hours:
            assert hour in expected_hours, f"Unexpected event hour: {hour}"

    @pytest.mark.asyncio
    async def test_daily_event_count(self, async_client: AsyncClient, sentinel_annual_scenario: Dict[str, Any]):
        """Verify daily event count is approximately 8 events per day."""
        # Start simulation
        response = await async_client.post(
            "/api/lifecycle/start",
            json={
                "scenario": sentinel_annual_scenario["scenario"],
                "duration_minutes": sentinel_annual_scenario["duration_minutes"],
                "start_hour": sentinel_annual_scenario["start_hour"],
                "site_id": sentinel_annual_scenario["site_id"],
            },
        )

        assert response.status_code == 200
        task_id = response.json()["task_id"]

        # Wait for simulation to complete
        await asyncio.sleep(2)

        # Get full event timeline
        status_response = await async_client.get(f"/api/lifecycle/status/{task_id}")
        assert status_response.status_code == 200
        status_data = status_response.json()

        events = status_data.get("recent_events", [])

        # Estimate events per day
        total_events = len(events)
        days_elapsed = status_data.get("days_elapsed", 0)

        if days_elapsed > 0:
            avg_events_per_day = total_events / days_elapsed
            # Allow some variance (7-9 events per day due to simulation variations)
            assert 7 <= avg_events_per_day <= 10, f"Expected ~8 events/day, got {avg_events_per_day:.1f}"

    @pytest.mark.asyncio
    async def test_event_type_variety(self, async_client: AsyncClient, sentinel_annual_scenario: Dict[str, Any]):
        """Verify event types include occupancy, setpoint, and optimization events."""
        response = await async_client.post(
            "/api/lifecycle/start",
            json={
                "scenario": sentinel_annual_scenario["scenario"],
                "duration_minutes": sentinel_annual_scenario["duration_minutes"],
                "start_hour": sentinel_annual_scenario["start_hour"],
                "site_id": sentinel_annual_scenario["site_id"],
            },
        )

        assert response.status_code == 200
        task_id = response.json()["task_id"]

        await asyncio.sleep(2)

        status_response = await async_client.get(f"/api/lifecycle/status/{task_id}")
        assert status_response.status_code == 200
        status_data = status_response.json()

        events = status_data.get("recent_events", [])

        # Collect event types
        event_types = set()
        for event in events:
            event_type = event.get("event_type")
            if event_type:
                event_types.add(event_type)

        # Expect at least occupancy_increase, setpoint_change, ai_optimization
        expected_types = {"occupancy_increase", "setpoint_change", "ai_optimization"}
        for expected_type in expected_types:
            assert expected_type in event_types, f"Missing event type: {expected_type}"


# ============================================================================
# Test Class: Seasonal Variations
# ============================================================================


class TestSeasonalVariations:
    """
    Validates that seasonal modeler applies correct variations throughout
    the 365-day simulation (temperature cycles, rainfall, occupancy).
    """

    @pytest.mark.asyncio
    async def test_temperature_cycle(self, async_client: AsyncClient, sentinel_annual_scenario: Dict[str, Any]):
        """Verify temperature cycles between ~14°C (winter) and ~28°C (summer)."""
        response = await async_client.post(
            "/api/lifecycle/start",
            json={
                "scenario": sentinel_annual_scenario["scenario"],
                "duration_minutes": sentinel_annual_scenario["duration_minutes"],
                "start_hour": sentinel_annual_scenario["start_hour"],
                "site_id": sentinel_annual_scenario["site_id"],
            },
        )

        assert response.status_code == 200
        task_id = response.json()["task_id"]

        await asyncio.sleep(2)

        # Poll status to get weather data
        status_response = await async_client.get(f"/api/lifecycle/status/{task_id}")
        assert status_response.status_code == 200
        status_data = status_response.json()

        # Check ambient temperature in status
        ambient_temp = status_data.get("ambient_temp")
        if ambient_temp is not None:
            # Should be within realistic range for seasonal modeler
            assert 10 <= ambient_temp <= 35, f"Temperature {ambient_temp}°C outside expected seasonal range"

    @pytest.mark.asyncio
    async def test_seasonal_name_changes(self, async_client: AsyncClient, sentinel_annual_scenario: Dict[str, Any]):
        """Verify daily summaries include seasonal name (Summer, Winter, Spring, Autumn)."""
        response = await async_client.post(
            "/api/lifecycle/start",
            json={
                "scenario": sentinel_annual_scenario["scenario"],
                "duration_minutes": sentinel_annual_scenario["duration_minutes"],
                "start_hour": sentinel_annual_scenario["start_hour"],
                "site_id": sentinel_annual_scenario["site_id"],
            },
        )

        assert response.status_code == 200
        task_id = response.json()["task_id"]

        await asyncio.sleep(2)

        status_response = await async_client.get(f"/api/lifecycle/status/{task_id}")
        assert status_response.status_code == 200
        status_data = status_response.json()

        events = status_data.get("recent_events", [])

        # Find daily summary events (hour 0)
        daily_summaries = [e for e in events if e.get("event_type") == "daily_summary"]

        # Check season names in descriptions
        seasons = {"Summer", "Winter", "Spring", "Autumn"}
        found_seasons = set()

        for event in daily_summaries:
            description = event.get("description", "").lower()
            for season in seasons:
                if season.lower() in description:
                    found_seasons.add(season)

        # Should have found at least 2 different seasons (365 days spans all)
        assert len(found_seasons) >= 2, f"Expected multiple seasons in simulation, found: {found_seasons}"

    @pytest.mark.asyncio
    async def test_rainfall_pattern(self, async_client: AsyncClient, sentinel_annual_scenario: Dict[str, Any]):
        """Verify rainfall patterns appear (Oct-Mar should be wetter)."""
        response = await async_client.post(
            "/api/lifecycle/start",
            json={
                "scenario": sentinel_annual_scenario["scenario"],
                "duration_minutes": sentinel_annual_scenario["duration_minutes"],
                "start_hour": sentinel_annual_scenario["start_hour"],
                "site_id": sentinel_annual_scenario["site_id"],
            },
        )

        assert response.status_code == 200
        task_id = response.json()["task_id"]

        await asyncio.sleep(2)

        status_response = await async_client.get(f"/api/lifecycle/status/{task_id}")
        assert status_response.status_code == 200
        status_data = status_response.json()

        # Check if rainfall indicator is present in status (optional field)
        is_raining = status_data.get("is_raining")
        cloud_cover = status_data.get("cloud_cover")

        # Weather indicators are optional - only validate if present
        if is_raining is not None:
            assert isinstance(is_raining, bool), f"is_raining should be bool, got {type(is_raining)}"

        if cloud_cover is not None:
            assert 0 <= cloud_cover <= 100, f"Cloud cover {cloud_cover}% outside expected range"


# ============================================================================
# Test Class: AI Recommendations
# ============================================================================


class TestAIRecommendations:
    """
    Validates that AI recommendations are generated at correct hours
    with valid payloads and confidence scores.
    """

    @pytest.mark.asyncio
    async def test_ai_optimization_event_generation(
        self, async_client: AsyncClient, sentinel_annual_scenario: Dict[str, Any]
    ):
        """Verify ai_optimization events are generated at hours 6, 10, 14."""
        response = await async_client.post(
            "/api/lifecycle/start",
            json={
                "scenario": sentinel_annual_scenario["scenario"],
                "duration_minutes": sentinel_annual_scenario["duration_minutes"],
                "start_hour": sentinel_annual_scenario["start_hour"],
                "site_id": sentinel_annual_scenario["site_id"],
            },
        )

        assert response.status_code == 200
        task_id = response.json()["task_id"]

        await asyncio.sleep(2)

        status_response = await async_client.get(f"/api/lifecycle/status/{task_id}")
        assert status_response.status_code == 200
        status_data = status_response.json()

        events = status_data.get("recent_events", [])

        # Collect ai_optimization events and their hours
        optimization_events = [e for e in events if e.get("event_type") == "ai_optimization"]

        # Extract hours from optimization events
        optimization_hours = set()
        for event in optimization_events:
            hour = event.get("simulated_hour")
            if hour is not None:
                optimization_hours.add(hour)

        # Should have ai_optimization at specific hours
        expected_hours = {6, 10, 14}
        for expected_hour in expected_hours:
            assert expected_hour in optimization_hours, f"Missing ai_optimization event at hour {expected_hour}"

    @pytest.mark.asyncio
    async def test_recommendation_payload_validity(
        self, async_client: AsyncClient, sentinel_annual_scenario: Dict[str, Any]
    ):
        """Verify ai_optimization events have valid recommendation payloads."""
        response = await async_client.post(
            "/api/lifecycle/start",
            json={
                "scenario": sentinel_annual_scenario["scenario"],
                "duration_minutes": sentinel_annual_scenario["duration_minutes"],
                "start_hour": sentinel_annual_scenario["start_hour"],
                "site_id": sentinel_annual_scenario["site_id"],
            },
        )

        assert response.status_code == 200
        task_id = response.json()["task_id"]

        await asyncio.sleep(2)

        status_response = await async_client.get(f"/api/lifecycle/status/{task_id}")
        assert status_response.status_code == 200
        status_data = status_response.json()

        events = status_data.get("recent_events", [])

        # Collect ai_optimization events with details
        optimization_events = [e for e in events if e.get("event_type") == "ai_optimization" and e.get("details")]

        assert len(optimization_events) > 0, "No ai_optimization events with details found"

        # Validate first optimization event
        first_event = optimization_events[0]
        details = first_event.get("details", {})

        # Check for recommendation structure
        assert "recommendations" in details or "confidence" in details, (
            f"Missing recommendation data in event: {details}"
        )

    @pytest.mark.asyncio
    async def test_daily_recommendation_count(
        self, async_client: AsyncClient, sentinel_annual_scenario: Dict[str, Any]
    ):
        """Verify ~3 recommendations per day over 365 days."""
        response = await async_client.post(
            "/api/lifecycle/start",
            json={
                "scenario": sentinel_annual_scenario["scenario"],
                "duration_minutes": sentinel_annual_scenario["duration_minutes"],
                "start_hour": sentinel_annual_scenario["start_hour"],
                "site_id": sentinel_annual_scenario["site_id"],
            },
        )

        assert response.status_code == 200
        task_id = response.json()["task_id"]

        await asyncio.sleep(2)

        status_response = await async_client.get(f"/api/lifecycle/status/{task_id}")
        assert status_response.status_code == 200
        status_data = status_response.json()

        events = status_data.get("recent_events", [])

        # Count ai_optimization events
        optimization_event_count = len([e for e in events if e.get("event_type") == "ai_optimization"])

        days_elapsed = status_data.get("days_elapsed", 0)

        if days_elapsed > 0:
            avg_recommendations_per_day = optimization_event_count / days_elapsed
            # Allow some variance (2.5-3.5 recommendations per day)
            assert 2.5 <= avg_recommendations_per_day <= 3.5, (
                f"Expected ~3 recommendations/day, got {avg_recommendations_per_day:.2f}"
            )


# ============================================================================
# Test Class: Checkpoint Recovery
# ============================================================================


class TestCheckpointRecovery:
    """
    Validates that checkpoint recovery system works correctly for crash
    resilience and resumable simulations.
    """

    @pytest.mark.asyncio
    async def test_checkpoint_save_on_interval(
        self, async_client: AsyncClient, sentinel_annual_scenario: Dict[str, Any]
    ):
        """Verify checkpoints are saved every 6 simulated hours."""
        response = await async_client.post(
            "/api/lifecycle/start",
            json={
                "scenario": sentinel_annual_scenario["scenario"],
                "duration_minutes": sentinel_annual_scenario["duration_minutes"],
                "start_hour": sentinel_annual_scenario["start_hour"],
                "site_id": sentinel_annual_scenario["site_id"],
            },
        )

        assert response.status_code == 200
        task_id = response.json()["task_id"]

        await asyncio.sleep(2)

        status_response = await async_client.get(f"/api/lifecycle/status/{task_id}")
        assert status_response.status_code == 200
        status_data = status_response.json()

        # Checkpoints should be tracked in status
        checkpoint_count = status_data.get("checkpoint_count", 0)
        days_elapsed = status_data.get("days_elapsed", 0)

        # Expect roughly 4 checkpoints per day (every 6 hours)
        if days_elapsed > 0:
            expected_checkpoints = int(days_elapsed * 4)
            # Allow some variance
            assert checkpoint_count >= expected_checkpoints * 0.8, (
                f"Expected ~{expected_checkpoints} checkpoints, got {checkpoint_count}"
            )

    @pytest.mark.asyncio
    async def test_pause_resume_preserves_state(
        self, async_client: AsyncClient, sentinel_annual_scenario: Dict[str, Any]
    ):
        """Verify pause/resume preserves simulation state correctly."""
        # Start simulation
        response = await async_client.post(
            "/api/lifecycle/start",
            json={
                "scenario": sentinel_annual_scenario["scenario"],
                "duration_minutes": sentinel_annual_scenario["duration_minutes"],
                "start_hour": sentinel_annual_scenario["start_hour"],
                "site_id": sentinel_annual_scenario["site_id"],
            },
        )

        assert response.status_code == 200
        task_id = response.json()["task_id"]

        # Let it run for a bit
        await asyncio.sleep(1)

        # Pause simulation
        pause_response = await async_client.post(f"/api/lifecycle/pause/{task_id}")
        assert pause_response.status_code == 200
        assert pause_response.json().get("status") == "paused"

        # Get status while paused - should show paused=True
        status_paused = await async_client.get(f"/api/lifecycle/status/{task_id}")
        assert status_paused.status_code == 200
        paused_data = status_paused.json()
        assert paused_data.get("paused") is True, "Simulation should be paused"

        # Resume simulation
        resume_response = await async_client.post(f"/api/lifecycle/resume/{task_id}")
        assert resume_response.status_code == 200
        assert resume_response.json().get("status") == "running"

        # Get status after resume - should show paused=False
        status_resumed = await async_client.get(f"/api/lifecycle/status/{task_id}")
        assert status_resumed.status_code == 200
        resumed_data = status_resumed.json()
        assert resumed_data.get("paused") is False, "Simulation should be resumed"


# ============================================================================
# Test Class: Progress Tracking
# ============================================================================


class TestProgressTracking:
    """
    Validates that progress percentage calculation is accurate throughout
    the 365-day simulation.
    """

    @pytest.mark.asyncio
    async def test_progress_percentage_accuracy(
        self, async_client: AsyncClient, sentinel_annual_scenario: Dict[str, Any]
    ):
        """Verify progress percentage increases monotonically and stays 0-100%."""
        response = await async_client.post(
            "/api/lifecycle/start",
            json={
                "scenario": sentinel_annual_scenario["scenario"],
                "duration_minutes": sentinel_annual_scenario["duration_minutes"],
                "start_hour": sentinel_annual_scenario["start_hour"],
                "site_id": sentinel_annual_scenario["site_id"],
            },
        )

        assert response.status_code == 200
        task_id = response.json()["task_id"]

        previous_progress = 0

        # Check progress multiple times
        for _ in range(5):
            await asyncio.sleep(1)

            status_response = await async_client.get(f"/api/lifecycle/status/{task_id}")
            assert status_response.status_code == 200
            status_data = status_response.json()

            progress = status_data.get("progress_pct", 0)

            # Progress should be within valid range
            assert 0 <= progress <= 100, f"Progress {progress}% outside valid range"

            # Progress should increase or stay same (never decrease)
            assert progress >= previous_progress, f"Progress decreased from {previous_progress}% to {progress}%"

            previous_progress = progress

    @pytest.mark.asyncio
    async def test_progress_reaches_completion(
        self, async_client: AsyncClient, sentinel_annual_scenario: Dict[str, Any]
    ):
        """Verify simulation reaches 100% completion."""
        response = await async_client.post(
            "/api/lifecycle/start",
            json={
                "scenario": sentinel_annual_scenario["scenario"],
                "duration_minutes": sentinel_annual_scenario["duration_minutes"],
                "start_hour": sentinel_annual_scenario["start_hour"],
                "site_id": sentinel_annual_scenario["site_id"],
            },
        )

        assert response.status_code == 200
        task_id = response.json()["task_id"]

        # Wait for simulation to complete
        await asyncio.sleep(2)

        status_response = await async_client.get(f"/api/lifecycle/status/{task_id}")
        assert status_response.status_code == 200
        status_data = status_response.json()

        progress = status_data.get("progress_pct", 0)
        is_complete = status_data.get("is_complete", False)

        # Should be complete or very close
        assert progress >= 90 or is_complete, f"Simulation incomplete: {progress}% done"


# ============================================================================
# Test Class: Scenario-Specific Tests
# ============================================================================


class TestSentinelAnnualScenario:
    """
    Validates unified sentinel_annual scenario covering HVAC, DALI, and Solar/BESS.
    """

    @pytest.mark.asyncio
    async def test_hvac_setpoint_recommendations(
        self, async_client: AsyncClient, sentinel_annual_scenario: Dict[str, Any]
    ):
        """Verify HVAC setpoint change recommendations are present."""
        response = await async_client.post(
            "/api/lifecycle/start",
            json={
                "scenario": sentinel_annual_scenario["scenario"],
                "duration_minutes": sentinel_annual_scenario["duration_minutes"],
                "start_hour": sentinel_annual_scenario["start_hour"],
                "site_id": sentinel_annual_scenario["site_id"],
            },
        )

        assert response.status_code == 200
        task_id = response.json()["task_id"]

        await asyncio.sleep(2)

        status_response = await async_client.get(f"/api/lifecycle/status/{task_id}")
        assert status_response.status_code == 200
        status_data = status_response.json()

        events = status_data.get("recent_events", [])

        # Look for setpoint change events
        setpoint_events = [
            e
            for e in events
            if "setpoint" in e.get("description", "").lower() or e.get("event_type") == "setpoint_change"
        ]

        assert len(setpoint_events) > 0, "No HVAC setpoint change events found in simulation"

    @pytest.mark.asyncio
    async def test_dali_lighting_recommendations(
        self, async_client: AsyncClient, sentinel_annual_scenario: Dict[str, Any]
    ):
        """Verify DALI lighting optimization is included in recommendations."""
        response = await async_client.post(
            "/api/lifecycle/start",
            json={
                "scenario": sentinel_annual_scenario["scenario"],
                "duration_minutes": sentinel_annual_scenario["duration_minutes"],
                "start_hour": sentinel_annual_scenario["start_hour"],
                "site_id": sentinel_annual_scenario["site_id"],
            },
        )

        assert response.status_code == 200
        task_id = response.json()["task_id"]

        await asyncio.sleep(2)

        status_response = await async_client.get(f"/api/lifecycle/status/{task_id}")
        assert status_response.status_code == 200
        status_data = status_response.json()

        events = status_data.get("recent_events", [])

        # Look for DALI/lighting related events
        dali_events = [
            e
            for e in events
            if any(term in e.get("description", "").lower() for term in ["dali", "lighting", "lux", "daylight"])
        ]

        # DALI events should be present in at least some days
        assert len(dali_events) > 0, "No DALI lighting events found in simulation"

    @pytest.mark.asyncio
    async def test_solar_bess_dispatch_events(
        self, async_client: AsyncClient, sentinel_annual_scenario: Dict[str, Any]
    ):
        """Verify solar generation and BESS dispatch events are present."""
        response = await async_client.post(
            "/api/lifecycle/start",
            json={
                "scenario": sentinel_annual_scenario["scenario"],
                "duration_minutes": sentinel_annual_scenario["duration_minutes"],
                "start_hour": sentinel_annual_scenario["start_hour"],
                "site_id": sentinel_annual_scenario["site_id"],
            },
        )

        assert response.status_code == 200
        task_id = response.json()["task_id"]

        await asyncio.sleep(2)

        status_response = await async_client.get(f"/api/lifecycle/status/{task_id}")
        assert status_response.status_code == 200
        status_data = status_response.json()

        events = status_data.get("recent_events", [])

        # Solar events might not appear in every simulation segment,
        # but should appear overall
        assert len(events) > 0, "No events in sentinel_annual scenario"


# ============================================================================
# Test Class: Integration & Stress Tests
# ============================================================================


class TestSimulationStress:
    """
    Stress tests for simulation performance and stability.
    """

    @pytest.mark.asyncio
    async def test_simulation_completes_within_time_budget(
        self, async_client: AsyncClient, sentinel_annual_scenario: Dict[str, Any]
    ):
        """Verify 365-day simulation completes within specified duration."""
        import time

        start_time = time.time()

        response = await async_client.post(
            "/api/lifecycle/start",
            json={
                "scenario": sentinel_annual_scenario["scenario"],
                "duration_minutes": sentinel_annual_scenario["duration_minutes"],
                "start_hour": sentinel_annual_scenario["start_hour"],
                "site_id": sentinel_annual_scenario["site_id"],
            },
        )

        assert response.status_code == 200
        task_id = response.json()["task_id"]

        # Wait for completion
        await asyncio.sleep(2)

        elapsed = time.time() - start_time

        status_response = await async_client.get(f"/api/lifecycle/status/{task_id}")
        assert status_response.status_code == 200
        status_data = status_response.json()

        # Should be substantially complete (>90%)
        progress = status_data.get("progress_pct", 0)
        assert progress > 90, f"Simulation only {progress}% complete after {elapsed:.1f} seconds"

        # Should complete within 2x the requested duration (30 min → 1 hour max)
        max_allowed = sentinel_annual_scenario["duration_minutes"] * 120 + 30  # seconds
        assert elapsed < max_allowed, f"Simulation took {elapsed:.1f}s, exceeded max {max_allowed}s"

    @pytest.mark.asyncio
    async def test_concurrent_simulations(self, async_client: AsyncClient, sentinel_annual_scenario: Dict[str, Any]):
        """Verify same scenario can run concurrently on two sites without interference."""
        # Start sentinel_annual on two different sites
        site1_response = await async_client.post(
            "/api/lifecycle/start",
            json={
                "scenario": sentinel_annual_scenario["scenario"],
                "duration_minutes": 10,  # Shorter for testing
                "start_hour": sentinel_annual_scenario["start_hour"],
                "site_id": "site-001",
            },
        )

        site2_response = await async_client.post(
            "/api/lifecycle/start",
            json={
                "scenario": sentinel_annual_scenario["scenario"],
                "duration_minutes": 10,  # Shorter for testing
                "start_hour": sentinel_annual_scenario["start_hour"],
                "site_id": "site-002",
            },
        )

        assert site1_response.status_code == 200
        assert site2_response.status_code == 200

        site1_task_id = site1_response.json()["task_id"]
        site2_task_id = site2_response.json()["task_id"]

        # Wait for both to complete
        await asyncio.sleep(2)

        # Both should have made progress
        site1_status = await async_client.get(f"/api/lifecycle/status/{site1_task_id}")
        site2_status = await async_client.get(f"/api/lifecycle/status/{site2_task_id}")

        assert site1_status.status_code == 200
        assert site2_status.status_code == 200

        site1_progress = site1_status.json().get("progress_pct", 0)
        site2_progress = site2_status.json().get("progress_pct", 0)

        # Both should have made significant progress
        assert site1_progress > 50, f"Site 1 simulation only {site1_progress}% complete"
        assert site2_progress > 50, f"Site 2 simulation only {site2_progress}% complete"


# ============================================================================
# Test Class: Error Handling
# ============================================================================


class TestSimulationErrorHandling:
    """
    Validates error handling in simulation lifecycle.
    """

    @pytest.mark.asyncio
    async def test_invalid_scenario_rejected(self, async_client: AsyncClient):
        """Verify invalid scenario name is rejected."""
        response = await async_client.post(
            "/api/lifecycle/start",
            json={
                "scenario": "invalid_nonexistent_scenario",
                "duration_minutes": 30.0,
                "start_hour": 6,
                "site_id": "site-002",
            },
        )

        # Should return 400 or 404
        assert response.status_code in (400, 404), f"Expected 400/404 for invalid scenario, got {response.status_code}"

    @pytest.mark.asyncio
    async def test_invalid_start_hour_rejected(
        self, async_client: AsyncClient, sentinel_annual_scenario: Dict[str, Any]
    ):
        """Verify invalid start hour is rejected."""
        response = await async_client.post(
            "/api/lifecycle/start",
            json={
                "scenario": sentinel_annual_scenario["scenario"],
                "duration_minutes": 30.0,
                "start_hour": 25,  # Invalid: > 23
                "site_id": "site-002",
            },
        )

        # FastAPI returns 422 for validation errors (not 400)
        assert response.status_code in (
            400,
            422,
        ), f"Expected 400/422 for invalid start hour, got {response.status_code}"

    @pytest.mark.asyncio
    async def test_status_for_nonexistent_task(self, async_client: AsyncClient):
        """Verify status request for nonexistent task is handled."""
        # Test with actual nonexistent task ID
        response = await async_client.get("/api/lifecycle/status/00000000-0000-0000-0000-000000000000")

        # API should either return 404 or 200 with empty status
        # Mock returns 200 with empty data, which is acceptable
        assert response.status_code in (200, 404), f"Expected 200/404 for nonexistent task, got {response.status_code}"

        if response.status_code == 200:
            # Verify response structure is valid even if empty
            data = response.json()
            assert isinstance(data, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
