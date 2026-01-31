"""Repository for energy centre and component operations."""

from typing import List, Optional, Dict, Any
import logging
from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class EnergyCentreRepository:
    """Repository for energy centre database operations.

    Handles multiple tables:
    - energy_centres: Main container
    - mv_incomers: Medium voltage supply
    - transformers: MV/LV transformers
    - lv_switchboards: Main distribution
    - ats_units: Automatic transfer switches
    - power_meters: Energy metering
    - pfc_banks: Power factor correction
    - ups_systems: UPS with battery monitoring
    - feeders: Distribution feeders
    """

    def __init__(self):
        """Initialize the repository with a Supabase client."""
        self.client = get_supabase_client()

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def get_building_uuid(self, building_code: str) -> Optional[str]:
        """Get building UUID from building code."""
        response = self.client.table('buildings').select('id').eq(
            'code', building_code
        ).execute()

        if response.data:
            return response.data[0]['id']
        return None

    def get_ec_uuid(self, centre_id: str) -> Optional[str]:
        """Get energy centre UUID from centre_id."""
        response = self.client.table('energy_centres').select('id').eq(
            'centre_id', centre_id
        ).execute()

        if response.data:
            return response.data[0]['id']
        return None

    def get_ec_uuid_by_building(self, building_code: str) -> Optional[str]:
        """Get energy centre UUID by building code."""
        building_uuid = self.get_building_uuid(building_code)
        if not building_uuid:
            return None

        response = self.client.table('energy_centres').select('id').eq(
            'building_id', building_uuid
        ).execute()

        if response.data:
            return response.data[0]['id']
        return None

    # =========================================================================
    # Energy Centres
    # =========================================================================

    def get_energy_centre(self, building_code: str) -> Optional[Dict[str, Any]]:
        """Get energy centre for a building."""
        building_uuid = self.get_building_uuid(building_code)
        if not building_uuid:
            return None

        response = self.client.table('energy_centres').select("*").eq(
            'building_id', building_uuid
        ).execute()

        if response.data:
            return response.data[0]
        return None

    def get_energy_centre_by_id(self, centre_id: str) -> Optional[Dict[str, Any]]:
        """Get energy centre by centre_id."""
        response = self.client.table('energy_centres').select("*").eq(
            'centre_id', centre_id
        ).execute()

        if response.data:
            return response.data[0]
        return None

    def upsert_energy_centre(self, ec_data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert or update an energy centre."""
        response = self.client.table('energy_centres').upsert(
            ec_data,
            on_conflict='centre_id'
        ).execute()
        return response.data[0] if response.data else {}

    def delete_energy_centre(self, centre_id: str) -> bool:
        """Delete an energy centre (cascades to components)."""
        response = self.client.table('energy_centres').delete().eq(
            'centre_id', centre_id
        ).execute()
        return len(response.data) > 0

    # =========================================================================
    # MV Incomers
    # =========================================================================

    def get_mv_incomers(self, centre_id: str) -> List[Dict[str, Any]]:
        """Get MV incomers for an energy centre."""
        ec_uuid = self.get_ec_uuid(centre_id)
        if not ec_uuid:
            return []

        response = self.client.table('mv_incomers').select("*").eq(
            'energy_centre_id', ec_uuid
        ).execute()

        return response.data

    def upsert_mv_incomer(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert or update an MV incomer."""
        response = self.client.table('mv_incomers').upsert(
            data,
            on_conflict='incomer_id'
        ).execute()
        return response.data[0] if response.data else {}

    def upsert_mv_incomers(self, incomers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Insert or update multiple MV incomers."""
        if not incomers:
            return []
        response = self.client.table('mv_incomers').upsert(
            incomers,
            on_conflict='incomer_id'
        ).execute()
        return response.data

    # =========================================================================
    # Transformers
    # =========================================================================

    def get_transformers(self, centre_id: str) -> List[Dict[str, Any]]:
        """Get transformers for an energy centre."""
        ec_uuid = self.get_ec_uuid(centre_id)
        if not ec_uuid:
            return []

        response = self.client.table('transformers').select("*").eq(
            'energy_centre_id', ec_uuid
        ).execute()

        return response.data

    def upsert_transformer(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert or update a transformer."""
        response = self.client.table('transformers').upsert(
            data,
            on_conflict='transformer_id'
        ).execute()
        return response.data[0] if response.data else {}

    def upsert_transformers(self, transformers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Insert or update multiple transformers."""
        if not transformers:
            return []
        response = self.client.table('transformers').upsert(
            transformers,
            on_conflict='transformer_id'
        ).execute()
        return response.data

    # =========================================================================
    # LV Switchboards
    # =========================================================================

    def get_switchboards(self, centre_id: str) -> List[Dict[str, Any]]:
        """Get LV switchboards for an energy centre."""
        ec_uuid = self.get_ec_uuid(centre_id)
        if not ec_uuid:
            return []

        response = self.client.table('lv_switchboards').select("*").eq(
            'energy_centre_id', ec_uuid
        ).execute()

        return response.data

    def upsert_switchboard(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert or update an LV switchboard."""
        response = self.client.table('lv_switchboards').upsert(
            data,
            on_conflict='switchboard_id'
        ).execute()
        return response.data[0] if response.data else {}

    def upsert_switchboards(self, switchboards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Insert or update multiple switchboards."""
        if not switchboards:
            return []
        response = self.client.table('lv_switchboards').upsert(
            switchboards,
            on_conflict='switchboard_id'
        ).execute()
        return response.data

    def get_switchboard_uuid(self, switchboard_id: str) -> Optional[str]:
        """Get switchboard UUID from switchboard_id."""
        response = self.client.table('lv_switchboards').select('id').eq(
            'switchboard_id', switchboard_id
        ).execute()

        if response.data:
            return response.data[0]['id']
        return None

    # =========================================================================
    # ATS Units
    # =========================================================================

    def get_ats_units(self, centre_id: str) -> List[Dict[str, Any]]:
        """Get ATS units for an energy centre."""
        ec_uuid = self.get_ec_uuid(centre_id)
        if not ec_uuid:
            return []

        response = self.client.table('ats_units').select("*").eq(
            'energy_centre_id', ec_uuid
        ).execute()

        return response.data

    def upsert_ats_unit(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert or update an ATS unit."""
        response = self.client.table('ats_units').upsert(
            data,
            on_conflict='ats_id'
        ).execute()
        return response.data[0] if response.data else {}

    def upsert_ats_units(self, ats_units: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Insert or update multiple ATS units."""
        if not ats_units:
            return []
        response = self.client.table('ats_units').upsert(
            ats_units,
            on_conflict='ats_id'
        ).execute()
        return response.data

    # =========================================================================
    # Power Meters
    # =========================================================================

    def get_power_meters(self, centre_id: str) -> List[Dict[str, Any]]:
        """Get power meters for an energy centre."""
        ec_uuid = self.get_ec_uuid(centre_id)
        if not ec_uuid:
            return []

        response = self.client.table('power_meters').select("*").eq(
            'energy_centre_id', ec_uuid
        ).execute()

        return response.data

    def upsert_power_meter(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert or update a power meter."""
        response = self.client.table('power_meters').upsert(
            data,
            on_conflict='meter_id'
        ).execute()
        return response.data[0] if response.data else {}

    def upsert_power_meters(self, meters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Insert or update multiple power meters."""
        if not meters:
            return []
        response = self.client.table('power_meters').upsert(
            meters,
            on_conflict='meter_id'
        ).execute()
        return response.data

    # =========================================================================
    # PFC Banks
    # =========================================================================

    def get_pfc_banks(self, centre_id: str) -> List[Dict[str, Any]]:
        """Get PFC banks for an energy centre."""
        ec_uuid = self.get_ec_uuid(centre_id)
        if not ec_uuid:
            return []

        response = self.client.table('pfc_banks').select("*").eq(
            'energy_centre_id', ec_uuid
        ).execute()

        return response.data

    def upsert_pfc_bank(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert or update a PFC bank."""
        response = self.client.table('pfc_banks').upsert(
            data,
            on_conflict='pfc_id'
        ).execute()
        return response.data[0] if response.data else {}

    def upsert_pfc_banks(self, pfc_banks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Insert or update multiple PFC banks."""
        if not pfc_banks:
            return []
        response = self.client.table('pfc_banks').upsert(
            pfc_banks,
            on_conflict='pfc_id'
        ).execute()
        return response.data

    # =========================================================================
    # UPS Systems
    # =========================================================================

    def get_ups_systems(self, centre_id: str) -> List[Dict[str, Any]]:
        """Get UPS systems for an energy centre."""
        ec_uuid = self.get_ec_uuid(centre_id)
        if not ec_uuid:
            return []

        response = self.client.table('ups_systems').select("*").eq(
            'energy_centre_id', ec_uuid
        ).execute()

        return response.data

    def upsert_ups_system(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert or update a UPS system."""
        response = self.client.table('ups_systems').upsert(
            data,
            on_conflict='ups_id'
        ).execute()
        return response.data[0] if response.data else {}

    def upsert_ups_systems(self, ups_systems: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Insert or update multiple UPS systems."""
        if not ups_systems:
            return []
        response = self.client.table('ups_systems').upsert(
            ups_systems,
            on_conflict='ups_id'
        ).execute()
        return response.data

    # =========================================================================
    # Feeders
    # =========================================================================

    def get_feeders(self, centre_id: str) -> List[Dict[str, Any]]:
        """Get feeders for an energy centre."""
        ec_uuid = self.get_ec_uuid(centre_id)
        if not ec_uuid:
            return []

        response = self.client.table('feeders').select("*").eq(
            'energy_centre_id', ec_uuid
        ).execute()

        return response.data

    def upsert_feeder(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert or update a feeder."""
        response = self.client.table('feeders').upsert(
            data,
            on_conflict='feeder_id'
        ).execute()
        return response.data[0] if response.data else {}

    def upsert_feeders(self, feeders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Insert or update multiple feeders."""
        if not feeders:
            return []
        response = self.client.table('feeders').upsert(
            feeders,
            on_conflict='feeder_id'
        ).execute()
        return response.data

    # =========================================================================
    # Full Energy Centre Operations
    # =========================================================================

    def get_full_energy_centre(self, building_code: str) -> Dict[str, Any]:
        """Get complete energy centre configuration for a building.

        Returns:
            Dict with energy_centre and all components
        """
        ec = self.get_energy_centre(building_code)
        if not ec:
            return {}

        centre_id = ec.get('centre_id')

        return {
            'energy_centre': ec,
            'mv_incomers': self.get_mv_incomers(centre_id),
            'transformers': self.get_transformers(centre_id),
            'lv_switchboards': self.get_switchboards(centre_id),
            'ats_units': self.get_ats_units(centre_id),
            'power_meters': self.get_power_meters(centre_id),
            'pfc_banks': self.get_pfc_banks(centre_id),
            'ups_systems': self.get_ups_systems(centre_id),
            'feeders': self.get_feeders(centre_id),
        }

    def delete_all_by_building(self, building_code: str) -> Dict[str, int]:
        """Delete all energy centre data for a building.

        Deletes energy_centre which cascades to all components.

        Returns:
            Dict with count of deleted items
        """
        building_uuid = self.get_building_uuid(building_code)
        if not building_uuid:
            return {'energy_centres': 0}

        response = self.client.table('energy_centres').delete().eq(
            'building_id', building_uuid
        ).execute()

        return {'energy_centres': len(response.data)}
