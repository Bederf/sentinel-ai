"""Focused tests for site onboarding behavior."""

import json

import pytest


class TestCreateSiteOnboarding:
    """Tests for site creation defaults used by the onboarding wizard."""

    @pytest.mark.asyncio
    async def test_create_site_starts_with_processing_disabled(self, monkeypatch, tmp_path):
        from app.api import sites as sites_api

        sites_dir = tmp_path / "sites"
        data_dir = tmp_path / "data"
        processing_file = data_dir / "site_processing_state.json"

        sites_dir.mkdir(parents=True, exist_ok=True)
        data_dir.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(sites_api, "SITES_DIR", sites_dir)
        monkeypatch.setattr(sites_api, "DATA_DIR", data_dir)
        monkeypatch.setattr(sites_api, "_PROCESSING_STATE_FILE", processing_file)
        monkeypatch.setattr(sites_api.settings, "use_json_storage", True)

        request = sites_api.CreateSiteRequest(
            name="Kloof Shopping Centre",
            address="Kloof Road",
            region="KwaZulu-Natal",
            type="retail",
            floors=["G", "L1"],
            sqm=12000,
        )

        response = await sites_api.create_site(request)

        assert response.id == "site-001"
        assert response.name == "Kloof Shopping Centre"

        building_json = sites_dir / response.id / "building.json"
        assert building_json.exists()

        with processing_file.open() as handle:
            processing_state = json.load(handle)

        assert processing_state[response.id] is False
