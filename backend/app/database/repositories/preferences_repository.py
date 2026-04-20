"""Repository for dashboard preferences operations.

Implements Supabase + JSON fallback pattern for user preferences persistence.
"""

import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.database.supabase_client import get_supabase_client

if TYPE_CHECKING:
    from app.api.preferences import DashboardPreferences

logger = logging.getLogger(__name__)


class PreferencesRepository:
    """Repository for dashboard preferences database operations.

    Implements fallback pattern:
    - Primary: Supabase (if available)
    - Fallback: JSON file (if USE_JSON_STORAGE=true or Supabase unavailable)
    """

    def __init__(self):
        """Initialize the repository."""
        self.use_json = os.getenv("USE_JSON_STORAGE", "false").lower() == "true"
        self.json_file = Path(__file__).parent.parent / "data" / "dashboard_preferences.json"
        self.client = None

        # Force JSON in TESTING mode
        if os.getenv("TESTING", "").lower() == "true":
            self.use_json = True

        if not self.use_json:
            try:
                self.client = get_supabase_client()
            except Exception as e:
                logger.warning(f"Supabase client initialization failed, falling back to JSON: {e}")
                self.use_json = True

        # Ensure JSON file exists
        if self.use_json:
            self._ensure_json_file_exists()

    def _ensure_json_file_exists(self) -> None:
        """Ensure the JSON storage file exists."""
        if not self.json_file.exists():
            self.json_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.json_file, "w") as f:
                json.dump({}, f, indent=2)
            logger.info(f"Created JSON preferences file: {self.json_file}")

    def _load_json_data(self) -> dict[str, Any]:
        """Load all preferences from JSON file."""
        try:
            with open(self.json_file) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading JSON preferences: {e}")
            return {}

    def _save_json_data(self, data: dict[str, Any]) -> None:
        """Save all preferences to JSON file."""
        try:
            with open(self.json_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving JSON preferences: {e}")

    async def get_by_user_id(self, user_id: str) -> dict[str, Any] | None:
        """Get preferences by user ID.

        Args:
            user_id: User ID to retrieve preferences for

        Returns:
            Dictionary with preferences or None if not found
        """
        if self.use_json:
            data = self._load_json_data()
            return data.get(user_id)

        try:
            result = self.client.table("dashboard_preferences").select("*").eq("user_id", user_id).execute()
            if result.data and len(result.data) > 0:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"Error retrieving preferences for user {user_id}: {e}")
            return None

    async def upsert(self, user_id: str, preferences: "DashboardPreferences") -> dict[str, Any]:
        """Create or update preferences for a user.

        Args:
            user_id: User ID to save preferences for
            preferences: DashboardPreferences instance to save

        Returns:
            Dictionary with saved preferences
        """
        if self.use_json:
            data = self._load_json_data()
            data[user_id] = {
                "user_id": user_id,
                "visible_kpi_cards": preferences.visible_kpi_cards,
                "visible_sections": preferences.visible_sections,
                "kpi_card_order": preferences.kpi_card_order,
                "section_order": preferences.section_order,
                "default_energy_period": preferences.default_energy_period,
                "default_energy_site_id": preferences.default_energy_site_id,
            }
            self._save_json_data(data)
            return data[user_id]

        try:
            data = {
                "user_id": user_id,
                "visible_kpi_cards": preferences.visible_kpi_cards,
                "visible_sections": preferences.visible_sections,
                "kpi_card_order": preferences.kpi_card_order,
                "section_order": preferences.section_order,
                "default_energy_period": preferences.default_energy_period,
                "default_energy_site_id": preferences.default_energy_site_id,
            }

            result = self.client.table("dashboard_preferences").upsert(data, on_conflict="user_id").execute()

            if result.data and len(result.data) > 0:
                return result.data[0]
            return data
        except Exception as e:
            logger.error(f"Error upserting preferences for user {user_id}: {e}")
            raise

    async def delete(self, user_id: str) -> bool:
        """Delete preferences for a user.

        Args:
            user_id: User ID to delete preferences for

        Returns:
            True if deletion succeeded, False otherwise
        """
        if self.use_json:
            data = self._load_json_data()
            if user_id in data:
                del data[user_id]
                self._save_json_data(data)
                return True
            return False

        try:
            self.client.table("dashboard_preferences").delete().eq("user_id", user_id).execute()
            return True
        except Exception as e:
            logger.error(f"Error deleting preferences for user {user_id}: {e}")
            return False

    async def get_defaults(self) -> dict[str, Any]:
        """Get default preferences.

        Returns:
            Dictionary with default preferences
        """
        # Import here to avoid circular imports
        from app.api.preferences import DEFAULT_KPI_CARDS, DEFAULT_SECTIONS

        return {
            "user_id": "default-user",
            "visible_kpi_cards": DEFAULT_KPI_CARDS,
            "visible_sections": DEFAULT_SECTIONS,
            "kpi_card_order": DEFAULT_KPI_CARDS,
            "section_order": DEFAULT_SECTIONS,
            "default_energy_period": 30,
            "default_energy_site_id": None,
        }
