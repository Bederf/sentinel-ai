"""Repository for integration/log source operations."""

from typing import List, Optional, Dict, Any
from datetime import datetime
from app.database.supabase_client import get_supabase_client


class IntegrationRepository:
    """Repository for integration database operations."""

    def __init__(self):
        self.client = get_supabase_client()

    # ==================== Log Sources ====================

    def get_log_sources(
        self,
        building_id: Optional[str] = None,
        source_type: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """Get log sources with optional filtering."""
        query = self.client.table('log_sources').select("*")

        if building_id:
            query = query.eq('building_id', building_id)
        if source_type:
            query = query.eq('source_type', source_type)
        if is_active is not None:
            query = query.eq('is_active', is_active)

        response = query.order('created_at', desc=True).execute()
        return response.data

    def get_log_source(self, source_id: str) -> Optional[Dict[str, Any]]:
        """Get log source by ID."""
        response = self.client.table('log_sources').select("*").eq('id', source_id).execute()
        return response.data[0] if response.data else None

    def create_log_source(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new log source."""
        response = self.client.table('log_sources').insert(data).execute()
        return response.data[0]

    def update_log_source(self, source_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a log source."""
        response = self.client.table('log_sources').update(data).eq('id', source_id).execute()
        return response.data[0] if response.data else None

    def delete_log_source(self, source_id: str) -> bool:
        """Delete a log source."""
        response = self.client.table('log_sources').delete().eq('id', source_id).execute()
        return len(response.data) > 0

    def update_sync_status(
        self,
        source_id: str,
        status: str,
        records: int = 0,
        error: Optional[str] = None,
    ) -> None:
        """Update last sync status for a log source."""
        self.client.table('log_sources').update({
            'last_sync_at': datetime.utcnow().isoformat(),
            'last_sync_status': status,
            'last_sync_records': records,
            'last_sync_error': error,
        }).eq('id', source_id).execute()

    # ==================== Column Mappings ====================

    def get_column_mappings(self, source_id: str) -> List[Dict[str, Any]]:
        """Get column mappings for a log source."""
        response = self.client.table('column_mappings').select("*").eq(
            'log_source_id', source_id
        ).execute()
        return response.data

    def save_column_mappings(
        self,
        source_id: str,
        mappings: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Save column mappings (replace all for source)."""
        # Delete existing
        self.client.table('column_mappings').delete().eq('log_source_id', source_id).execute()

        # Insert new
        if mappings:
            for m in mappings:
                m['log_source_id'] = source_id
            response = self.client.table('column_mappings').insert(mappings).execute()
            return response.data
        return []

    # ==================== Point-Asset Mappings ====================

    def get_point_mappings(
        self,
        building_id: str,
        confidence: Optional[str] = None,
        verified_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """Get point-to-asset mappings for a building."""
        query = self.client.table('point_asset_mappings').select("*").eq(
            'building_id', building_id
        )

        if confidence:
            query = query.eq('match_confidence', confidence)
        if verified_only:
            query = query.eq('is_verified', True)

        response = query.execute()
        return response.data

    def get_point_mapping(self, building_id: str, point_id: str) -> Optional[Dict[str, Any]]:
        """Get mapping for a specific point."""
        response = self.client.table('point_asset_mappings').select("*").eq(
            'building_id', building_id
        ).eq('bms_point_id', point_id).execute()
        return response.data[0] if response.data else None

    def upsert_point_mapping(self, building_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create or update point mapping."""
        data['building_id'] = building_id
        response = self.client.table('point_asset_mappings').upsert(
            data,
            on_conflict='building_id,bms_point_id'
        ).execute()
        return response.data[0]

    def bulk_upsert_point_mappings(
        self,
        building_id: str,
        mappings: List[Dict[str, Any]],
    ) -> int:
        """Bulk upsert point mappings."""
        for m in mappings:
            m['building_id'] = building_id

        response = self.client.table('point_asset_mappings').upsert(
            mappings,
            on_conflict='building_id,bms_point_id'
        ).execute()
        return len(response.data)

    def verify_point_mapping(self, mapping_id: str, cafm_asset_id: str) -> Dict[str, Any]:
        """Manually verify/correct a point mapping."""
        response = self.client.table('point_asset_mappings').update({
            'cafm_asset_id': cafm_asset_id,
            'match_confidence': 'manual',
            'is_verified': True,
        }).eq('id', mapping_id).execute()
        return response.data[0]

    # ==================== Ingested Data ====================

    def insert_alarms(self, alarms: List[Dict[str, Any]]) -> int:
        """Insert parsed alarms (with deduplication)."""
        if not alarms:
            return 0

        # Upsert to handle duplicates
        response = self.client.table('ingested_alarms').upsert(
            alarms,
            on_conflict='log_source_id,source_hash'
        ).execute()
        return len(response.data)

    def insert_trends(self, trends: List[Dict[str, Any]]) -> int:
        """Insert parsed trends (with deduplication)."""
        if not trends:
            return 0

        response = self.client.table('ingested_trends').upsert(
            trends,
            on_conflict='log_source_id,point_id,recorded_at'
        ).execute()
        return len(response.data)

    def get_recent_alarms(
        self,
        building_id: str,
        limit: int = 100,
        severity: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get recent alarms for a building."""
        query = self.client.table('ingested_alarms').select("*").eq(
            'building_id', building_id
        )

        if severity:
            query = query.eq('severity', severity)

        response = query.order('occurred_at', desc=True).limit(limit).execute()
        return response.data

    # ==================== Sync Jobs ====================

    def create_sync_job(self, source_id: str, file_name: Optional[str] = None) -> Dict[str, Any]:
        """Create a new sync job record."""
        response = self.client.table('sync_jobs').insert({
            'log_source_id': source_id,
            'status': 'running',
            'file_name': file_name,
        }).execute()
        return response.data[0]

    def complete_sync_job(
        self,
        job_id: str,
        status: str,
        processed: int,
        inserted: int,
        skipped: int,
        failed: int,
        error_message: Optional[str] = None,
        processing_time_ms: Optional[int] = None,
    ) -> None:
        """Complete a sync job with results."""
        self.client.table('sync_jobs').update({
            'completed_at': datetime.utcnow().isoformat(),
            'status': status,
            'records_processed': processed,
            'records_inserted': inserted,
            'records_skipped': skipped,
            'records_failed': failed,
            'error_message': error_message,
            'processing_time_ms': processing_time_ms,
        }).eq('id', job_id).execute()

    def get_sync_jobs(
        self,
        source_id: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get recent sync jobs for a source."""
        response = self.client.table('sync_jobs').select("*").eq(
            'log_source_id', source_id
        ).order('started_at', desc=True).limit(limit).execute()
        return response.data

    # ==================== CAFM Data ====================

    def upsert_cafm_assets(
        self,
        building_id: str,
        source_id: str,
        assets: List[Dict[str, Any]],
    ) -> int:
        """Upsert synced CAFM assets."""
        for a in assets:
            a['building_id'] = building_id
            a['log_source_id'] = source_id
            a['last_synced_at'] = datetime.utcnow().isoformat()

        response = self.client.table('cafm_assets').upsert(
            assets,
            on_conflict='building_id,cafm_id'
        ).execute()
        return len(response.data)

    def get_cafm_assets(self, building_id: str) -> List[Dict[str, Any]]:
        """Get CAFM assets for a building."""
        response = self.client.table('cafm_assets').select("*").eq(
            'building_id', building_id
        ).order('asset_tag').execute()
        return response.data

    # ==================== Reference Data ====================

    def get_alarm_taxonomy(self) -> List[Dict[str, Any]]:
        """Get alarm code taxonomy."""
        response = self.client.table('alarm_taxonomy').select("*").execute()
        return response.data

    def get_severity_mappings(self, source_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get severity mappings (global or per-source)."""
        query = self.client.table('severity_mappings').select("*")
        if source_id:
            query = query.or_(f"log_source_id.eq.{source_id},log_source_id.is.null")
        else:
            query = query.is_('log_source_id', 'null')
        response = query.execute()
        return response.data
