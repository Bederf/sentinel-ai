from datetime import UTC, datetime, timedelta

from app.schemas.cockpit import CockpitSourceStatus
from app.services.building_posture_resolver import resolve_building_posture
from app.services.building_state_engine import build_building_state_payload
from app.services.building_state_models import NarrativeCandidate, NarrativeLocation
from app.services.cockpit_issue_fusion import CockpitIssueFusionService
from app.services.dominant_narrative_selector import select_dominant_narrative
from app.services.narrative_candidate_generator import generate_narrative_candidates


class _NoOpRepo:
    def __init__(self) -> None:
        self.client = None

    def get_active_by_site(self, site_id: str | None = None):
        return []

    def get_all(self, *args, **kwargs):
        return []


def _candidate(
    *,
    candidate_id: str,
    voice: str,
    breach: int | None,
    criticality: float,
    propagation_risk: float,
    eroding_margin: bool = False,
) -> NarrativeCandidate:
    return NarrativeCandidate(
        candidate_id=candidate_id,
        voice=voice,  # type: ignore[arg-type]
        message=f"{candidate_id} message",
        location=NarrativeLocation(epicenter="L0", affected=["L1"], propagation="upward"),
        action="Watch this.",
        time_to_constraint_breach_min=breach,
        affected_occupants_est=20,
        system_criticality=criticality,
        propagation_risk=propagation_risk,
        eroding_margin=eroding_margin,
    )


def test_resolve_building_posture_returns_calm_when_no_candidates():
    assert resolve_building_posture([]) == "calm"


def test_resolve_building_posture_marks_compensating_for_margin_erosion():
    posture = resolve_building_posture(
        [
            _candidate(
                candidate_id="comfort",
                voice="comfort_stress",
                breach=22,
                criticality=0.8,
                propagation_risk=0.5,
                eroding_margin=True,
            )
        ]
    )

    assert posture == "compensating"


def test_selector_prefers_comfort_over_energy_for_comparable_timing():
    posture = "compensating"
    primary, secondary = select_dominant_narrative(
        posture,
        [
            _candidate(
                candidate_id="energy",
                voice="energy_pressure",
                breach=18,
                criticality=0.5,
                propagation_risk=0.4,
                eroding_margin=True,
            ),
            _candidate(
                candidate_id="comfort",
                voice="comfort_stress",
                breach=18,
                criticality=0.6,
                propagation_risk=0.4,
                eroding_margin=True,
            ),
        ],
    )

    assert primary is not None
    assert primary.voice == "comfort_stress"
    assert len(secondary) == 1


def test_selector_critical_prefers_fastest_breach():
    primary, _ = select_dominant_narrative(
        "critical",
        [
            _candidate(
                candidate_id="slower-impact",
                voice="asset_stress",
                breach=12,
                criticality=0.95,
                propagation_risk=0.8,
            ),
            _candidate(
                candidate_id="fast-comfort",
                voice="comfort_stress",
                breach=7,
                criticality=0.7,
                propagation_risk=0.5,
            ),
        ],
    )

    assert primary is not None
    assert primary.candidate_id == "fast-comfort"


def test_selector_prefers_distinct_secondary_voices_before_duplicates():
    primary, secondaries = select_dominant_narrative(
        "compensating",
        [
            _candidate(
                candidate_id="comfort-primary",
                voice="comfort_stress",
                breach=16,
                criticality=0.9,
                propagation_risk=0.7,
                eroding_margin=True,
            ),
            _candidate(
                candidate_id="comfort-secondary",
                voice="comfort_stress",
                breach=18,
                criticality=0.7,
                propagation_risk=0.5,
                eroding_margin=True,
            ),
            _candidate(
                candidate_id="energy-secondary",
                voice="energy_pressure",
                breach=22,
                criticality=0.4,
                propagation_risk=0.4,
            ),
            _candidate(
                candidate_id="stability-secondary",
                voice="operational_stability",
                breach=20,
                criticality=0.6,
                propagation_risk=0.5,
                eroding_margin=True,
            ),
        ],
    )

    assert primary is not None
    assert [candidate.voice for candidate in secondaries] == ["operational_stability", "energy_pressure"]


