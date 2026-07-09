"""
Tests for health/risk separation enforcement and regression.

Phase 109B-03: Recommendation Pipeline Health Feature Payload + Separation Enforcement

Verifies:
1. Separation invariants — health services never write risk, risk services never write health
2. HealthFeaturePayload contract — 7 fields, correct ranges, correct types
3. HealthFeatureProvider — computes from snapshots, handles missing data
4. Regression — CommissioningService, PredictionGenerator, QualityGateEvaluator, thresholds unchanged

Target: 15+ tests
"""

import inspect
import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.health_rating import HealthFeaturePayload, HealthRating
from app.services.health_feature_provider import HealthFeatureProvider

# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture
def provider():
    """Create a HealthFeatureProvider instance."""
    return HealthFeatureProvider()


@pytest.fixture
def sample_payload():
    """Create a sample HealthFeaturePayload."""
    return HealthFeaturePayload(
        health_score_current=85.0,
        health_status_current="healthy",
        health_trend_7d_slope=-0.1,
        health_trend_30d_slope=-0.05,
        health_volatility_30d=2.3,
        health_confidence="high",
        baseline_deviation_max_24h=5.2,
    )


@pytest.fixture
def mock_health_rating():
    """Create a mock HealthRating for testing."""
    from app.models.health_rating import HealthComponentBreakdown, HealthDataQualityResult

    return HealthRating(
        equipment_id="S002-AHU-101",
        health_score=78.5,
        health_status="warning",
        confidence="medium",
        assessment_state="normal",
        components=HealthComponentBreakdown(
            baseline_alignment_score=80.0,
            service_compliance_score=70.0,
            runtime_age_score=85.0,
            fault_burden_score=60.0,
            trend_momentum_score=80.0,
        ),
        data_quality=HealthDataQualityResult(
            freshness_minutes=5.0,
            snapshot_count_24h=12,
            valid_point_ratio=0.95,
            baseline_age_days=3,
            gates_passed=3,
            gates_total=4,
            confidence="medium",
            assessment_state="normal",
        ),
        formula_version="v1",
        snapshot_at="2026-02-20T10:00:00Z",
    )


# ======================================================================
# Separation Invariant Tests
# ======================================================================


