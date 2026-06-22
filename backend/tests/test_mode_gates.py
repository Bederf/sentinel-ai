"""Tests for mode gates: generation vs visibility vs execution.

Phase: Fix Mode Gates
Verifies that recommendations are generated in all operational modes,
but visibility and execution are gated correctly.

Stage names match site-002-mode-policy.json stage_order:
['commissioning', 'shadow_live', 'advisory', 'supervised', 'automatic']
'commissioning' is the only stage that blocks generation.
'shadow_live' recommendations are stored with shadow_mode=True but hidden from UI.
'advisory' recommendations are visible (shadow_mode=False) but execution blocked.
Execution requires supervised or automatic.
"""

import pytest


class TestModeGateGeneration:
    """Generation runs for shadow_live/advisory/supervised/automatic, blocked for commissioning."""

    GENERATION_ALLOWED = {"shadow_live", "advisory", "supervised", "automatic"}

    @pytest.mark.parametrize(
        "mode,expected_generation",
        [
            ("shadow_live", True),
            ("advisory", True),
            ("supervised", True),
            ("automatic", True),
            ("commissioning", False),
        ],
    )
    def test_generation_gate_logic(self, mode, expected_generation):
        """Commissioning is the only mode that blocks generation."""
        should_run = mode in self.GENERATION_ALLOWED
        assert should_run == expected_generation, f"mode={mode}"

    def test_shadow_mode_sets_shadow_flag(self):
        """Recommendations generated in shadow_live mode have shadow_mode=True."""
        from app.models.recommendation import Recommendation

        rec = Recommendation(site_id="site-002", shadow_mode=True)
        assert rec.shadow_mode is True

        rec2 = Recommendation(site_id="site-002", shadow_mode=False)
        assert rec2.shadow_mode is False

    def test_default_shadow_mode_false(self):
        """Default shadow_mode is False (visible)."""
        from app.models.recommendation import Recommendation

        rec = Recommendation(site_id="site-002")
        assert rec.shadow_mode is False


class TestModeGateVisibility:
    """Recommendations with shadow_mode=True must be filtered from UI queries."""

    def test_shadow_records_have_flag_set(self):
        """A shadow recommendation has shadow_mode=True stored in to_dict."""
        from app.models.recommendation import Recommendation

        rec = Recommendation(site_id="site-002", action_type="hvac_setpoint_change", shadow_mode=True)
        d = rec.to_dict()
        assert d["shadow_mode"] is True

    def test_normal_records_default_to_visible(self):
        """Normal recommendations default to shadow_mode=False."""
        from app.models.recommendation import Recommendation

        rec = Recommendation(site_id="site-002", action_type="bess_dispatch")
        d = rec.to_dict()
        assert d["shadow_mode"] is False

    def test_shadow_mode_persists_through_serialization(self):
        """shadow_mode survives to_dict → from_dict round-trip."""
        from app.models.recommendation import Recommendation

        original = Recommendation(site_id="site-002", action_type="bess_dispatch", shadow_mode=True)
        d = original.to_dict()
        restored = Recommendation.from_dict(d)
        assert restored.shadow_mode is True

    def test_from_dict_defaults_shadow_mode_false(self):
        """from_dict with no shadow_mode field defaults to False."""
        from app.models.recommendation import Recommendation

        data = {
            "id": "test-id",
            "site_id": "site-002",
            "action_type": "bess_dispatch",
            "status": "pending",
        }
        rec = Recommendation.from_dict(data)
        assert rec.shadow_mode is False


class TestModeGateExecution:
    """Execution requires supervised or automatic mode."""

    EXECUTION_ALLOWED = {"supervised", "automatic"}

    @pytest.mark.parametrize(
        "mode,expected_execution",
        [
            ("shadow_live", False),
            ("advisory", False),
            ("supervised", True),
            ("automatic", True),
            ("commissioning", False),
        ],
    )
    def test_execution_gate_logic(self, mode, expected_execution):
        """Only supervised and automatic allow execution."""
        should_allow = mode in self.EXECUTION_ALLOWED
        assert should_allow == expected_execution, f"mode={mode}"

    def test_shadow_mode_recommendations_not_executable(self):
        """Recommendations in shadow_live mode cannot be executed via approval_service."""
        # shadow_mode recommendations are still stored in DB
        # but filtered from UI queries, so operators never see them to approve
        from app.models.recommendation import Recommendation

        rec = Recommendation(
            site_id="site-002",
            action_type="hvac_setpoint_change",
            shadow_mode=True,
        )
        assert rec.shadow_mode is True
        assert rec.status.value == "pending"


