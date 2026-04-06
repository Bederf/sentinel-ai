"""
RUL Calculator Service (Phase 56-02)

Calculates Remaining Useful Life for equipment elements based on
degradation rates from ElementTrendService and failure thresholds
from inspection checklist templates.

Core intelligence:
- Predicts when elements will reach failure thresholds
- Classifies risk levels (low/medium/high/critical)
- Generates prioritized service recommendations
- Enables proactive maintenance scheduling
"""

import json
import logging
from pathlib import Path

from app.models.condition import (
    ElementRUL,
    ElementTrend,
    EquipmentRUL,
    RiskLevel,
    ServiceRecommendation,
    TrendDirection,
    Urgency,
)
from app.services.element_trend_service import get_element_trend_service

logger = logging.getLogger(__name__)

# Path to checklist templates for threshold extraction
CHECKLIST_TEMPLATES_PATH = Path(__file__).parent.parent / "data" / "inspection_checklist_templates.json"


class RULCalculator:
    """
    Remaining Useful Life calculator.

    Uses element trend data to predict when elements will reach
    failure thresholds, enabling proactive maintenance scheduling.
    """

    def __init__(self):
        """Initialize calculator with lazy-loaded thresholds."""
        self._threshold_cache: dict[str, dict[str, float]] = {}
        self._templates_loaded = False

    # ========================================================================
    # Threshold Loading
    # ========================================================================

    def _get_element_thresholds(self, equipment_type: str) -> dict[str, float]:
        """
        Get failure threshold values for each element of an equipment type.

        Loads from inspection_checklist_templates.json using tolerance_max
        values from measurement items. Falls back to sensible defaults.

        Args:
            equipment_type: Equipment type (chiller, ahu, fcu, generator, pump, vav)

        Returns:
            Dict mapping element_name (parameter_name) -> threshold_value
        """
        # Check cache first
        if equipment_type in self._threshold_cache:
            return self._threshold_cache[equipment_type]

        thresholds: dict[str, float] = {}

        # Load from checklist templates
        if not self._templates_loaded:
            self._load_templates()

        # Try to find matching template
        template_key = f"{equipment_type}_weekly"
        if template_key not in self._all_templates:
            template_key = f"{equipment_type}_monthly"

        if template_key in self._all_templates:
            template = self._all_templates[template_key]
            items = template.get("checklist_items", [])

            for item in items:
                if item.get("item_type") == "measurement":
                    param_name = item.get("parameter_name")
                    tolerance_max = item.get("tolerance_max")
                    if param_name and tolerance_max is not None:
                        thresholds[param_name] = float(tolerance_max)

        # Add fallback defaults for common measurements not in templates
        fallback_defaults = self._get_fallback_defaults(equipment_type)
        for key, value in fallback_defaults.items():
            if key not in thresholds:
                thresholds[key] = value

        # Cache result
        self._threshold_cache[equipment_type] = thresholds
        logger.debug(f"Loaded {len(thresholds)} thresholds for {equipment_type}")

        return thresholds

    def _load_templates(self):
        """Load all checklist templates from JSON file."""
        self._all_templates = {}
        try:
            if CHECKLIST_TEMPLATES_PATH.exists():
                with open(CHECKLIST_TEMPLATES_PATH) as f:
                    data = json.load(f)
                    self._all_templates = data.get("templates", {})
                logger.info(f"Loaded {len(self._all_templates)} checklist templates")
            else:
                logger.warning(f"Checklist templates not found at {CHECKLIST_TEMPLATES_PATH}")
        except Exception as e:
            logger.error(f"Error loading checklist templates: {e}")

        self._templates_loaded = True

    def _get_fallback_defaults(self, equipment_type: str) -> dict[str, float]:
        """
        Get fallback threshold defaults for common measurements.

        These are used when checklist templates don't cover a measurement.
        """
        common = {
            "vibration_rms": 4.5,  # mm/s - ISO 10816 alert level
            "vibration": 4.5,  # mm/s
        }

        type_specific = {
            "chiller": {
                "compressor_discharge_temp": 90.0,  # C
                "suction_pressure": 5.5,  # bar
                "discharge_pressure": 18.0,  # bar
                "oil_temperature": 65.0,  # C
                "motor_current": 160.0,  # A
            },
            "ahu": {
                "filter_dp": 150.0,  # Pa
                "fan_vibration_rms": 3.5,  # mm/s
                "supply_air_temp": 20.0,  # C
                "motor_current": 50.0,  # A
            },
            "fcu": {
                "filter_dp": 100.0,  # Pa
                "space_temp_delta": 1.0,  # C
                "fan_vibration": 3.0,  # mm/s
            },
            "generator": {
                "coolant_temp": 95.0,  # C
                "exhaust_temp": 550.0,  # C
                "battery_voltage": 28.0,  # V
                "oil_pressure": 6.0,  # bar
                "vibration_rms": 5.0,  # mm/s
            },
            "pump": {
                "vibration_rms": 3.0,  # mm/s
                "bearing_temp": 75.0,  # C
                "discharge_pressure": 8.0,  # bar
                "motor_current": 25.0,  # A
            },
            "vav": {
                "airflow_reading": 200.0,  # L/s
                "damper_position_error": 5.0,  # %
            },
        }

        defaults = dict(common)
        if equipment_type in type_specific:
            defaults.update(type_specific[equipment_type])

        return defaults

    # ========================================================================
    # Element RUL Calculation
    # ========================================================================

    def calculate_element_rul(self, element_trend: ElementTrend, threshold: float) -> ElementRUL:
        """
        Calculate Remaining Useful Life for a single element.

        Logic:
        - If trend is stable or improving: no predicted failure (days_until_threshold = None)
        - If degrading: days_remaining = (threshold - current_value) / rate_per_day
        - If current_value exceeds threshold: days_remaining = 0
        - Confidence from trend's R-squared value

        Risk levels:
        - >90 days = low
        - 30-90 days = medium
        - 7-30 days = high
        - <7 days = critical

        Args:
            element_trend: Trend data for the element
            threshold: Failure threshold value

        Returns:
            ElementRUL prediction
        """
        # Get current value from latest data point
        current_value = None
        unit = ""
        if element_trend.data_points:
            current_value = element_trend.data_points[-1].value
            unit = element_trend.data_points[-1].unit

        confidence = element_trend.r_squared if element_trend.r_squared is not None else 0.0

        # If stable or improving, no predicted failure
        if element_trend.trend_direction in (TrendDirection.STABLE, TrendDirection.IMPROVING):
            return ElementRUL(
                element_name=element_trend.element_name,
                current_value=current_value,
                threshold_value=threshold,
                unit=unit,
                days_until_threshold=None,
                confidence=confidence,
                risk_level=RiskLevel.LOW,
            )

        # Degrading - calculate days until threshold
        rate_per_day = element_trend.degradation_rate_per_day
        if rate_per_day is None or rate_per_day <= 0:
            # No valid rate
            return ElementRUL(
                element_name=element_trend.element_name,
                current_value=current_value,
                threshold_value=threshold,
                unit=unit,
                days_until_threshold=None,
                confidence=confidence,
                risk_level=RiskLevel.LOW,
            )

        # Check if already exceeds threshold
        if current_value is not None and current_value >= threshold:
            return ElementRUL(
                element_name=element_trend.element_name,
                current_value=current_value,
                threshold_value=threshold,
                unit=unit,
                days_until_threshold=0.0,
                confidence=confidence,
                risk_level=RiskLevel.CRITICAL,
            )

        # Calculate days remaining
        if current_value is not None:
            remaining = threshold - current_value
            days_remaining = remaining / rate_per_day
            days_remaining = max(0.0, round(days_remaining, 1))
        else:
            days_remaining = None

        # Classify risk level
        risk_level = self._classify_risk(days_remaining)

        return ElementRUL(
            element_name=element_trend.element_name,
            current_value=current_value,
            threshold_value=threshold,
            unit=unit,
            days_until_threshold=days_remaining,
            confidence=confidence,
            risk_level=risk_level,
        )

    def _classify_risk(self, days_remaining: float | None) -> RiskLevel:
        """Classify risk level based on days until threshold."""
        if days_remaining is None:
            return RiskLevel.LOW
        if days_remaining <= 0:
            return RiskLevel.CRITICAL
        if days_remaining < 7:
            return RiskLevel.CRITICAL
        if days_remaining < 30:
            return RiskLevel.HIGH
        if days_remaining < 90:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    # ========================================================================
    # Equipment RUL Calculation
    # ========================================================================

    async def calculate_equipment_rul(self, equipment_id: str, days: int = 90) -> EquipmentRUL:
        """
        Calculate RUL for all elements of an equipment item.

        Steps:
        1. Get trend summary from ElementTrendService
        2. Get thresholds for equipment type
        3. Calculate RUL for each element
        4. Determine overall risk from worst element
        5. Generate service window recommendation

        Args:
            equipment_id: Equipment identifier
            days: History window for trend calculation

        Returns:
            EquipmentRUL with per-element predictions and overall assessment
        """
        trend_service = get_element_trend_service()
        summary = await trend_service.get_equipment_trend_summary(equipment_id, days=days)

        # Determine equipment type from summary or fallback
        equipment_type = summary.equipment_type or self._infer_equipment_type(equipment_id)

        # Get thresholds for this equipment type
        thresholds = self._get_element_thresholds(equipment_type)

        # Calculate RUL for each element
        element_ruls: list[ElementRUL] = []
        for trend in summary.element_trends:
            # Find matching threshold
            threshold = self._find_threshold(trend.element_name, thresholds)
            if threshold is None:
                # No threshold available - skip
                continue

            rul = self.calculate_element_rul(trend, threshold)
            element_ruls.append(rul)

        # If no element trends found, return empty RUL
        if not summary.element_trends:
            return EquipmentRUL(
                equipment_id=equipment_id,
                equipment_type=equipment_type,
                element_ruls=[],
                overall_risk_level=RiskLevel.LOW,
                message="No inspection data available for RUL prediction",
            )

        # If no elements had thresholds, still return what we have
        if not element_ruls:
            return EquipmentRUL(
                equipment_id=equipment_id,
                equipment_type=equipment_type,
                element_ruls=[],
                overall_risk_level=RiskLevel.LOW,
                message="No threshold data available for RUL calculation",
            )

        # Find worst element (earliest threshold breach)
        worst_element_name = None
        days_until_first = None

        for rul in element_ruls:
            if rul.days_until_threshold is not None:
                if days_until_first is None or rul.days_until_threshold < days_until_first:
                    days_until_first = rul.days_until_threshold
                    worst_element_name = rul.element_name

        # Overall risk = worst individual element risk
        risk_order = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
        overall_risk = RiskLevel.LOW
        for rul in element_ruls:
            if risk_order.index(rul.risk_level) > risk_order.index(overall_risk):
                overall_risk = rul.risk_level

        # Recommended service window
        service_window = self._recommend_service_window(days_until_first)

        # Build message
        degrading_count = sum(1 for r in element_ruls if r.days_until_threshold is not None)
        message = self._build_rul_message(element_ruls, degrading_count, worst_element_name, days_until_first)

        return EquipmentRUL(
            equipment_id=equipment_id,
            equipment_type=equipment_type,
            element_ruls=element_ruls,
            worst_element_name=worst_element_name,
            days_until_first_threshold=days_until_first,
            overall_risk_level=overall_risk,
            recommended_service_window=service_window,
            message=message,
        )

    def _find_threshold(self, element_name: str, thresholds: dict[str, float]) -> float | None:
        """
        Find a threshold value for an element name.

        Tries exact match first, then partial/fuzzy matching.
        """
        # Exact match
        if element_name in thresholds:
            return thresholds[element_name]

        # Try lowercase match
        element_lower = element_name.lower()
        for key, value in thresholds.items():
            if key.lower() == element_lower:
                return value

        # Try partial match (element_name contains key or vice versa)
        for key, value in thresholds.items():
            if key.lower() in element_lower or element_lower in key.lower():
                return value

        return None

    def _infer_equipment_type(self, equipment_id: str) -> str:
        """Infer equipment type from equipment ID naming convention."""
        eid = equipment_id.upper()
        if "CH" in eid or "CHILLER" in eid:
            return "chiller"
        if "AHU" in eid:
            return "ahu"
        if "FCU" in eid:
            return "fcu"
        if "GEN" in eid:
            return "generator"
        if "PUMP" in eid or "PMP" in eid:
            return "pump"
        if "VAV" in eid:
            return "vav"
        return "general"

    def _recommend_service_window(self, days_until_first: float | None) -> str | None:
        """
        Generate service window recommendation based on worst element.

        Returns:
            String recommendation or None if all stable
        """
        if days_until_first is None:
            return None

        if days_until_first <= 0:
            return "immediate attention required"
        if days_until_first < 7:
            return "immediate attention required"
        if days_until_first < 30:
            return f"within {int(days_until_first)} days - schedule soon"
        if days_until_first < 90:
            return f"within {int(days_until_first)} days"
        return "next scheduled service"

    def _build_rul_message(
        self,
        element_ruls: list[ElementRUL],
        degrading_count: int,
        worst_element: str | None,
        days_until_first: float | None,
    ) -> str:
        """Build human-readable RUL summary message."""
        total = len(element_ruls)

        if degrading_count == 0:
            return f"All {total} monitored elements are stable. No predicted failures."

        if days_until_first is not None and days_until_first <= 0:
            return f"{worst_element} has exceeded its failure threshold. Immediate attention required."

        if worst_element and days_until_first is not None:
            return (
                f"{degrading_count} of {total} elements degrading. "
                f"First threshold ({worst_element}) predicted in "
                f"{int(days_until_first)} days."
            )

        return f"{degrading_count} of {total} elements showing degradation."

    # ========================================================================
    # Service Recommendations
    # ========================================================================

    async def get_service_recommendations(self, equipment_id: str, days: int = 90) -> list[ServiceRecommendation]:
        """
        Generate prioritized service recommendations for degrading elements.

        For each element with a degrading trend, generates a recommendation
        with action, urgency, and reason based on element type.

        Args:
            equipment_id: Equipment identifier
            days: History window for trend calculation

        Returns:
            List of ServiceRecommendation sorted by urgency (immediate first)
        """
        # Get RUL data
        equipment_rul = await self.calculate_equipment_rul(equipment_id, days=days)

        recommendations: list[ServiceRecommendation] = []

        for rul in equipment_rul.element_ruls:
            # Only recommend for elements approaching threshold
            if rul.days_until_threshold is None:
                continue

            # Determine urgency
            urgency = self._rul_to_urgency(rul.days_until_threshold)

            # Generate action and reason based on element type
            action, reason = self._generate_recommendation(
                rul.element_name, rul.days_until_threshold, rul.current_value, rul.threshold_value, rul.unit
            )

            recommendations.append(
                ServiceRecommendation(
                    equipment_id=equipment_id,
                    element_name=rul.element_name,
                    recommended_action=action,
                    urgency=urgency,
                    reason=reason,
                    estimated_days_remaining=rul.days_until_threshold,
                    confidence=rul.confidence,
                )
            )

        # Sort by urgency (immediate first)
        urgency_order = {
            Urgency.IMMEDIATE: 0,
            Urgency.URGENT: 1,
            Urgency.SOON: 2,
            Urgency.ROUTINE: 3,
        }
        recommendations.sort(key=lambda r: urgency_order.get(r.urgency, 4))

        return recommendations

    def _rul_to_urgency(self, days_remaining: float) -> Urgency:
        """Map days remaining to urgency level."""
        if days_remaining <= 0:
            return Urgency.IMMEDIATE
        if days_remaining < 7:
            return Urgency.IMMEDIATE
        if days_remaining < 30:
            return Urgency.URGENT
        if days_remaining < 90:
            return Urgency.SOON
        return Urgency.ROUTINE

    def _generate_recommendation(
        self,
        element_name: str,
        days_remaining: float,
        current_value: float | None,
        threshold_value: float,
        unit: str,
    ) -> tuple:
        """
        Generate action and reason based on element type.

        Returns:
            (action_string, reason_string) tuple
        """
        element_lower = element_name.lower()

        # Classify element type and generate appropriate action
        if any(kw in element_lower for kw in ("vibration", "bearing", "vib")):
            action = "Inspect bearings, check alignment, measure detailed vibration spectrum"
        elif any(kw in element_lower for kw in ("temp", "temperature", "thermal")):
            action = "Check refrigerant levels, clean heat exchangers, verify airflow"
        elif any(kw in element_lower for kw in ("pressure", "bar", "kpa", "psi")):
            action = "Check for leaks, inspect valves, verify pump operation"
        elif any(kw in element_lower for kw in ("filter", "dp")):
            action = "Replace filters, check housing seals"
        elif any(kw in element_lower for kw in ("current", "voltage", "motor", "electrical")):
            action = "Check connections, measure insulation resistance"
        elif any(kw in element_lower for kw in ("fuel",)):
            action = "Check fuel supply, inspect fuel lines and filters"
        elif any(kw in element_lower for kw in ("airflow", "damper")):
            action = "Inspect damper actuator, calibrate airflow sensor"
        else:
            action = "Inspect element, compare with baseline measurements"

        # Build reason
        if days_remaining <= 0:
            reason = (
                f"{element_name} has exceeded threshold "
                f"({current_value} {unit} vs limit {threshold_value} {unit}). "
                f"Immediate action required."
            )
        else:
            reason = (
                f"{element_name} trending toward threshold "
                f"({current_value} {unit} approaching {threshold_value} {unit}). "
                f"Estimated {int(days_remaining)} days remaining."
            )

        return action, reason


# ============================================================================
# Singleton Instance
# ============================================================================

_rul_calculator: RULCalculator | None = None


def get_rul_calculator() -> RULCalculator:
    """Get singleton RULCalculator instance."""
    global _rul_calculator
    if _rul_calculator is None:
        _rul_calculator = RULCalculator()
    return _rul_calculator
