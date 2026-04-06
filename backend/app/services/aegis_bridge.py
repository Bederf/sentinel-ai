"""AEGIS Bridge — Wire BESS dispatch through the PARASITE governance pipeline.

Converts solar_arbitrage_engine dispatch actions into Recommendation objects
that flow through the existing quality gate -> tier routing -> approval ->
COV -> audit pipeline.

Phase 0: Writes are permanently blocked (aegis_bess_writer_enabled=False).
All dispatch actions land in Tier 2 approval queue with write_status="blocked".

Phase 1 (future): Set aegis_bess_writer_enabled=True, implement Modbus writer.
"""

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.config.settings import settings
from app.database.repositories.parasite_decision_repository import (
    get_parasite_decision_repository,
)
from app.database.repositories.recommendation_repository import RecommendationRepository
from app.models.recommendation import (
    ActionRiskLevel,
    Recommendation,
    RecommendationStatus,
)
from app.services.bess_dispatch_engine import BESSState, get_bess_dispatch_engine
from app.services.decision_event_logger import emit_decision_event
from app.services.solar_arbitrage_engine import (
    DispatchAction,
    DispatchActionType,
    get_solar_arbitrage_engine,
)
from app.services.tier_routing_engine import TierRoutingEngine

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------


def _score_confidence(
    dispatch_command,
    context: dict | None = None,
) -> float:
    """Score confidence for BESS dispatch. Returns value in [0.70, 0.79].

    Base: 0.80 (deterministic given inputs)
    Deductions: -0.02 per warning constraint, -0.05 if LS active, -0.03 if no forecast
    Floor: 0.70 (always Tier 2 minimum)
    Cap: 0.79 (never reaches Tier 3 threshold 0.85; HIGH risk blocks it anyway)
    """
    score = 0.80

    # Deduct for constraint warnings
    warnings = sum(1 for c in dispatch_command.constraints_applied if c.severity == "warning")
    score -= warnings * 0.02

    # Deduct for load shedding active
    if context and context.get("ls_stage", 0) > 0:
        score -= 0.05

    # Deduct if no forecast data
    if not context or not context.get("forecast_available", True):
        score -= 0.03

    return max(0.70, min(0.79, score))


# ---------------------------------------------------------------------------
# Savings estimation
# ---------------------------------------------------------------------------


def _estimate_savings(dispatch_action: DispatchAction) -> float:
    """Estimate cost savings in ZAR for a dispatch action."""
    if dispatch_action.action in (
        DispatchActionType.DISCHARGE.value,
        "discharge",
    ):
        # Discharge during peak: save the peak rate on displaced grid kWh
        kwh = dispatch_action.power_kw * (5 / 60)  # 5-minute cycle
        return round(kwh * dispatch_action.rate_per_kwh, 2)
    if dispatch_action.action in (
        DispatchActionType.CHARGE.value,
        "charge",
    ):
        # Charging at off-peak: "savings" is negative (cost), but the value
        # is recouped during discharge.  Report 0 for the charge leg.
        return 0.0
    return 0.0


def _estimate_demand_shaving(
    dispatch_action: DispatchAction,
    bess_state: BESSState,
) -> float:
    """Estimate demand shaving in kW."""
    if dispatch_action.action in (
        DispatchActionType.DISCHARGE.value,
        "discharge",
    ):
        return dispatch_action.power_kw
    return 0.0


# ---------------------------------------------------------------------------
# Recommendation builder
# ---------------------------------------------------------------------------