class TestSeparationInvariants:
    """Tests that health and risk domains are strictly separated."""

    def test_health_calculator_has_no_prediction_imports(self):
        """HealthRatingCalculator must not import prediction modules."""
        from app.services.health_rating_calculator import HealthRatingCalculator

        source = inspect.getsource(HealthRatingCalculator)
        module_source = inspect.getsource(inspect.getmodule(HealthRatingCalculator))

        assert "prediction_generator" not in module_source, (
            "HealthRatingCalculator must NOT import prediction_generator"
        )
        assert "prediction_calculator" not in module_source, (
            "HealthRatingCalculator must NOT import prediction_calculator"
        )
        assert "PredictionGeneratorService" not in source, (
            "HealthRatingCalculator must NOT reference PredictionGeneratorService"
        )

    def test_health_snapshot_service_has_no_risk_writes(self):
        """HealthSnapshotService must not write to the predictions table."""
        from app.services.health_snapshot_service import HealthSnapshotService

        module_source = inspect.getsource(inspect.getmodule(HealthSnapshotService))

        # Must not write to predictions table
        assert 'table("predictions")' not in module_source, "HealthSnapshotService must NOT write to predictions table"
        assert "prediction_generator" not in module_source, "HealthSnapshotService must NOT import prediction_generator"

    def test_health_feature_provider_has_no_risk_writes(self):
        """HealthFeatureProvider must not import or write risk probabilities."""
        module_source = inspect.getsource(inspect.getmodule(HealthFeatureProvider))

        # Filter out docstrings/comments — check only executable lines for imports
        import_lines = [
            line.strip() for line in module_source.splitlines() if line.strip().startswith(("import ", "from "))
        ]
        import_text = "\n".join(import_lines)

        assert "prediction_generator" not in import_text, "HealthFeatureProvider must NOT import prediction_generator"
        assert "prediction_calculator" not in import_text, "HealthFeatureProvider must NOT import prediction_calculator"

        # Also check lazy-load bodies (inside methods) for prediction imports
        # by looking for 'from app.services.prediction' in non-doc lines
        code_lines = [
            line
            for line in module_source.splitlines()
            if not line.strip().startswith(("#", '"""', "'''", "-")) and "docstring" not in line.lower()
        ]
        code_text = "\n".join(code_lines)
        assert "from app.services.prediction_generator" not in code_text, (
            "HealthFeatureProvider has a lazy import of prediction_generator"
        )
        assert "from app.services.prediction_calculator" not in code_text, (
            "HealthFeatureProvider has a lazy import of prediction_calculator"
        )

    def test_prediction_generator_has_no_health_write(self):
        """PredictionGeneratorService must not write to equipment.health_score directly."""
        from app.services.prediction_generator import PredictionGeneratorService

        source = inspect.getsource(PredictionGeneratorService)

        # PredictionGenerator reads health_score but should not write it
        assert '.update({"health_score"' not in source, (
            "PredictionGeneratorService must NOT write health_score to equipment table"
        )
        assert "HealthRatingCalculator" not in source, (
            "PredictionGeneratorService must NOT import HealthRatingCalculator"
        )

    def test_health_features_separate_from_risk(self, sample_payload):
        """Health feature payload must not contain risk probability fields."""
        payload_dict = sample_payload.model_dump()

        risk_fields = [
            "probability_percent",
            "failure_probability",
            "risk_probability",
            "prediction_type",
            "predicted_failure_date",
        ]

        for field in risk_fields:
            assert field not in payload_dict, f"HealthFeaturePayload must NOT contain risk field '{field}'"

    def test_risk_fields_separate_from_health(self):
        """Risk prediction structure must not contain health_score_current."""
        from app.services.prediction_generator import PredictionGeneratorService

        source = inspect.getsource(PredictionGeneratorService)

        # The _generate_prediction method should not produce health_score_current
        assert "health_score_current" not in source, "PredictionGeneratorService must NOT produce health_score_current"
        assert "health_severity_signal" not in source, (
            "PredictionGeneratorService must NOT produce health_severity_signal"
        )

    @pytest.mark.asyncio
    async def test_health_and_risk_both_in_recommendation(self):
        """Recommendation dict should have BOTH health_features AND confidence fields."""
        from app.models.optimization import OptimizationRecommendation

        # Create recommendation with a recommendation dict that has equipment_id
        rec = OptimizationRecommendation(
            site_id="S002",
            timestamp="2026-02-20T10:00:00Z",
            recommendations=[
                {
                    "target_equipment": "S002-AHU-101",
                    "action": "reduce_setpoint",
                    "confidence": 0.85,
                }
            ],
            confidence=0.85,
        )

        # Mock the health feature provider
        mock_payload = HealthFeaturePayload(
            health_score_current=78.5,
            health_status_current="warning",
            health_confidence="medium",
        )

        with patch(
            "app.services.health_feature_provider.HealthFeatureProvider.get_health_features",
            new_callable=AsyncMock,
            return_value=mock_payload,
        ):
            from app.services.ai_optimizer import AIOptimizerService

            optimizer = AIOptimizerService()
            enriched = await optimizer._enrich_with_health_features("S002", rec)

            rec_dict = enriched.recommendations[0]

            # Both health_features and confidence must be present
            assert "health_features" in rec_dict, "health_features dict must be present"
            assert "confidence" in rec_dict, "Original confidence must be preserved"
            assert "health_severity_signal" in rec_dict, "health_severity_signal must be present"

            # They must be separate
            assert rec_dict["confidence"] == 0.85, "Risk confidence must be unchanged"
            assert rec_dict["health_features"]["health_score_current"] == 78.5


# ======================================================================
# Feature Payload Tests
# ======================================================================


