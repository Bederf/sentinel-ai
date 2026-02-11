"""Repository for water consumption and alert data operations.

Implements dual-write pattern: Supabase (primary) + JSON file (backup).
Gracefully falls back to JSON-only when Supabase is unavailable.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta
import json
import os
from pathlib import Path

from app.database.supabase_client import get_supabase_client
from app.models.water_meter import WaterConsumption, WaterAlert, WaterMeter


class WaterConsumptionRepository:
    """Repository for water consumption data with dual-write support."""

    def __init__(self):
        """Initialize repository with Supabase client."""
        self.client = get_supabase_client()
        self.json_backup_dir = Path("backend/app/data/buildings")

    def _get_json_backup_path(self, site: str) -> Path:
        """Get path to JSON backup file for a site."""
        site_dir = self.json_backup_dir / site
        site_dir.mkdir(parents=True, exist_ok=True)
        return site_dir / "water_consumption.json"

    def _load_json_backup(self, site: str) -> Dict[str, Any]:
        """Load consumption data from JSON backup."""
        json_path = self._get_json_backup_path(site)
        if not json_path.exists():
            return {"consumption": [], "alerts": []}
        with open(json_path, "r") as f:
            return json.load(f)

    def _save_json_backup(self, site: str, data: Dict[str, Any]) -> None:
        """Save consumption data to JSON backup."""
        json_path = self._get_json_backup_path(site)
        with open(json_path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def create_consumption(
        self,
        meter_id: str,
        site: str,
        volume_liters: float,
        flow_rate_lpm: float,
        timestamp: datetime,
        pulse_count: int = 0,
        temperature: Optional[float] = None,
        pressure: Optional[float] = None,
        zone_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Create a new water consumption record.

        Args:
            meter_id: Meter identifier
            site: Building site code
            volume_liters: Cumulative volume in liters
            flow_rate_lpm: Flow rate in liters per minute
            timestamp: Reading timestamp
            pulse_count: Raw pulse count
            temperature: Water temperature
            pressure: Water pressure
            zone_id: Zone identifier for zone-aware tracking

        Returns:
            Created record or None if failed
        """
        consumption_data = {
            "meter_id": meter_id,
            "site": site,
            "volume_liters": volume_liters,
            "flow_rate_lpm": flow_rate_lpm,
            "timestamp": timestamp.isoformat(),
            "pulse_count": pulse_count,
            "temperature": temperature,
            "pressure": pressure,
            "zone_id": zone_id,
        }

        # Try Supabase first
        try:
            response = (
                self.client.table("water_consumption")
                .insert(consumption_data)
                .execute()
            )
            record = response.data[0]

            # Backup to JSON
            self._backup_consumption(site, record)
            return record

        except Exception as e:
            # Fallback to JSON only
            print(f"Supabase error, using JSON fallback: {e}")
            return self._create_consumption_json(site, consumption_data)

    def _backup_consumption(self, site: str, record: Dict[str, Any]) -> None:
        """Append consumption record to JSON backup."""
        try:
            backup_data = self._load_json_backup(site)
            backup_data["consumption"].append(record)
            self._save_json_backup(site, backup_data)
        except Exception as e:
            print(f"Warning: JSON backup failed: {e}")

    def _create_consumption_json(self, site: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create consumption record in JSON-only mode."""
        backup_data = self._load_json_backup(site)
        backup_data["consumption"].append(data)
        self._save_json_backup(site, backup_data)
        return data

    def get_consumption_by_site(
        self,
        site: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Get consumption data for a site.

        Args:
            site: Building site code
            start_date: Start date (default: 30 days ago)
            end_date: End date (default: today)
            limit: Maximum records to return

        Returns:
            List of consumption records
        """
        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date - timedelta(days=30)

        # Try Supabase first
        try:
            response = (
                self.client.table("water_consumption")
                .select("*")
                .eq("site", site)
                .gte("timestamp", start_date.isoformat())
                .lte("timestamp", end_date.isoformat())
                .order("timestamp", desc=False)
                .limit(limit)
                .execute()
            )
            return response.data

        except Exception as e:
            # Fallback to JSON
            print(f"Supabase error, using JSON fallback: {e}")
            return self._get_consumption_json(site, start_date, end_date, limit)

    def _get_consumption_json(
        self,
        site: str,
        start_date: date,
        end_date: date,
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Get consumption from JSON backup."""
        backup_data = self._load_json_backup(site)
        records = backup_data.get("consumption", [])

        # Filter by date range
        filtered = []
        for record in records:
            record_date = datetime.fromisoformat(record["timestamp"]).date()
            if start_date <= record_date <= end_date:
                filtered.append(record)

        # Sort and limit
        filtered.sort(key=lambda x: x["timestamp"])
        return filtered[:limit]

    def get_consumption_by_meter(
        self,
        meter_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Get consumption data for a specific meter.

        Args:
            meter_id: Meter identifier
            start_date: Start date
            end_date: End date
            limit: Maximum records

        Returns:
            List of consumption records
        """
        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date - timedelta(days=30)

        try:
            response = (
                self.client.table("water_consumption")
                .select("*")
                .eq("meter_id", meter_id)
                .gte("timestamp", start_date.isoformat())
                .lte("timestamp", end_date.isoformat())
                .order("timestamp", desc=False)
                .limit(limit)
                .execute()
            )
            return response.data

        except Exception:
            # Fallback to JSON with meter filter
            all_records = self._get_consumption_json(
                meter_id.split("-")[0].replace("S", "site-"),
                start_date,
                end_date,
                limit,
            )
            return [r for r in all_records if r["meter_id"] == meter_id]

    def get_latest_consumption(self, site: str, meter_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get the most recent consumption reading.

        Args:
            site: Building site code
            meter_id: Optional meter filter

        Returns:
            Latest consumption record or None
        """
        try:
            query = self.client.table("water_consumption").select("*").eq("site", site)
            if meter_id:
                query = query.eq("meter_id", meter_id)
            response = query.order("timestamp", desc=True).limit(1).execute()
            return response.data[0] if response.data else None

        except Exception:
            # Fallback to JSON
            backup_data = self._load_json_backup(site)
            records = backup_data.get("consumption", [])
            if meter_id:
                records = [r for r in records if r["meter_id"] == meter_id]
            if records:
                return max(records, key=lambda x: x["timestamp"])
            return None

    def create_alert(
        self,
        meter_id: str,
        site: str,
        alert_type: str,
        severity: str,
        flow_rate_lpm: float,
        threshold_lpm: float,
        duration_minutes: float,
        description: str,
    ) -> Optional[Dict[str, Any]]:
        """Create a water leak alert.

        Args:
            meter_id: Meter that generated the alert
            site: Building site code
            alert_type: Type of leak detected
            severity: Alert severity level
            flow_rate_lpm: Flow rate at alert time
            threshold_lpm: Threshold exceeded
            duration_minutes: Duration of condition
            description: Alert description

        Returns:
            Created alert record
        """
        import uuid
        alert_data = {
            "alert_id": str(uuid.uuid4()),
            "meter_id": meter_id,
            "site": site,
            "alert_type": alert_type,
            "severity": severity,
            "status": "active",
            "timestamp": datetime.now().isoformat(),
            "flow_rate_lpm": flow_rate_lpm,
            "threshold_lpm": threshold_lpm,
            "duration_minutes": duration_minutes,
            "description": description,
            "resolved_at": None,
            "resolved_by": None,
            "resolution_notes": None,
        }

        # Try Supabase first
        try:
            response = (
                self.client.table("water_alerts")
                .insert(alert_data)
                .execute()
            )
            record = response.data[0]
            self._backup_alert(site, record)
            return record

        except Exception as e:
            # Fallback to JSON only
            print(f"Supabase error, using JSON fallback: {e}")
            return self._create_alert_json(site, alert_data)

    def _backup_alert(self, site: str, record: Dict[str, Any]) -> None:
        """Append alert to JSON backup."""
        try:
            backup_data = self._load_json_backup(site)
            backup_data.setdefault("alerts", []).append(record)
            self._save_json_backup(site, backup_data)
        except Exception as e:
            print(f"Warning: JSON backup failed: {e}")

    def _create_alert_json(self, site: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create alert in JSON-only mode."""
        backup_data = self._load_json_backup(site)
        backup_data.setdefault("alerts", []).append(data)
        self._save_json_backup(site, backup_data)
        return data

    def get_alerts(
        self,
        site: str,
        severity: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get water alerts for a site.

        Args:
            site: Building site code
            severity: Filter by severity level
            start_date: Start date
            end_date: End date
            status: Filter by status (active, resolved, etc.)

        Returns:
            List of alert records
        """
        try:
            query = self.client.table("water_alerts").select("*").eq("site", site)
            if severity:
                query = query.eq("severity", severity)
            if status:
                query = query.eq("status", status)
            if start_date:
                query = query.gte("timestamp", start_date.isoformat())
            if end_date:
                query = query.lte("timestamp", end_date.isoformat())
            response = query.order("timestamp", desc=True).execute()
            return response.data

        except Exception:
            # Fallback to JSON
            return self._get_alerts_json(site, severity, start_date, end_date, status)

    def _get_alerts_json(
        self,
        site: str,
        severity: Optional[str],
        start_date: Optional[date],
        end_date: Optional[date],
        status: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Get alerts from JSON backup."""
        backup_data = self._load_json_backup(site)
        records = backup_data.get("alerts", [])

        # Apply filters
        filtered = []
        for record in records:
            if severity and record["severity"] != severity:
                continue
            if status and record["status"] != status:
                continue
            if start_date or end_date:
                record_date = datetime.fromisoformat(record["timestamp"]).date()
                if start_date and record_date < start_date:
                    continue
                if end_date and record_date > end_date:
                    continue
            filtered.append(record)

        # Sort by timestamp descending
        filtered.sort(key=lambda x: x["timestamp"], reverse=True)
        return filtered

    def get_active_alerts(self, site: str) -> List[Dict[str, Any]]:
        """Get all active (unresolved) alerts.

        Args:
            site: Building site code

        Returns:
            List of active alerts
        """
        return self.get_alerts(site, status="active")

    def resolve_alert(
        self,
        alert_id: str,
        resolved_by: str,
        resolution_notes: str,
    ) -> Optional[Dict[str, Any]]:
        """Mark an alert as resolved.

        Args:
            alert_id: Alert identifier
            resolved_by: User resolving the alert
            resolution_notes: Resolution description

        Returns:
            Updated alert record
        """
        update_data = {
            "status": "resolved",
            "resolved_at": datetime.now().isoformat(),
            "resolved_by": resolved_by,
            "resolution_notes": resolution_notes,
        }

        try:
            response = (
                self.client.table("water_alerts")
                .update(update_data)
                .eq("alert_id", alert_id)
                .execute()
            )
            return response.data[0] if response.data else None

        except Exception:
            # Fallback to JSON
            return self._resolve_alert_json(alert_id, update_data)

    def _resolve_alert_json(self, alert_id: str, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Resolve alert in JSON backup."""
        # Find the site for this alert
        for site_dir in self.json_backup_dir.iterdir():
            if not site_dir.is_dir() or not site_dir.name.startswith("site-"):
                continue
            backup_data = self._load_json_backup(site_dir.name)
            alerts = backup_data.get("alerts", [])
            for alert in alerts:
                if alert["alert_id"] == alert_id:
                    alert.update(update_data)
                    self._save_json_backup(site_dir.name, backup_data)
                    return alert
        return None

    def get_daily_summary(
        self,
        site: str,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Get daily consumption summary.

        Args:
            site: Building site code
            days: Number of days to summarize

        Returns:
            Summary statistics
        """
        records = self.get_consumption_by_site(site, limit=days * 24 * 60)  # Rough estimate

        if not records:
            return {
                "total_liters": 0,
                "average_daily_liters": 0,
                "peak_flow_rate_lpm": 0,
                "average_flow_rate_lpm": 0,
                "days": 0,
            }

        total_liters = max(r["volume_liters"] for r in records) - min(r["volume_liters"] for r in records)
        peak_flow = max(r["flow_rate_lpm"] for r in records)
        avg_flow = sum(r["flow_rate_lpm"] for r in records) / len(records)

        return {
            "total_liters": round(total_liters, 2),
            "average_daily_liters": round(total_liters / days, 2) if days > 0 else 0,
            "peak_flow_rate_lpm": round(peak_flow, 2),
            "average_flow_rate_lpm": round(avg_flow, 2),
            "days": days,
        }


def get_water_consumption_repository() -> WaterConsumptionRepository:
    """Get singleton instance of WaterConsumptionRepository."""
    return WaterConsumptionRepository()
