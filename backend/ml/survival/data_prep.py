"""
Survival Data Preparation - Prepare datasets for Cox Proportional Hazards model.

Creates survival datasets with:
- Time-to-event (duration) from install to failure or censoring
- Event indicator (1 = failure, 0 = censored/still running)
- Equipment features as covariates
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


class SurvivalDataPrep:
    """Prepare survival data for Cox Proportional Hazards model."""

    def __init__(self, data_path: str | None = None):
        """
        Initialize data prep.

        Args:
            data_path: Path to equipment data file
        """
        if data_path is None:
            data_path = Path(__file__).parent.parent.parent / "app" / "data" / "equipment.json"
        self.data_path = Path(data_path)
        self._equipment_cache = None
        self._alerts_cache = None

    def _load_equipment(self) -> list[dict]:
        """Load equipment data from JSON file."""
        if self._equipment_cache is None:
            if self.data_path.exists():
                with open(self.data_path) as f:
                    self._equipment_cache = json.load(f)
            else:
                logger.warning(f"Equipment file not found: {self.data_path}")
                self._equipment_cache = []
        return self._equipment_cache

    def _load_alerts(self) -> list[dict]:
        """Load alerts for alarm history."""
        if self._alerts_cache is None:
            alerts_path = self.data_path.parent / "alerts.json"
            if alerts_path.exists():
                with open(alerts_path) as f:
                    self._alerts_cache = json.load(f)
            else:
                self._alerts_cache = []
        return self._alerts_cache

    def prepare_survival_data(self) -> "pd.DataFrame":
        """
        Create survival dataset with time-to-event and censoring.

        Returns:
            DataFrame with columns: equipment_id, duration, event, and features
        """
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("pandas is required for survival analysis. Install with: pip install pandas")

        equipment_list = self._load_equipment()

        if not equipment_list:
            logger.warning("No equipment data found")
            return pd.DataFrame()

        records = []
        for eq in equipment_list:
            try:
                # Get first failure (if any) - for demo, simulate based on status
                first_failure = self._get_first_failure(eq)

                # Get features at observation time
                features = self._get_features_at_observation(eq)

                install_date = datetime.fromisoformat(eq["install_date"])

                if first_failure:
                    # Equipment failed
                    duration = (first_failure - install_date).days
                    event = 1  # Failure occurred
                else:
                    # Equipment still running (censored)
                    duration = (datetime.utcnow() - install_date).days
                    event = 0  # Right-censored

                record = {
                    "equipment_id": eq["id"],
                    "equipment_type": eq["type"],
                    "duration": max(1, duration),  # Minimum 1 day
                    "event": event,
                    **features,
                }
                records.append(record)
            except Exception as e:
                logger.warning(f"Error processing equipment {eq.get('id', 'unknown')}: {e}")
                continue

        df = pd.DataFrame(records)
        logger.info(f"Prepared survival dataset: {len(df)} samples, {df['event'].sum()} events")
        return df

    def _get_first_failure(self, equipment: dict) -> datetime | None:
        """
        Get first major failure for equipment.

        For demo: Simulate failures based on status and health_score.
        In production: Query work orders for failure records.
        """
        status = equipment.get("status", "normal")
        health_score = equipment.get("health_score", 100)
        install_date = datetime.fromisoformat(equipment["install_date"])

        # Demo simulation: Create realistic failure patterns
        # Use equipment ID as seed for consistency
        equipment_id_num = hash(equipment["id"]) % 1000 / 1000.0

        if status == "critical" or health_score < 50:
            # Failed recently
            days_running = (datetime.utcnow() - install_date).days
            failure_date = install_date + timedelta(days=days_running * (0.7 + equipment_id_num * 0.2))
            return failure_date
        elif status == "warning" or health_score < 70:
            # 50% chance of having failed
            if equipment_id_num > 0.5:
                days_running = (datetime.utcnow() - install_date).days
                failure_date = install_date + timedelta(days=days_running * (0.5 + equipment_id_num * 0.3))
                return failure_date
        else:
            # 15% of normal equipment have failed
            if equipment_id_num > 0.85:
                days_running = (datetime.utcnow() - install_date).days
                failure_date = install_date + timedelta(days=days_running * (0.6 + equipment_id_num * 0.3))
                return failure_date

        # No failure (censored)
        return None

    def _get_features_at_observation(self, equipment: dict) -> dict:
        """
        Get features relevant for survival analysis.

        Features include:
        - Asset characteristics (age, life used, criticality)
        - Service history (service count, days since service)
        - Alarm history (recent alarms)
        - Equipment type indicators
        """
        install_date = datetime.fromisoformat(equipment["install_date"])
        equipment_type = equipment["type"]

        # Calculate age-related features
        age_days = (datetime.utcnow() - install_date).days
        age_years = age_days / 365.25

        # Expected life by equipment type (years)
        expected_life = {
            "chiller": 20,
            "ahu": 15,
            "cooling_tower": 12,
            "ups": 8,
            "generator": 15,
            "pump": 10,
            "fcu": 12,
            "vrf": 12,
        }

        expected_life_years = expected_life.get(equipment_type, 15)
        life_used_pct = (age_years / expected_life_years * 100) if expected_life_years > 0 else 0

        # Health score as criticality proxy
        health_score = equipment.get("health_score", 100)
        criticality = 5 if health_score > 90 else (3 if health_score > 70 else 1)

        # Service history features (from equipment data)
        last_service_str = equipment.get("last_service")
        if last_service_str:
            try:
                last_service = datetime.fromisoformat(last_service_str)
                days_since_service = (datetime.utcnow() - last_service).days
            except Exception:
                days_since_service = 365
        else:
            days_since_service = 365

        # Simulate service count (demo data doesn't have full history)
        service_count_12m = max(0, int(365 / max(30, days_since_service)))

        # Alarm history (from alerts)
        alarm_count_30d = self._get_alarm_count(equipment["id"], days=30)
        critical_alarms_30d = self._get_critical_alarm_count(equipment["id"], days=30)

        # Sensor summary (simulated - in production, query from InfluxDB)
        # For demo, use health_score as proxy
        vibration_rms_mean = 100 - health_score if equipment_type in ["pump", "ahu", "chiller"] else 0
        temp_deviation_mean = abs(health_score - 100) / 10 if equipment_type in ["chiller", "ahu"] else 0

        return {
            # Asset characteristics
            "age_at_observation_years": round(age_years, 2),
            "expected_life_years": expected_life_years,
            "life_used_pct": round(min(100, life_used_pct), 2),
            "criticality": criticality,
            # Service history
            "service_count_12m": service_count_12m,
            "days_since_service": days_since_service,
            "overdue_services": 1 if days_since_service > 180 else 0,
            # Alarm history
            "alarm_count_30d": alarm_count_30d,
            "critical_alarms_30d": critical_alarms_30d,
            # Sensor summary (simulated)
            "vibration_rms_mean": round(vibration_rms_mean, 2),
            "temp_deviation_mean": round(temp_deviation_mean, 2),
            # Equipment type as categorical (one-hot encoded)
            "is_chiller": 1 if equipment_type == "chiller" else 0,
            "is_ahu": 1 if equipment_type == "ahu" else 0,
            "is_generator": 1 if equipment_type == "generator" else 0,
            "is_fcu": 1 if equipment_type == "fcu" else 0,
            "is_ups": 1 if equipment_type == "ups" else 0,
            "is_cooling_tower": 1 if equipment_type == "cooling_tower" else 0,
            "is_pump": 1 if equipment_type == "pump" else 0,
        }

    def _get_alarm_count(self, equipment_id: str, days: int) -> int:
        """Get alarm count for equipment in recent days."""
        alerts = self._load_alerts()
        cutoff = datetime.utcnow() - timedelta(days=days)

        count = 0
        for alert in alerts:
            # Match by equipment_id or related equipment
            if alert.get("equipment_id") == equipment_id:
                try:
                    alert_date = datetime.fromisoformat(alert.get("timestamp", ""))
                    if alert_date >= cutoff:
                        count += 1
                except Exception:
                    pass
        return count

    def _get_critical_alarm_count(self, equipment_id: str, days: int) -> int:
        """Get critical alarm count for equipment."""
        alerts = self._load_alerts()
        cutoff = datetime.utcnow() - timedelta(days=days)

        count = 0
        for alert in alerts:
            if alert.get("equipment_id") == equipment_id and alert.get("severity") == "critical":
                try:
                    alert_date = datetime.fromisoformat(alert.get("timestamp", ""))
                    if alert_date >= cutoff:
                        count += 1
                except Exception:
                    pass
        return count

    def get_training_summary(self) -> dict:
        """Get summary statistics about the prepared dataset."""
        df = self.prepare_survival_data()

        if len(df) == 0:
            return {"error": "No data available"}

        return {
            "n_samples": len(df),
            "n_events": int(df["event"].sum()),
            "n_censored": len(df) - int(df["event"].sum()),
            "event_rate": float(df["event"].mean()),
            "median_duration": float(df["duration"].median()),
            "max_duration": int(df["duration"].max()),
            "equipment_types": df["equipment_type"].value_counts().to_dict(),
        }
