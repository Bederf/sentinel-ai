"""Unit tests for SIMBIOT service initialization behavior."""

import pytest

from app.config.settings import settings
from app.services.simbiot_service import SimbiotService


@pytest.mark.asyncio
async def test_initialise_from_settings_missing_credentials(monkeypatch):
    """Service should explicitly disable itself when required creds are missing."""
    monkeypatch.setattr(settings, "simbiot_api_url", "")
    monkeypatch.setattr(settings, "simbiot_api_key", "")
    monkeypatch.setattr(settings, "simbiot_username", "")
    monkeypatch.setattr(settings, "simbiot_password", "")

    service = SimbiotService()
    await service.initialise_from_settings()

    assert service.status["enabled"] is False
    assert service.status["reason"] == "missing_credentials"


@pytest.mark.asyncio
async def test_work_order_skips_when_service_disabled():
    """Disabled SIMBIOT service should not attempt CAFM writes."""
    service = SimbiotService()

    result = await service.create_work_order(None)
    assert result is None
    assert service.status["enabled"] is False
