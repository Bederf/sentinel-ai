"""Deterministic dominant narrative selection for the cockpit."""

from __future__ import annotations

from app.services.building_state_models import BuildingPosture, NarrativeCandidate, Voice

VOICE_PRIORITY: dict[Voice, int] = {
    "comfort_stress": 5,
    "operational_stability": 4,
    "asset_stress": 3,
    "occupant_friction": 2,
    "energy_pressure": 1,
}


def _is_eligible(candidate: NarrativeCandidate) -> bool:
    return (
        not candidate.resolved
        and candidate.spatially_grounded
        and (
            candidate.time_to_constraint_breach_min is not None
            or candidate.eroding_margin
        )
    )


def _compute_scope_impact(candidate: NarrativeCandidate) -> float:
    zone_count = len({candidate.location.epicenter, *candidate.location.affected})
    normalized_zone_count = min(zone_count / 4, 1.0)
    normalized_occupants = min((candidate.affected_occupants_est or 0) / 50, 1.0)
    return (
        normalized_zone_count * 0.30
        + normalized_occupants * 0.25
        + candidate.system_criticality * 0.25
        + candidate.propagation_risk * 0.20
    )


def _time_term(candidate: NarrativeCandidate) -> float:
    if candidate.time_to_constraint_breach_min is None:
        return 0.0
    return 1 / max(candidate.time_to_constraint_breach_min, 1)


def _posture_weighted_score(posture: BuildingPosture, candidate: NarrativeCandidate) -> float:
    impact_term = _compute_scope_impact(candidate)
    time_term = _time_term(candidate)
    voice_term = VOICE_PRIORITY[candidate.voice] * 0.01

    if posture == "critical":
        return time_term * 10 + impact_term + voice_term
    if posture == "strained":
        return impact_term * 2.5 + time_term * 4 + voice_term
    if posture == "compensating":
        margin_bonus = 0.5 if candidate.eroding_margin else 0.0
        return margin_bonus + impact_term * 1.5 + time_term * 3 + voice_term
    if posture == "drifting":
        return time_term * 5 + impact_term + voice_term
    return voice_term


def select_dominant_narrative(
    posture: BuildingPosture,
    candidates: list[NarrativeCandidate],
) -> tuple[NarrativeCandidate | None, list[NarrativeCandidate]]:
    eligible = [candidate for candidate in candidates if _is_eligible(candidate)]
    if posture == "calm" or not eligible:
        return None, []

    ranked = sorted(
        eligible,
        key=lambda candidate: (
            _posture_weighted_score(posture, candidate),
            _compute_scope_impact(candidate),
            VOICE_PRIORITY[candidate.voice],
        ),
        reverse=True,
    )

    primary = ranked[0]
    secondaries: list[NarrativeCandidate] = []
    seen_secondary_voices: set[Voice] = {primary.voice}
    deferred_same_voice: list[NarrativeCandidate] = []

    for candidate in ranked[1:]:
        if candidate.candidate_id == primary.candidate_id:
            continue
        if candidate.message == primary.message:
            continue
        if candidate.voice in seen_secondary_voices:
            deferred_same_voice.append(candidate)
            continue
        secondaries.append(candidate)
        seen_secondary_voices.add(candidate.voice)
        if len(secondaries) == 2:
            break

    if len(secondaries) < 2:
        for candidate in deferred_same_voice:
            secondaries.append(candidate)
            if len(secondaries) == 2:
                break

    return primary, secondaries
