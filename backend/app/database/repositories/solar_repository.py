"""Repository for solar/BESS equipment operations."""

import logging
import time
from typing import Any

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class SolarRepository:
    """Repository for solar site, plant, inverter, BESS, and meter operations.

    Provides unified access to solar infrastructure data from Supabase
    with automatic JSON fallback when Supabase is unavailable.
    """

    def __init__(self):
        """Initialize the repository with a Supabase client."""
        self.client = get_supabase_client()

    def _execute_with_retry(self, query, max_retries: int = 3):
        """Execute a Supabase query with retry on rate limit.

        Args:
            query: Supabase query object
            max_retries: Maximum number of retries

        Returns:
            Response data
        """
        delay = 0.5
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                return query.execute()
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "rate limit" in error_msg.lower():
                    last_error = e
                    if attempt < max_retries:
                        logger.warning(f"Rate limit hit, retrying in {delay}s... (attempt {attempt + 1}/{max_retries})")
                        time.sleep(delay)
                        delay *= 2.0
                    else:
                        logger.error(f"Rate limit persists after {max_retries} retries")
                        raise e
                else:
                    raise e

        if last_error:
            raise last_error

    # === Solar Sites ===

    def get_sites(self) -> list[dict[str, Any]]:
        """Get all registered solar sites."""
        try:
            response = self._execute_with_retry(self.client.table("solar_sites").select("*"))
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to fetch solar sites: {e}")
            return []

    def get_site_by_id(self, site_id: str) -> dict[str, Any] | None:
        """Get a solar site by its ID."""
        try:
            response = self._execute_with_retry(self.client.table("solar_sites").select("*").eq("site_id", site_id))
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Failed to fetch solar site {site_id}: {e}")
            return None

    def create_site(self, site_data: dict[str, Any]) -> dict[str, Any] | None:
        """Create a new solar site."""
        try:
            response = self._execute_with_retry(self.client.table("solar_sites").insert(site_data))
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Failed to create solar site: {e}")
            return None

    # === Solar Plants ===

    def get_plants(self, site_id: str | None = None) -> list[dict[str, Any]]:
        """Get all solar plants, optionally filtered by site."""
        try:
            query = self.client.table("solar_plants").select("*")
            if site_id:
                query = query.eq("site_id", site_id)
            response = self._execute_with_retry(query)
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to fetch solar plants: {e}")
            return []

    def get_plant_by_id(self, plant_id: str) -> dict[str, Any] | None:
        """Get a solar plant by its ID."""
        try:
            response = self._execute_with_retry(self.client.table("solar_plants").select("*").eq("plant_id", plant_id))
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Failed to fetch solar plant {plant_id}: {e}")
            return None

    def create_plant(self, plant_data: dict[str, Any]) -> dict[str, Any] | None:
        """Create a new solar plant."""
        try:
            response = self._execute_with_retry(self.client.table("solar_plants").insert(plant_data))
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Failed to create solar plant: {e}")
            return None

    # === Solar Inverters ===

    def get_inverters(self, site_id: str | None = None, plant_id: str | None = None) -> list[dict[str, Any]]:
        """Get all inverters, optionally filtered by site or plant."""
        try:
            query = self.client.table("solar_inverters").select("*")
            if site_id:
                query = query.eq("site_id", site_id)
            if plant_id:
                query = query.eq("plant_id", plant_id)
            response = self._execute_with_retry(query)
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to fetch solar inverters: {e}")
            return []

    def get_inverter_by_id(self, inverter_id: str) -> dict[str, Any] | None:
        """Get an inverter by its ID."""
        try:
            response = self._execute_with_retry(
                self.client.table("solar_inverters").select("*").eq("inverter_id", inverter_id)
            )
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Failed to fetch inverter {inverter_id}: {e}")
            return None

    def create_inverter(self, inverter_data: dict[str, Any]) -> dict[str, Any] | None:
        """Create a new inverter record."""
        try:
            response = self._execute_with_retry(self.client.table("solar_inverters").insert(inverter_data))
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Failed to create inverter: {e}")
            return None

    # === BESS Containers ===

    def get_bess(self, site_id: str | None = None) -> list[dict[str, Any]]:
        """Get all BESS containers, optionally filtered by site."""
        try:
            query = self.client.table("solar_bess").select("*")
            if site_id:
                query = query.eq("site_id", site_id)
            response = self._execute_with_retry(query)
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to fetch BESS containers: {e}")
            return []

    def get_bess_by_id(self, container_id: str) -> dict[str, Any] | None:
        """Get a BESS container by its ID."""
        try:
            response = self._execute_with_retry(
                self.client.table("solar_bess").select("*").eq("container_id", container_id)
            )
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Failed to fetch BESS container {container_id}: {e}")
            return None

    def create_bess(self, bess_data: dict[str, Any]) -> dict[str, Any] | None:
        """Create a new BESS container record."""
        try:
            response = self._execute_with_retry(self.client.table("solar_bess").insert(bess_data))
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Failed to create BESS container: {e}")
            return None

    # === Grid Meters ===

    def get_meters(self, site_id: str | None = None) -> list[dict[str, Any]]:
        """Get all grid meters, optionally filtered by site."""
        try:
            query = self.client.table("solar_meters").select("*")
            if site_id:
                query = query.eq("site_id", site_id)
            response = self._execute_with_retry(query)
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to fetch meters: {e}")
            return []

    def get_meter_by_id(self, meter_id: str) -> dict[str, Any] | None:
        """Get a meter by its ID."""
        try:
            response = self._execute_with_retry(self.client.table("solar_meters").select("*").eq("meter_id", meter_id))
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Failed to fetch meter {meter_id}: {e}")
            return None

    def create_meter(self, meter_data: dict[str, Any]) -> dict[str, Any] | None:
        """Create a new meter record."""
        try:
            response = self._execute_with_retry(self.client.table("solar_meters").insert(meter_data))
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Failed to create meter: {e}")
            return None

    # === Equipment Hierarchy ===

    def get_system_status(self, site_id: str) -> dict[str, Any] | None:
        """Get complete equipment hierarchy and status for a site."""
        try:
            site = self.get_site_by_id(site_id)
            if not site:
                return None

            plants = self.get_plants(site_id)
            inverters = self.get_inverters(site_id)
            bess = self.get_bess(site_id)
            meters = self.get_meters(site_id)

            return {
                "site": site,
                "plants": plants,
                "inverters": inverters,
                "bess": bess,
                "meters": meters,
            }
        except Exception as e:
            logger.error(f"Failed to fetch system status for {site_id}: {e}")
            return None
