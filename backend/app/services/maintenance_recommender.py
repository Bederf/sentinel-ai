"""Maintenance Recommender Service.

Generates specific maintenance recommendations based on ML predictions,
equipment history, and fleet-wide experience.
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass, field

from app.services.ollama_client import get_ollama_client
from app.services.vector_db import get_vector_db_service
from ml.explanations.templates import MAINTENANCE_RECOMMENDATION_TEMPLATE
from ml.explanations.parser import ExplanationParser

logger = logging.getLogger(__name__)


@dataclass
class MaintenanceRecommendation:
    """A structured maintenance recommendation."""
    equipment_id: str
    equipment_type: str
    risk_level: str
    immediate_actions: List[str] = field(default_factory=list)
    scheduled_maintenance: List[Dict[str, str]] = field(default_factory=list)
    preventive_measures: List[str] = field(default_factory=list)
    spare_parts: List[Dict[str, Any]] = field(default_factory=list)
    technician_skills: List[str] = field(default_factory=list)
    estimated_downtime: str = ""
    priority: str = "medium"
    generated_at: str = ""
    llm_used: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "equipment_id": self.equipment_id,
            "equipment_type": self.equipment_type,
            "risk_level": self.risk_level,
            "immediate_actions": self.immediate_actions,
            "scheduled_maintenance": self.scheduled_maintenance,
            "preventive_measures": self.preventive_measures,
            "spare_parts": self.spare_parts,
            "technician_skills": self.technician_skills,
            "estimated_downtime": self.estimated_downtime,
            "priority": self.priority,
            "generated_at": self.generated_at,
            "llm_used": self.llm_used
        }


# Default maintenance actions by equipment type and risk level
DEFAULT_MAINTENANCE_ACTIONS = {
    "chiller": {
        "critical": [
            "Shut down and lock out equipment immediately",
            "Contact manufacturer technical support",
            "Arrange emergency refrigerant check"
        ],
        "high": [
            "Schedule immediate inspection within 24-48 hours",
            "Check refrigerant levels and pressures",
            "Verify compressor oil levels and quality"
        ],
        "medium": [
            "Schedule inspection within 7 days",
            "Review recent operating logs",
            "Check condenser and evaporator approach temps"
        ],
        "low": [
            "Include in next scheduled PM",
            "Monitor trend data for changes"
        ]
    },
    "ahu": {
        "critical": [
            "Switch to backup unit if available",
            "Isolate and lock out for inspection",
            "Check for fire/smoke conditions"
        ],
        "high": [
            "Inspect filters and replace if dirty",
            "Check belt tension and condition",
            "Verify damper operation"
        ],
        "medium": [
            "Schedule filter replacement",
            "Check VFD parameters",
            "Review zone temperatures"
        ],
        "low": [
            "Include in quarterly PM",
            "Check coil cleanliness"
        ]
    },
    "generator": {
        "critical": [
            "Do not attempt start",
            "Check fuel system for leaks",
            "Verify battery disconnect is open"
        ],
        "high": [
            "Perform immediate load test",
            "Check coolant level and condition",
            "Verify fuel quality"
        ],
        "medium": [
            "Schedule oil analysis",
            "Check battery specific gravity",
            "Review run hours"
        ],
        "low": [
            "Continue monthly exercising",
            "Schedule next annual service"
        ]
    },
    "default": {
        "critical": [
            "Isolate equipment immediately",
            "Contact supervisor",
            "Document current conditions"
        ],
        "high": [
            "Schedule priority inspection",
            "Review recent alarms",
            "Check safety systems"
        ],
        "medium": [
            "Add to maintenance queue",
            "Monitor for changes"
        ],
        "low": [
            "Continue normal monitoring"
        ]
    }
}

# Common spare parts by equipment type
COMMON_SPARE_PARTS = {
    "chiller": ["Refrigerant", "Compressor oil", "Filters", "Gaskets", "Contactors"],
    "ahu": ["V-belt set", "Filters", "Bearings", "Damper actuators", "Fan motor"],
    "boiler": ["Flame sensor", "Igniter", "Gaskets", "Control valves", "Refractory"],
    "generator": ["Fuel filters", "Oil filters", "Air filters", "Coolant", "Batteries"],
    "cooling_tower": ["Fill media", "Fan belts", "Float valve", "Drift eliminator"],
    "vfd": ["Cooling fans", "Capacitors", "Control board"],
    "ups": ["Batteries", "Capacitors", "Cooling fans"],
    "fcu": ["Filters", "Valve actuator", "Fan motor", "Thermostat"]
}


class MaintenanceRecommender:
    """Service for generating maintenance recommendations.

    Combines ML predictions with equipment history and knowledge base
    to generate specific, actionable maintenance recommendations.
    """

    def __init__(self, supabase_client):
        """Initialize the recommender.

        Args:
            supabase_client: Supabase client for database access
        """
        self.ollama = get_ollama_client()
        self.vector_db = get_vector_db_service(supabase_client)
        self._supabase_client = supabase_client

    async def generate_recommendation(
        self,
        equipment_id: str,
        equipment_type: str,
        predictions: Dict[str, Any],
        maintenance_history: Optional[List[Dict]] = None,
        sensor_readings: Optional[Dict[str, Any]] = None
    ) -> MaintenanceRecommendation:
        """Generate maintenance recommendations based on predictions.

        Args:
            equipment_id: Equipment identifier
            equipment_type: Type of equipment
            predictions: Comprehensive prediction results
            maintenance_history: Optional recent maintenance records
            sensor_readings: Optional current sensor readings

        Returns:
            MaintenanceRecommendation with structured recommendations
        """
        overall_risk = predictions.get("overall_risk", {})
        risk_level = overall_risk.get("risk_level", "low")
        predicted_failure = predictions.get("predictions", {}).get(
            "failure_type", {}
        ).get("predicted_failure", "Unknown")

        # Check if LLM is available
        ollama_available = await self.ollama.is_available()

        if ollama_available:
            recommendation = await self._generate_llm_recommendation(
                equipment_id=equipment_id,
                equipment_type=equipment_type,
                risk_level=risk_level,
                predicted_failure=predicted_failure,
                predictions=predictions,
                maintenance_history=maintenance_history,
                sensor_readings=sensor_readings
            )
        else:
            recommendation = self._generate_fallback_recommendation(
                equipment_id=equipment_id,
                equipment_type=equipment_type,
                risk_level=risk_level,
                predicted_failure=predicted_failure
            )

        return recommendation

    async def _generate_llm_recommendation(
        self,
        equipment_id: str,
        equipment_type: str,
        risk_level: str,
        predicted_failure: str,
        predictions: Dict[str, Any],
        maintenance_history: Optional[List[Dict]] = None,
        sensor_readings: Optional[Dict[str, Any]] = None
    ) -> MaintenanceRecommendation:
        """Generate recommendation using LLM.

        Args:
            equipment_id: Equipment identifier
            equipment_type: Type of equipment
            risk_level: Current risk level
            predicted_failure: Predicted failure type
            predictions: Full predictions
            maintenance_history: Recent maintenance records
            sensor_readings: Current sensor readings

        Returns:
            MaintenanceRecommendation from LLM
        """
        # Format maintenance history
        if maintenance_history:
            history_text = "\n".join([
                f"- {h.get('date', 'Unknown')}: {h.get('description', 'No description')}"
                for h in maintenance_history[:5]
            ])
        else:
            history_text = "No recent maintenance history available."

        # Format sensor readings
        if sensor_readings:
            sensor_text = "\n".join([
                f"- {k}: {v}"
                for k, v in sensor_readings.items()
            ])
        else:
            sensor_text = "No current sensor readings available."

        # Get fleet context from knowledge base
        query = f"{predicted_failure} {equipment_type}"
        knowledge = self.vector_db.search_knowledge(
            query=query,
            equipment_type=equipment_type,
            n_results=2,
            similarity_threshold=0.2
        )

        if knowledge:
            fleet_text = "\n".join([
                f"- {k.get('title', 'Unknown')}: {k.get('solution', k.get('description', ''))}"
                for k in knowledge
            ])
        else:
            fleet_text = "No similar equipment experience found."

        # Build prompt
        prompt = MAINTENANCE_RECOMMENDATION_TEMPLATE.format(
            equipment_type=equipment_type,
            equipment_id=equipment_id,
            risk_level=risk_level,
            predicted_failure=predicted_failure,
            maintenance_history=history_text,
            sensor_context=sensor_text,
            fleet_context=fleet_text
        )

        # Generate with LLM
        raw_response = await self.ollama.generate(prompt, temperature=0.3)

        # Parse response
        parsed = ExplanationParser.parse_recommendation(raw_response)

        return MaintenanceRecommendation(
            equipment_id=equipment_id,
            equipment_type=equipment_type,
            risk_level=risk_level,
            immediate_actions=parsed.immediate_actions,
            scheduled_maintenance=parsed.scheduled_maintenance,
            preventive_measures=parsed.preventive_measures,
            spare_parts=[p.to_dict() for p in parsed.spare_parts],
            technician_skills=parsed.technician_skills,
            estimated_downtime=parsed.estimated_downtime,
            priority=self._risk_to_priority(risk_level),
            generated_at=datetime.now().isoformat(),
            llm_used=True
        )

    def _generate_fallback_recommendation(
        self,
        equipment_id: str,
        equipment_type: str,
        risk_level: str,
        predicted_failure: str
    ) -> MaintenanceRecommendation:
        """Generate fallback recommendation without LLM.

        Args:
            equipment_id: Equipment identifier
            equipment_type: Type of equipment
            risk_level: Current risk level
            predicted_failure: Predicted failure type

        Returns:
            MaintenanceRecommendation with default actions
        """
        # Get default actions for this equipment type and risk level
        type_actions = DEFAULT_MAINTENANCE_ACTIONS.get(
            equipment_type.lower(),
            DEFAULT_MAINTENANCE_ACTIONS["default"]
        )
        immediate = type_actions.get(risk_level, type_actions.get("low", []))

        # Build scheduled maintenance based on risk
        if risk_level == "critical":
            scheduled = [
                {"timeline": "Immediate", "action": "Emergency repair/replacement"},
                {"timeline": "24 hours", "action": "Root cause analysis"}
            ]
        elif risk_level == "high":
            scheduled = [
                {"timeline": "48 hours", "action": "Detailed inspection"},
                {"timeline": "1 week", "action": "Corrective maintenance"}
            ]
        elif risk_level == "medium":
            scheduled = [
                {"timeline": "2 weeks", "action": "Scheduled inspection"},
                {"timeline": "1 month", "action": "Preventive maintenance"}
            ]
        else:
            scheduled = [
                {"timeline": "Next PM cycle", "action": "Include in routine maintenance"}
            ]

        # Get common spare parts for this equipment type
        spare_parts = COMMON_SPARE_PARTS.get(equipment_type.lower(), [])
        parts_list = [{"name": p, "quantity": None, "part_number": None} for p in spare_parts[:3]]

        # Standard preventive measures
        preventive = [
            "Document current equipment condition with photos",
            "Review and update maintenance procedures if needed",
            "Check calibration of all sensors and controls"
        ]

        # Standard skills based on equipment type
        skills = ["HVAC certification"] if equipment_type.lower() in ["chiller", "ahu", "fcu"] else []
        skills.append("Equipment-specific training")

        return MaintenanceRecommendation(
            equipment_id=equipment_id,
            equipment_type=equipment_type,
            risk_level=risk_level,
            immediate_actions=immediate,
            scheduled_maintenance=scheduled,
            preventive_measures=preventive,
            spare_parts=parts_list,
            technician_skills=skills,
            estimated_downtime=self._estimate_downtime(risk_level),
            priority=self._risk_to_priority(risk_level),
            generated_at=datetime.now().isoformat(),
            llm_used=False
        )

    def _risk_to_priority(self, risk_level: str) -> str:
        """Convert risk level to maintenance priority.

        Args:
            risk_level: Risk level (critical, high, medium, low)

        Returns:
            Priority string
        """
        return {
            "critical": "emergency",
            "high": "urgent",
            "medium": "planned",
            "low": "routine"
        }.get(risk_level.lower(), "routine")

    def _estimate_downtime(self, risk_level: str) -> str:
        """Estimate downtime based on risk level.

        Args:
            risk_level: Risk level

        Returns:
            Estimated downtime string
        """
        return {
            "critical": "4-8 hours (emergency repair)",
            "high": "2-4 hours",
            "medium": "1-2 hours",
            "low": "0.5-1 hour"
        }.get(risk_level.lower(), "1-2 hours")

    async def get_fleet_recommendations(
        self,
        equipment_list: List[Dict[str, Any]],
        predictions_map: Dict[str, Dict]
    ) -> List[MaintenanceRecommendation]:
        """Generate recommendations for multiple equipment.

        Args:
            equipment_list: List of equipment info dicts
            predictions_map: Map of equipment_id -> predictions

        Returns:
            List of recommendations sorted by priority
        """
        recommendations = []

        for equipment in equipment_list:
            equipment_id = equipment.get("id")
            if equipment_id not in predictions_map:
                continue

            predictions = predictions_map[equipment_id]
            recommendation = await self.generate_recommendation(
                equipment_id=equipment_id,
                equipment_type=equipment.get("equipment_type", "unknown"),
                predictions=predictions
            )
            recommendations.append(recommendation)

        # Sort by priority (emergency first)
        priority_order = {"emergency": 0, "urgent": 1, "planned": 2, "routine": 3}
        recommendations.sort(key=lambda r: priority_order.get(r.priority, 4))

        return recommendations


def get_maintenance_recommender(supabase_client) -> MaintenanceRecommender:
    """Factory function for MaintenanceRecommender.

    Args:
        supabase_client: Supabase client for database access

    Returns:
        MaintenanceRecommender instance
    """
    return MaintenanceRecommender(supabase_client)