async def create_dispatch_recommendation(
    site_id: str,
    dispatch_action: DispatchAction,
    dispatch_command,
    bess_state: BESSState,
    context: dict | None = None,
) -> Recommendation:
    """Convert a validated dispatch command into a Recommendation for the pipeline."""

    confidence_score = _score_confidence(dispatch_command, context)

    action_payload = {
        "point": "dispatch_command",
        "value": {
            "action": dispatch_action.action,
            "power_kw": dispatch_command.actual_power_kw,
            "requested_power_kw": dispatch_command.requested_power_kw,
            "target_soc_pct": dispatch_action.target_soc_pct,
            "duration_minutes": dispatch_command.duration_minutes,
            "tariff_band": dispatch_action.tariff_band,
            "rate_per_kwh": dispatch_action.rate_per_kwh,
        },
        "original_value": {
            "soc_pct": bess_state.soc_pct,
            "power_kw": bess_state.power_kw,
            "temperature_c": bess_state.temperature_c,
            "grid_frequency_hz": bess_state.grid_frequency_hz,
        },
    }

    expected_impact = {
        "cost_saving_zar": _estimate_savings(dispatch_action),
        "kwh_shifted": round(
            dispatch_command.actual_power_kw * (dispatch_command.duration_minutes / 60),
            2,
        ),
        "generator_runtime_avoided_min": (context.get("gen_avoided_min", 0) if context else 0),
        "demand_shaving_kw": _estimate_demand_shaving(dispatch_action, bess_state),
    }

    rec = Recommendation(
        id=str(uuid.uuid4()),
        site_id=site_id,
        target_equipment="S002-BESS-B1-001",
        action_type="bess_dispatch",
        risk_level=ActionRiskLevel.HIGH,
        confidence="medium",
        confidence_score=confidence_score,
        requires_approval=True,
        status=RecommendationStatus.PENDING,
        correlation_id=str(uuid.uuid4()),
        reason=dispatch_action.reason,
        profile="cost_saving",
        action=action_payload,
        expected_impact=expected_impact,
    )

    return rec


# ---------------------------------------------------------------------------
# Contributing factors for parasite_decisions
# ---------------------------------------------------------------------------


