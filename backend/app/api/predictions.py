"""Predictions API endpoints - AI-driven failure predictions."""

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

# Load data directory
DATA_DIR = Path(__file__).parent.parent / "data"


def load_predictions() -> list[dict]:
    """Load predictions from JSON file."""
    predictions_file = DATA_DIR / "predictions.json"
    if predictions_file.exists():
        with open(predictions_file) as f:
            return json.load(f)
    return []


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


class PredictionResponse:
    """Prediction response model (using dict for simplicity)."""


@router.get("/predictions")
async def list_predictions(
    site_id: Optional[str] = Query(None, description="Filter by site ID"),
    equipment_type: Optional[str] = Query(None, description="Filter by equipment type"),
    severity: Optional[str] = Query(None, description="Filter by severity (critical/high/medium)"),
    min_probability: Optional[int] = Query(None, description="Minimum probability percentage"),
) -> dict:
    """
    List all AI-driven failure predictions.

    Returns predictions based on historical FM data:
    - CAFM work orders (repeat calls, fault codes)
    - BCC alarm logs (frequency, severity, patterns)
    - Asset register (age, condition, expected life)
    - Technician notes (observations, recommendations)

    Query Parameters:
    - site_id: Filter predictions for specific site
    - equipment_type: Filter by equipment type (chiller, ahu, ups, etc.)
    - severity: Filter by severity level (critical, high, medium)
    - min_probability: Show only predictions above this probability

    Returns:
        Dictionary with predictions list and summary statistics
    """
    predictions = load_predictions()

    # Apply filters
    if site_id:
        predictions = [p for p in predictions if p["site_id"] == site_id]

    if equipment_type:
        predictions = [p for p in predictions if p["equipment_type"] == equipment_type]

    if severity:
        predictions = [p for p in predictions if p["severity"].lower() == severity.lower()]

    if min_probability is not None:
        predictions = [p for p in predictions if p["probability_percent"] >= min_probability]

    # Calculate summary statistics
    total_predictions = len(predictions)

    if total_predictions > 0:
        avg_probability = sum(p["probability_percent"] for p in predictions) / total_predictions
        total_repair_cost = sum(p["financial_impact"]["repair_cost_zar"] for p in predictions)
        total_potential_loss = sum(p["financial_impact"]["potential_loss_zar"] for p in predictions)
        potential_savings = total_potential_loss - total_repair_cost
    else:
        avg_probability = 0
        total_repair_cost = 0
        total_potential_loss = 0
        potential_savings = 0

    # Count by severity
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for pred in predictions:
        sev = pred["severity"].lower()
        if sev in severity_counts:
            severity_counts[sev] += 1

    # Count by equipment type
    type_counts: dict[str, int] = {}
    for pred in predictions:
        eq_type = pred["equipment_type"]
        type_counts[eq_type] = type_counts.get(eq_type, 0) + 1

    return {
        "total": total_predictions,
        "avg_probability": round(avg_probability, 1),
        "total_repair_cost_zar": total_repair_cost,
        "total_potential_loss_zar": total_potential_loss,
        "potential_savings_zar": potential_savings,
        "by_severity": severity_counts,
        "by_equipment_type": type_counts,
        "predictions": predictions,
    }


@router.get("/predictions/{prediction_id}")
async def get_prediction(prediction_id: str) -> dict:
    """
    Get detailed prediction by ID.

    Returns complete prediction details including:
    - All evidence (work orders, alarms, technician notes)
    - Contributing factors with weights
    - Similar historical failures
    - Financial impact analysis
    - Recommended actions

    Args:
        prediction_id: Prediction ID (e.g., "pred-001")

    Returns:
        Complete prediction details

    Raises:
        HTTPException 404: If prediction not found
    """
    predictions = load_predictions()

    prediction = next((p for p in predictions if p["id"] == prediction_id), None)

    if not prediction:
        raise HTTPException(status_code=404, detail=f"Prediction {prediction_id} not found")

    return prediction


@router.get("/predictions/summary/overview")
async def get_predictions_summary() -> dict:
    """
    Get predictions overview summary for dashboard.

    Returns aggregated statistics:
    - Total predictions
    - Average probability
    - High-priority predictions (>80% probability)
    - Total potential savings

    Use this for dashboard KPI cards.
    """
    predictions = load_predictions()

    total = len(predictions)
    high_priority = sum(1 for p in predictions if p["probability_percent"] >= 80)
    critical_count = sum(1 for p in predictions if p["severity"] == "critical")

    if total > 0:
        avg_probability = sum(p["probability_percent"] for p in predictions) / total
        total_repair = sum(p["financial_impact"]["repair_cost_zar"] for p in predictions)
        total_damage = sum(p["financial_impact"]["potential_loss_zar"] for p in predictions)
    else:
        avg_probability = 0
        total_repair = 0
        total_damage = 0

    return {
        "total_predictions": total,
        "high_priority_count": high_priority,
        "critical_count": critical_count,
        "avg_probability": round(avg_probability, 1),
        "total_repair_cost_zar": total_repair,
        "total_potential_damage_zar": total_damage,
        "potential_savings_zar": total_damage - total_repair,
    }