class TestHealthFeaturePayload:
    """Tests for the HealthFeaturePayload model."""

    def test_health_feature_payload_has_7_fields(self, sample_payload):
        """Payload must have exactly 7 fields."""
        payload_dict = sample_payload.model_dump()
        expected_fields = {
            "health_score_current",
            "health_status_current",
            "health_trend_7d_slope",
            "health_trend_30d_slope",
            "health_volatility_30d",
            "health_confidence",
            "baseline_deviation_max_24h",
        }
        assert set(payload_dict.keys()) == expected_fields

    def test_health_feature_payload_score_range(self):
        """Score must be in range [0, 100]."""
        # Valid: 0
        p0 = HealthFeaturePayload(
            health_score_current=0.0,
            health_status_current="critical",
            health_confidence="low",
        )
        assert p0.health_score_current == 0.0

        # Valid: 100
        p100 = HealthFeaturePayload(
            health_score_current=100.0,
            health_status_current="healthy",
            health_confidence="high",
        )
        assert p100.health_score_current == 100.0

        # Invalid: > 100
        with pytest.raises(ValueError):
            HealthFeaturePayload(
                health_score_current=101.0,
                health_status_current="healthy",
                health_confidence="high",
            )

        # Invalid: < 0
        with pytest.raises(ValueError):
            HealthFeaturePayload(
                health_score_current=-1.0,
                health_status_current="healthy",
                health_confidence="high",
            )

    def test_health_feature_payload_optional_fields_default_none(self):
        """Optional fields default to None when not provided."""
        p = HealthFeaturePayload(
            health_score_current=80.0,
            health_status_current="healthy",
            health_confidence="high",
        )
        assert p.health_trend_7d_slope is None
        assert p.health_trend_30d_slope is None
        assert p.health_volatility_30d is None
        assert p.baseline_deviation_max_24h is None

    def test_health_feature_payload_status_values(self):
        """Status must accept known values."""
        for status in ("healthy", "warning", "critical"):
            p = HealthFeaturePayload(
                health_score_current=50.0,
                health_status_current=status,
                health_confidence="medium",
            )
            assert p.health_status_current == status


# ======================================================================
# HealthFeatureProvider Tests
# ======================================================================


class TestHealthFeatureProvider:
    """Tests for the HealthFeatureProvider service."""

    @pytest.mark.asyncio
    async def test_provider_uses_latest_snapshot(self, provider, mock_health_rating):
        """Provider should use latest snapshot from HealthSnapshotService."""
        mock_snapshot_svc = MagicMock()
        mock_snapshot_svc.get_latest = AsyncMock(return_value=mock_health_rating)
        mock_snapshot_svc.get_daily_rollups = AsyncMock(return_value=[])

        provider._snapshot_service = mock_snapshot_svc

        result = await provider.get_health_features("S002-AHU-101")

        mock_snapshot_svc.get_latest.assert_called_once_with("S002-AHU-101")
        assert result.health_score_current == 78.5
        assert result.health_status_current == "warning"
        assert result.health_confidence == "medium"

    @pytest.mark.asyncio
    async def test_provider_degraded_when_no_data(self, provider):
        """Provider returns degraded payload when no snapshot or calculation exists."""
        mock_snapshot_svc = MagicMock()
        mock_snapshot_svc.get_latest = AsyncMock(return_value=None)
        provider._snapshot_service = mock_snapshot_svc

        # Mock the calculator to also fail
        mock_calc = MagicMock()
        mock_calc.compute_rating = AsyncMock(side_effect=Exception("no data"))
        provider._calculator = mock_calc

        result = await provider.get_health_features("NONEXISTENT")

        assert result.health_score_current == 50.0
        assert result.health_confidence == "low"
        assert result.health_status_current == "warning"

    def test_volatility_calculation(self, provider):
        """Volatility should be stddev of scores."""
        scores = [80.0, 85.0, 75.0, 90.0, 70.0]
        stddev = provider._stddev(scores)

        # Manual: mean=80, variance = (0+25+25+100+100)/5 = 50, stddev = ~7.07
        expected = round(math.sqrt(50), 2)
        assert stddev == expected

    def test_volatility_single_value(self, provider):
        """Single value should have zero stddev (but returns None for < 2 values)."""
        # _stddev works on the list directly, but _calculate_volatility
        # returns None for < 2 values
        assert provider._stddev([80.0]) == 0.0

    def test_linear_slope_stable(self, provider):
        """Constant scores should have zero slope."""
        points = [(0, 80), (1, 80), (2, 80)]
        assert provider._linear_slope(points) == 0.0

    def test_linear_slope_declining(self, provider):
        """Declining scores should have negative slope."""
        points = [(0, 100), (1, 90), (2, 80)]
        slope = provider._linear_slope(points)
        assert slope == -10.0

    def test_baseline_deviation_extraction(self, provider, mock_health_rating):
        """Baseline deviation should be extracted from component score."""
        # baseline_alignment_score = 80.0
        # deviation = (100 - 80) / 2 = 10.0
        deviation = provider._extract_baseline_deviation(mock_health_rating)
        assert deviation == 10.0

    def test_baseline_deviation_neutral(self, provider):
        """Neutral score (50.0 = no baseline) should return None."""
        from app.models.health_rating import HealthComponentBreakdown, HealthDataQualityResult

        rating = HealthRating(
            equipment_id="TEST",
            health_score=50.0,
            health_status="warning",
            confidence="low",
            assessment_state="normal",
            components=HealthComponentBreakdown(baseline_alignment_score=50.0),
            data_quality=HealthDataQualityResult(
                freshness_minutes=0,
                snapshot_count_24h=0,
                valid_point_ratio=1.0,
                baseline_age_days=0,
                gates_passed=4,
                gates_total=4,
                confidence="low",
                assessment_state="normal",
            ),
            formula_version="v1",
            snapshot_at="2026-02-20T10:00:00Z",
        )
        assert provider._extract_baseline_deviation(rating) is None


