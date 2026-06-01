"""Tests for /api/residential/setarea endpoint.

Phase 214 — Wave 6
Covers:
- bot_agent auth accepted
- Invalid area code rejected at API level (400)
- Updates residential_sites.eskom_area_code
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.api.residential_onboarding import SetareaRequest


class TestSetareaEndpoint:
    """Tests for PATCH /api/residential/setarea."""

    def test_bot_agent_auth_accepted(self):
        """Router must accept PATCH /api/residential/setarea with bot_agent auth."""
        from app.api.residential_onboarding import router

        routes = [r.path for r in router.routes]
        assert "/api/residential/setarea" in routes

    @pytest.mark.asyncio
    async def test_invalid_area_code_rejected_at_api_level(self):
        """When validate_area_code returns False, endpoint raises HTTPException 400."""
        from fastapi import HTTPException

        from app.api.residential_onboarding import setarea_residential_site

        with patch("app.api.residential_onboarding._validate_area_code") as mock_validate:
            mock_validate.return_value = False  # invalid

            request = SetareaRequest(site_id="res-123", eskom_area_code="invalid-area-code")

            with pytest.raises(HTTPException) as exc_info:
                await setarea_residential_site(request)
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_valid_area_code_updates_db(self):
        """Valid area code → DB updated, returns status=updated."""
        from app.api.residential_onboarding import setarea_residential_site

        with patch("app.api.residential_onboarding._validate_area_code") as mock_validate:
            mock_validate.return_value = True  # valid

            with patch("app.api.residential_onboarding.get_supabase_client") as mock_sb:
                mock_client = MagicMock()
                # Site lookup
                mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"id": 1, "is_active": True}]
                )
                # Update call
                mock_client.table.return_value.update.return_value.execute.return_value = MagicMock(
                    data=[{"site_id": "res-123", "eskom_area_code": "sandton-2"}]
                )
                mock_sb.return_value = mock_client

                request = SetareaRequest(site_id="res-123", eskom_area_code="sandton-2")
                result = await setarea_residential_site(request)
                assert result["status"] == "updated"
                assert result["eskom_area_code"] == "sandton-2"

    @pytest.mark.asyncio
    async def test_site_not_found_returns_404(self):
        """Non-existent site_id → HTTPException 404."""
        from fastapi import HTTPException

        from app.api.residential_onboarding import setarea_residential_site

        with patch("app.api.residential_onboarding._validate_area_code") as mock_validate:
            mock_validate.return_value = True

            with patch("app.api.residential_onboarding.get_supabase_client") as mock_sb:
                mock_client = MagicMock()
                mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[]  # empty = site not found
                )
                mock_sb.return_value = mock_client

                request = SetareaRequest(site_id="nonexistent", eskom_area_code="sandton-2")

                with pytest.raises(HTTPException) as exc_info:
                    await setarea_residential_site(request)
                assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_inactive_site_returns_400(self):
        """Site exists but is_active=False → HTTPException 400."""
        from fastapi import HTTPException

        from app.api.residential_onboarding import setarea_residential_site

        with patch("app.api.residential_onboarding._validate_area_code") as mock_validate:
            mock_validate.return_value = True

            with patch("app.api.residential_onboarding.get_supabase_client") as mock_sb:
                mock_client = MagicMock()
                mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"id": 1, "is_active": False}]
                )
                mock_sb.return_value = mock_client

                request = SetareaRequest(site_id="res-inactive", eskom_area_code="sandton-2")

                with pytest.raises(HTTPException) as exc_info:
                    await setarea_residential_site(request)
                assert exc_info.value.status_code == 400