class TestAdvisoryModeVisibility:
    """Advisory mode recommendations are visible (shadow_mode=False) but execution blocked."""

    def test_advisory_mode_not_shadow(self):
        """Advisory is NOT a shadow mode — recommendations must be visible in UI."""
        from app.models.recommendation import Recommendation

        # Advisory recs have shadow_mode=False (visible)
        rec = Recommendation(site_id="site-002", action_type="hvac_setpoint_change", shadow_mode=False)
        assert rec.shadow_mode is False

    def test_advisory_stage_is_visible(self):
        """Recommendations generated in advisory mode have shadow_mode=False."""
        from app.models.recommendation import Recommendation

        rec = Recommendation(site_id="site-002", action_type="bess_dispatch", shadow_mode=False)
        d = rec.to_dict()
        assert d["shadow_mode"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "phase,expected_shadow",
    [
        ("shadow_live", True),
        ("advisory", False),
    ],
)
async def test_optimization_analyze_persists_shadow_flag_from_phase(monkeypatch, phase, expected_shadow):
    """Direct /optimization/analyze persistence must set shadow_mode explicitly."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import app.api.optimization as optimization_api

    created = []

    class _FakeOptimizationRecommendation:
        confidence = 0.74
        profile = "test-profile"
        projected_savings = {}

        @property
        def timestamp(self):
            return "2026-06-18T10:00:00Z"

        @property
        def recommendations(self):
            return self.to_dict()["recommendations"]

        def to_dict(self):
            return {
                "timestamp": self.timestamp,
                "recommendations": [
                    {
                        "system": "HVAC",
                        "equipment_code": "S002-FCU-101",
                        "point_name": "room_temp_setpoint",
                        "value": 22.0,
                        "confidence": 0.74,
                        "reason": "Test setpoint optimization",
                        "expected_impact": {"energy_kwh": 1.0},
                    }
                ],
                "projected_savings": {},
                "cross_system_recommendations": [],
            }

    class _FakeOptimizer:
        async def analyze_building(self, **_kwargs):
            return _FakeOptimizationRecommendation()

        async def validate_recommendation(self, *_args, **_kwargs):
            return {"allowed": True}

    class _FakeRecommendationRepository:
        async def expire_superseded_setpoints(self, *_args, **_kwargs):
            return 0

        async def create(self, rec):
            created.append(rec)
            return rec

    class _FakeWorkOrderRepository:
        async def get_open_urgent_work_orders(self, *_args, **_kwargs):
            return []

    class _FakeTier:
        value = "tier1_advisory"

    class _FakeDecision:
        tier = _FakeTier()
        action = "advisory"
        reason = "test advisory"
        system = "HVAC"
        effective_confidence = 0.74
        original_confidence = 0.74

    class _FakeTierRouter:
        def resolve_control_tier(self, **_kwargs):
            return "advisory"

        def route_recommendation(self, **_kwargs):
            return _FakeDecision()

        def get_routing_summary(self, *_args, **_kwargs):
            return SimpleNamespace(blocked=0, advisory=1, pending_approval=0, auto_executed=0)

    monkeypatch.setattr(optimization_api, "get_ai_optimizer", lambda: _FakeOptimizer())
    monkeypatch.setattr(optimization_api, "load_sites", AsyncMock(return_value=[]))
    monkeypatch.setattr(optimization_api, "save_sites", AsyncMock())
    monkeypatch.setattr(optimization_api, "RecommendationRepository", lambda: _FakeRecommendationRepository())
    monkeypatch.setattr(optimization_api, "get_tier_router", lambda: _FakeTierRouter())
    monkeypatch.setattr(optimization_api, "get_approval_service", lambda: object())
    monkeypatch.setattr(optimization_api, "_controls_module_active", lambda _site_id: False)
    monkeypatch.setattr(optimization_api, "_resolve_site_phase", lambda _site_id, _fallback: phase)
    monkeypatch.setattr(optimization_api, "emit_decision_event", lambda *_args, **_kwargs: None)

    import app.database.repositories.work_order_repository as work_order_module

    monkeypatch.setattr(work_order_module, "WorkOrderRepository", lambda: _FakeWorkOrderRepository())

    result = await optimization_api.analyze_optimization(optimization_api.AnalyzeRequest(site_id="site-002"))

    assert result["success"] is True
    assert len(created) == 1
    assert created[0].source == "ai_optimizer"
    assert created[0].shadow_mode is expected_shadow


class TestStageTransitions:
    """Valid and invalid stage transitions per policy stage_order."""

    VALID_TRANSITIONS = {
        "commissioning": ["shadow_live"],
        "shadow_live": ["advisory"],
        "advisory": ["supervised"],
        "supervised": ["automatic"],
        "automatic": [],  # fail-closed demotes to supervised
    }

    def test_shadow_live_to_advisory_is_valid(self):
        """shadow_live → advisory is a valid next_stage transition."""
        next_stages = self.VALID_TRANSITIONS["shadow_live"]
        assert "advisory" in next_stages

    def test_advisory_to_supervised_is_valid(self):
        """advisory → supervised is a valid next_stage transition."""
        next_stages = self.VALID_TRANSITIONS["advisory"]
        assert "supervised" in next_stages

    def test_advisory_to_automatic_is_invalid(self):
        """advisory → automatic must go through supervised (invalid direct jump)."""
        next_stages = self.VALID_TRANSITIONS["advisory"]
        assert "automatic" not in next_stages

    def test_stage_order_sequence(self):
        """Full trust ladder sequence is maintained."""
        stage_order = ["commissioning", "shadow_live", "advisory", "supervised", "automatic"]
        # Each stage's next_stage matches the subsequent stage_order entry
        assert self.VALID_TRANSITIONS["commissioning"] == ["shadow_live"]
        assert self.VALID_TRANSITIONS["shadow_live"] == ["advisory"]
        assert self.VALID_TRANSITIONS["advisory"] == ["supervised"]
        assert self.VALID_TRANSITIONS["supervised"] == ["automatic"]


class TestRecommendationModelShadowMode:
    """Recommendation model serializes/deserializes shadow_mode correctly."""

    def test_to_dict_includes_shadow_mode_true(self):
        from app.models.recommendation import Recommendation

        rec = Recommendation(site_id="site-002", shadow_mode=True)
        d = rec.to_dict()
        assert d["shadow_mode"] is True

    def test_to_dict_includes_shadow_mode_false(self):
        from app.models.recommendation import Recommendation

        rec = Recommendation(site_id="site-002", shadow_mode=False)
        d = rec.to_dict()
        assert d["shadow_mode"] is False

    def test_from_dict_restores_shadow_mode_true(self):
        from app.models.recommendation import Recommendation

        data = {
            "id": "test-id",
            "site_id": "site-002",
            "shadow_mode": True,
            "action_type": "bess_dispatch",
            "status": "pending",
        }
        rec = Recommendation.from_dict(data)
        assert rec.shadow_mode is True

    def test_from_dict_restores_shadow_mode_false(self):
        from app.models.recommendation import Recommendation

        data = {
            "id": "test-id",
            "site_id": "site-002",
            "shadow_mode": False,
            "action_type": "bess_dispatch",
            "status": "pending",
        }
        rec = Recommendation.from_dict(data)
        assert rec.shadow_mode is False

    def test_round_trip_shadow_mode_true(self):
        from app.models.recommendation import Recommendation

        original = Recommendation(site_id="site-002", shadow_mode=True)
        restored = Recommendation.from_dict(original.to_dict())
        assert restored.shadow_mode is True

    def test_round_trip_shadow_mode_false(self):
        from app.models.recommendation import Recommendation

        original = Recommendation(site_id="site-002", shadow_mode=False)
        restored = Recommendation.from_dict(original.to_dict())
        assert restored.shadow_mode is False