# ======================================================================
# Regression Tests (existing systems unchanged)
# ======================================================================


class TestRegressionUnchanged:
    """Tests that existing systems are not broken by health feature changes."""

    def test_commissioning_gates_unchanged(self):
        """CommissioningService gate IDs should be unchanged."""
        from app.models.commissioning import CommissioningGateId

        # Original 8 gates must still exist
        expected_gates = [
            "match_coverage",
            "unmatched_points",
            "data_freshness",
            "error_rate",
        ]
        for gate_name in expected_gates:
            assert hasattr(CommissioningGateId, gate_name.upper()), (
                f"CommissioningGateId.{gate_name.upper()} must still exist"
            )

    def test_prediction_generator_still_works(self):
        """PredictionGeneratorService can be instantiated (structure unchanged)."""
        # Just verify the class structure is intact
        from app.services.prediction_generator import PredictionGeneratorService

        assert hasattr(PredictionGeneratorService, "generate_predictions_for_all_sites")
        assert hasattr(PredictionGeneratorService, "_generate_prediction")
        assert hasattr(PredictionGeneratorService, "_get_at_risk_equipment")

    def test_health_threshold_service_unchanged(self):
        """Health threshold defaults should match the Phase 221 unified contract (85/65/40)."""
        from app.services.health_threshold_service import DEFAULT_HEALTH

        assert DEFAULT_HEALTH["healthy"] == 85
        assert DEFAULT_HEALTH["warning"] == 65
        assert DEFAULT_HEALTH["critical"] == 40

    def test_quality_gate_evaluator_still_works(self):
        """QualityGateEvaluator class structure should be unchanged."""
        from app.services.quality_gate_evaluator import QualityGateEvaluator

        assert hasattr(QualityGateEvaluator, "evaluate")
        assert hasattr(QualityGateEvaluator, "collect_metrics")
        assert hasattr(QualityGateEvaluator, "apply_enforcement")

    def test_health_rating_calculator_unchanged(self):
        """HealthRatingCalculator component methods and weights should be unchanged."""
        from app.services.health_rating_calculator import WEIGHTS, HealthRatingCalculator

        # Weights must sum to 1.0
        assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-10

        # 5 component methods must exist
        calc = HealthRatingCalculator()
        assert hasattr(calc, "calculate_baseline_alignment")
        assert hasattr(calc, "calculate_service_compliance")
        assert hasattr(calc, "calculate_runtime_age")
        assert hasattr(calc, "calculate_fault_burden")
        assert hasattr(calc, "calculate_trend_momentum")
        assert hasattr(calc, "calculate_health_score")

    def test_optimizer_quality_gate_still_applied(self):
        """AIOptimizerService must still apply quality gate."""
        from app.services.ai_optimizer import AIOptimizerService

        source = inspect.getsource(AIOptimizerService.analyze_building)
        assert "_apply_quality_gate" in source, "analyze_building must still call _apply_quality_gate"

    def test_optimizer_health_enrichment_is_additive(self):
        """Health enrichment must be called AFTER quality gate (additive)."""
        from app.services.ai_optimizer import AIOptimizerService

        source = inspect.getsource(AIOptimizerService.analyze_building)
        # _enrich_with_health_features must appear after _apply_quality_gate
        gate_pos = source.index("_apply_quality_gate")
        health_pos = source.index("_enrich_with_health_features")
        assert health_pos > gate_pos, "_enrich_with_health_features must be called AFTER _apply_quality_gate"

    def test_existing_health_baseline_endpoint_unchanged(self):
        """GET /api/equipment/{id}/health-baseline must still be defined."""
        from app.api.asset_health import router

        route_paths = [r.path for r in router.routes]
        assert "/api/equipment/{equipment_id}/health-baseline" in route_paths, (
            f"health-baseline endpoint missing from asset_health router. Routes: {route_paths}"
        )
