"""Unit tests for SIMBIOT service initialization behavior."""

import pytest

from app.services.simbiot_service import SimbiotService


@pytest.mark.asyncio
async def test_uninitialised_service_reports_disabled():
    """Service should report not_initialised when initialise() has not been called."""
    service = SimbiotService()

    assert service.status["enabled"] is False
    assert service.status["reason"] == "not_initialised"


@pytest.mark.asyncio
async def test_work_order_skips_when_service_disabled():
    """Disabled SIMBIOT service should not attempt CAFM writes."""
    service = SimbiotService()

    result = await service.create_work_order(None)
    assert result is None
    assert service.status["enabled"] is False
