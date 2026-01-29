"""Repository for integration/log source operations."""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
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

    # ==================== Monitoring Aggregations ====================

    def get_integration_health(self, building_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get integration health summary.

        Returns aggregate metrics for monitoring dashboard:
        - sources_count: Total log sources
        - active_sources: Count of active sources
        - last_sync: Most recent sync timestamp
        - total_records_ingested: Sum of all ingested records
        - total_points_mapped: Count of point mappings
        - unmatched_points: Count of unmatched point mappings
        - recent_errors_count: Failed sync jobs in last 24 hours
        """
        # Get log sources
        sources_query = self.client.table('log_sources').select("*")
        if building_id:
            sources_query = sources_query.eq('building_id', building_id)
        sources_response = sources_query.execute()
        sources = sources_response.data or []

        sources_count = len(sources)
        active_sources = len([s for s in sources if s.get('is_active')])

        # Find most recent sync and sum records
        last_sync = None
        total_records_ingested = 0
        for source in sources:
            sync_at = source.get('last_sync_at')
            if sync_at:
                if last_sync is None or sync_at > last_sync:
                    last_sync = sync_at
            records = source.get('last_sync_records') or 0
            total_records_ingested += records

        # Get point mappings count
        mappings_query = self.client.table('point_asset_mappings').select("id,match_confidence")
        if building_id:
            mappings_query = mappings_query.eq('building_id', building_id)
        mappings_response = mappings_query.execute()
        mappings = mappings_response.data or []

        total_points_mapped = len(mappings)
        unmatched_points = len([m for m in mappings if m.get('match_confidence') == 'unmatched'])

        # Get failed sync jobs in last 24 hours
        cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        failed_jobs_query = self.client.table('sync_jobs').select("id").eq(
            'status', 'failed'
        ).gte('started_at', cutoff)
        if building_id:
            # Need to filter by log_source building_id via join or subquery
            # For simplicity, filter sources first then get job IDs
            source_ids = [s['id'] for s in sources]
            if source_ids:
                failed_jobs_query = failed_jobs_query.in_('log_source_id', source_ids)
            else:
                # No sources for this building
                failed_jobs_query = None

        recent_errors_count = 0
        if failed_jobs_query:
            failed_response = failed_jobs_query.execute()
            recent_errors_count = len(failed_response.data or [])

        return {
            'sources_count': sources_count,
            'active_sources': active_sources,
            'last_sync': last_sync,
            'total_records_ingested': total_records_ingested,
            'total_points_mapped': total_points_mapped,
            'unmatched_points': unmatched_points,
            'recent_errors_count': recent_errors_count,
        }

    def get_quality_metrics(self, building_id: str) -> Dict[str, Any]:
        """
        Get data quality metrics for a building.

        Returns:
        - match_coverage: Percentage of points matched (0-100)
        - data_freshness_hours: Hours since last sync
        - error_rate: Percentage of failed sync jobs in last 7 days (0-100)
        - duplicate_rate: Percentage of skipped records (0-100)
        - overall_score: Weighted quality score (0-100)
        - trend: Quality trend ('improving', 'stable', 'degrading')
        """
        # Get point mappings for match coverage
        mappings_response = self.client.table('point_asset_mappings').select(
            "id,match_confidence"
        ).eq('building_id', building_id).execute()
        mappings = mappings_response.data or []

        total_points = len(mappings)
        matched_points = len([m for m in mappings if m.get('match_confidence') != 'unmatched'])
        match_coverage = (matched_points / total_points * 100) if total_points > 0 else 0

        # Get data freshness from log sources
        sources_response = self.client.table('log_sources').select(
            "last_sync_at"
        ).eq('building_id', building_id).execute()
        sources = sources_response.data or []

        data_freshness_hours = float('inf')
        now = datetime.utcnow()
        for source in sources:
            sync_at = source.get('last_sync_at')
            if sync_at:
                # Parse ISO format
                try:
                    sync_time = datetime.fromisoformat(sync_at.replace('Z', '+00:00').replace('+00:00', ''))
                    hours = (now - sync_time).total_seconds() / 3600
                    if hours < data_freshness_hours:
                        data_freshness_hours = hours
                except (ValueError, TypeError):
                    pass

        if data_freshness_hours == float('inf'):
            data_freshness_hours = 9999  # Never synced

        # Get error rate from sync jobs in last 7 days
        cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat()

        # Get source IDs for this building
        source_ids_response = self.client.table('log_sources').select("id").eq(
            'building_id', building_id
        ).execute()
        source_ids = [s['id'] for s in (source_ids_response.data or [])]

        total_jobs = 0
        failed_jobs = 0
        total_processed = 0
        total_skipped = 0

        if source_ids:
            jobs_response = self.client.table('sync_jobs').select(
                "status,records_processed,records_skipped"
            ).in_('log_source_id', source_ids).gte('started_at', cutoff).execute()
            jobs = jobs_response.data or []

            total_jobs = len(jobs)
            failed_jobs = len([j for j in jobs if j.get('status') == 'failed'])
            for job in jobs:
                total_processed += job.get('records_processed') or 0
                total_skipped += job.get('records_skipped') or 0

        error_rate = (failed_jobs / total_jobs * 100) if total_jobs > 0 else 0
        duplicate_rate = (total_skipped / total_processed * 100) if total_processed > 0 else 0

        # Calculate freshness score (100 = fresh, 0 = stale)
        # Consider 1 hour as perfect, 24+ hours as 0
        if data_freshness_hours <= 1:
            freshness_score = 100
        elif data_freshness_hours >= 24:
            freshness_score = 0
        else:
            freshness_score = max(0, 100 - (data_freshness_hours - 1) * (100 / 23))

        # Calculate overall score: weighted average
        overall_score = (
            match_coverage * 0.4 +
            freshness_score * 0.3 +
            (100 - error_rate) * 0.2 +
            (100 - duplicate_rate) * 0.1
        )

        # Trend is static for now (would need historical data to calculate)
        trend = 'stable'

        return {
            'match_coverage': round(match_coverage, 1),
            'data_freshness_hours': round(data_freshness_hours, 1),
            'error_rate': round(error_rate, 1),
            'duplicate_rate': round(duplicate_rate, 1),
            'overall_score': round(overall_score, 1),
            'trend': trend,
        }

    def get_sync_jobs_summary(
        self,
        building_id: Optional[str] = None,
        days: int = 7,
    ) -> List[Dict[str, Any]]:
        """
        Get sync job summary for the last N days.

        Returns list of sync jobs with:
        - log_source_id, status, records_processed, records_inserted,
          records_failed, processing_time_ms, started_at, completed_at
        """
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

        # If building_id specified, get source IDs first
        source_ids = None
        if building_id:
            sources_response = self.client.table('log_sources').select("id").eq(
                'building_id', building_id
            ).execute()
            source_ids = [s['id'] for s in (sources_response.data or [])]
            if not source_ids:
                return []

        query = self.client.table('sync_jobs').select(
            "id,log_source_id,status,records_processed,records_inserted,"
            "records_failed,records_skipped,processing_time_ms,started_at,completed_at,file_name"
        ).gte('started_at', cutoff)

        if source_ids:
            query = query.in_('log_source_id', source_ids)

        response = query.order('started_at', desc=True).limit(100).execute()
        return response.data or []
