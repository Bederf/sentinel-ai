"""Predictions API endpoints - AI-driven failure predictions from Supabase."""

import json

from fastapi import APIRouter, HTTPException, Query, Request

from app.database.repositories.prediction_repository import PredictionRepository
from app.middleware.rate_limiter import limiter
from app.services.prediction_generator import get_prediction_generator
from app.services.prediction_taxonomy import (
    normalize_prediction_confidence,
    normalize_prediction_severity,
    normalize_prediction_urgency,
)

router = APIRouter()


def _parse_json_field(value, default):
    """Parse a field that might be a JSON string or already an object.

    Supabase JSONB fields can be returned as strings in some cases.
    This helper ensures we always get the parsed object.
    """
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return default
    return value


def format_prediction_for_frontend(pred: dict) -> dict:
    """Format Supabase prediction data to match frontend expectations.

    Transform Supabase data structure to match the JSON structure the frontend expects.

    Maps database severity values to frontend states:
    - critical → critical
    - warning → warning
    - healthy → healthy
    Legacy values (high/medium/low) are still mapped for backwards compatibility.
    """
    # Extract related data
    building = pred.get("building", {})
    equipment = pred.get("equipment", {})

    # Map database severity to frontend severity
    # DB values (after migration 032): critical, warning, healthy
    # Legacy DB values: critical, high, medium, low
    # Frontend expects: critical, high, warning, healthy
    db_severity = pred["severity"]
    if db_severity == "critical":
        severity = "critical"
    elif db_severity in ("warning", "high"):
        severity = "warning"
    elif db_severity in ("healthy", "low", "medium"):
        severity = "healthy"
    else:
        severity = "healthy"  # Default fallback

    # Extract financial impact
    financial_impact = {
        "repair_cost_zar": pred.get("repair_cost_zar", 0),
        "replacement_cost_zar": pred.get("replacement_cost_zar", 0),
        "downtime_cost_per_hour_zar": pred.get("downtime_cost_per_hour_zar", 0),
        "potential_loss_zar": pred.get("potential_loss_zar", 0),
    }

    # Parse evidence to extract alarms count and last reading
    evidence = _parse_json_field(pred.get("evidence"), {})

    # Extract alarm count from evidence
    alarm_count = 0
    if evidence and "alarm_frequency" in evidence:
        alarm_freq = evidence["alarm_frequency"]
        if isinstance(alarm_freq, dict):
            alarm_count = sum(alarm_freq.values())

    # Extract last reading info from evidence
    last_reading_value = None
    last_reading_parameter = None
    latest_reading_obj = None
    if evidence and "last_reading" in evidence:
        last_reading = evidence["last_reading"]
        if isinstance(last_reading, dict):
            last_reading_value = last_reading.get("value")
            last_reading_parameter = last_reading.get("parameter")
            latest_reading_obj = last_reading  # Pass object through for frontend

    return {
        "id": pred["code"],  # Use code as frontend ID
        "uuid": pred["id"],  # Keep UUID for reference
        "equipment_id": equipment.get("code", pred["equipment_id"]),
        "equipment_name": equipment.get("name", "Unknown"),
        "equipment_type": equipment.get("type", "unknown"),
        # Baseline lifecycle state drives the frontend prediction gate:
        # only rolling_active/locked equipment renders prediction cards.
        "baseline_state": equipment.get("baseline_state") or "none",
        "site_id": building.get("code", pred["site_id"]),
        "site_name": building.get("name", "Unknown"),
        # Prediction details
        "prediction_type": pred["prediction_type"],
        "probability_percent": pred["probability_percent"],
        "confidence": normalize_prediction_confidence(pred.get("confidence")) or pred.get("confidence"),
        "predicted_failure_date": pred["predicted_failure_date"],
        "timeframe_days": pred["timeframe_days"],
        "severity": severity,  # Mapped to system values
        # Evidence - parse JSON strings if needed (Supabase returns JSONB as strings)
        "evidence": evidence,
        "contributing_factors": _parse_json_field(pred.get("contributing_factors"), []),
        "similar_failures": _parse_json_field(pred.get("similar_failures"), []),
        # Financial
        "financial_impact": financial_impact,
        # Status
        "status": pred.get("status", "active"),
        "recommended_action": pred.get("recommended_action"),
        "urgency": normalize_prediction_urgency(pred.get("urgency")) or pred.get("urgency"),
        # Extracted fields for UI display
        "alarms": alarm_count if alarm_count > 0 else None,
        "last_reading": f"{last_reading_parameter}: {last_reading_value}"
        if last_reading_parameter and last_reading_value is not None
        else None,
        # Frontend expects latest_reading as object inside evidence
        "latest_reading": latest_reading_obj,  # Object form for PredictionCard
    }


