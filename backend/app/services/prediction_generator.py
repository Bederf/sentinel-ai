"""
Prediction Generator Service

Automatically generates predictions for equipment with health scores below threshold.
Runs as a background job to detect at-risk equipment and create predictions.

Phase: Automatic Prediction Generation
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from app.database.supabase_client import get_supabase_client
from app.database.repositories.prediction_repository import PredictionRepository
from app.services.health_threshold_service import get_health_thresholds, get_health_status
from app.services.prediction_taxonomy import (
    FORMULA_VERSION_STATIC,
    confidence_from_probability,
    normalize_prediction_urgency,
    urgency_from_severity,
)

logger = logging.getLogger(__name__)

# Minimum probability threshold for creating predictions
MIN_PROBABILITY_THRESHOLD = 60


class PredictionGeneratorService:
    """Service for automatic prediction generation based on equipment health."""

    def __init__(self):
        """Initialize the prediction generator service."""
        self.supabase = get_supabase_client()
        self.prediction_repo = PredictionRepository()

    async def generate_predictions_for_all_sites(self) -> Dict[str, Any]:
        """
        Generate predictions for all equipment with health below threshold.

        Main entry point for prediction generation. Called by background scheduler.

        Returns:
            Dict with generation results including counts and any errors
        """
        results = {
            "generated": 0,
            "skipped_duplicate": 0,
            "skipped_low_probability": 0,
            "resolved": 0,
            "errors": [],
            "timestamp": datetime.now().isoformat(),
        }

        try:
            # Get health thresholds
            thresholds = get_health_thresholds()
            healthy_threshold = thresholds.get("healthy", 90)

            logger.info(f"Starting prediction generation (health threshold: {healthy_threshold})")

            # Get equipment with health below threshold
            at_risk_equipment = self._get_at_risk_equipment(healthy_threshold)
            logger.info(f"Found {len(at_risk_equipment)} equipment below health threshold")

            # Get equipment IDs with existing active predictions
            active_prediction_ids = set(self.prediction_repo.get_active_equipment_ids())

            # Generate predictions for at-risk equipment
            for equipment in at_risk_equipment:
                try:
                    equipment_id = equipment.get("id")

                    # Check for duplicate
                    if equipment_id in active_prediction_ids:
                        results["skipped_duplicate"] += 1
                        continue

                    # Generate prediction
                    prediction = self._generate_prediction(equipment)

                    # Check probability threshold
                    if prediction["probability_percent"] < MIN_PROBABILITY_THRESHOLD:
                        results["skipped_low_probability"] += 1
                        continue

                    # Store prediction
                    self.prediction_repo.create(prediction)
                    results["generated"] += 1
                    logger.info(
                        f"Generated prediction for {equipment.get('name')} (health: {equipment.get('health_score')}%)"
                    )

                except Exception as e:
                    error_msg = f"Error generating prediction for {equipment.get('id')}: {str(e)}"
                    logger.error(error_msg)
                    results["errors"].append(error_msg)

            # Auto-resolve predictions for improved equipment
            resolved_count = await self.auto_resolve_improved_equipment(healthy_threshold)
            results["resolved"] = resolved_count

            logger.info(
                f"Prediction generation complete: {results['generated']} generated, "
                f"{results['skipped_duplicate']} skipped (duplicate), "
                f"{results['resolved']} resolved"
            )

        except Exception as e:
            error_msg = f"Prediction generation failed: {str(e)}"
            logger.error(error_msg)
            results["errors"].append(error_msg)

        return results

    def _get_at_risk_equipment(self, threshold: int) -> List[Dict[str, Any]]:
        """
        Query equipment with health score below threshold.

        Args:
            threshold: Health score threshold (equipment below this is at-risk)

        Returns:
            List of equipment records with health below threshold
        """
        try:
            response = (
                self.supabase.table("equipment")
                .select("*, building:buildings(id, name, code)")
                .lt("health_score", threshold)
                .execute()
            )

            return response.data or []

        except Exception as e:
            logger.error(f"Failed to query at-risk equipment: {e}")
            return []

    def _generate_prediction(self, equipment: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a prediction record for equipment.

        Args:
            equipment: Equipment record from database

        Returns:
            Prediction record ready for insertion
        """
        health_score = equipment.get("health_score", 50)
        equipment_type = equipment.get("type", "unknown")
        _building = equipment.get("building", {})

        # Calculate probability based on health (inverse relationship)
        probability = min(95, max(60, 100 - health_score + 10))

        # Determine severity based on health status - aligned with database constraint
        # Database allows: critical, warning, healthy (NOT high, medium, low)
        health_status = get_health_status(health_score)
        if health_status == "critical":
            severity = "critical"
            timeframe_days = 7
            urgency = "critical"
        elif health_status == "warning":
            severity = "warning"  # Use 'warning' not 'high' (DB constraint)
            timeframe_days = 14
            urgency = "warning"
        else:
            # Healthy equipment shouldn't reach here (only generate for health < 90)
            # But if it does, use 'healthy' not 'low'
            severity = "healthy"
            timeframe_days = 30
            urgency = "healthy"

        # Calculate predicted failure date
        predicted_date = datetime.now() + timedelta(days=timeframe_days)

        # Generate prediction code
        code = f"pred-auto-{uuid.uuid4().hex[:8]}"

        # Determine prediction type based on equipment type
        prediction_type = self._determine_prediction_type(equipment_type, health_score)

        # Build evidence from available data
        evidence = self._build_evidence(equipment)

        # Calculate financial impact
        financial_impact = self._calculate_financial_impact(equipment_type, severity)

        # Get contributing factors
        contributing_factors = self._get_contributing_factors(equipment)

        # Generate recommended action
        recommended_action = self._get_recommended_action(equipment_type, severity, prediction_type)

        return {
            "code": code,
            "building_id": equipment.get("building_id"),
            "equipment_id": equipment.get("id"),
            "prediction_type": prediction_type,
            "probability_percent": probability,
            "confidence": confidence_from_probability(probability, high_threshold=80, medium_threshold=65),
            "predicted_failure_date": predicted_date.isoformat(),
            "timeframe_days": timeframe_days,
            "severity": severity,
            "status": "active",
            "evidence": evidence,
            "contributing_factors": contributing_factors,
            "similar_failures": [],
            "repair_cost_zar": financial_impact["repair_cost"],
            "replacement_cost_zar": financial_impact["replacement_cost"],
            "downtime_cost_per_hour_zar": financial_impact["downtime_cost_per_hour"],
            "potential_loss_zar": financial_impact["potential_loss"],
            "recommended_action": recommended_action,
            "urgency": normalize_prediction_urgency(urgency) or urgency_from_severity(severity),
        }

    def _determine_prediction_type(self, equipment_type: str, health_score: float) -> str:
        """Determine the type of failure prediction based on equipment."""
        type_lower = equipment_type.lower()

        if "chiller" in type_lower:
            if health_score < 50:
                return "compressor_failure"
            return "refrigerant_leak"
        elif "ahu" in type_lower:
            if health_score < 50:
                return "motor_failure"
            return "belt_wear"
        elif "pump" in type_lower:
            return "bearing_failure"
        elif "boiler" in type_lower:
            return "heat_exchanger_fouling"
        elif "ups" in type_lower:
            return "battery_degradation"
        elif "generator" in type_lower:
            return "fuel_system_issue"
        else:
            return "component_degradation"

    def _build_evidence(self, equipment: Dict[str, Any]) -> Dict[str, Any]:
        """Build evidence data for prediction."""
        health_score = equipment.get("health_score", 50)

        return {
            "health_score": health_score,
            "health_trend": "declining" if health_score < 70 else "stable",
            "formula_version": FORMULA_VERSION_STATIC,
            "data_source": "automatic_health_monitoring",
            "last_reading": {
                "parameter": "health_score",
                "value": health_score,
                "baseline": 90,
                "threshold": 70,
                "trend": "declining",
            },
        }

    def _calculate_financial_impact(self, equipment_type: str, severity: str) -> Dict[str, int]:
        """Calculate estimated financial impact."""
        # Base costs by equipment type (ZAR)
        base_costs = {
            "chiller": {"repair": 85000, "replacement": 2500000, "downtime": 15000},
            "ahu": {"repair": 25000, "replacement": 450000, "downtime": 8000},
            "pump": {"repair": 15000, "replacement": 120000, "downtime": 5000},
            "boiler": {"repair": 45000, "replacement": 800000, "downtime": 12000},
            "ups": {"repair": 35000, "replacement": 650000, "downtime": 25000},
            "generator": {"repair": 75000, "replacement": 1500000, "downtime": 30000},
            "default": {"repair": 20000, "replacement": 200000, "downtime": 5000},
        }

        # Severity multipliers (normalized severity states only)
        severity_multipliers = {
            "critical": 1.5,
            "warning": 1.0,
            "healthy": 0.8,
        }

        # Get costs for equipment type
        type_lower = equipment_type.lower()
        costs = base_costs.get("default", base_costs["default"])
        for key in base_costs:
            if key in type_lower:
                costs = base_costs[key]
                break

        multiplier = severity_multipliers.get(severity, 1.0)

        repair_cost = int(costs["repair"] * multiplier)
        replacement_cost = costs["replacement"]
        downtime_cost = int(costs["downtime"] * multiplier)

        # Estimate potential loss (downtime * estimated hours)
        estimated_hours = {"critical": 48, "warning": 8, "healthy": 4}.get(severity, 8)
        potential_loss = downtime_cost * estimated_hours + repair_cost

        return {
            "repair_cost": repair_cost,
            "replacement_cost": replacement_cost,
            "downtime_cost_per_hour": downtime_cost,
            "potential_loss": potential_loss,
        }

    def _get_contributing_factors(self, equipment: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get contributing factors for the prediction."""
        health_score = equipment.get("health_score", 50)
        factors = []

        # Health score factor
        if health_score < 70:
            factors.append(
                {
                    "factor": "Low Health Score",
                    "weight": 0.4,
                    "description": f"Equipment health at {health_score}%, below acceptable threshold",
                }
            )

        # Age factor (if available)
        install_date = equipment.get("install_date")
        if install_date:
            try:
                age_years = (datetime.now() - datetime.fromisoformat(install_date.replace("Z", "+00:00"))).days / 365
                if age_years > 10:
                    factors.append(
                        {
                            "factor": "Equipment Age",
                            "weight": 0.3,
                            "description": f"Equipment is {age_years:.1f} years old",
                        }
                    )
            except Exception:
                pass

        # Runtime factor (if available)
        runtime = equipment.get("runtime_hours", 0)
        if runtime > 20000:
            factors.append(
                {
                    "factor": "High Runtime",
                    "weight": 0.2,
                    "description": f"Equipment has {runtime:,} operating hours",
                }
            )

        # Default factor if none found
        if not factors:
            factors.append(
                {
                    "factor": "Health Monitoring",
                    "weight": 0.5,
                    "description": "Detected through automated health monitoring",
                }
            )

        return factors

    def _get_recommended_action(self, equipment_type: str, severity: str, prediction_type: str) -> str:
        """Generate recommended action based on prediction."""
        actions = {
            "compressor_failure": "Schedule compressor inspection and vibration analysis",
            "refrigerant_leak": "Perform leak detection and refrigerant level check",
            "motor_failure": "Inspect motor bearings and windings, check amperage draw",
            "belt_wear": "Replace drive belts and check pulley alignment",
            "bearing_failure": "Replace bearings and check lubrication system",
            "heat_exchanger_fouling": "Schedule chemical cleaning of heat exchanger",
            "battery_degradation": "Test battery cells and schedule replacement",
            "fuel_system_issue": "Inspect fuel filters, injectors, and tank condition",
            "component_degradation": "Schedule comprehensive equipment inspection",
        }

        base_action = actions.get(prediction_type, "Schedule maintenance inspection")

        if severity == "critical":
            return f"URGENT: {base_action}. Immediate attention required."
        elif severity == "warning":
            return f"{base_action}. Schedule within 7 days."
        else:
            return f"{base_action}. Schedule at next maintenance window."

    async def auto_resolve_improved_equipment(self, threshold: int) -> int:
        """
        Auto-resolve predictions for equipment that has improved above threshold.

        Args:
            threshold: Health score threshold

        Returns:
            Number of predictions resolved
        """
        resolved_count = 0

        try:
            # Get equipment IDs with active predictions
            active_ids = self.prediction_repo.get_active_equipment_ids()

            if not active_ids:
                return 0

            # Check which have improved
            response = (
                self.supabase.table("equipment")
                .select("id, health_score")
                .in_("id", active_ids)
                .gte("health_score", threshold)
                .execute()
            )

            improved_equipment = response.data or []

            # Resolve predictions for improved equipment
            for equipment in improved_equipment:
                equipment_id = equipment.get("id")
                count = self.prediction_repo.resolve_by_equipment(equipment_id)
                resolved_count += count
                if count > 0:
                    logger.info(
                        f"Auto-resolved {count} prediction(s) for equipment {equipment_id} "
                        f"(health improved to {equipment.get('health_score')}%)"
                    )

        except Exception as e:
            logger.error(f"Failed to auto-resolve predictions: {e}")

        return resolved_count


# Singleton instance
_generator_instance: Optional[PredictionGeneratorService] = None


def get_prediction_generator() -> PredictionGeneratorService:
    """Get singleton prediction generator instance."""
    global _generator_instance
    if _generator_instance is None:
        _generator_instance = PredictionGeneratorService()
    return _generator_instance
