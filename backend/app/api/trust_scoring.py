"""API endpoints for dynamic trust scoring and validation.

Phase 162: Semantic Control Foundation — Plan 04.
Provides trust profile queries, manual validation triggers, and
equipment-level trust summaries.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.trust_history import TrustProfile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/trust-scoring", tags=["trust_scoring"])

# Module-level singleton (lazy-initialised to avoid import-time I/O)
_trust_service = None


def _get_trust_service():
    global _trust_service
    if _trust_service is None:
        from app.services.simbiot.trust_scoring_service import TrustScoringService

        _trust_service = TrustScoringService()
    return _trust_service


# ------------------------------------------------------------------
# Request / response models
# ------------------------------------------------------------------


class TrustProfileResponse(BaseModel):
    """Response containing the three-layer trust profile for a point."""

    point_id: str
    trust_profile: TrustProfile
    recommendation: str


class ValidationRequest(BaseModel):
    """Request to manually trigger a validation run for a point."""

    site_id: str
    validation_passed: bool


class ValidationResponse(BaseModel):
    """Result of a manual validation trigger."""

    point_id: str
    site_id: str
    validation_passed: bool
    message: str


class EquipmentTrustSummary(BaseModel):
    """Aggregated trust metrics for all classified points on a piece of equipment."""

    equipment_id: str
    site_id: str
    point_count: int
    average_trust_score: float
    average_data_quality: float
    automation_tier_distribution: dict  # {"observe_only": n, "supervised": n, "automatic": n}
    risk_distribution: dict  # {"LOW": n, "MEDIUM": n, "HIGH": n}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _recommendation_for(profile: TrustProfile) -> str:
    """Generate a one-line human-readable recommendation from a trust profile."""
    if profile.automation_tier == "observe_only":
        return "Safety-critical point — monitor only; no autonomous control permitted."
    if profile.automation_tier == "supervised":
        return (
            f"Trust score {profile.overall_trust_score:.2f} — supervised control "
            "requires operator approval before execution."
        )
    return f"Trust score {profile.overall_trust_score:.2f} — automatic control permitted within defined envelope."


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.get("/profile/{point_id}", response_model=TrustProfileResponse)
async def get_trust_profile(point_id: str, site_id: str) -> TrustProfileResponse:
    """Get the three-layer trust profile for a classified point.

    Layers:
    - Classification confidence (40 %)
    - Data quality score (30 %)
    - Control trust history (30 %)
    """
    from app.database.repositories.trust_history_repository import (
        TrustHistoryRepository,
    )
    from app.models.trust_history import TrustHistory

    repo = TrustHistoryRepository()
    history = await repo.get_trust_history(point_id, site_id)

    if history is None:
        # Return a default profile for points with no history yet
        history = TrustHistory(point_id=point_id, site_id=site_id)

    # Build a minimal synthetic trust profile from history alone
    # (full profile requires a PointClassification — see trust scoring service)
    overall_trust = TrustHistory.calculate_trust_score(
        history.stability_days,
        history.validation_runs,
        history.successful_actions,
        history.failed_actions,
    )

    profile = TrustProfile(
        point_id=point_id,
        classification_confidence=0.0,  # Requires classifier context
        evidence_count=0,
        required_evidence_met=False,
        data_quality_score=0.0,  # Requires live data quality context
        stability_days=history.stability_days,
        control_trust_score=history.trust_score,
        validation_runs=history.validation_runs,
        successful_actions=history.successful_actions,
        failed_actions=history.failed_actions,
        overall_trust_score=overall_trust,
        risk_level="MEDIUM" if overall_trust < 0.6 else "LOW",
        automation_tier="supervised" if overall_trust < 0.6 else "automatic",
    )

    return TrustProfileResponse(
        point_id=point_id,
        trust_profile=profile,
        recommendation=_recommendation_for(profile),
    )


@router.post("/profile/{point_id}/validate", response_model=ValidationResponse)
async def run_validation(point_id: str, body: ValidationRequest) -> ValidationResponse:
    """Manually trigger a validation run and update the trust score.

    This endpoint is called by the static validation engine after each
    validation pass to keep the trust history current.
    """
    service = _get_trust_service()
    await service.update_trust_after_validation(point_id, body.site_id, body.validation_passed)

    status_word = "passed" if body.validation_passed else "failed"
    return ValidationResponse(
        point_id=point_id,
        site_id=body.site_id,
        validation_passed=body.validation_passed,
        message=f"Validation {status_word}; trust history updated.",
    )


@router.get(
    "/equipment/{equipment_id}/trust-summary",
    response_model=EquipmentTrustSummary,
)
async def get_equipment_trust_summary(equipment_id: str, site_id: str) -> EquipmentTrustSummary:
    """Get aggregated trust metrics for all classified points on a piece of equipment.

    Useful for dashboards that need a single readiness score per equipment unit.
    """
    from app.database.repositories.trust_history_repository import (
        DATA_DIR,
        TrustHistoryRepository,
    )
    from app.models.trust_history import TrustHistory
    import json

    repo = TrustHistoryRepository()
    profiles: list[TrustHistory] = []

    # Load all records and filter by site (equipment prefix match)
    if not repo._use_json and repo.client is not None:
        try:
            result = (
                repo.client.table("trust_history")
                .select("*")
                .eq("site_id", site_id)
                .like("point_id", f"{equipment_id}%")
                .execute()
            )
            profiles = [TrustHistory(**row) for row in (result.data or [])]
        except Exception as exc:
            logger.warning("Supabase query failed: %s", exc)

    if not profiles and DATA_DIR.exists():
        for path in DATA_DIR.glob(f"{site_id}__{equipment_id}*.json"):
            try:
                with path.open() as fh:
                    profiles.append(TrustHistory(**json.load(fh)))
            except Exception:
                pass

    if not profiles:
        raise HTTPException(
            status_code=404,
            detail=f"No trust history found for equipment {equipment_id} at site {site_id}",
        )

    tier_dist: dict[str, int] = {"observe_only": 0, "supervised": 0, "automatic": 0}
    risk_dist: dict[str, int] = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    total_trust = 0.0
    total_quality = 0.0

    for hist in profiles:
        # Approximate tier using control trust only (no classifier context here)
        tier = "supervised" if hist.trust_score < 0.6 else "automatic"
        tier_dist[tier] = tier_dist.get(tier, 0) + 1
        risk = "LOW" if hist.trust_score >= 0.6 else "MEDIUM"
        risk_dist[risk] = risk_dist.get(risk, 0) + 1
        total_trust += hist.trust_score

    return EquipmentTrustSummary(
        equipment_id=equipment_id,
        site_id=site_id,
        point_count=len(profiles),
        average_trust_score=total_trust / len(profiles),
        average_data_quality=total_quality / len(profiles) if profiles else 0.0,
        automation_tier_distribution=tier_dist,
        risk_distribution=risk_dist,
    )
