"""Tests for trust history models and trust scoring service.

Phase 162: Semantic Control Foundation — Plan 04.
Covers trust formula correctness, three-layer model, automation tier
decision table, risk assessment, repository round-trips, and edge cases.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.models.point_classification import PointClassification
from app.models.semantic_tag import SafetyClass
from app.models.trust_history import TrustHistory, TrustProfile
from app.services.simbiot.trust_scoring_service import TrustScoringService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_classification(
    point_id: str = "S001-AHU-B1-001.SAT",
    confidence_score: float = 0.85,
    data_quality_score: float = 0.9,
    highest_safety_class: SafetyClass | None = SafetyClass.MEDIUM,
    evidence_count: int = 3,
) -> PointClassification:
    from app.models.point_classification import EvidenceRecord
    from app.models.semantic_tag import EvidenceSource

    evidence = [
        EvidenceRecord(
            source=EvidenceSource.HAYSTACK_ID,
            value_found="SAT",
            rule_matched="SAT",
            weight=0.8,
            contributed_confidence=0.3,
            evidence_description="Haystack ID match",
        )
        for _ in range(evidence_count)
    ]

    return PointClassification(
        point_id=point_id,
        site_id="S001",
        equipment_type="ahu",
        semantic_tags=["supply_air_temperature_sensor"],
        confidence_score=confidence_score,
        data_quality_score=data_quality_score,
        classification_date=datetime.utcnow(),
        highest_safety_class=highest_safety_class,
        evidence_records=evidence,
    )


def _make_trust_history(
    point_id: str = "S001-AHU-B1-001.SAT",
    site_id: str = "S001",
    stability_days: int = 0,
    validation_runs: int = 0,
    successful_actions: int = 0,
    failed_actions: int = 0,
) -> TrustHistory:
    history = TrustHistory(
        point_id=point_id,
        site_id=site_id,
        stability_days=stability_days,
        validation_runs=validation_runs,
        successful_actions=successful_actions,
        failed_actions=failed_actions,
    )
    history.trust_score = TrustHistory.calculate_trust_score(
        stability_days, validation_runs, successful_actions, failed_actions
    )
    return history


# ---------------------------------------------------------------------------
# Task 1: TrustHistory.calculate_trust_score
# ---------------------------------------------------------------------------


class TestTrustScoreCalculationFormula:
    """Verify the trust formula matches the specification."""

    def test_trust_score_calculation_formula(self):
        """Verify formula: stability + action_boost - failure_penalty."""
        # 30 stability days * 5 validation runs → full stability score
        score = TrustHistory.calculate_trust_score(
            stability_days=30,
            validation_runs=5,
            successful_actions=10,
            failed_actions=0,
        )
        # stability_score = min(30/30, 0.6) * 1.0 = 0.6
        # success_rate = 10/(10+0+1) ≈ 0.909
        # action_score = min(10/10, 0.3) = 0.3
        # trust = 0.6 + (0.3 * 0.909) - 0.0 ≈ 0.873
        assert score == pytest.approx(0.873, abs=0.01)

    def test_new_point_starts_with_zero_trust(self):
        """Brand-new point with no history → 0.0 computed score."""
        score = TrustHistory.calculate_trust_score(0, 0, 0, 0)
        assert score == pytest.approx(0.0)

    def test_stability_days_increase_trust(self):
        """More stability days → higher trust (5 validation runs to unlock)."""
        score_low = TrustHistory.calculate_trust_score(5, 5, 0, 0)
        score_high = TrustHistory.calculate_trust_score(20, 5, 0, 0)
        assert score_high > score_low

    def test_successful_actions_boost_trust(self):
        """Successful actions contribute a positive boost."""
        base = TrustHistory.calculate_trust_score(10, 5, 0, 0)
        boosted = TrustHistory.calculate_trust_score(10, 5, 10, 0)
        assert boosted > base

    def test_failed_actions_penalize_trust(self):
        """Each failed action applies a -0.1 penalty to the raw score (clamped at 0)."""
        no_failures = TrustHistory.calculate_trust_score(10, 5, 5, 0)
        with_failure = TrustHistory.calculate_trust_score(10, 5, 5, 1)
        # Score should be lower when a failure is recorded
        assert with_failure < no_failures
        # The net reduction is affected by both the -0.1 penalty AND the changed
        # success_rate component; the combined delta is > 0.1 in this scenario.
        assert no_failures - with_failure > 0.05

    def test_trust_score_capped_at_1_0(self):
        """Trust score never exceeds 1.0."""
        score = TrustHistory.calculate_trust_score(
            stability_days=365,
            validation_runs=1000,
            successful_actions=10000,
            failed_actions=0,
        )
        assert score <= 1.0

    def test_trust_score_floored_at_0_0(self):
        """Trust score never goes below 0.0."""
        score = TrustHistory.calculate_trust_score(
            stability_days=0,
            validation_runs=5,
            successful_actions=0,
            failed_actions=100,
        )
        assert score >= 0.0

    def test_validation_factor_ramps_below_5_runs(self):
        """Validation factor is runs/5 when runs < 5 (avoids false trust)."""
        score_2_runs = TrustHistory.calculate_trust_score(30, 2, 0, 0)
        score_5_runs = TrustHistory.calculate_trust_score(30, 5, 0, 0)
        # 2/5 = 0.4 factor vs 1.0 factor
        assert score_5_runs > score_2_runs


# ---------------------------------------------------------------------------
# Task 2: TrustProfile.calculate_overall_trust
# ---------------------------------------------------------------------------


class TestOverallTrustCalculation:
    """Verify weighted averaging formula."""

    def test_overall_trust_calculation(self):
        """Weights: classification 40%, data quality 30%, control 30%."""
        overall = TrustProfile.calculate_overall_trust(
            classification_confidence=1.0,
            data_quality_score=1.0,
            control_trust_score=1.0,
        )
        assert overall == pytest.approx(1.0)

    def test_overall_trust_partial_weights(self):
        """Partial scores should combine proportionally."""
        overall = TrustProfile.calculate_overall_trust(
            classification_confidence=0.8,
            data_quality_score=0.6,
            control_trust_score=0.4,
        )
        expected = 0.4 * 0.8 + 0.3 * 0.6 + 0.3 * 0.4
        assert overall == pytest.approx(expected)

    def test_overall_trust_zero_baseline(self):
        """All-zero inputs → zero overall trust."""
        overall = TrustProfile.calculate_overall_trust(0.0, 0.0, 0.0)
        assert overall == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Task 3: Automation tier determination
# ---------------------------------------------------------------------------


class TestAutomationTierDetermination:
    """Test decision table for all safety classes."""

    def test_high_safety_always_observe_only(self):
        """HIGH safety class always → observe_only regardless of trust."""
        for trust in [0.0, 0.5, 0.9, 1.0]:
            tier = TrustProfile.determine_automation_tier(trust, "HIGH")
            assert tier == "observe_only", f"Expected observe_only for trust={trust}"

    def test_medium_safety_low_trust_supervised(self):
        """MEDIUM safety + trust < 0.6 → supervised."""
        tier = TrustProfile.determine_automation_tier(0.55, "MEDIUM")
        assert tier == "supervised"

    def test_medium_safety_high_trust_automatic(self):
        """MEDIUM safety + trust >= 0.6 → automatic."""
        tier = TrustProfile.determine_automation_tier(0.6, "MEDIUM")
        assert tier == "automatic"

    def test_low_safety_low_trust_supervised(self):
        """LOW safety + trust < 0.4 → supervised."""
        tier = TrustProfile.determine_automation_tier(0.3, "LOW")
        assert tier == "supervised"

    def test_low_safety_adequate_trust_automatic(self):
        """LOW safety + trust >= 0.4 → automatic."""
        tier = TrustProfile.determine_automation_tier(0.4, "LOW")
        assert tier == "automatic"

    def test_medium_safety_boundary_at_0_6(self):
        """MEDIUM safety boundary: exactly 0.6 is automatic."""
        assert TrustProfile.determine_automation_tier(0.599, "MEDIUM") == "supervised"
        assert TrustProfile.determine_automation_tier(0.600, "MEDIUM") == "automatic"

    def test_low_safety_boundary_at_0_4(self):
        """LOW safety boundary: exactly 0.4 is automatic."""
        assert TrustProfile.determine_automation_tier(0.399, "LOW") == "supervised"
        assert TrustProfile.determine_automation_tier(0.400, "LOW") == "automatic"


# ---------------------------------------------------------------------------
# Task 4: Risk level assessment (TrustScoringService)
# ---------------------------------------------------------------------------


class TestRiskLevelAssessment:
    """Verify risk calculation based on trust and safety class."""

    def setup_method(self):
        self.service = TrustScoringService()

    def test_high_safety_always_high_risk(self):
        """HIGH safety class → always HIGH risk."""
        assert self.service._assess_risk_level(0.9, "HIGH") == "HIGH"
        assert self.service._assess_risk_level(0.1, "HIGH") == "HIGH"

    def test_medium_safety_low_trust_high_risk(self):
        """MEDIUM safety + trust < 0.4 → HIGH risk."""
        assert self.service._assess_risk_level(0.3, "MEDIUM") == "HIGH"

    def test_medium_safety_adequate_trust_medium_risk(self):
        """MEDIUM safety + trust >= 0.4 → MEDIUM risk."""
        assert self.service._assess_risk_level(0.5, "MEDIUM") == "MEDIUM"

    def test_low_safety_very_low_trust_high_risk(self):
        """LOW safety + trust < 0.3 → HIGH risk."""
        assert self.service._assess_risk_level(0.2, "LOW") == "HIGH"

    def test_low_safety_medium_trust_medium_risk(self):
        """LOW safety + 0.3 <= trust < 0.6 → MEDIUM risk."""
        assert self.service._assess_risk_level(0.5, "LOW") == "MEDIUM"

    def test_low_safety_high_trust_low_risk(self):
        """LOW safety + trust >= 0.6 → LOW risk."""
        assert self.service._assess_risk_level(0.7, "LOW") == "LOW"


# ---------------------------------------------------------------------------
# Task 5: TrustScoringService.calculate_trust_profile
# ---------------------------------------------------------------------------


class TestTrustProfileCalculation:
    """Test full three-layer trust profile assembly."""

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_new_point_starts_with_neutral_control_trust(self):
        """No history → control_trust_score defaults to 0.5."""
        service = TrustScoringService()

        # Repo returns None (no history)
        mock_repo = AsyncMock()
        mock_repo.get_trust_history.return_value = None
        service.trust_history_repo = mock_repo

        classification = _make_classification()
        profile = self._run(service.calculate_trust_profile(classification))

        assert profile.control_trust_score == pytest.approx(0.5)
        assert profile.validation_runs == 0
        assert profile.successful_actions == 0
        assert profile.failed_actions == 0

    def test_existing_history_used_in_profile(self):
        """Existing trust history is reflected in the trust profile."""
        service = TrustScoringService()

        history = _make_trust_history(stability_days=20, validation_runs=10, successful_actions=5)
        mock_repo = AsyncMock()
        mock_repo.get_trust_history.return_value = history
        service.trust_history_repo = mock_repo

        classification = _make_classification()
        profile = self._run(service.calculate_trust_profile(classification))

        assert profile.stability_days == 20
        assert profile.validation_runs == 10
        assert profile.successful_actions == 5

    def test_overall_trust_uses_weighted_formula(self):
        """Overall trust is a weighted combination of all three layers."""
        service = TrustScoringService()

        history = _make_trust_history(stability_days=15, validation_runs=10)
        mock_repo = AsyncMock()
        mock_repo.get_trust_history.return_value = history
        service.trust_history_repo = mock_repo

        classification = _make_classification(confidence_score=0.8, data_quality_score=0.7)
        profile = self._run(service.calculate_trust_profile(classification))

        expected_overall = TrustProfile.calculate_overall_trust(0.8, 0.7, history.trust_score)
        assert profile.overall_trust_score == pytest.approx(expected_overall)

    def test_high_safety_produces_observe_only_tier(self):
        """HIGH safety class always returns observe_only tier."""
        service = TrustScoringService()
        mock_repo = AsyncMock()
        mock_repo.get_trust_history.return_value = None
        service.trust_history_repo = mock_repo

        classification = _make_classification(highest_safety_class=SafetyClass.HIGH)
        profile = self._run(service.calculate_trust_profile(classification))

        assert profile.automation_tier == "observe_only"
        assert profile.risk_level == "HIGH"


# ---------------------------------------------------------------------------
# Task 6: Trust history persistence
# ---------------------------------------------------------------------------


class TestTrustHistoryPersistence:
    """Test round-trip to repository (JSON fallback path)."""

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_trust_history_persistence_roundtrip(self, tmp_path):
        """Store and retrieve trust history via JSON fallback."""
        from app.database.repositories.trust_history_repository import (
            TrustHistoryRepository,
        )

        repo = TrustHistoryRepository()
        repo._use_json = True  # Force JSON path

        # Patch DATA_DIR to use tmp_path
        with patch(
            "app.database.repositories.trust_history_repository.DATA_DIR",
            tmp_path,
        ):
            history = _make_trust_history(stability_days=10, validation_runs=3, successful_actions=2)
            self._run(repo.upsert_trust_history(history))
            loaded = self._run(repo.get_trust_history(history.point_id, history.site_id))

        assert loaded is not None
        assert loaded.point_id == history.point_id
        assert loaded.stability_days == history.stability_days
        assert loaded.successful_actions == history.successful_actions

    def test_validation_runs_increment(self, tmp_path):
        """Validation run counter increments and stability_days increases on pass."""
        from app.database.repositories.trust_history_repository import (
            TrustHistoryRepository,
        )

        repo = TrustHistoryRepository()
        repo._use_json = True

        with patch(
            "app.database.repositories.trust_history_repository.DATA_DIR",
            tmp_path,
        ):
            self._run(repo.increment_validation_run("point-1", "S001", had_error=False))
            history = self._run(repo.get_trust_history("point-1", "S001"))
            assert history.validation_runs == 1
            assert history.stability_days == 1

            self._run(repo.increment_validation_run("point-1", "S001", had_error=False))
            history = self._run(repo.get_trust_history("point-1", "S001"))
            assert history.validation_runs == 2
            assert history.stability_days == 2

    def test_validation_error_resets_stability_days(self, tmp_path):
        """A validation error resets stability_days to 0."""
        from app.database.repositories.trust_history_repository import (
            TrustHistoryRepository,
        )

        repo = TrustHistoryRepository()
        repo._use_json = True

        with patch(
            "app.database.repositories.trust_history_repository.DATA_DIR",
            tmp_path,
        ):
            # Build up 5 days
            for _ in range(5):
                self._run(repo.increment_validation_run("point-2", "S001", had_error=False))

            # Trigger an error
            self._run(repo.increment_validation_run("point-2", "S001", had_error=True))
            history = self._run(repo.get_trust_history("point-2", "S001"))
            assert history.stability_days == 0
            assert history.last_validation_error is not None

    def test_control_action_recording(self, tmp_path):
        """Control action outcomes update success/failure counters."""
        from app.database.repositories.trust_history_repository import (
            TrustHistoryRepository,
        )

        repo = TrustHistoryRepository()
        repo._use_json = True

        with patch(
            "app.database.repositories.trust_history_repository.DATA_DIR",
            tmp_path,
        ):
            self._run(
                repo.record_control_action(
                    "point-3",
                    "S001",
                    success=True,
                    expected_outcome={"value": 22.0},
                    actual_outcome={"value": 22.1},
                )
            )
            history = self._run(repo.get_trust_history("point-3", "S001"))
            assert history.successful_actions == 1
            assert history.failed_actions == 0
            assert history.last_successful_action is not None

            self._run(
                repo.record_control_action(
                    "point-3",
                    "S001",
                    success=False,
                    expected_outcome={"value": 22.0},
                    actual_outcome={"value": 25.0},
                )
            )
            history = self._run(repo.get_trust_history("point-3", "S001"))
            assert history.successful_actions == 1
            assert history.failed_actions == 1


# ---------------------------------------------------------------------------
# Task 7: Bootstrap helper
# ---------------------------------------------------------------------------


class TestBootstrapTrustHistory:
    """TrustScoringService.bootstrap_trust_history returns zeroed record."""

    def test_bootstrap_returns_zeroed_history(self):
        history = TrustScoringService.bootstrap_trust_history("p-001", "S001")
        assert history.point_id == "p-001"
        assert history.site_id == "S001"
        assert history.stability_days == 0
        assert history.validation_runs == 0
        assert history.trust_score == pytest.approx(0.0)
