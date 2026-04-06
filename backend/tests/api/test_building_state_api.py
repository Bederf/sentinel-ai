from __future__ import annotations

from datetime import datetime

import pytest

from app.api import building_state
from app.services.building_state_models import (
    BuildingStatePayload,
    NarrativeLocation,
    OperatorGuidance,
    PrimaryNarrative,
    SecondaryTension,
)


@pytest.mark.asyncio
async def test_get_building_state_returns_explicit_calm_payload(monkeypatch):
    monkey_payload = BuildingStatePayload(
        site_id="site-123",
        building_posture="calm",
        primary_narrative=None,
        secondary_tensions=[],
        operator_guidance=OperatorGuidance(headline="No action needed.", mode="none"),
    )
    monkeypatch.setattr(building_state, "build_building_state_payload", lambda site_id: monkey_payload)
    response = await building_state.get_building_state("site-123")
    payload = response["payload"]

    assert payload is not None
    assert payload.site_id == "site-123"
    assert payload.building_posture == "calm"
    assert payload.primary_narrative is None
    assert payload.operator_guidance.mode == "none"


@pytest.mark.asyncio
async def test_get_building_state_returns_active_stub_for_site_002(monkeypatch):
    monkey_payload = BuildingStatePayload(
        site_id="site-002",
        building_posture="compensating",
        primary_narrative=PrimaryNarrative(
            voice="comfort_stress",
            message="Cooling drift is spreading upward from the basement plant.",
            location=NarrativeLocation(epicenter="B1", affected=["L0", "L1"], propagation="upward"),
            time_to_breach_min=18,
            urgency="prepare",
            action="Prepare standby cooling.",
        ),
        secondary_tensions=[
            SecondaryTension(voice="energy_pressure", message="Load is rising as the building compensates."),
            SecondaryTension(
                voice="operational_stability",
                message="Chiller cycling margin is tightening around the plant transition.",
            ),
        ],
        operator_guidance=OperatorGuidance(headline="Prepare for intervention.", mode="prepare"),
    )
    monkeypatch.setattr(building_state, "build_building_state_payload", lambda site_id: monkey_payload)
    response = await building_state.get_building_state("site-002")
    payload = response["payload"]

    assert payload is not None
    assert payload.building_posture == "compensating"
    assert payload.primary_narrative is not None
    assert payload.primary_narrative.voice == "comfort_stress"
    assert payload.primary_narrative.time_to_breach_min == 18
    assert payload.operator_guidance.mode == "prepare"
    assert len(payload.secondary_tensions) == 2
    assert response["site_id"] == "site-002"
    assert isinstance(datetime.fromisoformat(response["fetched_at"]), datetime)
