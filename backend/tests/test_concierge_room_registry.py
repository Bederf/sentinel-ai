"""
Tests for room registry data and repository (Phase 161).
"""

import json
import re
from unittest.mock import patch

import pytest

from app.database.repositories.room_registry_repository import (
    _JSON_FALLBACK_PATH,
    RoomRegistryRepository,
)

# ---------------------------------------------------------------------------
# JSON fallback data tests
# ---------------------------------------------------------------------------

ROOM_ID_PATTERN = re.compile(r"^FA\d-\d+Q\d+-(?:MR|PR)-\d+$")


def _load_room_registry_json() -> list[dict]:
    with open(_JSON_FALLBACK_PATH) as f:
        return json.load(f)


def test_room_registry_json_has_s001_rooms():
    """JSON file loads and has >= 5 rooms, all with site_id='S001'."""
    rooms = _load_room_registry_json()
    assert len(rooms) >= 5
    for room in rooms:
        assert room["site_id"] == "S001"


def test_room_id_format_matches_convention():
    """All room_ids match FA\\d-\\d+Q\\d+-(?:MR|PR)-\\d+ pattern."""
    rooms = _load_room_registry_json()
    for room in rooms:
        assert ROOM_ID_PATTERN.match(room["room_id"]), f"room_id {room['room_id']!r} does not match expected pattern"


# ---------------------------------------------------------------------------
# Repository fallback tests (no Supabase)
# ---------------------------------------------------------------------------


@pytest.fixture
def repo_no_supabase():
    """Repository with Supabase client set to None (forces JSON fallback)."""
    with patch(
        "app.database.repositories.room_registry_repository.get_supabase_client",
        return_value=None,
    ):
        repo = RoomRegistryRepository()
        assert repo.client is None
        yield repo


@pytest.mark.asyncio
async def test_room_registry_repository_fallback(repo_no_supabase):
    """Repository returns rooms from JSON when no Supabase."""
    rooms = await repo_no_supabase.get_rooms_by_site("S001")
    assert len(rooms) >= 5
    assert all(r["site_id"] == "S001" for r in rooms)


@pytest.mark.asyncio
async def test_validate_room_exists_returns_true_for_known_room(repo_no_supabase):
    """FA2-1Q1-MR-01 exists in the registry."""
    assert await repo_no_supabase.validate_room_exists("FA2-1Q1-MR-01") is True


@pytest.mark.asyncio
async def test_validate_room_exists_returns_false_for_unknown_room(repo_no_supabase):
    """FAKE-ROOM returns False."""
    assert await repo_no_supabase.validate_room_exists("FAKE-ROOM") is False
