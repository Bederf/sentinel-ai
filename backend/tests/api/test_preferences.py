"""
Tests for dashboard preferences API.

RED phase tests for TDD - tests written before implementation.
Tests verify:
1. Repository pattern integration
2. Supabase + JSON fallback behavior
3. API endpoint functionality
4. Data validation
5. Header parsing
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database.repositories.preferences_repository import PreferencesRepository
from app.api.preferences import DashboardPreferences, DEFAULT_KPI_CARDS, DEFAULT_SECTIONS

client = TestClient(app)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def default_preferences():
    """Default preferences for testing."""
    return {
        "visible_kpi_cards": DEFAULT_KPI_CARDS,
        "visible_sections": DEFAULT_SECTIONS,
        "kpi_card_order": DEFAULT_KPI_CARDS,
        "section_order": DEFAULT_SECTIONS,
        "default_energy_period": 30,
        "default_energy_site_id": None,
    }


@pytest.fixture
def custom_preferences():
    """Custom preferences for testing updates."""
    return {
        "visible_kpi_cards": ["kpi-active-risks", "kpi-protected-sites"],
        "visible_sections": ["energy-analytics", "risk-predictions"],
        "kpi_card_order": ["kpi-active-risks", "kpi-protected-sites"],
        "section_order": ["energy-analytics", "risk-predictions"],
        "default_energy_period": 45,
        "default_energy_site_id": "site-001",
    }


@pytest.fixture
def preferences_repository():
    """Preferences repository for testing."""
    return PreferencesRepository()


@pytest.fixture
def mock_supabase_unavailable(monkeypatch):
    """Mock Supabase as unavailable, forcing JSON fallback."""
    def mock_get_supabase_client():
        raise Exception("Supabase unavailable")

    monkeypatch.setenv("USE_JSON_STORAGE", "true")


# ============================================================================
# API Endpoint Tests
# ============================================================================

class TestGetDashboardPreferences:
    """Tests for GET /api/preferences/dashboard endpoint."""

    def test_get_dashboard_preferences_default_user(self, default_preferences):
        """Test getting preferences for default user (no X-User-ID header)."""
        response = client.get("/api/preferences/dashboard")

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "default-user"
        assert "preferences" in data
        assert data["preferences"]["visible_kpi_cards"] == DEFAULT_KPI_CARDS
        assert data["preferences"]["default_energy_period"] == 30

    def test_get_dashboard_preferences_named_user(self):
        """Test getting preferences for named user (with X-User-ID header)."""
        response = client.get(
            "/api/preferences/dashboard",
            headers={"X-User-ID": "user-123"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "user-123"
        assert "preferences" in data

    def test_get_dashboard_preferences_not_found(self):
        """Test getting preferences for new user returns defaults."""
        response = client.get(
            "/api/preferences/dashboard",
            headers={"X-User-ID": "new-user-xyz"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "new-user-xyz"
        assert data["preferences"]["visible_kpi_cards"] == DEFAULT_KPI_CARDS
        assert data["preferences"]["default_energy_period"] == 30

    def test_get_default_preferences_endpoint(self, default_preferences):
        """Test GET /api/preferences/dashboard/defaults endpoint."""
        response = client.get("/api/preferences/dashboard/defaults")

        assert response.status_code == 200
        data = response.json()
        assert data["visible_kpi_cards"] == DEFAULT_KPI_CARDS
        assert data["visible_sections"] == DEFAULT_SECTIONS
        assert data["default_energy_period"] == 30


class TestUpdateDashboardPreferences:
    """Tests for PUT /api/preferences/dashboard endpoint."""

    def test_update_dashboard_preferences_upsert(self, custom_preferences):
        """Test creating new preferences (upsert for new user)."""
        response = client.put(
            "/api/preferences/dashboard",
            json=custom_preferences,
            headers={"X-User-ID": "test-user-update"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "test-user-update"
        assert data["preferences"]["visible_kpi_cards"] == custom_preferences["visible_kpi_cards"]
        assert data["preferences"]["default_energy_period"] == 45
        assert data["preferences"]["default_energy_site_id"] == "site-001"

    def test_update_dashboard_preferences_update_existing(self, custom_preferences):
        """Test updating existing preferences."""
        user_id = "test-user-update-existing"

        # First create preferences
        response1 = client.put(
            "/api/preferences/dashboard",
            json={
                "visible_kpi_cards": ["kpi-protected-sites"],
                "visible_sections": DEFAULT_SECTIONS,
                "kpi_card_order": ["kpi-protected-sites"],
                "section_order": DEFAULT_SECTIONS,
                "default_energy_period": 20,
            },
            headers={"X-User-ID": user_id}
        )
        assert response1.status_code == 200

        # Then update them
        response2 = client.put(
            "/api/preferences/dashboard",
            json=custom_preferences,
            headers={"X-User-ID": user_id}
        )

        assert response2.status_code == 200
        data = response2.json()
        assert data["preferences"]["default_energy_period"] == 45

    def test_update_preserves_fields(self):
        """Test that update preserves all fields correctly."""
        user_id = "test-user-preserve"
        prefs = {
            "visible_kpi_cards": ["kpi-active-risks"],
            "visible_sections": ["energy-analytics"],
            "kpi_card_order": ["kpi-active-risks"],
            "section_order": ["energy-analytics"],
            "default_energy_period": 60,
            "default_energy_site_id": "site-002",
        }

        response = client.put(
            "/api/preferences/dashboard",
            json=prefs,
            headers={"X-User-ID": user_id}
        )

        assert response.status_code == 200
        data = response.json()
        prefs_obj = data["preferences"]
        assert prefs_obj["visible_kpi_cards"] == prefs["visible_kpi_cards"]
        assert prefs_obj["visible_sections"] == prefs["visible_sections"]
        assert prefs_obj["default_energy_site_id"] == "site-002"


class TestResetDashboardPreferences:
    """Tests for DELETE /api/preferences/dashboard endpoint."""

    def test_reset_dashboard_preferences(self):
        """Test resetting preferences to defaults."""
        user_id = "test-user-reset"

        # First create preferences
        client.put(
            "/api/preferences/dashboard",
            json={
                "visible_kpi_cards": ["kpi-active-risks"],
                "visible_sections": ["energy-analytics"],
                "kpi_card_order": ["kpi-active-risks"],
                "section_order": ["energy-analytics"],
                "default_energy_period": 45,
            },
            headers={"X-User-ID": user_id}
        )

        # Then delete
        response = client.delete(
            "/api/preferences/dashboard",
            headers={"X-User-ID": user_id}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["user_id"] == user_id
        assert "reset to defaults" in data["message"].lower()


# ============================================================================
# Validation Tests
# ============================================================================

class TestValidation:
    """Tests for Pydantic model validation."""

    @pytest.mark.parametrize("invalid_period", [6, 91, 100, 0, -1])
    def test_invalid_energy_period(self, invalid_period):
        """Test that invalid energy periods are rejected (must be 7-90)."""
        response = client.put(
            "/api/preferences/dashboard",
            json={
                "visible_kpi_cards": DEFAULT_KPI_CARDS,
                "visible_sections": DEFAULT_SECTIONS,
                "kpi_card_order": DEFAULT_KPI_CARDS,
                "section_order": DEFAULT_SECTIONS,
                "default_energy_period": invalid_period,
            },
            headers={"X-User-ID": "test-user"}
        )

        # Should fail validation (422 Unprocessable Entity)
        assert response.status_code == 422

    def test_valid_energy_period_boundaries(self):
        """Test that valid energy periods are accepted (7-90)."""
        for period in [7, 30, 90]:
            response = client.put(
                "/api/preferences/dashboard",
                json={
                    "visible_kpi_cards": DEFAULT_KPI_CARDS,
                    "visible_sections": DEFAULT_SECTIONS,
                    "kpi_card_order": DEFAULT_KPI_CARDS,
                    "section_order": DEFAULT_SECTIONS,
                    "default_energy_period": period,
                },
                headers={"X-User-ID": f"test-user-period-{period}"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["preferences"]["default_energy_period"] == period

    def test_missing_fields_use_defaults(self):
        """Test that missing fields use default values."""
        response = client.put(
            "/api/preferences/dashboard",
            json={
                "visible_kpi_cards": DEFAULT_KPI_CARDS,
                # Missing visible_sections, kpi_card_order, section_order
                "default_energy_period": 30,
            },
            headers={"X-User-ID": "test-user-missing"}
        )

        # Should succeed with defaults for missing fields
        assert response.status_code == 200
        data = response.json()
        # The missing fields should use defaults
        assert data["preferences"]["visible_sections"] == DEFAULT_SECTIONS
        assert data["preferences"]["section_order"] == DEFAULT_SECTIONS


# ============================================================================
# Header Parsing Tests
# ============================================================================

class TestHeaderParsing:
    """Tests for X-User-ID header extraction."""

    def test_x_user_id_header_extraction(self):
        """Test that X-User-ID header is correctly extracted."""
        user_id = "custom-user-123"
        response = client.get(
            "/api/preferences/dashboard",
            headers={"X-User-ID": user_id}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == user_id

    def test_missing_x_user_id_defaults_to_default_user(self):
        """Test that missing X-User-ID defaults to 'default-user'."""
        response = client.get("/api/preferences/dashboard")

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "default-user"

    def test_empty_x_user_id_defaults_to_default_user(self):
        """Test that empty X-User-ID defaults to 'default-user'."""
        response = client.get(
            "/api/preferences/dashboard",
            headers={"X-User-ID": ""}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "default-user"


# ============================================================================
# Repository Tests
# ============================================================================

class TestPreferencesRepository:
    """Tests for PreferencesRepository implementation."""

    @pytest.mark.asyncio
    async def test_repository_get_by_user_id(self):
        """Test repository get_by_user_id method."""
        repo = PreferencesRepository()

        # Should return None or default for new user
        result = await repo.get_by_user_id("repo-test-user-1")
        # Result can be None or empty dict depending on mode
        assert result is None or isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_repository_upsert(self):
        """Test repository upsert method."""
        repo = PreferencesRepository()
        prefs = DashboardPreferences(
            visible_kpi_cards=["kpi-active-risks"],
            default_energy_period=50,
        )

        result = await repo.upsert("repo-test-user-2", prefs)

        assert result is not None
        assert isinstance(result, dict)
        assert result["user_id"] == "repo-test-user-2"
        assert result["default_energy_period"] == 50

    @pytest.mark.asyncio
    async def test_repository_delete(self):
        """Test repository delete method."""
        repo = PreferencesRepository()

        # First create preferences
        prefs = DashboardPreferences()
        await repo.upsert("repo-test-user-3", prefs)

        # Then delete
        result = await repo.delete("repo-test-user-3")

        assert result is True

    @pytest.mark.asyncio
    async def test_repository_get_defaults(self):
        """Test repository get_defaults method."""
        repo = PreferencesRepository()

        defaults = await repo.get_defaults()

        assert defaults["user_id"] == "default-user"
        assert defaults["visible_kpi_cards"] == DEFAULT_KPI_CARDS
        assert defaults["default_energy_period"] == 30

    @pytest.mark.asyncio
    async def test_repository_json_storage_mode(self, monkeypatch):
        """Test repository in JSON storage fallback mode."""
        monkeypatch.setenv("USE_JSON_STORAGE", "true")

        # Create new repository with JSON mode forced
        repo = PreferencesRepository()
        assert repo.use_json is True

    @pytest.mark.asyncio
    async def test_repository_upsert_retrieval_cycle(self):
        """Test full upsert and retrieve cycle."""
        repo = PreferencesRepository()
        user_id = "repo-test-cycle"
        prefs = DashboardPreferences(
            visible_kpi_cards=["kpi-protected-sites", "kpi-active-risks"],
            default_energy_period=75,
        )

        # Upsert
        await repo.upsert(user_id, prefs)

        # Retrieve
        result = await repo.get_by_user_id(user_id)

        assert result is not None
        assert result["user_id"] == user_id
        assert result["default_energy_period"] == 75


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests for complete workflows."""

    def test_complete_user_preference_lifecycle(self):
        """Test complete lifecycle: create -> read -> update -> delete."""
        user_id = "lifecycle-test-user"

        # 1. Create preferences
        create_response = client.put(
            "/api/preferences/dashboard",
            json={
                "visible_kpi_cards": ["kpi-protected-sites"],
                "visible_sections": DEFAULT_SECTIONS,
                "kpi_card_order": ["kpi-protected-sites"],
                "section_order": DEFAULT_SECTIONS,
                "default_energy_period": 40,
            },
            headers={"X-User-ID": user_id}
        )
        assert create_response.status_code == 200

        # 2. Read preferences
        read_response = client.get(
            "/api/preferences/dashboard",
            headers={"X-User-ID": user_id}
        )
        assert read_response.status_code == 200
        data = read_response.json()
        assert data["preferences"]["default_energy_period"] == 40

        # 3. Update preferences
        update_response = client.put(
            "/api/preferences/dashboard",
            json={
                "visible_kpi_cards": ["kpi-active-risks"],
                "visible_sections": ["energy-analytics"],
                "kpi_card_order": ["kpi-active-risks"],
                "section_order": ["energy-analytics"],
                "default_energy_period": 60,
            },
            headers={"X-User-ID": user_id}
        )
        assert update_response.status_code == 200

        # 4. Verify update
        verify_response = client.get(
            "/api/preferences/dashboard",
            headers={"X-User-ID": user_id}
        )
        assert verify_response.status_code == 200
        data = verify_response.json()
        assert data["preferences"]["default_energy_period"] == 60

        # 5. Delete preferences
        delete_response = client.delete(
            "/api/preferences/dashboard",
            headers={"X-User-ID": user_id}
        )
        assert delete_response.status_code == 200

    def test_multiple_users_isolation(self):
        """Test that different users' preferences are isolated."""
        # Create preferences for user 1
        response1 = client.put(
            "/api/preferences/dashboard",
            json={
                "visible_kpi_cards": ["kpi-protected-sites"],
                "visible_sections": DEFAULT_SECTIONS,
                "kpi_card_order": ["kpi-protected-sites"],
                "section_order": DEFAULT_SECTIONS,
                "default_energy_period": 30,
            },
            headers={"X-User-ID": "user-1"}
        )
        assert response1.status_code == 200

        # Create preferences for user 2
        response2 = client.put(
            "/api/preferences/dashboard",
            json={
                "visible_kpi_cards": ["kpi-active-risks"],
                "visible_sections": ["energy-analytics"],
                "kpi_card_order": ["kpi-active-risks"],
                "section_order": ["energy-analytics"],
                "default_energy_period": 60,
            },
            headers={"X-User-ID": "user-2"}
        )
        assert response2.status_code == 200

        # Verify user 1 preferences unchanged
        get1 = client.get(
            "/api/preferences/dashboard",
            headers={"X-User-ID": "user-1"}
        )
        assert get1.json()["preferences"]["default_energy_period"] == 30

        # Verify user 2 preferences unchanged
        get2 = client.get(
            "/api/preferences/dashboard",
            headers={"X-User-ID": "user-2"}
        )
        assert get2.json()["preferences"]["default_energy_period"] == 60