@limiter.limit("120/minute")
@router.get("/predictions")
async def list_predictions(
    request: Request,
    site_code: str | None = Query(None, description="Filter by building code (e.g., site-002)"),
    equipment_type: str | None = Query(None, description="Filter by equipment type"),
    severity: str | None = Query(None, description="Filter by severity (critical/warning/healthy)"),
    min_probability: int | None = Query(None, description="Minimum probability percentage"),
    min_confidence: str | None = Query(None, description="Minimum confidence level (high/medium/low)"),
    has_last_reading: bool | None = Query(None, description="Filter to only predictions with last_reading data"),
) -> dict:
    """
    List all AI-driven failure predictions from Supabase.

    Returns predictions with building and equipment information joined.

    Query Parameters:
    - site_code: Filter by building code (e.g., site-002)
    - equipment_type: Filter by equipment type (chiller, ahu, ups, etc.)
    - severity: Filter by severity level (critical, warning, healthy)
    - min_probability: Show only predictions above this probability

    Returns:
        Dictionary with predictions list and summary statistics
    """
    repo = PredictionRepository()

    # Get predictions from Supabase with building and equipment data joined
    query = (
        repo.client.table("predictions")
        .select("""
        *,
        building:sites!inner(id, name, code),
        equipment:equipment!inner(id, code, name, type, baseline_state)
    """)
        .eq("status", "active")
    )  # Only active predictions

    # Apply filters
    if site_code:
        # First get building UUID by code
        site_result = repo.client.table("sites").select("id").eq("code", site_code).execute()
        if site_result.data:
            query = query.eq("site_id", site_result.data[0]["id"])
        else:
            # Building not found, return empty results
            return {
                "predictions": [],
                "total": 0,
                "avg_probability": 0,
                "by_severity": {"critical": 0, "warning": 0, "healthy": 0},
            }

    if severity:
        normalized_severity = normalize_prediction_severity(severity)
        if not normalized_severity:
            raise HTTPException(status_code=400, detail="Invalid severity. Use critical, warning, or healthy.")
        query = query.eq("severity", normalized_severity)

    if min_probability is not None:
        query = query.gte("probability_percent", min_probability)

    # Filter by confidence (stored as canonical strings: low/medium/high)
    if min_confidence is not None:
        confidence_order = ["low", "medium", "high"]
        if min_confidence.lower() in confidence_order:
            allowed = confidence_order[confidence_order.index(min_confidence.lower()) :]
            query = query.in_("confidence", allowed)

    # Filter to predictions that have last_reading in evidence
    if has_last_reading:
        query = query.contains("evidence", {"last_reading": {}})

    response = query.execute()
    predictions = response.data

    # Format predictions for frontend
    formatted_predictions = [format_prediction_for_frontend(p) for p in predictions]

    # Filter by equipment_type after formatting (it's in the equipment object)
    if equipment_type:
        formatted_predictions = [
            p for p in formatted_predictions if p["equipment_type"].lower() == equipment_type.lower()
        ]

    # Calculate summary statistics
    total = len(formatted_predictions)

    if total > 0:
        avg_probability = sum(p["probability_percent"] for p in formatted_predictions) / total
        total_repair = sum(p["financial_impact"]["repair_cost_zar"] for p in formatted_predictions)
        total_loss = sum(p["financial_impact"]["potential_loss_zar"] for p in formatted_predictions)
    else:
        avg_probability = 0
        total_repair = 0
        total_loss = 0

    # Count by severity (uses new schema: critical, warning, healthy)
    severity_counts = {"critical": 0, "warning": 0, "healthy": 0}
    for pred in formatted_predictions:
        sev = pred["severity"].lower()
        if sev in severity_counts:
            severity_counts[sev] += 1

    return {
        "predictions": formatted_predictions,
        "total": total,
        "avg_probability": round(avg_probability, 1),
        "total_repair_cost_zar": total_repair,
        "total_potential_loss_zar": total_loss,
        "potential_savings_zar": total_loss - total_repair,
        "by_severity": severity_counts,
    }


@router.get("/predictions/{prediction_code}")
async def get_prediction(prediction_code: str) -> dict:
    """
    Get detailed prediction by code.

    Returns complete prediction details including:
    - All evidence (work orders, alarms, technician notes)
    - Contributing factors with weights
    - Similar historical failures
    - Financial impact analysis
    - Recommended actions

    Args:
        prediction_code: Prediction code (e.g., "pred-001")

    Returns:
        Complete prediction details

    Raises:
        HTTPException 404: If prediction not found
    """
    repo = PredictionRepository()

    # Get prediction with joins
    response = (
        repo.client.table("predictions")
        .select("""
        *,
        building:sites!inner(id, name, code, address),
        equipment:equipment!inner(id, code, name, type, manufacturer, model, baseline_state)
    """)
        .eq("code", prediction_code)
        .execute()
    )

    if not response.data:
        raise HTTPException(status_code=404, detail=f"Prediction {prediction_code} not found")

    prediction = format_prediction_for_frontend(response.data[0])
    return prediction