def test_selector_never_returns_more_than_two_secondaries():
    primary, secondaries = select_dominant_narrative(
        "compensating",
        [
            _candidate(
                candidate_id="comfort-primary",
                voice="comfort_stress",
                breach=16,
                criticality=0.9,
                propagation_risk=0.7,
                eroding_margin=True,
            ),
            _candidate(
                candidate_id="stability-secondary",
                voice="operational_stability",
                breach=20,
                criticality=0.7,
                propagation_risk=0.5,
                eroding_margin=True,
            ),
            _candidate(
                candidate_id="asset-secondary",
                voice="asset_stress",
                breach=22,
                criticality=0.8,
                propagation_risk=0.4,
            ),
            _candidate(
                candidate_id="occupant-secondary",
                voice="occupant_friction",
                breach=24,
                criticality=0.6,
                propagation_risk=0.4,
            ),
            _candidate(
                candidate_id="energy-secondary",
                voice="energy_pressure",
                breach=26,
                criticality=0.5,
                propagation_risk=0.3,
            ),
        ],
    )

    assert primary is not None
    assert len(secondaries) == 2


def test_build_building_state_payload_defensively_caps_secondaries_to_two(monkeypatch):
    comfort = _candidate(
        candidate_id="comfort-primary",
        voice="comfort_stress",
        breach=16,
        criticality=0.9,
        propagation_risk=0.7,
        eroding_margin=True,
    )
    overflow_secondaries = [
        _candidate(
            candidate_id="stability-secondary",
            voice="operational_stability",
            breach=20,
            criticality=0.7,
            propagation_risk=0.5,
            eroding_margin=True,
        ),
        _candidate(
            candidate_id="asset-secondary",
            voice="asset_stress",
            breach=22,
            criticality=0.8,
            propagation_risk=0.4,
        ),
        _candidate(
            candidate_id="occupant-secondary",
            voice="occupant_friction",
            breach=24,
            criticality=0.6,
            propagation_risk=0.4,
        ),
    ]

    monkeypatch.setattr(
        "app.services.building_state_engine.generate_narrative_candidates",
        lambda site_id, issue_service=None, operating_mode=None: [comfort, *overflow_secondaries],
    )
    monkeypatch.setattr(
        "app.services.building_state_engine.resolve_site_operating_mode",
        lambda site_id: "comfort",
    )
    monkeypatch.setattr(
        "app.services.building_state_engine.resolve_building_posture",
        lambda candidates: "compensating",
    )
    monkeypatch.setattr(
        "app.services.building_state_engine.select_dominant_narrative",
        lambda posture, candidates: (comfort, overflow_secondaries),
    )

    payload = build_building_state_payload("site-123")

    assert len(payload.secondary_tensions) == 2


def test_selector_returns_max_two_secondary_tensions():
    primary, secondaries = select_dominant_narrative(
        "compensating",
        [
            _candidate(
                candidate_id="comfort-primary",
                voice="comfort_stress",
                breach=15,
                criticality=0.9,
                propagation_risk=0.7,
                eroding_margin=True,
            ),
            _candidate(
                candidate_id="stability-secondary",
                voice="operational_stability",
                breach=18,
                criticality=0.7,
                propagation_risk=0.5,
                eroding_margin=True,
            ),
            _candidate(
                candidate_id="asset-secondary",
                voice="asset_stress",
                breach=20,
                criticality=0.8,
                propagation_risk=0.4,
            ),
            _candidate(
                candidate_id="occupant-secondary",
                voice="occupant_friction",
                breach=22,
                criticality=0.5,
                propagation_risk=0.4,
            ),
        ],
    )

    assert primary is not None
    assert len(secondaries) == 2


def test_building_state_payload_defensively_caps_secondary_tensions_to_two(monkeypatch):
    monkeypatch.setattr(
        "app.services.building_state_engine.generate_narrative_candidates",
        lambda site_id, issue_service=None, operating_mode=None: [
            _candidate(
                candidate_id="comfort-primary",
                voice="comfort_stress",
                breach=15,
                criticality=0.9,
                propagation_risk=0.7,
                eroding_margin=True,
            )
        ],
    )
    monkeypatch.setattr(
        "app.services.building_state_engine.resolve_building_posture",
        lambda candidates: "compensating",
    )
    monkeypatch.setattr(
        "app.services.building_state_engine.select_dominant_narrative",
        lambda posture, candidates: (
            candidates[0],
            [
                _candidate(
                    candidate_id="secondary-1",
                    voice="operational_stability",
                    breach=18,
                    criticality=0.7,
                    propagation_risk=0.5,
                ),
                _candidate(
                    candidate_id="secondary-2",
                    voice="asset_stress",
                    breach=20,
                    criticality=0.8,
                    propagation_risk=0.4,
                ),
                _candidate(
                    candidate_id="secondary-3",
                    voice="occupant_friction",
                    breach=22,
                    criticality=0.5,
                    propagation_risk=0.4,
                ),
            ],
        ),
    )

    payload = build_building_state_payload("site-123")

    assert payload.primary_narrative is not None
    assert len(payload.secondary_tensions) == 2


