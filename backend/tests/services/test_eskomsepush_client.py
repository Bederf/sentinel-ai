from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.services.residential.eskomsepush_client as mod
from app.services.residential.eskomsepush_client import (
    AreaSchedule,
    _area_cache,
    _fetch_area_async,
    get_area_schedule,
    validate_area_code,
)


def _clear_cache():
    _area_cache.clear()


# ── get_area_schedule ─────────────────────────────────────────────────────────

def test_get_area_schedule_returns_none_when_empty():
    _clear_cache()
    assert get_area_schedule("sandton-2") is None


def test_get_area_schedule_returns_cached_entry():
    _clear_cache()
    entry = AreaSchedule("sandton-2", 2, None, None, datetime.utcnow())
    _area_cache["sandton-2"] = entry
    assert get_area_schedule("sandton-2") is entry


# ── _fetch_area_async ─────────────────────────────────────────────────────────

def _mock_esp(is_configured: bool = True) -> MagicMock:
    """Return a MagicMock replacing _esp_service — avoids patching read-only property."""
    svc = MagicMock()
    svc.is_configured.return_value = is_configured
    return svc


@pytest.mark.asyncio
async def test_fetch_area_updates_cache():
    _clear_cache()
    api_response = {
        "events": [
            {"start": "2026-05-30T18:00:00Z", "end": "2026-05-30T20:30:00Z", "note": "Stage 2"}
        ],
        "info": {"stage": "2"},
    }
    svc = _mock_esp()
    svc.get_area_information = AsyncMock(return_value=api_response)

    with patch.object(mod, "_esp_service", svc):
        await _fetch_area_async("sandton-2")

    schedule = get_area_schedule("sandton-2")
    assert schedule is not None
    assert schedule.stage == 2
    assert schedule.is_stale is False
    assert schedule.next_slot_start is not None


@pytest.mark.asyncio
async def test_fetch_area_marks_stale_on_api_failure_with_existing_cache():
    _clear_cache()
    _area_cache["sandton-2"] = AreaSchedule("sandton-2", 1, None, None, datetime.utcnow())
    svc = _mock_esp()
    svc.get_area_information = AsyncMock(side_effect=Exception("timeout"))

    with patch.object(mod, "_esp_service", svc):
        await _fetch_area_async("sandton-2")

    schedule = get_area_schedule("sandton-2")
    assert schedule is not None
    assert schedule.is_stale is True
    assert schedule.stage == 1  # preserved from before


@pytest.mark.asyncio
async def test_fetch_area_creates_null_stale_on_first_failure():
    _clear_cache()
    svc = _mock_esp()
    svc.get_area_information = AsyncMock(side_effect=Exception("offline"))

    with patch.object(mod, "_esp_service", svc):
        await _fetch_area_async("fourways-7")

    schedule = get_area_schedule("fourways-7")
    assert schedule is not None
    assert schedule.is_stale is True
    assert schedule.stage is None


@pytest.mark.asyncio
async def test_fetch_area_noop_when_not_configured():
    _clear_cache()
    svc = _mock_esp(is_configured=False)
    with patch.object(mod, "_esp_service", svc):
        await _fetch_area_async("sandton-2")
    assert get_area_schedule("sandton-2") is None


# ── Shared cache: two sites same area → one API call ─────────────────────────

@pytest.mark.asyncio
async def test_shared_cache_single_fetch_for_same_area():
    _clear_cache()
    api_response = {"events": [], "info": {"stage": "0"}}
    call_count = 0

    async def _mock_get(area_id):
        nonlocal call_count
        call_count += 1
        return api_response

    svc = _mock_esp()
    svc.get_area_information = _mock_get

    with patch.object(mod, "_esp_service", svc):
        await _fetch_area_async("sandton-2")
        schedule = get_area_schedule("sandton-2")

    assert call_count == 1
    assert schedule is not None


# ── validate_area_code ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_validate_area_code_returns_true_when_found():
    svc = _mock_esp()
    svc.search_areas = AsyncMock(return_value=[{"id": "sandton-2"}])
    with patch.object(mod, "_esp_service", svc):
        assert await validate_area_code("sandton-2") is True


@pytest.mark.asyncio
async def test_validate_area_code_returns_false_when_not_found():
    svc = _mock_esp()
    svc.search_areas = AsyncMock(return_value=[{"id": "other-area"}])
    with patch.object(mod, "_esp_service", svc):
        assert await validate_area_code("sandton-2") is False


@pytest.mark.asyncio
async def test_validate_area_code_fail_open_when_not_configured():
    svc = _mock_esp(is_configured=False)
    with patch.object(mod, "_esp_service", svc):
        assert await validate_area_code("any-area") is True
