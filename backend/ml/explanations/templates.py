"""Equipment-specific prompt templates for generating ML prediction explanations.

These templates are designed to produce structured output that can be parsed
into actionable maintenance recommendations.
"""

from typing import Optional

# Base template for prediction explanation
PREDICTION_EXPLANATION_TEMPLATE = """You are a BMS (Building Management System) expert explaining equipment predictions to maintenance technicians.

## Equipment Information
- **Type:** {equipment_type}
- **ID:** {equipment_id}
- **Manufacturer:** {manufacturer}
- **Model:** {model}

## ML Prediction Summary
- **Failure Probability (30 days):** {failure_prob_30d:.1f}%
- **Predicted Failure Type:** {predicted_failure}
- **Confidence:** {confidence:.0f}%
- **Anomaly Score:** {anomaly_score:.4f} (threshold: {anomaly_threshold:.4f})
- **Risk Level:** {risk_level}
- **Remaining Useful Life:** {rul_days} days

## Top Contributing Factors
{contributing_factors}

## Relevant Technical Documentation
{rag_context}

---

Generate a structured explanation using EXACTLY this format:

### SUMMARY
[2-3 sentences explaining what this prediction means in plain English]

### KEY_FACTORS
[List the top 3-5 factors that led to this prediction, one per line starting with "- "]

### RECOMMENDED_ACTIONS
[List prioritized actions, format each as: "- [PRIORITY] Action description" where PRIORITY is HIGH, MEDIUM, or LOW]

### PARTS_NEEDED
[List parts likely needed, format each as: "- Part name (quantity if known)"]
[If no parts needed, write: "- None anticipated"]

### LABOR_ESTIMATE
[Estimated labor time in format: "X hours" or "X-Y hours"]

### ADDITIONAL_NOTES
[Any other relevant information for the technician]
"""

# Template for generating maintenance recommendations
MAINTENANCE_RECOMMENDATION_TEMPLATE = """You are a maintenance planning expert for building management systems.

Based on the equipment prediction and analysis, generate specific maintenance recommendations.

## Equipment Details
- **Type:** {equipment_type}
- **ID:** {equipment_id}
- **Current Risk Level:** {risk_level}
- **Predicted Issue:** {predicted_failure}

## Historical Context
{maintenance_history}

## Recent Sensor Readings
{sensor_context}

## Similar Equipment Experience
{fleet_context}

---

Generate maintenance recommendations in this exact format:

### IMMEDIATE_ACTIONS
[Actions to take within 24 hours, if any]
[Format: "- Action description"]

### SCHEDULED_MAINTENANCE
[Actions to schedule within the risk window]
[Format: "- [Timeline] Action description"]

### PREVENTIVE_MEASURES
[Steps to prevent recurrence]
[Format: "- Measure description"]

### SPARE_PARTS
[Parts to have on hand]
[Format: "- Part name | Part number (if known) | Quantity"]

### TECHNICIAN_SKILLS
[Required skills/certifications]
[Format: "- Skill/certification required"]

### ESTIMATED_DOWNTIME
[Expected equipment downtime for maintenance]
[Format: "X hours" or "X-Y hours"]
"""

# Equipment-specific context additions
EQUIPMENT_CONTEXTS = {
    "chiller": """
## Chiller-Specific Considerations
- Check refrigerant levels and pressure differentials
- Review compressor amp draws and oil levels
- Consider condenser/evaporator fouling
- Monitor approach temperatures
- Check economizer operation if applicable
""",
    "ahu": """
## AHU-Specific Considerations
- Check filter differential pressure
- Review belt tension and condition
- Monitor supply/return air temperatures
- Check damper operation and calibration
- Review VFD operation and alarms
""",
    "boiler": """
## Boiler-Specific Considerations
- Check combustion efficiency and CO levels
- Review water treatment and chemistry
- Monitor flame sensor operation
- Check gas pressure and valve operation
- Review safety interlock sequence
""",
    "cooling_tower": """
## Cooling Tower-Specific Considerations
- Check water treatment and blowdown rates
- Review fill media condition
- Monitor fan vibration and blade condition
- Check drift eliminator condition
- Review basin cleanliness and water level
""",
    "generator": """
## Generator-Specific Considerations
- Check fuel quality and tank levels
- Review oil analysis results
- Monitor coolant condition
- Check battery voltage and specific gravity
- Review load bank test results
""",
    "ups": """
## UPS-Specific Considerations
- Check battery health and capacity
- Review input/output power quality
- Monitor thermal conditions
- Check bypass operation
- Review event logs for warnings
""",
    "vfd": """
## VFD-Specific Considerations
- Check capacitor health
- Review thermal management
- Monitor input/output waveforms
- Check parameter settings
- Review fault history
""",
    "fcu": """
## FCU-Specific Considerations
- Check filter condition
- Review valve operation
- Monitor coil performance
- Check drain pan and condensate
- Review thermostat operation
""",
}


