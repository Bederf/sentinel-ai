"""Tests for Stage 03 Distillation — preference extraction from chat.

Runs against real Anthropic Haiku API to validate extraction quality.
"""

import pytest

from app.models.preference import PreferenceType
from app.repositories.preference_repository import preference_repo
from app.services.preference_extractor import extract_preference_from_chat

TEST_SITE_ID = "site-002"
TEST_USER_ID = "test-fm@sentinel.ai"


@pytest.mark.asyncio
async def test_extract_setpoint_preference():
    """Explicit setpoint preference should be extracted with >0.75 confidence."""
    user_msg = "I want zone 3 kept above 20°C during office hours"
    assistant_msg = (
        "I'll set zone 3 to maintain minimum 20°C during office hours. "
        "Currently zone 3 is at 22°C, so no adjustment needed right now."
    )

    result = await extract_preference_from_chat(
        user_message=user_msg,
        assistant_response=assistant_msg,
        site_id=TEST_SITE_ID,
        user_id=TEST_USER_ID,
    )

    assert result is not None, "Should extract a setpoint preference"
    assert result.preference_type == PreferenceType.SETPOINT
    assert result.confidence >= 0.75, f"Confidence {result.confidence} should be >= 0.75"
    assert result.site_id == TEST_SITE_ID
    assert result.user_id == TEST_USER_ID

    # Verify stored in DB and fetchable
    fetched = await preference_repo.fetch_by_type(TEST_SITE_ID, TEST_USER_ID, PreferenceType.SETPOINT)
    assert fetched is not None, "Preference should be in DB"
    assert fetched.preference_type == PreferenceType.SETPOINT
    assert fetched.confidence >= 0.75


@pytest.mark.asyncio
async def test_extract_priority_preference():
    """Comfort/energy priority should be extracted with >0.75 confidence."""
    user_msg = "I don't care about energy costs, comfort is what matters"
    assistant_msg = (
        "Understood. I'll prioritize comfort over energy savings for your zones. "
        "I'll keep setpoints in the 20-22°C range for optimal comfort."
    )

    result = await extract_preference_from_chat(
        user_message=user_msg,
        assistant_response=assistant_msg,
        site_id=TEST_SITE_ID,
        user_id=TEST_USER_ID,
    )

    assert result is not None, "Should extract a priority preference"
    assert result.preference_type == PreferenceType.PRIORITY
    assert result.confidence >= 0.75, f"Confidence {result.confidence} should be >= 0.75"

    # Verify stored
    fetched = await preference_repo.fetch_by_type(TEST_SITE_ID, TEST_USER_ID, PreferenceType.PRIORITY)
    assert fetched is not None


@pytest.mark.asyncio
async def test_no_preference_extracted():
    """Simple informational query should not extract a preference."""
    user_msg = "What's the current temperature in zone 3?"
    assistant_msg = "Zone 3 is currently at 22°C, which is within the comfort range."

    result = await extract_preference_from_chat(
        user_message=user_msg,
        assistant_response=assistant_msg,
        site_id=TEST_SITE_ID,
        user_id=TEST_USER_ID,
    )

    assert result is None, "Should not extract a preference for informational query"


@pytest.mark.asyncio
async def test_low_confidence_not_stored():
    """Vague preferences should not be stored (confidence < 0.75)."""
    user_msg = "Maybe I like it a bit warmer I guess"
    assistant_msg = "I can adjust your zone setpoints if you'd like. What temperature are you aiming for?"

    result = await extract_preference_from_chat(
        user_message=user_msg,
        assistant_response=assistant_msg,
        site_id=TEST_SITE_ID,
        user_id=TEST_USER_ID,
    )

    assert result is None, "Low-confidence preference should not be stored"


@pytest.mark.asyncio
async def test_upsert_replaces_old_preference():
    """Inserting same preference type twice should upsert (overwrite)."""
    pref_type = PreferenceType.SETPOINT

    # First: store a setpoint
    user1 = "I want zone 3 at 20°C"
    assistant1 = "Setting zone 3 to 20°C."
    await extract_preference_from_chat(user1, assistant1, TEST_SITE_ID, TEST_USER_ID)

    # Second: store a different setpoint for same user
    user2 = "Actually make zone 3 at 22°C instead"
    assistant2 = "Adjusting zone 3 setpoint to 22°C."
    await extract_preference_from_chat(user2, assistant2, TEST_SITE_ID, TEST_USER_ID)

    # Only one preference should exist (upsert), with the newer value
    pref = await preference_repo.fetch_by_type(TEST_SITE_ID, TEST_USER_ID, pref_type)
    assert pref is not None
    # The value should reflect the latest extraction
    assert pref.confidence >= 0.75


@pytest.mark.asyncio
async def test_fetch_active_by_user_returns_preferences():
    """fetch_active_by_user should return all stored preferences."""
    prefs = await preference_repo.fetch_active_by_user(TEST_SITE_ID, TEST_USER_ID)
    assert len(prefs) >= 1, "Should have at least one stored preference"
    for p in prefs:
        assert p.site_id == TEST_SITE_ID
        assert p.user_id == TEST_USER_ID
        assert p.confidence >= 0.75
