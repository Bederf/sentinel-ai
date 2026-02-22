"""Prediction Calculator Service - Calculates failure predictions from historical data."""

from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict

from app.services.csv_loader import WorkOrderData, AssetData, AlarmData
from app.services.health_threshold_service import get_health_thresholds
from app.services.prediction_taxonomy import (
    FORMULA_VERSION_STATIC,
    confidence_from_probability,
    severity_from_probability,
    urgency_from_severity,
)
from pathlib import Path
import json

# Load data directory
DATA_DIR = Path(__file__).parent.parent / "data"


def load_sites() -> list[dict]:
    """Load sites from JSON file."""
    sites_file = DATA_DIR / "sites.json"
    if sites_file.exists():
        with open(sites_file) as f:
            return json.load(f)
    return []


def load_equipment() -> list[dict]:
    """Load equipment from JSON file."""
    equipment_file = DATA_DIR / "equipment.json"
    if equipment_file.exists():
        with open(equipment_file) as f:
            return json.load(f)
    return []


class PredictionCalculator:
    """Calculate failure predictions from work orders, alarms, and asset data."""

    # Keywords in technician notes that indicate failure risk
    RISK_KEYWORDS = [
        "recommend replacement",
        "urgent",
        "will fail",
        "end of life",
        "same pattern as",
        "critical",
        "failing",
        "deteriorating",
        "worn",
        "replacement needed",
        "schedule replacement",
    ]

    # Prediction type mappings based on fault codes and equipment type
    PREDICTION_TYPES = {
        "compressor": "compressor_failure",
        "bearing": "bearing_failure",
        "motor": "motor_failure",
        "refrigerant": "refrigerant_leak_failure",
        "starting": "starting_failure",
        "controller": "controller_failure",
        "vibration": "vibration_failure",
        "oil": "oil_system_failure",
    }

    @staticmethod
    def calculate_predictions(min_probability: int = 60) -> List[Dict[str, Any]]:
        """
        Calculate failure predictions from equipment health scores and historical data.

        Uses existing health scores from equipment.json which are calculated using:
        - Operational Performance: 35%
        - Maintenance History: 25%
        - Asset Age & Lifecycle: 20%
        - Anomaly Indicators: 20%

        Args:
            min_probability: Minimum probability threshold (default: 60%)

        Returns:
            List of prediction dictionaries
        """
        predictions = []

        # Load all data
        work_orders = WorkOrderData.load()
        assets = AssetData.load()
        alarms = AlarmData.load()
        equipment = load_equipment()
        sites = load_sites()

        # Create lookups
        site_lookup = {s["id"]: s for s in sites}
        asset_lookup = {a["asset_id"]: a for a in assets}

        # Group work orders by asset_id (from work orders) and equipment_id
        wo_by_asset: Dict[str, List[Dict]] = defaultdict(list)
        wo_by_equipment: Dict[str, List[Dict]] = defaultdict(list)
        for wo in work_orders:
            asset_id = wo.get("asset_id", "")
            if asset_id:
                wo_by_asset[asset_id].append(wo)
            # Also try to match by equipment name/site (case-insensitive)
            site_id = wo.get("site_id", "").upper()  # Normalize to uppercase
            asset_tag = wo.get("asset_tag", "")
            for eq in equipment:
                eq_site_id = eq.get("site_id", "").upper()  # Normalize to uppercase
                if eq_site_id == site_id:
                    eq_name = eq.get("name", "").upper()
                    if eq_name in asset_tag.upper() or asset_tag.upper() in eq_name:
                        wo_by_equipment[eq["id"]].append(wo)

        # Group alarms by asset_id and equipment_id
        alarms_by_asset: Dict[str, List[Dict]] = defaultdict(list)
        alarms_by_equipment: Dict[str, List[Dict]] = defaultdict(list)
        for alarm in alarms:
            asset_id = alarm.get("asset_id", "")
            if asset_id:
                alarms_by_asset[asset_id].append(alarm)
            # Also try to match by equipment name/site (case-insensitive)
            site_id = alarm.get("site_id", "").upper()  # Normalize to uppercase
            asset_tag = alarm.get("asset_tag", "")
            for eq in equipment:
                eq_site_id = eq.get("site_id", "").upper()  # Normalize to uppercase
                if eq_site_id == site_id:
                    eq_name = eq.get("name", "").upper()
                    if eq_name in asset_tag.upper() or asset_tag.upper() in eq_name:
                        alarms_by_equipment[eq["id"]].append(alarm)

        # Analyze each equipment item (use health score as base)
        thresholds = get_health_thresholds()

        for eq in equipment:
            health_score = eq.get("health_score", 100)

            # Skip equipment with good health (above configured healthy threshold)
            # Only generate predictions for equipment with health below healthy threshold
            if health_score >= thresholds["healthy"]:
                continue

            # Get site info
            site_id = eq.get("site_id", "")
            site = site_lookup.get(site_id, {})
            site_name = site.get("name", eq.get("site_name", "Unknown"))

            # Find matching asset if possible (case-insensitive site matching)
            asset = None
            eq_site_id_normalized = site_id.upper()
            for a in assets:
                asset_site_id = a.get("site_id", "").upper()
                if asset_site_id == eq_site_id_normalized:
                    asset_tag = a.get("asset_tag", "").upper()
                    eq_name = eq.get("name", "").upper()
                    if eq_name in asset_tag or asset_tag in eq_name:
                        asset = a
                        break

            # Get work orders and alarms for this equipment
            asset_wo = wo_by_equipment.get(eq["id"], [])
            asset_alarms = alarms_by_equipment.get(eq["id"], [])

            # Calculate prediction based on health score
            prediction = PredictionCalculator._calculate_prediction_from_health(
                equipment=eq,
                asset=asset,
                work_orders=asset_wo,
                alarms=asset_alarms,
                site=site,
                site_name=site_name,
            )

            if prediction and prediction.get("probability_percent", 0) >= min_probability:
                predictions.append(prediction)

        # Sort by probability (highest first)
        predictions.sort(key=lambda p: p.get("probability_percent", 0), reverse=True)

        return predictions

    @staticmethod
    def _calculate_prediction_from_health(
        equipment: Dict[str, Any],
        asset: Optional[Dict[str, Any]],
        work_orders: List[Dict[str, Any]],
        alarms: List[Dict[str, Any]],
        site: Dict[str, Any],
        site_name: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate prediction from equipment health score.

        Health score is already calculated using:
        - Operational Performance: 35%
        - Maintenance History: 25%
        - Asset Age & Lifecycle: 20%
        - Anomaly Indicators: 20%

        We use inverse health score as base probability, then adjust based on work orders/alarms.
        """
        thresholds = get_health_thresholds()
        health_score = equipment.get("health_score", 100)

        # Base probability calculation - more aggressive for degraded equipment
        # Health score thresholds from configured settings:
        # - healthy-100%: Healthy (no prediction)
        # - warning to healthy-1%: Degraded (should generate predictions with 50%+ probability)
        # - critical to warning-1%: Critical (60%+ probability)

        if health_score >= thresholds["healthy"]:
            return None  # Healthy equipment

        # For degraded equipment, use a more aggressive probability scale
        # This ensures all degraded equipment generates actionable predictions
        if health_score < thresholds["critical"]:
            # Critical equipment: 60-75% base probability
            base_probability = 75 - (health_score * 0.3)  # Scale from 60-75%
        elif health_score < thresholds["warning"]:
            # Severely degraded: 55-65% base probability
            base_probability = 65 - ((health_score - thresholds["critical"]) * 0.5)
        else:
            # Moderately degraded: 50-55% base probability
            base_probability = 55 - ((health_score - thresholds["warning"]) * 0.5)

        # Ensure minimum 50% for any degraded equipment
        base_probability = max(50, base_probability)

        # Get site info
        site_id = equipment.get("site_id", "")

        # Calculate repeat work orders in last 6 months
        six_months_ago = datetime.now() - timedelta(days=180)
        recent_wo = [wo for wo in work_orders if wo.get("reported_date") and wo["reported_date"] >= six_months_ago]

        repeat_wo_count = sum(1 for wo in recent_wo if wo.get("repeat_call"))

        # Group by fault code to find patterns
        fault_code_counts: Dict[str, int] = defaultdict(int)
        for wo in recent_wo:
            fault_code = wo.get("fault_code", "")
            if fault_code:
                fault_code_counts[fault_code] += 1

        # Find most common fault code
        most_common_fault = max(fault_code_counts.items(), key=lambda x: x[1]) if fault_code_counts else None

        # Analyze technician notes for risk keywords
        risk_notes = []
        for wo in recent_wo:
            notes = wo.get("technician_notes", "").lower()
            if notes:
                for keyword in PredictionCalculator.RISK_KEYWORDS:
                    if keyword.lower() in notes:
                        risk_notes.append(wo.get("technician_notes", ""))
                        break

        # Calculate alarm frequency
        recent_alarms = [a for a in alarms if a.get("triggered_at") and a.get("triggered_at") >= six_months_ago]
        alarm_frequency: Dict[str, int] = defaultdict(int)
        for alarm in recent_alarms:
            code = alarm.get("alarm_code", "")
            if code:
                alarm_frequency[code] += 1

        # Adjust probability based on additional risk factors
        # Repeat work orders increase probability
        if repeat_wo_count >= 3:
            base_probability += 15
        elif repeat_wo_count >= 2:
            base_probability += 10
        elif repeat_wo_count >= 1:
            base_probability += 5

        # Risk notes increase probability
        if len(risk_notes) >= 2:
            base_probability += 10
        elif len(risk_notes) >= 1:
            base_probability += 5

        # Recent alarms increase probability
        if len(recent_alarms) >= 10:
            base_probability += 10
        elif len(recent_alarms) >= 5:
            base_probability += 5

        # Cap at 95% max
        probability = min(95, base_probability)

        # Determine confidence and severity from shared taxonomy
        confidence = confidence_from_probability(
            probability,
            high_threshold=85,
            medium_threshold=70,
        )
        severity = severity_from_probability(probability)

        # Calculate predicted failure date (based on probability and health score)
        # Lower health score = sooner failure
        # Uses configured thresholds for determining timeframe
        if health_score < thresholds["critical"]:
            timeframe_days = 14  # 2 weeks
        elif health_score < thresholds["warning"]:
            timeframe_days = 30  # 1 month
        elif health_score < thresholds["healthy"]:
            timeframe_days = 60  # 2 months
        else:
            timeframe_days = 90  # 3 months

        predicted_date = datetime.now() + timedelta(days=timeframe_days)

        # Determine prediction type from fault codes and equipment type
        eq_type = equipment.get("type", "").lower()
        prediction_type = "general_failure"

        if most_common_fault:
            fault_code = most_common_fault[0].lower()
            for key, pred_type in PredictionCalculator.PREDICTION_TYPES.items():
                if key in fault_code or key in eq_type:
                    prediction_type = pred_type
                    break

        # Build contributing factors
        contributing_factors = []
        contributing_factors.append(
            {
                "factor": "Equipment Health Score",
                "weight": 0.40,
                "description": f"Health score of {health_score}% indicates degraded condition",
            }
        )
        if repeat_wo_count > 0:
            contributing_factors.append(
                {
                    "factor": "Repeat fault calls",
                    "weight": 0.25,
                    "description": f"{repeat_wo_count} work orders in 6 months{' for same fault code' if most_common_fault else ''}",
                }
            )
        if risk_notes:
            contributing_factors.append(
                {
                    "factor": "Technician observations",
                    "weight": 0.20,
                    "description": f"Risk indicators documented in {len(risk_notes)} service visit(s)",
                }
            )
        # Calculate age from asset or equipment install_date
        age_years = 0
        expected_life = 20  # Default expected life

        if asset and asset.get("age_years", 0) > 0:
            age_years = asset.get("age_years", 0)
            expected_life = asset.get("expected_life_years", 20)
        elif equipment.get("install_date"):
            # Calculate age from equipment install_date
            try:
                install_date = datetime.strptime(equipment["install_date"], "%Y-%m-%d")
                age_years = (datetime.now() - install_date).days // 365
                # Set expected life based on equipment type
                expected_life_by_type = {
                    "chiller": 20,
                    "ahu": 20,
                    "fcu": 15,
                    "split": 12,
                    "split_unit": 12,
                    "generator": 25,
                    "ups": 10,
                    "vav": 15,
                    "transformer": 30,
                    "fire_panel": 15,
                }
                for key, life in expected_life_by_type.items():
                    if key in eq_type.lower():
                        expected_life = life
                        break
            except (ValueError, TypeError):
                pass

        age_factor = age_years / expected_life if expected_life > 0 else 0
        if age_years > 0 and age_factor > 0.5:
            contributing_factors.append(
                {
                    "factor": "Asset age",
                    "weight": 0.15,
                    "description": f"{age_years} years old, {int((age_factor * 100))}% through expected life ({expected_life} years)",
                }
            )

        # Estimate financial impact
        repair_cost = 25000
        replacement_cost = 100000

        # Scale based on equipment type and criticality
        if "chiller" in eq_type or "generator" in eq_type:
            repair_cost *= 2
            replacement_cost *= 3
        elif "ahu" in eq_type:
            repair_cost *= 1.5
            replacement_cost *= 2

        downtime_hours = 8 if probability >= 85 else 4
        downtime_cost_per_hour = 5000 if (asset and asset.get("criticality") == "critical") else 2000
        potential_loss = repair_cost + (downtime_hours * downtime_cost_per_hour)

        # Generate parts required based on equipment type
        parts_required = PredictionCalculator._get_parts_for_equipment_type(eq_type, prediction_type)

        # Generate cost impact breakdown
        cost_impact = PredictionCalculator._generate_cost_impact(repair_cost, potential_loss, eq_type, downtime_hours)

        # Generate prediction ID
        eq_id_num = equipment.get("id", "").replace("eqp-", "").zfill(3)
        pred_id = f"pred-{eq_id_num}"

        return {
            "id": pred_id,
            "equipment_id": equipment.get("id", ""),
            "site_id": site_id,
            "site_name": site_name,
            "equipment_name": equipment.get("name", "Unknown"),
            "equipment_type": eq_type,
            "prediction_type": prediction_type,
            "probability_percent": int(probability),
            "confidence": confidence,
            "predicted_failure_date": predicted_date.strftime("%Y-%m-%d"),
            "timeframe_days": timeframe_days,
            "severity": severity,
            "evidence": {
                "repeat_work_orders": repeat_wo_count,
                "repeat_period_months": 6,
                "alarm_frequency": dict(alarm_frequency),
                "asset_age_years": age_years,
                "expected_life_years": expected_life,
                "technician_notes": risk_notes[:5]
                if risk_notes
                else PredictionCalculator._generate_synthetic_notes(health_score, age_years, expected_life, eq_type),
                "health_score": health_score,
                "latest_reading": {
                    "parameter": "health_score",
                    "value": health_score,
                    "baseline": thresholds["healthy"],
                    "threshold": thresholds["warning"],
                    "trend": "decreasing" if health_score < thresholds["healthy"] else "stable",
                },
                "formula_version": FORMULA_VERSION_STATIC,
            },
            "contributing_factors": contributing_factors,
            "similar_failures": [],
            "financial_impact": {
                "repair_cost_zar": repair_cost,
                "replacement_cost_zar": replacement_cost,
                "downtime_cost_per_hour_zar": downtime_cost_per_hour,
                "estimated_repair_hours": downtime_hours,
                "potential_loss_zar": potential_loss,
            },
            "recommended_action": f"Schedule preventive maintenance within {timeframe_days} days to prevent failure",
            "parts_required": parts_required,
            "cost_impact": cost_impact,
            "urgency": urgency_from_severity(severity),
            "formula_version": FORMULA_VERSION_STATIC,
        }

    @staticmethod
    def _get_parts_for_equipment_type(eq_type: str, prediction_type: str) -> List[Dict[str, Any]]:
        """
        Get typical parts required for equipment type and prediction type.

        Returns realistic parts list based on common failure modes.
        """
        parts_catalog = {
            "chiller": [
                {
                    "part_number": "CP-2234",
                    "name": "Compressor Assembly",
                    "quantity": 1,
                    "cost_zar": 85000,
                    "lead_time_days": 14,
                },
                {
                    "part_number": "RV-1122",
                    "name": "Refrigerant Valve Kit",
                    "quantity": 2,
                    "cost_zar": 4500,
                    "lead_time_days": 5,
                },
                {
                    "part_number": "SF-3345",
                    "name": "Shaft Seal Set",
                    "quantity": 1,
                    "cost_zar": 2800,
                    "lead_time_days": 3,
                },
                {
                    "part_number": "OC-5567",
                    "name": "Oil Charge (15L)",
                    "quantity": 1,
                    "cost_zar": 3200,
                    "lead_time_days": 2,
                },
            ],
            "ahu": [
                {
                    "part_number": "BM-4456",
                    "name": "Belt Motor Assembly",
                    "quantity": 1,
                    "cost_zar": 12000,
                    "lead_time_days": 7,
                },
                {"part_number": "VB-2233", "name": "V-Belt Set", "quantity": 2, "cost_zar": 850, "lead_time_days": 2},
                {"part_number": "BR-7789", "name": "Bearing Kit", "quantity": 4, "cost_zar": 1200, "lead_time_days": 3},
                {
                    "part_number": "FT-3344",
                    "name": "Filter Set (MERV-13)",
                    "quantity": 6,
                    "cost_zar": 450,
                    "lead_time_days": 1,
                },
            ],
            "fcu": [
                {"part_number": "FM-1123", "name": "Fan Motor", "quantity": 1, "cost_zar": 4500, "lead_time_days": 5},
                {
                    "part_number": "CV-2234",
                    "name": "Control Valve",
                    "quantity": 1,
                    "cost_zar": 2800,
                    "lead_time_days": 4,
                },
                {
                    "part_number": "CT-3345",
                    "name": "Condensate Tray",
                    "quantity": 1,
                    "cost_zar": 650,
                    "lead_time_days": 2,
                },
            ],
            "split": [
                {
                    "part_number": "CP-5567",
                    "name": "Compressor Unit",
                    "quantity": 1,
                    "cost_zar": 18000,
                    "lead_time_days": 10,
                },
                {
                    "part_number": "CF-6678",
                    "name": "Condenser Fan Motor",
                    "quantity": 1,
                    "cost_zar": 3500,
                    "lead_time_days": 5,
                },
                {
                    "part_number": "EV-7789",
                    "name": "Expansion Valve",
                    "quantity": 1,
                    "cost_zar": 2200,
                    "lead_time_days": 4,
                },
                {
                    "part_number": "RC-8890",
                    "name": "Refrigerant Charge (R410A)",
                    "quantity": 1,
                    "cost_zar": 1800,
                    "lead_time_days": 2,
                },
            ],
            "generator": [
                {
                    "part_number": "FP-1234",
                    "name": "Fuel Pump Assembly",
                    "quantity": 1,
                    "cost_zar": 15000,
                    "lead_time_days": 14,
                },
                {
                    "part_number": "SR-2345",
                    "name": "Starter Relay",
                    "quantity": 1,
                    "cost_zar": 2500,
                    "lead_time_days": 5,
                },
                {"part_number": "BT-3456", "name": "Battery Set", "quantity": 2, "cost_zar": 4500, "lead_time_days": 3},
                {
                    "part_number": "FK-4567",
                    "name": "Filter Kit (Oil/Fuel/Air)",
                    "quantity": 1,
                    "cost_zar": 1200,
                    "lead_time_days": 2,
                },
            ],
            "vav": [
                {
                    "part_number": "DA-1122",
                    "name": "Damper Actuator",
                    "quantity": 1,
                    "cost_zar": 3500,
                    "lead_time_days": 5,
                },
                {
                    "part_number": "PS-2233",
                    "name": "Pressure Sensor",
                    "quantity": 1,
                    "cost_zar": 1800,
                    "lead_time_days": 3,
                },
                {
                    "part_number": "CT-3344",
                    "name": "Controller Board",
                    "quantity": 1,
                    "cost_zar": 4200,
                    "lead_time_days": 7,
                },
            ],
        }

        # Find matching parts based on equipment type
        for key in parts_catalog:
            if key in eq_type.lower():
                return parts_catalog[key]

        # Default generic parts if no match
        return [
            {"part_number": "GN-0001", "name": "Service Kit", "quantity": 1, "cost_zar": 2500, "lead_time_days": 5},
            {"part_number": "GN-0002", "name": "Consumables Pack", "quantity": 1, "cost_zar": 800, "lead_time_days": 2},
        ]

    @staticmethod
    def _generate_cost_impact(
        repair_cost: float, potential_loss: float, eq_type: str, downtime_hours: int
    ) -> Dict[str, Any]:
        """
        Generate detailed cost impact breakdown for preventive vs reactive maintenance.

        Shows financial justification for proactive maintenance.
        """
        # Calculate preventive maintenance costs (typically 30-40% of emergency repair)
        preventive_labor = repair_cost * 0.25
        preventive_parts = repair_cost * 0.15
        preventive_total = preventive_labor + preventive_parts

        # Calculate failure scenario costs
        emergency_premium = 1.5  # 50% premium for emergency callout
        failure_repair = repair_cost * emergency_premium
        failure_downtime = potential_loss - repair_cost  # Downtime component
        failure_total = failure_repair + failure_downtime

        # Calculate potential savings
        savings = failure_total - preventive_total
        savings_percent = (savings / failure_total * 100) if failure_total > 0 else 0

        return {
            "preventive_breakdown": {
                "labor_cost_zar": int(preventive_labor),
                "parts_cost_zar": int(preventive_parts),
                "downtime_hours": max(1, downtime_hours // 4),  # Scheduled maintenance is faster
                "total_zar": int(preventive_total),
            },
            "failure_breakdown": {
                "emergency_repair_zar": int(failure_repair),
                "downtime_loss_zar": int(failure_downtime),
                "downtime_hours": downtime_hours,
                "total_zar": int(failure_total),
            },
            "potential_savings_zar": int(savings),
            "savings_percent": round(savings_percent, 1),
            "roi_message": f"Preventive maintenance saves R{int(savings):,} ({round(savings_percent)}% reduction)",
        }

    @staticmethod
    def _generate_synthetic_notes(health_score: int, age_years: int, expected_life: int, eq_type: str) -> List[str]:
        """
        Generate synthetic technician observations based on equipment condition.

        When no actual work order notes exist, generates realistic observations
        based on health score, age, and equipment type.
        """
        thresholds = get_health_thresholds()
        notes = []
        age_factor = age_years / expected_life if expected_life > 0 else 0

        # Health-based observations (using configured thresholds)
        if health_score < thresholds["critical"]:
            notes.append(
                f"Equipment showing significant degradation. Health score at {health_score}% - recommend urgent attention."
            )
            notes.append(
                "Multiple performance indicators below acceptable thresholds. Schedule comprehensive inspection."
            )
        elif health_score < thresholds["warning"]:
            notes.append(
                f"Health score declined to {health_score}%. Preventive maintenance recommended within 30 days."
            )
            notes.append("Monitoring shows gradual performance decline. Review maintenance schedule.")
        elif health_score < thresholds["healthy"]:
            notes.append(f"Health score at {health_score}%. Normal wear patterns observed - continue monitoring.")

        # Age-based observations
        if age_factor > 1.0:
            notes.append(
                f"Unit is {age_years - expected_life} years beyond expected service life. Replacement planning recommended."
            )
        elif age_factor > 0.8:
            notes.append(
                f"Asset is {int(age_factor * 100)}% through expected life cycle. Begin CAPEX planning for replacement."
            )
        elif age_factor > 0.6:
            notes.append(f"Unit age at {age_years} years - approaching end of optimal service period.")

        # Equipment-type specific observations
        type_observations = {
            "chiller": [
                "Compressor showing increased run times for equivalent cooling load.",
                "Oil analysis indicates early signs of wear particles.",
            ],
            "ahu": [
                "Belt tension checked - minor wear observed on drive system.",
                "Bearing temperature trending slightly elevated.",
            ],
            "fcu": [
                "Coil efficiency below optimal - consider cleaning schedule.",
                "Fan motor current draw slightly elevated.",
            ],
            "split": [
                "Refrigerant pressure readings slightly off baseline.",
                "Condenser coil requires cleaning for optimal heat rejection.",
            ],
            "generator": [
                "Fuel system inspection shows normal wear.",
                "Battery bank voltage holding but approaching replacement window.",
            ],
            "ups": [
                "Battery impedance increasing - monitor for replacement timing.",
                "Inverter efficiency within acceptable parameters.",
            ],
        }

        for key, obs in type_observations.items():
            if key in eq_type.lower():
                if health_score < thresholds["warning"]:
                    notes.extend(obs)
                else:
                    notes.append(obs[0])
                break

        # If no notes generated, add generic observation
        if not notes:
            notes.append(f"Equipment health at {health_score}%. Routine monitoring in progress.")

        return notes[:5]  # Limit to 5 notes
