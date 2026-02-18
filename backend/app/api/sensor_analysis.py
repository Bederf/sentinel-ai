"""
Sensor Data API Endpoints (Phase 41-03)

REST API for phyphox sensor data processing, baseline management, and trend analysis.

Endpoints:
- POST /api/sensor-analysis/process - Process phyphox data
- POST /api/sensor-analysis/clawd/phyphox - Webhook for Sentry bot
- GET /api/sensor-analysis/instructions/{type} - Get technician instructions
- POST /api/sensor-analysis/baseline/{equipment_id} - Capture baseline
- GET /api/sensor-analysis/baseline/{equipment_id} - Get baseline
- GET /api/sensor-analysis/trend/{equipment_id} - Get trend analysis
- POST /api/sensor-analysis/score - Calculate condition score
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, UploadFile, Form, HTTPException, Query

from app.services.sentry_integration.phyphox_handler import get_phyphox_handler
from app.services.anomaly_reporter import get_anomaly_reporter
from app.services.condition_scorer import get_condition_scorer
from app.services.baseline_comparator import get_baseline_comparator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sensor-analysis", tags=["sensor-analysis"])

# In-memory storage for demo (would use database in production)
_baselines = {}
_recordings = {}
_demo_loaded = False


def _load_demo_data():
    """Load demo baselines and recordings from JSON files on first access."""
    global _demo_loaded
    if _demo_loaded:
        return

    data_dir = Path(__file__).parent.parent / "data" / "sensor_analysis"

    # Load baselines
    baselines_file = data_dir / "demo_baselines.json"
    if baselines_file.exists():
        try:
            with open(baselines_file, "r") as f:
                baselines = json.load(f)
            for equipment_id, baseline in baselines.items():
                _baselines[equipment_id] = baseline
            logger.info(f"Loaded {len(baselines)} demo baselines")
        except Exception as e:
            logger.warning(f"Failed to load demo baselines: {e}")

    # Load recordings
    recordings_file = data_dir / "demo_recordings.json"
    if recordings_file.exists():
        try:
            with open(recordings_file, "r") as f:
                recordings = json.load(f)
            for equipment_id, recs in recordings.items():
                if equipment_id not in _recordings:
                    _recordings[equipment_id] = []
                _recordings[equipment_id].extend(recs)
            logger.info(f"Loaded demo recordings for {len(recordings)} equipment items")
        except Exception as e:
            logger.warning(f"Failed to load demo recordings: {e}")

    _demo_loaded = True


@router.post("/process")
async def process_sensor_data(
    file: UploadFile = File(...),
    equipment_id: str = Form(...),
    measurement_type: str = Form("vibration"),
    service_record_id: Optional[str] = Form(None)
):
    """
    Process phyphox screenshot or export file.

    Args:
        file: Screenshot image or CSV/JSON export
        equipment_id: Equipment UUID
        measurement_type: "vibration" or "audio"
        service_record_id: Optional link to service record

    Returns:
        Processed data with anomaly detection results
    """
    file_data = await file.read()
    handler = get_phyphox_handler()
    reporter = get_anomaly_reporter()

    result = await handler.process_phyphox_data(
        file_data=file_data,
        filename=file.filename,
        equipment_id=equipment_id,
        service_record_id=service_record_id,
        measurement_type=measurement_type
    )

    # Generate report
    result['report'] = reporter.generate_report(result, equipment_id)

    # Store recording for trend analysis
    recording_id = f"{equipment_id}-{datetime.utcnow().isoformat()}"
    result['recording_id'] = recording_id
    result['created_at'] = datetime.utcnow().isoformat()

    if equipment_id not in _recordings:
        _recordings[equipment_id] = []
    _recordings[equipment_id].append(result)

    # Compare to baseline if available
    if equipment_id in _baselines:
        comparator = get_baseline_comparator()
        comparison = comparator.compare_to_baseline(
            result, _baselines[equipment_id], measurement_type
        )
        result['baseline_comparison'] = comparison

    return result


@router.post("/clawd/phyphox")
async def clawd_phyphox_webhook(
    file: UploadFile = File(...),
    equipment_id: str = Form(...),
    chat_id: str = Form(...),
    measurement_type: str = Form("vibration"),
    service_record_id: Optional[str] = Form(None)
):
    """
    Webhook for Sentry bot to submit phyphox data.
    Returns formatted message for Telegram.
    """
    file_data = await file.read()
    handler = get_phyphox_handler()
    reporter = get_anomaly_reporter()

    result = await handler.process_phyphox_data(
        file_data=file_data,
        filename=file.filename,
        equipment_id=equipment_id,
        service_record_id=service_record_id,
        measurement_type=measurement_type
    )

    # Store recording
    result['created_at'] = datetime.utcnow().isoformat()
    if equipment_id not in _recordings:
        _recordings[equipment_id] = []
    _recordings[equipment_id].append(result)

    # Compare to baseline if available
    baseline_info = ""
    if equipment_id in _baselines:
        comparator = get_baseline_comparator()
        comparison = comparator.compare_to_baseline(
            result, _baselines[equipment_id], measurement_type
        )
        result['baseline_comparison'] = comparison

        if comparison.get('alerts'):
            baseline_info = reporter.generate_comparison_report(
                comparison, equipment_id
            )

    # Generate Telegram message
    report = reporter.generate_report(result, equipment_id)

    # Add baseline comparison if relevant
    if baseline_info:
        report += "\n\n" + baseline_info

    return {
        "success": True,
        "telegram_message": report,
        "anomalies": result.get('anomalies', {}),
        "requires_followup": result.get('anomalies', {}).get('severity') in ('medium', 'high'),
        "chat_id": chat_id
    }


@router.get("/instructions/{measurement_type}")
async def get_technician_instructions(
    measurement_type: str,
    equipment_type: Optional[str] = Query(None, description="Equipment type for specific guidance")
):
    """Get phyphox instructions for technicians."""
    handler = get_phyphox_handler()
    return {
        "instructions": handler.get_technician_instructions(measurement_type, equipment_type)
    }


@router.post("/baseline/{equipment_id}")
async def capture_baseline(
    equipment_id: str,
    file: UploadFile = File(...),
    measurement_type: str = Form("vibration"),
    condition: str = Form("good"),
    technician: Optional[str] = Form(None),
    notes: Optional[str] = Form(None)
):
    """
    Capture baseline reading for equipment (during onboarding/condition inspection).
    This becomes the reference for all future comparisons.
    """
    file_data = await file.read()
    handler = get_phyphox_handler()
    reporter = get_anomaly_reporter()

    # Process the phyphox data
    result = await handler.process_phyphox_data(
        file_data=file_data,
        filename=file.filename,
        equipment_id=equipment_id,
        measurement_type=measurement_type
    )

    # Build baseline record
    baseline = {
        'equipment_id': equipment_id,
        'captured_at': datetime.utcnow().isoformat(),
        'captured_by': technician,
        'condition_at_capture': condition,
        'notes': notes,
        'vibration_rms_ms2': result.get('rms_total_ms2') or result.get('rms_value'),
        'vibration_peak_frequencies_hz': result.get('peak_frequencies_hz'),
        'dominant_frequency_hz': result.get('dominant_frequency_hz'),
        'audio_noise_floor_db': result.get('overall_level_db'),
        'full_data': result,
        'is_active': True
    }

    # Store baseline (in-memory for demo)
    _baselines[equipment_id] = baseline

    # Generate report
    report = reporter.generate_baseline_report(result, equipment_id, condition)

    return {
        "success": True,
        "message": f"Baseline captured for equipment {equipment_id}",
        "baseline": baseline,
        "report": report,
        "next_steps": "Future readings will be compared against this baseline"
    }


@router.get("/baseline/{equipment_id}")
async def get_baseline(equipment_id: str):
    """Get current baseline for equipment."""
    _load_demo_data()  # Ensure demo data is loaded
    if equipment_id in _baselines:
        return {
            "equipment_id": equipment_id,
            "baseline": _baselines[equipment_id],
            "has_baseline": True
        }

    return {
        "equipment_id": equipment_id,
        "baseline": None,
        "has_baseline": False,
        "message": "No baseline captured yet"
    }


@router.delete("/baseline/{equipment_id}")
async def delete_baseline(equipment_id: str):
    """Delete baseline for equipment (e.g., before recapturing)."""
    if equipment_id in _baselines:
        del _baselines[equipment_id]
        return {"success": True, "message": f"Baseline deleted for {equipment_id}"}

    return {"success": False, "message": "No baseline found"}


@router.get("/trend/{equipment_id}")
async def get_equipment_trend(
    equipment_id: str,
    limit: int = Query(10, description="Number of recent readings to analyze")
):
    _load_demo_data()  # Ensure demo data is loaded
    """Get trend analysis for equipment based on historical readings."""
    if equipment_id not in _recordings or len(_recordings[equipment_id]) < 2:
        return {
            "equipment_id": equipment_id,
            "trend": "insufficient_data",
            "message": "Need 2+ readings for trend analysis",
            "readings_count": len(_recordings.get(equipment_id, []))
        }

    comparator = get_baseline_comparator()
    recordings = _recordings[equipment_id][-limit:]

    # Get baseline if available
    baseline = _baselines.get(equipment_id, {})

    trend = comparator.generate_trend_report(equipment_id, recordings, baseline)

    return {
        "equipment_id": equipment_id,
        **trend
    }


@router.post("/score")
async def calculate_condition_score(
    equipment_id: str = Form(...),
    asset_class: str = Form("generator"),
    equipment_profile: str = Form("generator_default"),
    file: Optional[UploadFile] = File(None),
    use_latest: bool = Form(True)
):
    """
    Calculate condition score for equipment.

    Either provide a new file to analyze, or use the latest recording (use_latest=True).
    """
    scorer = get_condition_scorer()
    handler = get_phyphox_handler()

    # Get reading data
    if file:
        file_data = await file.read()
        reading = await handler.process_phyphox_data(
            file_data=file_data,
            filename=file.filename,
            equipment_id=equipment_id,
            measurement_type="vibration"
        )
    elif use_latest and equipment_id in _recordings and _recordings[equipment_id]:
        reading = _recordings[equipment_id][-1]
    else:
        raise HTTPException(status_code=400, detail="No reading data available")

    # Get baseline if available
    baseline = _baselines.get(equipment_id)

    # Calculate score
    result = scorer.calculate_score(
        reading=reading,
        baseline=baseline,
        equipment_profile=equipment_profile,
        asset_class=asset_class
    )

    # Add Telegram-formatted output
    result['telegram_message'] = scorer.format_for_telegram(result, equipment_id)

    return result


@router.get("/recordings/{equipment_id}")
async def get_recordings(
    equipment_id: str,
    limit: int = Query(20, description="Maximum number of recordings to return")
):
    """Get historical recordings for equipment."""
    _load_demo_data()  # Ensure demo data is loaded
    recordings = _recordings.get(equipment_id, [])

    return {
        "equipment_id": equipment_id,
        "total_count": len(recordings),
        "recordings": recordings[-limit:]
    }


@router.get("/health")
async def health_check():
    """Health check endpoint for sensor analysis service."""
    _load_demo_data()  # Ensure demo data is loaded
    return {
        "status": "healthy",
        "baselines_count": len(_baselines),
        "recordings_count": sum(len(r) for r in _recordings.values()),
        "equipment_with_data": list(_recordings.keys())
    }