def test_build_building_state_payload_returns_explicit_calm_for_unknown_site():
    class HealthyFusion:
        @staticmethod
        def aggregate(site_id):
            return (
                [],
                [
                    CockpitSourceStatus(
                        source="bms",
                        label="BMS",
                        state="healthy",
                        badge_tone="normal",
                        last_updated_at=datetime.now(UTC),
                        freshness_seconds=10,
                        stale_after_seconds=90,
                        degraded_after_seconds=45,
                        degraded_confidence=False,
                        message="Telemetry current",
                    )
                ],
                [],
                None,
            )

    payload = build_building_state_payload("site-123", issue_service=HealthyFusion())

    assert payload.building_posture == "calm"
    assert payload.primary_narrative is None
    assert payload.operator_guidance.mode == "none"


def test_build_building_state_payload_returns_primary_and_secondary_for_site_002():
    payload = build_building_state_payload("site-002")

    assert payload.building_posture == "compensating"
    assert payload.primary_narrative is not None
    assert payload.primary_narrative.voice == "comfort_stress"
    assert payload.operator_guidance.mode == "prepare"
    assert len(payload.secondary_tensions) == 2


def test_generate_narrative_candidates_uses_fused_issues_before_fallback():
    service = CockpitIssueFusionService(
        alert_repo=_NoOpRepo(),
        email_repo=_NoOpRepo(),
        work_order_repo=_NoOpRepo(),
        audit_repo=_NoOpRepo(),
    )
    timestamp = datetime.now(UTC).isoformat()

    issues = generate_narrative_candidates(
        "S002",
        issue_service=service,
    )
    assert issues[0].candidate_id == "comfort-s002-b1-upward-drift"

    generated_from_alert = generate_narrative_candidates(
        "S002",
        issue_service=type(
            "StubFusion",
            (),
            {
                "aggregate": staticmethod(
                    lambda site_id: service.aggregate(
                        site_id,
                        alert_entries=[
                            {
                                "id": "alert-live-1",
                                "site_id": "S002",
                                "equipment_id": "S002-CHILLER-B1-001",
                                "zone_id": "Zone-L2-Boardroom-A",
                                "floor_id": "L2",
                                "type": "thermal",
                                "title": "Boardroom cooling drift",
                                "summary": "Cooling drift is accelerating toward discomfort.",
                                "severity": "critical",
                                "status": "new",
                                "recommended_action": "Prepare standby cooling.",
                                "impact": "Executive zone comfort is degrading.",
                                "updated_at": timestamp,
                                "created_at": timestamp,
                            }
                        ],
                        intake_entries=[],
                        work_order_entries=[],
                    )
                )
            },
        )(),
    )

    assert generated_from_alert[0].candidate_id == "alert-live-1"
    assert generated_from_alert[0].voice == "comfort_stress"
    assert generated_from_alert[0].location.epicenter == "L2"
    assert generated_from_alert[0].time_to_constraint_breach_min is not None


def test_generate_narrative_candidates_does_not_promote_source_health_to_primary_building_narrative():
    class DegradedFusion:
        @staticmethod
        def aggregate(site_id):
            return (
                [],
                [
                    CockpitSourceStatus(
                        source="bms",
                        label="BMS",
                        state="stale",
                        badge_tone="critical",
                        last_updated_at=datetime.now(UTC),
                        freshness_seconds=200,
                        stale_after_seconds=90,
                        degraded_after_seconds=45,
                        degraded_confidence=True,
                        message="Data stale",
                    )
                ],
                [],
                None,
            )

    candidates = generate_narrative_candidates("site-123", issue_service=DegradedFusion())

    assert candidates == []