def get_equipment_specific_template(
    equipment_type: str,
    include_context: bool = True
) -> str:
    """Get the explanation template with equipment-specific additions.

    Args:
        equipment_type: Type of equipment (chiller, ahu, boiler, etc.)
        include_context: Whether to include equipment-specific context

    Returns:
        Complete template string
    """
    template = PREDICTION_EXPLANATION_TEMPLATE

    if include_context and equipment_type.lower() in EQUIPMENT_CONTEXTS:
        # Insert equipment-specific context before the RAG context
        equipment_context = EQUIPMENT_CONTEXTS[equipment_type.lower()]
        template = template.replace(
            "## Relevant Technical Documentation",
            f"{equipment_context}\n## Relevant Technical Documentation"
        )

    return template


def format_contributing_factors(factors: list) -> str:
    """Format contributing factors for template insertion.

    Args:
        factors: List of factor dictionaries with 'name'/'factor' and 'importance'/'weight'

    Returns:
        Formatted string for template
    """
    if not factors:
        return "- No specific factors identified"

    lines = []
    for f in factors[:5]:  # Top 5 factors
        name = f.get('name', f.get('factor', 'Unknown'))
        importance = f.get('importance', f.get('weight', 0))
        if isinstance(importance, (int, float)):
            lines.append(f"- **{name}:** {importance:.1%} contribution")
        else:
            lines.append(f"- **{name}:** {importance}")

    return "\n".join(lines)


def format_prediction_for_template(
    equipment_id: str,
    equipment_type: str,
    predictions: dict,
    equipment_info: Optional[dict] = None
) -> dict:
    """Format prediction data for template insertion.

    Args:
        equipment_id: Equipment identifier
        equipment_type: Type of equipment
        predictions: Comprehensive prediction results
        equipment_info: Optional equipment metadata

    Returns:
        Dictionary ready for template formatting
    """
    # Extract values with defaults
    survival = predictions.get("survival", {})
    anomaly = predictions.get("anomaly", {})
    failure_type = predictions.get("failure_type", {})

    # Get failure probability from survival analysis
    failure_probs = survival.get("failure_probability", {})
    failure_prob_30d = failure_probs.get("30d", 0) if isinstance(failure_probs, dict) else 0

    # Get RUL from survival
    rul_estimate = survival.get("rul_estimate", {})
    rul_days = rul_estimate.get("median", "Unknown") if isinstance(rul_estimate, dict) else "Unknown"

    # Get contributing factors from failure type prediction
    contributing_factors = failure_type.get("contributing_factors", [])

    return {
        "equipment_id": equipment_id,
        "equipment_type": equipment_type,
        "manufacturer": equipment_info.get("manufacturer", "Unknown") if equipment_info else "Unknown",
        "model": equipment_info.get("model", "Unknown") if equipment_info else "Unknown",
        "failure_prob_30d": float(failure_prob_30d) * 100,
        "predicted_failure": failure_type.get("predicted_failure", "Unknown"),
        "confidence": float(failure_type.get("confidence", 0)) * 100,
        "anomaly_score": float(anomaly.get("anomaly_score", 0)),
        "anomaly_threshold": float(anomaly.get("threshold", 0.001)),
        "risk_level": predictions.get("overall_risk", {}).get("risk_level", "Unknown"),
        "rul_days": rul_days,
        "contributing_factors": format_contributing_factors(contributing_factors),
    }
