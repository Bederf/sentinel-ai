"""Repository for prediction operations."""

from typing import Any

from app.database.supabase_client import get_supabase_client
from app.services.cache_service import CacheInvalidation, CacheKeys, CacheService, cache


class PredictionRepository:
    """Repository for prediction database operations."""

    _COLUMNS = (
        "id, code, equipment_id, site_id, severity, status, "
        "probability_percent, prediction_type, predicted_failure_date, "
        "timeframe_days, confidence, "
        "repair_cost_zar, replacement_cost_zar, "
        "downtime_cost_per_hour_zar, potential_loss_zar, "
        "created_at, updated_at"
    )

    def __init__(self):
        """Initialize the repository with a Supabase client."""
        self.client = get_supabase_client()

    def get_all(
        self,
        site_id: str | None = None,
        equipment_id: str | None = None,
        status: str | None = None,
        severity: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get all predictions with optional filtering.

        Args:
            site_id: Filter by building UUID
            equipment_id: Filter by equipment UUID
            status: Filter by status
            severity: Filter by severity

        Returns:
            List of predictions
        """
        # Join with equipment and buildings to get related data
        query = self.client.table("predictions").select(
            "*, equipment:equipment_id(id, code, name, type), building:site_id(id, code, name)"
        )

        if site_id:
            query = query.eq("site_id", site_id)
        if equipment_id:
            query = query.eq("equipment_id", equipment_id)
        if status:
            query = query.eq("status", status)
        if severity:
            query = query.eq("severity", severity)

        response = query.execute()
        return response.data

    def get_by_id(self, prediction_id: str) -> dict[str, Any] | None:
        """Get prediction by its code.

        Args:
            prediction_id: Prediction code

        Returns:
            Prediction data or None if not found
        """
        response = self.client.table("predictions").select(self._COLUMNS).eq("code", prediction_id).execute()

        if response.data:
            return response.data[0]
        return None

    def get_by_uuid(self, uuid: str) -> dict[str, Any] | None:
        """Get prediction by its UUID.

        Args:
            uuid: Prediction UUID

        Returns:
            Prediction data or None if not found
        """
        response = self.client.table("predictions").select(self._COLUMNS).eq("id", uuid).execute()

        if response.data:
            return response.data[0]
        return None

    def get_active_by_site(self, site_uuid: str) -> list[dict[str, Any]]:
        """Get active predictions for a building.

        Args:
            site_uuid: Building UUID

        Returns:
            List of active predictions
        """
        cached = cache.get(CacheKeys.predictions_active(site_uuid))
        if cached is not None:
            return cached

        response = (
            self.client.table("predictions")
            .select(self._COLUMNS)
            .eq("site_id", site_uuid)
            .eq("status", "active")
            .execute()
        )

        result = response.data
        cache.set(CacheKeys.predictions_active(site_uuid), result, CacheService.TTL_DYNAMIC)
        return result

    def get_active_by_equipment(self, equipment_uuid: str) -> list[dict[str, Any]]:
        """Get active predictions for equipment.

        Args:
            equipment_uuid: Equipment UUID

        Returns:
            List of active predictions
        """
        response = (
            self.client.table("predictions")
            .select(self._COLUMNS)
            .eq("equipment_id", equipment_uuid)
            .eq("status", "active")
            .execute()
        )

        return response.data

    def get_critical_predictions(self) -> list[dict[str, Any]]:
        """Get all critical active predictions.

        Returns:
            List of critical predictions
        """
        response = (
            self.client.table("predictions")
            .select(self._COLUMNS)
            .eq("severity", "critical")
            .eq("status", "active")
            .execute()
        )

        return response.data

    def get_high_probability_predictions(self, threshold: int = 70) -> list[dict[str, Any]]:
        """Get predictions with high probability.

        Args:
            threshold: Probability threshold (default: 70)

        Returns:
            List of high probability predictions
        """
        response = (
            self.client.table("predictions")
            .select(self._COLUMNS)
            .gte("probability_percent", threshold)
            .eq("status", "active")
            .execute()
        )

        return response.data

    def create(self, prediction_data: dict[str, Any]) -> dict[str, Any]:
        """Create a new prediction.

        Args:
            prediction_data: Prediction data

        Returns:
            Created prediction
        """
        response = self.client.table("predictions").insert(prediction_data).execute()
        result = response.data[0]
        CacheInvalidation.on_prediction_change(site_id=prediction_data.get("site_id"))
        return result

    def update(self, prediction_id: str, prediction_data: dict[str, Any]) -> dict[str, Any] | None:
        """Update a prediction.

        Args:
            prediction_id: Prediction code
            prediction_data: Data to update

        Returns:
            Updated prediction or None if not found
        """
        prediction = self.get_by_id(prediction_id)
        if not prediction:
            return None

        response = self.client.table("predictions").update(prediction_data).eq("id", prediction["id"]).execute()

        if response.data:
            CacheInvalidation.on_prediction_change()
            return response.data[0]
        return None

    def acknowledge(self, prediction_id: str) -> dict[str, Any] | None:
        """Acknowledge a prediction.

        Args:
            prediction_id: Prediction code

        Returns:
            Updated prediction or None if not found
        """
        return self.update(prediction_id, {"status": "acknowledged"})

    def resolve(self, prediction_id: str) -> dict[str, Any] | None:
        """Resolve a prediction.

        Args:
            prediction_id: Prediction code

        Returns:
            Updated prediction or None if not found
        """
        return self.update(prediction_id, {"status": "resolved"})

    def mark_false_positive(self, prediction_id: str) -> dict[str, Any] | None:
        """Mark a prediction as false positive.

        Args:
            prediction_id: Prediction code

        Returns:
            Updated prediction or None if not found
        """
        return self.update(prediction_id, {"status": "false_positive"})

    def delete(self, prediction_id: str) -> bool:
        """Delete a prediction.

        Args:
            prediction_id: Prediction code

        Returns:
            True if deleted, False if not found
        """
        prediction = self.get_by_id(prediction_id)
        if not prediction:
            return False

        response = self.client.table("predictions").delete().eq("id", prediction["id"]).execute()

        if len(response.data) > 0:
            CacheInvalidation.on_prediction_change()
            return True
        return False

    def has_active_prediction_for_equipment(self, equipment_id: str) -> bool:
        """Check if equipment already has an active or acknowledged prediction.

        This prevents duplicate predictions for equipment that already has
        an ongoing prediction being tracked.

        Args:
            equipment_id: Equipment UUID

        Returns:
            True if an active/acknowledged prediction exists, False otherwise
        """
        response = (
            self.client.table("predictions")
            .select("id")
            .eq("equipment_id", equipment_id)
            .in_("status", ["active", "acknowledged"])
            .execute()
        )

        return len(response.data) > 0

    def get_active_equipment_ids(self) -> list[str]:
        """Get list of equipment IDs that have active predictions.

        Returns:
            List of equipment UUIDs with active predictions
        """
        response = self.client.table("predictions").select("equipment_id").eq("status", "active").execute()

        return [p["equipment_id"] for p in response.data]

    def resolve_by_equipment(self, equipment_id: str) -> int:
        """Resolve all active predictions for equipment.

        Used when equipment health improves above threshold.

        Args:
            equipment_id: Equipment UUID

        Returns:
            Number of predictions resolved
        """
        response = (
            self.client.table("predictions")
            .update({"status": "resolved"})
            .eq("equipment_id", equipment_id)
            .eq("status", "active")
            .execute()
        )

        count = len(response.data)
        if count > 0:
            CacheInvalidation.on_prediction_change()
        return count