def test_build_building_state_payload_prefers_fused_issue_feed():
    timestamp = datetime.now(UTC).isoformat()
    fusion = type(
        "StubFusion",
        (),
        {
            "aggregate": staticmethod(
                lambda site_id: CockpitIssueFusionService(
                    alert_repo=_NoOpRepo(),
                    email_repo=_NoOpRepo(),
                    work_order_repo=_NoOpRepo(),
                    audit_repo=_NoOpRepo(),
                ).aggregate(
                    site_id,
                    alert_entries=[
                        {
                            "id": "alert-live-2",
                            "site_id": "S002",
                            "zone_id": "Zone-L4-Boardroom-A",
                            "floor_id": "L4",
                            "type": "thermal",
                            "title": "Boardroom thermal drift",
                            "summary": "Cooling drift is accelerating across the executive meeting space.",
                            "severity": "critical",
                            "status": "new",
                            "recommended_action": "Prepare standby cooling.",
                            "impact": "Occupied meeting space will breach comfort bounds.",
                            "updated_at": timestamp,
                            "created_at": timestamp,
                        }
                    ],
                    intake_entries=[],
                    work_order_entries=[],
                )
            )
        },
    )()

    payload = build_building_state_payload("S002", issue_service=fusion)

    assert payload.primary_narrative is not None
    assert payload.primary_narrative.message == "Occupied meeting space will breach comfort bounds."
    assert payload.primary_narrative.location.epicenter == "L4"


def test_asset_backed_issue_prefers_asset_stress_voice():
    timestamp = datetime.now(UTC)
    service = CockpitIssueFusionService(
        alert_repo=_NoOpRepo(),
        email_repo=_NoOpRepo(),
        work_order_repo=_NoOpRepo(),
        audit_repo=_NoOpRepo(),
    )

    generated = generate_narrative_candidates(
        "S002",
        issue_service=type(
            "AssetFusion",
            (),
            {
                "aggregate": staticmethod(
                    lambda site_id: service.aggregate(
                        site_id,
                        alert_entries=[
                            {
                                "id": "alert-asset-1",
                                "site_id": "S002",
                                "equipment_id": "S002-CHILLER-B1-001",
                                "floor_id": "B1",
                                "type": "fault",
                                "title": "Lead chiller fault",
                                "summary": "Compressor loading is unstable.",
                                "severity": "high",
                                "status": "new",
                                "updated_at": timestamp.isoformat(),
                                "created_at": timestamp.isoformat(),
                            }
                        ],
                        intake_entries=[],
                        work_order_entries=[],
                    )
                )
            },
        )(),
        operating_mode="asset_preservation",
    )

    assert generated[0].voice == "asset_stress"
    assert generated[0].location.epicenter == "B1"


def test_hvac_fault_biases_to_energy_pressure_in_cost_saving_mode():
    timestamp = datetime.now(UTC)
    service = CockpitIssueFusionService(
        alert_repo=_NoOpRepo(),
        email_repo=_NoOpRepo(),
        work_order_repo=_NoOpRepo(),
        audit_repo=_NoOpRepo(),
    )

    generated = generate_narrative_candidates(
        "S002",
        issue_service=type(
            "CostModeFusion",
            (),
            {
                "aggregate": staticmethod(
                    lambda site_id: service.aggregate(
                        site_id,
                        alert_entries=[
                            {
                                "id": "alert-cost-1",
                                "site_id": "S002",
                                "equipment_id": "S002-AHU-L2-001",
                                "floor_id": "L2",
                                "type": "fault",
                                "title": "AHU efficiency drift",
                                "summary": "Air handling efficiency is slipping during the current operating window.",
                                "severity": "medium",
                                "status": "new",
                                "updated_at": timestamp.isoformat(),
                                "created_at": timestamp.isoformat(),
                            }
                        ],
                        intake_entries=[],
                        work_order_entries=[],
                    )
                )
            },
        )(),
        operating_mode="cost_saving",
    )

    assert generated[0].voice == "energy_pressure"


