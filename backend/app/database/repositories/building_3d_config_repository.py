"""Repository for Building 3D Configuration data access layer.

Handles CRUD operations for building_3d_configs table with JSON fallback support.
Follows the dual-write pattern: primary write to Supabase, fallback to JSON files.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

# JSON file storage directory
DATA_DIR = Path(__file__).parent.parent.parent / "data"
BUILDINGS_DIR = DATA_DIR / "buildings"


class Building3DConfigRepository:
    """Repository for building 3D configuration data access."""

    def __init__(self):
        """Initialize repository with Supabase client."""
        self.supabase = get_supabase_client()

    def create(
        self,
        building_id: str,
        site_id: str,
        name: str,
        floors: List[Dict[str, Any]],
        equipment_positions: Optional[List[Dict[str, Any]]] = None,
        code: Optional[str] = None,
        created_by: str = "system",
    ) -> Optional[Dict[str, Any]]:
        """Create a new building 3D configuration.

        Args:
            building_id: UUID of the building
            site_id: Site identifier (e.g., "site-002")
            name: Building name
            floors: List of floor definitions
            equipment_positions: List of equipment positions (default: empty)
            code: Optional building code
            created_by: Username of creator

        Returns:
            Created config dict or None if failed
        """
        try:
            payload = {
                "building_id": building_id,
                "site_id": site_id,
                "name": name,
                "code": code,
                "floors": floors,
                "equipment_positions": equipment_positions or [],
                "zones": [],
                "created_by": created_by,
                "updated_by": created_by,
            }

            # Write to Supabase (primary)
            if self.supabase:
                try:
                    response = self.supabase.table("building_3d_configs").insert(
                        payload
                    ).execute()

                    if response.data and len(response.data) > 0:
                        logger.info(
                            f"✓ Created 3D config for building {building_id} in Supabase"
                        )
                        return response.data[0]
                except Exception as e:
                    logger.warning(
                        f"Failed to save 3D config to Supabase: {e}. Using JSON fallback."
                    )

            # Fallback: write to JSON
            self._save_to_json(building_id, payload)
            return payload

        except Exception as e:
            logger.error(f"Failed to create 3D config: {e}")
            return None

    def get_by_building_id(self, building_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve 3D configuration by building ID.

        Args:
            building_id: UUID of the building

        Returns:
            Config dict or None if not found
        """
        try:
            # Try Supabase (primary)
            if self.supabase:
                try:
                    response = self.supabase.table("building_3d_configs").select(
                        "*"
                    ).eq("building_id", building_id).execute()

                    if response.data and len(response.data) > 0:
                        return response.data[0]
                except Exception as e:
                    logger.debug(f"Supabase query failed: {e}. Trying JSON fallback.")

            # Fallback: load from JSON
            return self._load_from_json(building_id)

        except Exception as e:
            logger.error(f"Failed to retrieve 3D config: {e}")
            return None

    def update(
        self,
        building_id: str,
        floors: Optional[List[Dict[str, Any]]] = None,
        equipment_positions: Optional[List[Dict[str, Any]]] = None,
        zones: Optional[List[Dict[str, Any]]] = None,
        updated_by: str = "system",
    ) -> Optional[Dict[str, Any]]:
        """Update an existing 3D configuration.

        Args:
            building_id: UUID of the building
            floors: Updated floor definitions (optional)
            equipment_positions: Updated equipment positions (optional)
            zones: Updated zone definitions (optional)
            updated_by: Username of updater

        Returns:
            Updated config dict or None if failed
        """
        try:
            # Get existing config
            existing = self.get_by_building_id(building_id)
            if not existing:
                logger.warning(f"3D config not found for building {building_id}")
                return None

            # Build update payload
            update_payload: Dict[str, Any] = {"updated_by": updated_by}
            if floors is not None:
                update_payload["floors"] = floors
            if equipment_positions is not None:
                update_payload["equipment_positions"] = equipment_positions
            if zones is not None:
                update_payload["zones"] = zones

            # Update Supabase (primary)
            if self.supabase:
                try:
                    response = (
                        self.supabase.table("building_3d_configs")
                        .update(update_payload)
                        .eq("building_id", building_id)
                        .execute()
                    )

                    if response.data and len(response.data) > 0:
                        logger.info(
                            f"✓ Updated 3D config for building {building_id} in Supabase"
                        )
                        return response.data[0]
                except Exception as e:
                    logger.warning(
                        f"Failed to update 3D config in Supabase: {e}. Using JSON fallback."
                    )

            # Fallback: update JSON
            updated = {**existing, **update_payload}
            self._save_to_json(building_id, updated)
            return updated

        except Exception as e:
            logger.error(f"Failed to update 3D config: {e}")
            return None

    def delete(self, building_id: str) -> bool:
        """Delete 3D configuration for a building.

        Args:
            building_id: UUID of the building

        Returns:
            True if deleted, False if not found or error
        """
        try:
            # Delete from Supabase (primary)
            if self.supabase:
                try:
                    self.supabase.table("building_3d_configs").delete().eq(
                        "building_id", building_id
                    ).execute()
                    logger.info(f"✓ Deleted 3D config for building {building_id}")
                except Exception as e:
                    logger.warning(f"Failed to delete from Supabase: {e}")

            # Delete JSON fallback
            json_file = BUILDINGS_DIR / building_id / "config_3d.json"
            if json_file.exists():
                json_file.unlink()
                logger.info(f"✓ Deleted JSON config for building {building_id}")

            return True

        except Exception as e:
            logger.error(f"Failed to delete 3D config: {e}")
            return False

    def _save_to_json(self, building_id: str, config: Dict[str, Any]) -> None:
        """Save configuration to JSON file (fallback storage).

        Args:
            building_id: Building ID
            config: Configuration data
        """
        try:
            config_dir = BUILDINGS_DIR / building_id
            config_dir.mkdir(parents=True, exist_ok=True)

            config_file = config_dir / "config_3d.json"

            # Ensure datetime serialization
            config_copy = config.copy()
            if isinstance(config_copy.get("created_at"), datetime):
                config_copy["created_at"] = config_copy["created_at"].isoformat()
            if isinstance(config_copy.get("updated_at"), datetime):
                config_copy["updated_at"] = config_copy["updated_at"].isoformat()

            with open(config_file, "w") as f:
                json.dump(config_copy, f, indent=2)

            logger.debug(f"✓ Saved 3D config to JSON: {config_file}")

        except Exception as e:
            logger.error(f"Failed to save 3D config to JSON: {e}")

    def _load_from_json(self, building_id: str) -> Optional[Dict[str, Any]]:
        """Load configuration from JSON file (fallback storage).

        Args:
            building_id: Building ID

        Returns:
            Configuration dict or None if not found
        """
        try:
            config_file = BUILDINGS_DIR / building_id / "config_3d.json"

            if not config_file.exists():
                return None

            with open(config_file) as f:
                config = json.load(f)

            logger.debug(f"✓ Loaded 3D config from JSON: {config_file}")
            return config

        except Exception as e:
            logger.error(f"Failed to load 3D config from JSON: {e}")
            return None


# Singleton instance
_building_3d_config_repository: Optional[Building3DConfigRepository] = None


def get_building_3d_config_repository() -> Building3DConfigRepository:
    """Get or create singleton repository instance.

    Returns:
        Building3DConfigRepository instance
    """
    global _building_3d_config_repository

    if _building_3d_config_repository is None:
        _building_3d_config_repository = Building3DConfigRepository()

    return _building_3d_config_repository