@router.get("/predictions/{prediction_code}/lineage")
async def get_prediction_lineage(prediction_code: str) -> dict:
    """Phase 236-01 (AC-7): evidence chain behind a prediction.

    Traces prediction → equipment → active rollup baseline → source service
    record → structured readings, so an operator can answer "show me the work
    order and readings that produced this baseline". Returns a grounded flag:
    false when the equipment has no rolling baseline yet (prediction is not
    baseline-grounded — the strict tab gate withholds it), true when a real
    baseline + source record back it.

    Raises:
        HTTPException 404: If the prediction is not found.
    """
    repo = PredictionRepository()
    client = repo.client

    pred = (
        client.table("predictions")
        .select("id, code, equipment_id, equipment:equipment!inner(id, code, baseline_state)")
        .eq("code", prediction_code)
        .execute()
    )
    if not pred.data:
        raise HTTPException(status_code=404, detail=f"Prediction {prediction_code} not found")

    row = pred.data[0]
    equipment = row.get("equipment") or {}
    equipment_uuid = equipment.get("id")
    baseline_state = equipment.get("baseline_state") or "none"

    lineage: dict = {
        "prediction_code": prediction_code,
        "equipment_code": equipment.get("code"),
        "baseline_state": baseline_state,
        "grounded": baseline_state in ("rolling_active", "locked"),
        "baseline": None,
        "service_record": None,
        "readings": [],
    }

    if not equipment_uuid:
        return lineage

    baseline = (
        client.table("equipment_baselines")
        .select("id, baseline_date, baseline_type, source_record_id, baseline_values, captured_by")
        .eq("equipment_id", equipment_uuid)
        .eq("status", "active")
        .order("baseline_date", desc=True)
        .limit(1)
        .execute()
    )
    if not baseline.data:
        return lineage

    b = baseline.data[0]
    element_values = b.get("baseline_values") if isinstance(b.get("baseline_values"), dict) else {}
    lineage["baseline"] = {
        "id": b.get("id"),
        "baseline_date": b.get("baseline_date"),
        "baseline_type": b.get("baseline_type"),
        "captured_by": b.get("captured_by"),
        "elements": [
            {
                "element_id": element_id,
                "value": (v or {}).get("value"),
                "sigma": (v or {}).get("sigma"),
                "n": (v or {}).get("n"),
                "unit": (v or {}).get("unit"),
            }
            for element_id, v in element_values.items()
            if isinstance(v, dict)
        ],
    }

    source_record_id = b.get("source_record_id")
    if not source_record_id:
        return lineage

    record = (
        client.table("service_records")
        .select("id, code, work_order_id, service_type, technician_name")
        .eq("id", source_record_id)
        .limit(1)
        .execute()
    )
    if record.data:
        lineage["service_record"] = record.data[0]

    readings = (
        client.table("service_readings")
        .select("element_id, reading_type, numeric_value, value, unit, captured_at")
        .eq("service_record_id", source_record_id)
        .order("captured_at", desc=True)
        .execute()
    )
    lineage["readings"] = readings.data or []
    return lineage


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
    repo = PredictionRepository()

    # Get all active predictions
    response = repo.client.table("predictions").select("*").eq("status", "active").execute()
    predictions = response.data

    total = len(predictions)
    high_priority = sum(1 for p in predictions if p["probability_percent"] >= 80)
    critical_count = sum(1 for p in predictions if p["severity"] == "critical")

    if total > 0:
        avg_probability = sum(p["probability_percent"] for p in predictions) / total
        total_repair = sum(p.get("repair_cost_zar", 0) for p in predictions)
        total_loss = sum(p.get("potential_loss_zar", 0) for p in predictions)
    else:
        avg_probability = 0
        total_repair = 0
        total_loss = 0

    return {
        "predictions": predictions,  # Raw predictions for further processing
        "total_predictions": total,
        "high_priority_count": high_priority,
        "critical_count": critical_count,
        "avg_probability": round(avg_probability, 1),
        "total_repair_cost_zar": total_repair,
        "total_potential_damage_zar": total_loss,
        "potential_savings_zar": total_loss - total_repair,
    }


@router.post("/predictions/generate")
async def generate_predictions_manual() -> dict:
    """
    Manually trigger prediction generation for at-risk equipment.

    This endpoint scans all equipment and generates predictions for those
    with health scores below the threshold (default: 90%).

    Features:
    - Duplicate prevention: Won't create duplicate predictions for equipment
      that already has an active prediction
    - Auto-resolve: Resolves predictions for equipment that has improved
    - Minimum probability: Only creates predictions above 60% probability

    Returns:
        Dictionary with generation results including:
        - generated: Number of new predictions created
        - skipped_duplicate: Predictions skipped due to existing active prediction
        - skipped_low_probability: Predictions skipped due to low probability
        - resolved: Number of predictions auto-resolved (equipment improved)
        - errors: List of any errors encountered
    """
    generator = get_prediction_generator()
    result = await generator.generate_predictions_for_all_sites()

    return {
        "status": "success" if not result.get("errors") else "partial",
        "generated": result.get("generated", 0),
        "skipped_duplicate": result.get("skipped_duplicate", 0),
        "skipped_low_probability": result.get("skipped_low_probability", 0),
        "resolved": result.get("resolved", 0),
        "errors": result.get("errors", []),
        "timestamp": result.get("timestamp"),
    }