def _build_contributing_factors(
    dispatch_action: DispatchAction,
    dispatch_command,
    bess_state: BESSState,
    recommendation: Recommendation,
    context: dict | None = None,
) -> dict[str, Any]:
    """Build contributing_factors dict for parasite_decisions record.

    Includes structured audit fields required for Phase 1 compliance review:
    - writer_enabled_at_decision: snapshot of writer setting at decision time
    - execution_mode: "blocked" | "shadow" | "live"
    - block_reason_code: structured code (not free text)
    - proposal_source: always "aegis" for BESS dispatch
    - proposal_id: stable join key to dispatch history JSONL
    - dispatch_window_start/end: ISO timestamps for the dispatch window
    - expected_delta_kw / target_soc_pct: expected equipment state change
    - quality_gate_status/reason: gate evaluation outcome
    """
    writer_enabled = getattr(settings, "aegis_bess_writer_enabled", False)

    # Determine execution mode from writer setting
    if writer_enabled:
        execution_mode = "live"
        block_reason_code = None
    else:
        execution_mode = "blocked"
        block_reason_code = "AEGIS_WRITE_BLOCKED"

    # Dispatch window: from now for duration_minutes
    now = datetime.now(UTC)
    dispatch_window_start = now.isoformat()
    dispatch_window_end = (now + timedelta(minutes=dispatch_command.duration_minutes)).isoformat()

    # Expected delta: difference between target and current
    expected_delta_kw = dispatch_command.actual_power_kw
    if dispatch_action.action in (DispatchActionType.DISCHARGE.value, "discharge"):
        expected_delta_kw = -expected_delta_kw  # Discharge reduces grid import

    constraints_evaluated = [c.to_dict() for c in dispatch_command.constraints_applied]
    # Derive warning/block counts from the same serialized constraint payload we store.
    # This avoids drift between counters and details in audit records.
    severities = [str(c.get("severity", "")).strip().lower() for c in constraints_evaluated]
    constraint_warnings = sum(1 for sev in severities if sev in {"warning", "warn"})
    constraint_blocks = sum(1 for sev in severities if sev in {"block", "blocked"})

    routing_gate_status = str(getattr(recommendation, "quality_gate_status", "") or "unknown").lower()

    command_fingerprint = {
        "point": "dispatch_command",
        "action": dispatch_action.action,
        "power_kw": dispatch_command.actual_power_kw,
        "requested_power_kw": dispatch_command.requested_power_kw,
        "target_soc_pct": dispatch_action.target_soc_pct,
        "duration_minutes": dispatch_command.duration_minutes,
        "tariff_band": dispatch_action.tariff_band,
    }
    command_hash = hashlib.sha256(
        json.dumps(command_fingerprint, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]

    return {
        # --- Domain context (original) ---
        "tariff_band": dispatch_action.tariff_band,
        "tariff_rate": dispatch_action.rate_per_kwh,
        "forecast_cloudy": context.get("forecast_cloudy") if context else None,
        "load_shedding_stage": context.get("ls_stage", 0) if context else 0,
        "demand_ratchet_kva": context.get("demand_ratchet_kva") if context else None,
        "bess_soc_pct": bess_state.soc_pct,
        "bess_temp_c": bess_state.temperature_c,
        "constraints_evaluated": constraints_evaluated,
        "constraint_warnings": constraint_warnings,
        "constraint_blocks": constraint_blocks,
        # --- Structured audit fields ---
        "created_by": "aegis",
        "approval_outcome": "pending",
        "dispatch_action_type": dispatch_action.action,
        "writer_enabled_at_decision": writer_enabled,
        "execution_mode": execution_mode,
        "block_reason_code": block_reason_code,
        "proposal_source": "aegis",
        "proposal_id": recommendation.correlation_id,
        "dispatch_window_start": dispatch_window_start,
        "dispatch_window_end": dispatch_window_end,
        "expected_delta_kw": round(expected_delta_kw, 2),
        "target_soc_pct": dispatch_action.target_soc_pct,
        "command_hash": command_hash,
        "quality_gate_status": routing_gate_status,
        "quality_gate_status_at_routing": routing_gate_status,
        "quality_gate_status_final": "pending",
        "quality_gate_reason": None,
        "quality_gate_reason_at_routing": None,
        "quality_gate_reason_final": None,
    }


# ---------------------------------------------------------------------------
# Tripwire alerts
# ---------------------------------------------------------------------------


def _check_tripwire_gate_fail(
    rec_dict: dict[str, Any],
    routing_result,
    site_id: str,
) -> None:
    """Emit an event if the quality gate evaluated to 'fail'.

    Silent on pass/unknown/pending — only fires on explicit failure.
    """
    cf = rec_dict.get("contributing_factors") or {}
    gate_status = str(cf.get("quality_gate_status", "")).lower()
    if gate_status == "fail":
        logger.warning(
            "AEGIS tripwire: quality gate FAIL for %s (decision %s)",
            site_id,
            routing_result.decision_id if routing_result else "unknown",
        )
        emit_decision_event(
            "aegis.tripwire.gate_fail",
            correlation_id=rec_dict.get("correlation_id", ""),
            decision_id=getattr(routing_result, "decision_id", ""),
            site_id=site_id,
            status="triggered",
            details={
                "quality_gate_status": gate_status,
                "command_hash": cf.get("command_hash"),
            },
        )


async def _check_tripwire_repeated_hash(
    rec_dict: dict[str, Any],
    routing_result,
    site_id: str,
) -> None:
    """Emit an event if the same command_hash appears >= 3 times in 1h unapproved.

    Detects the optimizer proposing the same blocked dispatch repeatedly,
    which may indicate a stuck arbitrage loop.
    """
    cf = rec_dict.get("contributing_factors") or {}
    command_hash = cf.get("command_hash")
    if not command_hash:
        return

    repo = get_parasite_decision_repository()
    one_hour_ago = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    recent = await repo.get_decisions_since(one_hour_ago)

    # Count decisions with the same command_hash that were NOT approved
    same_hash_unapproved = sum(
        1
        for d in recent
        if (d.get("contributing_factors") or {}).get("command_hash") == command_hash
        and (d.get("contributing_factors") or {}).get("approval_outcome", d.get("approval_outcome")) != "approved"
    )

    if same_hash_unapproved >= 3:
        logger.warning(
            "AEGIS tripwire: repeated hash %s (%d unapproved in 1h) for %s",
            command_hash,
            same_hash_unapproved,
            site_id,
        )
        emit_decision_event(
            "aegis.tripwire.repeated_hash",
            correlation_id=rec_dict.get("correlation_id", ""),
            decision_id=getattr(routing_result, "decision_id", ""),
            site_id=site_id,
            status="triggered",
            details={
                "command_hash": command_hash,
                "unapproved_count": same_hash_unapproved,
                "window": "1h",
            },
        )


# ---------------------------------------------------------------------------
# Main cycle
# ---------------------------------------------------------------------------


async def run_aegis_cycle(
    site_id: str,
    context: dict | None = None,
) -> dict | None:
    """Run one AEGIS dispatch cycle: arbitrage -> validate -> route -> persist.

    Called by solar_dispatch_service or scheduler.

    Returns:
        Recommendation dict if a proposal was created, None if idle.
    """
    try:
        # 1. Get current BESS state from simulated state
        from app.services.solar_dispatch_service import get_solar_dispatch_service

        dispatch_svc = get_solar_dispatch_service()
        current_soc = dispatch_svc._simulated_soc.get(site_id, 50.0)

        bess_state = BESSState(
            soc_pct=current_soc,
            temperature_c=25.0,  # Simulated ambient
            power_kw=0.0,
            grid_frequency_hz=50.0,
        )

        # 2. Get dispatch action from arbitrage engine
        engine = get_solar_arbitrage_engine()
        now = datetime.now(UTC)

        dispatch_action = engine.get_realtime_dispatch_action(
            site_id=site_id,
            current_soc_pct=bess_state.soc_pct,
            solar_gen_kw=0.0,  # Will be enriched by caller context
            site_load_kw=1800.0,
            load_shedding_active=bool(context and context.get("ls_stage", 0) > 0),
            timestamp=now,
        )

        # 3. If idle, log advisory and return None
        if dispatch_action.action in (
            DispatchActionType.IDLE.value,
            "idle",
        ):
            logger.debug("AEGIS cycle: idle action for %s, no proposal", site_id)
            return None

        # 4. Validate through BESS dispatch engine (constraints)
        bess_engine = get_bess_dispatch_engine()
        dispatch_command = bess_engine.execute_dispatch(
            site_id=site_id,
            action=dispatch_action.action,
            requested_power_kw=dispatch_action.power_kw,
            bess_state=bess_state,
            duration_minutes=5,
            reason=dispatch_action.reason,
            load_shedding_stage=context.get("ls_stage", 0) if context else 0,
        )

        # If constraint blocked the dispatch entirely
        if not dispatch_command.success:
            logger.info(
                "AEGIS cycle: dispatch blocked by constraints for %s: %s",
                site_id,
                dispatch_command.error_message,
            )
            return None

        # 5. Create recommendation
        rec = await create_dispatch_recommendation(
            site_id=site_id,
            dispatch_action=dispatch_action,
            dispatch_command=dispatch_command,
            bess_state=bess_state,
            context=context,
        )

        # 6. Persist recommendation
        rec_repo = RecommendationRepository()
        await rec_repo.upsert(rec)

        # 7. Route through tier routing engine
        router = TierRoutingEngine()
        rec_dict = rec.to_dict()
        rec_dict["contributing_factors"] = _build_contributing_factors(
            dispatch_action, dispatch_command, bess_state, rec, context
        )
        routing_result = await router.route_recommendation(rec_dict)

        logger.info(
            "AEGIS cycle: %s -> tier=%s action=%s confidence=%.2f for %s",
            dispatch_action.action,
            routing_result.tier,
            routing_result.action,
            routing_result.confidence_score,
            site_id,
        )

        # 8. Return recommendation dict for API
        result = rec.to_dict()
        result["routing"] = {
            "tier": routing_result.tier,
            "action": routing_result.action,
            "decision_id": routing_result.decision_id,
            "confidence_score": routing_result.confidence_score,
        }
        # Stable join key: links JSONL dispatch events to parasite_decisions
        result["aegis_proposal_id"] = rec.correlation_id

        # 9. Tripwire checks
        _check_tripwire_gate_fail(rec_dict, routing_result, site_id)
        await _check_tripwire_repeated_hash(rec_dict, routing_result, site_id)

        return result

    except Exception as e:
        logger.error("AEGIS cycle failed for %s: %s", site_id, e, exc_info=True)
        return None
