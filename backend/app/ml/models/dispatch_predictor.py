"""Dispatch Predictor -- ML model for forecasting BESS dispatch actions.

Predicts next dispatch action and timing based on:
  - Historical price patterns
  - Current BESS state
  - Weather forecast
  - Load shedding schedule
  - Building demand profile

Currently uses rule-based prediction (XGBoost/TensorFlow integration pending).
"""

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# === Dataclass Models ===


@dataclass
class DispatchPrediction:
    """Predicted next dispatch action and timing."""

    action: str  # charge / discharge / idle
    confidence_pct: float  # 0-100%
    next_action_start_hour: int  # When action should start (0-23)
    next_action_duration_hours: int  # Duration of action
    expected_power_kw: float  # Predicted power
    expected_revenue_r: float  # Expected revenue if discharge
    recommendation: str  # Human-readable recommendation
    reasoning: str  # Why this action was predicted


# === Dispatch Predictor ===


class DispatchPredictor:
    """ML-based dispatch action predictor.

    Current implementation uses rule-based heuristics. Future versions
    will integrate XGBoost/TensorFlow models trained on historical data.
    """

    def __init__(self):
        """Initialize predictor."""
        self._model_version = "1.0-rule-based"
        logger.info("Initialized DispatchPredictor %s", self._model_version)

    def predict_next_action(
        self,
        current_hour: int,
        current_soc_pct: float,
        price_forecasts: list[dict[str, Any]],
        temperature_forecast: list[float] | None = None,
        load_shedding_stage: int = 0,
        building_demand_kw: list[float] | None = None,
    ) -> DispatchPrediction:
        """Predict next BESS dispatch action.

        Algorithm:
          1. Analyze next 6 hours of price forecast
          2. Check BESS constraints (SOC, temp)
          3. Identify charge/discharge opportunities
          4. Rank by revenue potential
          5. Return top action with confidence

        Args:
            current_hour: Current hour (0-23 SAST)
            current_soc_pct: Current SOC (0-100%)
            price_forecasts: List of hourly price forecasts (next 24 hours)
            temperature_forecast: Hourly temperature forecast (optional)
            load_shedding_stage: Current LS stage (0-8)
            building_demand_kw: Hourly building demand forecast (optional)

        Returns:
            DispatchPrediction with action, timing, and confidence
        """
        # Default temps and demand if not provided
        temps = temperature_forecast or [20.0] * 24
        _demands = building_demand_kw or [1800.0] * 24

        # Look ahead window
        lookahead_hours = 6
        lookahead_forecasts = price_forecasts[current_hour : current_hour + lookahead_hours]

        # 1. Analyze price opportunity
        avg_price = (
            sum(f["final_price_r_per_kwh"] for f in lookahead_forecasts) / len(lookahead_forecasts)
            if lookahead_forecasts
            else 1.20
        )

        # 2. Check constraints
        temp = temps[current_hour] if current_hour < len(temps) else 20.0
        can_charge = 12 <= temp <= 40
        can_discharge = 12 <= temp <= 44

        # SOC constraints
        can_charge = can_charge and current_soc_pct < 95
        can_discharge = can_discharge and current_soc_pct > 20

        # Load shedding override
        if load_shedding_stage >= 6:
            can_discharge = False  # Emergency: charge only

        # 3. Identify opportunity
        is_low_price = False
        is_high_price = False
        lowest_price = float("inf")
        highest_price = float("-inf")
        lowest_hour = current_hour
        highest_hour = current_hour

        for i, forecast in enumerate(lookahead_forecasts):
            price = forecast["final_price_r_per_kwh"]
            if price < lowest_price:
                lowest_price = price
                lowest_hour = current_hour + i
            if price > highest_price:
                highest_price = price
                highest_hour = current_hour + i

        is_low_price = lowest_price < avg_price * 0.85
        is_high_price = highest_price > avg_price * 1.15

        # 4. Decide action
        action = "idle"
        next_action_start = current_hour + 1
        duration = 1
        power = 0.0
        revenue = 0.0
        confidence = 50.0
        reasoning = "No clear arbitrage opportunity"
        recommendation = "Continue idle operation"

        if is_high_price and can_discharge:
            # Discharge during peak pricing
            action = "discharge"
            next_action_start = highest_hour
            duration = 2  # Typical 2-hour peak period
            power = 250.0 * 0.8  # 80% rated power
            spread = highest_price - lowest_price
            revenue = spread * 250.0 * 0.9 * 2  # 2 hours, 90% efficiency
            confidence = min(90.0, 70.0 + (spread / 0.5) * 10)  # Higher confidence with larger spread
            reasoning = f"Peak price ${highest_price:.2f}/kWh at hour {highest_hour}"
            recommendation = (
                f"Discharge at hour {highest_hour} for {duration}h to capture peak arbitrage (R{revenue:.0f})"
            )

        elif is_low_price and can_charge:
            # Charge during off-peak pricing
            action = "charge"
            next_action_start = lowest_hour
            duration = 3  # Typical 3-hour off-peak window
            power = 250.0 * 0.7  # 70% rated power to protect battery
            revenue = 0.0  # Charging doesn't generate revenue (cost)
            confidence = min(85.0, 60.0 + (avg_price - lowest_price) / 0.2 * 10)
            reasoning = f"Off-peak price R{lowest_price:.2f}/kWh at hour {lowest_hour}"
            recommendation = f"Charge at hour {lowest_hour} for {duration}h to prepare for peak discharge"

        elif load_shedding_stage >= 4:
            # LS response
            if load_shedding_stage >= 6 and can_charge:
                action = "charge"
                next_action_start = current_hour
                duration = 2
                power = 250.0  # Full power charging
                confidence = 95.0
                reasoning = f"Load shedding stage {load_shedding_stage}: emergency response"
                recommendation = "Charge immediately to 80% SOC to support grid during LS"
            else:
                action = "idle"
                confidence = 80.0
                reasoning = f"Load shedding stage {load_shedding_stage}: holding position"
                recommendation = "Monitor grid frequency; prepare to support if requested"

        return DispatchPrediction(
            action=action,
            confidence_pct=confidence,
            next_action_start_hour=next_action_start % 24,
            next_action_duration_hours=duration,
            expected_power_kw=power,
            expected_revenue_r=revenue,
            recommendation=recommendation,
            reasoning=reasoning,
        )

    def predict_daily_dispatch_schedule(
        self,
        price_forecasts: list[dict[str, Any]],
        temperature_forecast: list[float] | None = None,
        load_shedding_schedule: list[int] | None = None,
        building_demand_forecast: list[float] | None = None,
    ) -> list[DispatchPrediction]:
        """Predict dispatch schedule for entire day.

        Args:
            price_forecasts: 24-hour price forecasts
            temperature_forecast: 24-hour temperature forecast
            load_shedding_schedule: LS stage for each hour
            building_demand_forecast: Building demand forecast

        Returns:
            List of hourly dispatch predictions
        """
        schedule = []
        current_soc = 50.0  # Assume starting at 50% SOC

        for hour in range(24):
            ls_stage = load_shedding_schedule[hour] if load_shedding_schedule else 0
            pred = self.predict_next_action(
                current_hour=hour,
                current_soc_pct=current_soc,
                price_forecasts=price_forecasts[hour:],
                temperature_forecast=temperature_forecast,
                load_shedding_stage=ls_stage,
                building_demand_kw=building_demand_forecast,
            )
            schedule.append(pred)

            # Update SOC for next hour
            if pred.action == "charge":
                current_soc = min(95.0, current_soc + 5.0)
            elif pred.action == "discharge":
                current_soc = max(20.0, current_soc - 4.0)

        return schedule

    def evaluate_prediction_accuracy(
        self,
        predictions: list[DispatchPrediction],
        actual_actions: list[str],
    ) -> dict[str, Any]:
        """Evaluate accuracy of predictions against actual dispatch.

        Args:
            predictions: List of DispatchPrediction objects
            actual_actions: List of actual actions taken ('charge', 'discharge', 'idle')

        Returns:
            Dict with accuracy metrics
        """
        if not predictions or not actual_actions:
            return {"accuracy_pct": 0.0, "total_predictions": 0}

        correct = sum(1 for pred, actual in zip(predictions, actual_actions, strict=False) if pred.action == actual)
        accuracy = (correct / len(predictions)) * 100 if predictions else 0.0

        # Weighted accuracy (consider confidence)
        weighted_correct = sum(
            pred.confidence_pct / 100.0 for pred, actual in zip(predictions, actual_actions, strict=False) if pred.action == actual
        )
        weighted_accuracy = (weighted_correct / len(predictions)) * 100 if predictions else 0.0

        return {
            "accuracy_pct": round(accuracy, 1),
            "weighted_accuracy_pct": round(weighted_accuracy, 1),
            "total_predictions": len(predictions),
            "correct_predictions": correct,
            "avg_confidence_pct": round(sum(p.confidence_pct for p in predictions) / len(predictions), 1),
        }


# === Singleton ===

_dispatch_predictor: DispatchPredictor | None = None


def get_dispatch_predictor() -> DispatchPredictor:
    """Get singleton DispatchPredictor instance."""
    global _dispatch_predictor
    if _dispatch_predictor is None:
        _dispatch_predictor = DispatchPredictor()
    return _dispatch_predictor