def test_hvac_fault_biases_to_comfort_stress_in_comfort_mode():
    timestamp = datetime.now(UTC)
    service = CockpitIssueFusionService(
        alert_repo=_NoOpRepo(),
        email_repo=_NoOpRepo(),
        work_order_repo=_NoOpRepo(),
        audit_repo=_NoOpRepo(),
    )

    generated = generate_narrative_candidates(
        "S002",
        issue_service=type(
            "ComfortModeFusion",
            (),
            {
                "aggregate": staticmethod(
                    lambda site_id: service.aggregate(
                        site_id,
                        alert_entries=[
                            {
                                "id": "alert-comfort-1",
                                "site_id": "S002",
                                "equipment_id": "S002-AHU-L2-001",
                                "floor_id": "L2",
                                "type": "fault",
                                "title": "AHU performance drift",
                                "summary": "Air handling is slipping during the current operating window.",
                                "severity": "medium",
                                "status": "new",
                                "updated_at": timestamp.isoformat(),
                                "created_at": timestamp.isoformat(),
                            }
                        ],
                        intake_entries=[],
                        work_order_entries=[],
                    )
                )
            },
        )(),
        operating_mode="comfort",
    )

    assert generated[0].voice == "comfort_stress"


def test_structured_constraint_type_wins_over_text_heuristics():
    timestamp = datetime.now(UTC)
    service = CockpitIssueFusionService(
        alert_repo=_NoOpRepo(),
        email_repo=_NoOpRepo(),
        work_order_repo=_NoOpRepo(),
        audit_repo=_NoOpRepo(),
    )

    generated = generate_narrative_candidates(
        "S002",
        issue_service=type(
            "StructuredFusion",
            (),
            {
                "aggregate": staticmethod(
                    lambda site_id: service.aggregate(
                        site_id,
                        alert_entries=[
                            {
                                "id": "alert-structured-1",
                                "site_id": "S002",
                                "zone_id": "Zone-L2-Boardroom-A",
                                "floor_id": "L2",
                                "type": "occupant",
                                "title": "Meeting room discomfort report",
                                "summary": "Occupants reported friction in the boardroom.",
                                "severity": "medium",
                                "status": "new",
                                "updated_at": timestamp.isoformat(),
                                "created_at": timestamp.isoformat(),
                            }
                        ],
                        intake_entries=[],
                        work_order_entries=[],
                    )
                )
            },
        )(),
    )

    assert generated[0].voice == "occupant_friction"


def test_sla_due_at_drives_time_to_constraint_breach_when_present():
    now = datetime.now(UTC)
    service = CockpitIssueFusionService(
        alert_repo=_NoOpRepo(),
        email_repo=_NoOpRepo(),
        work_order_repo=_NoOpRepo(),
        audit_repo=_NoOpRepo(),
    )

    generated = generate_narrative_candidates(
        "S002",
        issue_service=type(
            "SlaFusion",
            (),
            {
                "aggregate": staticmethod(
                    lambda site_id: service.aggregate(
                        site_id,
                        alert_entries=[
                            {
                                "id": "alert-sla-1",
                                "site_id": "S002",
                                "zone_id": "Zone-L2-Boardroom-A",
                                "floor_id": "L2",
                                "type": "thermal",
                                "title": "Boardroom drift",
                                "summary": "Cooling drift is accelerating.",
                                "severity": "low",
                                "status": "new",
                                "sla_due_at": (now + timedelta(minutes=9)).isoformat(),
                                "updated_at": now.isoformat(),
                                "created_at": now.isoformat(),
                            }
                        ],
                        intake_entries=[],
                        work_order_entries=[],
                    )
                )
            },
        )(),
    )

    assert generated[0].time_to_constraint_breach_min is not None
    assert generated[0].time_to_constraint_breach_min <= 9


def test_build_building_state_payload_does_not_report_calm_when_sources_are_unavailable():
    class UnavailableFusion:
        @staticmethod
        def aggregate(site_id):
            return (
                [],
                [
                    CockpitSourceStatus(
                        source="bms",
                        label="BMS",
                        state="unavailable",
                        badge_tone="critical",
                        last_updated_at=None,
                        freshness_seconds=None,
                        stale_after_seconds=90,
                        degraded_after_seconds=45,
                        degraded_confidence=True,
                        message="Source unavailable",
                    )
                ],
                [],
                None,
            )

    payload = build_building_state_payload("site-123", issue_service=UnavailableFusion())

    assert payload.building_posture == "drifting"
    assert payload.primary_narrative is not None
    assert payload.primary_narrative.voice == "operational_stability"
    assert payload.operator_guidance.mode == "watch"
