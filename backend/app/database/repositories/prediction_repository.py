"""Repository for prediction operations."""

from typing import List, Optional, Dict, Any
from app.database.supabase_client import get_supabase_client


class PredictionRepository:
    """Repository for prediction database operations."""

    def __init__(self):
        """Initialize the repository with a Supabase client."""
        self.client = get_supabase_client()

    def get_all(
        self,
        building_id: Optional[str] = None,
        equipment_id: Optional[str] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all predictions with optional filtering.

        Args:
            building_id: Filter by building UUID
            equipment_id: Filter by equipment UUID
            status: Filter by status
            severity: Filter by severity

        Returns:
            List of predictions
        """
        # Join with equipment and buildings to get related data
        query = self.client.table('predictions').select(
            "*, equipment:equipment_id(id, code, name, type), building:building_id(id, code, name)"
        )

        if building_id:
            query = query.eq('building_id', building_id)
        if equipment_id:
            query = query.eq('equipment_id', equipment_id)
        if status:
            query = query.eq('status', status)
        if severity:
            query = query.eq('severity', severity)

        response = query.execute()
        return response.data

    def get_by_id(self, prediction_id: str) -> Optional[Dict[str, Any]]:
        """Get prediction by its code.

        Args:
            prediction_id: Prediction code

        Returns:
            Prediction data or None if not found
        """
        response = self.client.table('predictions').select("*").eq(
            'code', prediction_id
        ).execute()

        if response.data:
            return response.data[0]
        return None

    def get_by_uuid(self, uuid: str) -> Optional[Dict[str, Any]]:
        """Get prediction by its UUID.

        Args:
            uuid: Prediction UUID

        Returns:
            Prediction data or None if not found
        """
        response = self.client.table('predictions').select("*").eq('id', uuid).execute()

        if response.data:
            return response.data[0]
        return None

    def get_active_by_building(self, building_uuid: str) -> List[Dict[str, Any]]:
        """Get active predictions for a building.

        Args:
            building_uuid: Building UUID

        Returns:
            List of active predictions
        """
        response = self.client.table('predictions').select("*").eq(
            'building_id', building_uuid
        ).eq('status', 'active').execute()

        return response.data

    def get_active_by_equipment(self, equipment_uuid: str) -> List[Dict[str, Any]]:
        """Get active predictions for equipment.

        Args:
            equipment_uuid: Equipment UUID

        Returns:
            List of active predictions
        """
        response = self.client.table('predictions').select("*").eq(
            'equipment_id', equipment_uuid
        ).eq('status', 'active').execute()

        return response.data

    def get_critical_predictions(self) -> List[Dict[str, Any]]:
        """Get all critical active predictions.

        Returns:
            List of critical predictions
        """
        response = self.client.table('predictions').select("*").eq(
            'severity', 'critical'
        ).eq('status', 'active').execute()

        return response.data

    def get_high_probability_predictions(self, threshold: int = 70) -> List[Dict[str, Any]]:
        """Get predictions with high probability.

        Args:
            threshold: Probability threshold (default: 70)

        Returns:
            List of high probability predictions
        """
        response = self.client.table('predictions').select("*").gte(
            'probability_percent', threshold
        ).eq('status', 'active').execute()

        return response.data

    def create(self, prediction_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new prediction.

        Args:
            prediction_data: Prediction data

        Returns:
            Created prediction
        """
        response = self.client.table('predictions').insert(prediction_data).execute()
        return response.data[0]

    def update(self, prediction_id: str, prediction_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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

        response = self.client.table('predictions').update(
            prediction_data
        ).eq('id', prediction['id']).execute()

        if response.data:
            return response.data[0]
        return None

    def acknowledge(self, prediction_id: str) -> Optional[Dict[str, Any]]:
        """Acknowledge a prediction.

        Args:
            prediction_id: Prediction code

        Returns:
            Updated prediction or None if not found
        """
        return self.update(prediction_id, {'status': 'acknowledged'})

    def resolve(self, prediction_id: str) -> Optional[Dict[str, Any]]:
        """Resolve a prediction.

        Args:
            prediction_id: Prediction code

        Returns:
            Updated prediction or None if not found
        """
        return self.update(prediction_id, {'status': 'resolved'})

    def mark_false_positive(self, prediction_id: str) -> Optional[Dict[str, Any]]:
        """Mark a prediction as false positive.

        Args:
            prediction_id: Prediction code

        Returns:
            Updated prediction or None if not found
        """
        return self.update(prediction_id, {'status': 'false_positive'})

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

        response = self.client.table('predictions').delete().eq(
            'id', prediction['id']
        ).execute()

        return len(response.data) > 0

    def has_active_prediction_for_equipment(self, equipment_id: str) -> bool:
        """Check if equipment already has an active or acknowledged prediction.

        This prevents duplicate predictions for equipment that already has
        an ongoing prediction being tracked.

        Args:
            equipment_id: Equipment UUID

        Returns:
            True if an active/acknowledged prediction exists, False otherwise
        """
        response = self.client.table('predictions').select("id").eq(
            'equipment_id', equipment_id
        ).in_('status', ['active', 'acknowledged']).execute()

        return len(response.data) > 0

    def get_active_equipment_ids(self) -> List[str]:
        """Get list of equipment IDs that have active predictions.

        Returns:
            List of equipment UUIDs with active predictions
        """
        response = self.client.table('predictions').select("equipment_id").eq(
            'status', 'active'
        ).execute()

        return [p['equipment_id'] for p in response.data]

    def resolve_by_equipment(self, equipment_id: str) -> int:
        """Resolve all active predictions for equipment.

        Used when equipment health improves above threshold.

        Args:
            equipment_id: Equipment UUID

        Returns:
            Number of predictions resolved
        """
        response = self.client.table('predictions').update(
            {'status': 'resolved'}
        ).eq('equipment_id', equipment_id).eq('status', 'active').execute()

        return len(response.data)
