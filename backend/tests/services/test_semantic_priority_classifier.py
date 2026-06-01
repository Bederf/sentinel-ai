"""Tests for SemanticPriorityClassifier — Phase 207-03.

Covers: keyword hit, keyword miss → embedding, empty input,
consumables categories, original priority passthrough, and integration smoke.
"""

from __future__ import annotations

import pytest

from app.models.priority_classification import PriorityClassification
from app.models.recommendation import Recommendation
from app.services.semantic_priority_classifier import (
    SemanticPriorityClassifier,
    get_semantic_priority_classifier,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture()
def classifier() -> SemanticPriorityClassifier:
    """Fresh classifier per test (taxonomy is cached at module level)."""
    return SemanticPriorityClassifier()


@pytest.fixture()
def rec_factory():
    """Create a minimal Recommendation dict for create_recommendation calls."""

    def _make(
        site_id: str = "site-002",
        action_type: str = "hvac_setpoint_change",
        issue_title: str = "",
        issue_description: str = "",
        priority: str = "HIGH",
    ) -> dict:
        return {
            "site_id": site_id,
            "action_type": action_type,
            "issue_title": issue_title,
            "issue_description": issue_description,
            "priority": priority,
            "reason": "test reason",
            "confidence": "medium",
        }

    return _make


# =============================================================================
# SemanticPriorityClassifier — unit tests
# =============================================================================


@pytest.mark.unit
class TestSemanticPriorityClassifierKeyword:
    """Stage 1 keyword matching tests."""

    def test_soap_dispenser_is_consumable_low(self, classifier: SemanticPriorityClassifier) -> None:
        """'replace soap dispenser' should be classified as consumable LOW."""
        result = classifier.classify_issue("replace soap dispenser", "dispenser empty", "CRITICAL")
        assert result.is_consumable is True
        assert result.corrected_priority == "LOW"
        assert result.classification_method == "keyword"
        assert result.confidence == 1.0

    def test_toilet_paper_is_consumable(self, classifier: SemanticPriorityClassifier) -> None:
        """'toilet paper finished' should be classified as consumable LOW."""
        result = classifier.classify_issue("toilet paper", "out of paper in ladies bathroom", "HIGH")
        assert result.is_consumable is True
        assert result.corrected_priority == "LOW"
        assert result.classification_method == "keyword"

    def test_battery_replacement_is_consumable_medium(self, classifier: SemanticPriorityClassifier) -> None:
        """'battery flat' should be classified as consumable MEDIUM (electrical category)."""
        result = classifier.classify_issue("battery replacement", "emergency light battery flat", "CRITICAL")
        assert result.is_consumable is True
        assert result.corrected_priority == "MEDIUM"
        assert result.classification_method == "keyword"

    def test_filter_replacement_is_consumable_low(self, classifier: SemanticPriorityClassifier) -> None:
        """HVAC filter replacement should be LOW."""
        result = classifier.classify_issue("replace air filter", "AHU filter needs replacing", "CRITICAL")
        assert result.is_consumable is True
        assert result.corrected_priority == "LOW"

    def test_non_consumable_chiller_fault(self, classifier: SemanticPriorityClassifier) -> None:
        """'chiller compressor fault' should NOT be marked as consumable."""
        result = classifier.classify_issue(
            "chiller compressor fault",
            "high discharge pressure alarm",
            "CRITICAL",
        )
        assert result.is_consumable is False
        assert result.corrected_priority == "CRITICAL"
        assert result.classification_method in ("none", "embedding")

    def test_sparking_outlet_is_not_consumable(self, classifier: SemanticPriorityClassifier) -> None:
        """'sparking power outlet' is an electrical fault, not a consumable."""
        result = classifier.classify_issue(
            "sparking power outlet",
            "smoke coming from wall socket",
            "CRITICAL",
        )
        assert result.is_consumable is False
        assert result.corrected_priority == "CRITICAL"

    def test_empty_input_returns_original_priority(self, classifier: SemanticPriorityClassifier) -> None:
        """Empty title and description should not raise — returns original priority."""
        result = classifier.classify_issue("", "", "HIGH")
        assert result.is_consumable is False
        assert result.corrected_priority == "HIGH"
        assert result.confidence == 0.0
        assert result.classification_method == "keyword"

    def test_keyword_only_description(self, classifier: SemanticPriorityClassifier) -> None:
        """Classification should work when only description is provided."""
        result = classifier.classify_issue(
            "",
            "hand towel dispenser in ablution is empty",
            "MEDIUM",
        )
        assert result.is_consumable is True
        assert result.corrected_priority == "LOW"
        assert result.classification_method == "keyword"

    def test_cleaning_chemical_is_consumable_low(self, classifier: SemanticPriorityClassifier) -> None:
        """Janitorial cleaning chemical should be LOW priority consumable."""
        result = classifier.classify_issue(
            "cleaning chemical reorder",
            "detergent supplies running low",
            "LOW",
        )
        assert result.is_consumable is True
        assert result.corrected_priority == "LOW"
        assert result.classification_method == "keyword"


# =============================================================================
# SemanticPriorityClassifier — integration smoke test
# =============================================================================


@pytest.mark.unit
class TestGetSingleton:
    def test_get_semantic_priority_classifier_returns_instance(self) -> None:
        """get_semantic_priority_classifier() should return a non-None instance."""
        cls = get_semantic_priority_classifier()
        assert cls is not None
        assert isinstance(cls, SemanticPriorityClassifier)


# =============================================================================
# PriorityClassification dataclass
# =============================================================================


@pytest.mark.unit
class TestPriorityClassificationDataclass:
    def test_all_fields_populated(self) -> None:
        """PriorityClassification should accept all documented fields."""
        pc = PriorityClassification(
            is_consumable=True,
            original_priority="CRITICAL",
            corrected_priority="LOW",
            reason="matched consumable item 'soap dispenser'",
            confidence=0.85,
            classification_method="embedding",
        )
        assert pc.is_consumable is True
        assert pc.original_priority == "CRITICAL"
        assert pc.corrected_priority == "LOW"
        assert pc.confidence == 0.85
        assert pc.classification_method == "embedding"

    def test_is_consumable_false(self) -> None:
        """Non-consumable should have is_consumable=False."""
        pc = PriorityClassification(
            is_consumable=False,
            original_priority="HIGH",
            corrected_priority="HIGH",
            reason="no consumable match",
            confidence=0.0,
            classification_method="none",
        )
        assert pc.is_consumable is False
        assert pc.corrected_priority == "HIGH"


# =============================================================================
# Recommendation.is_consumable field — integration smoke
# =============================================================================


@pytest.mark.unit
class TestRecommendationIsConsumable:
    def test_recommendation_accepts_is_consumable_field(self) -> None:
        """Recommendation dataclass should accept is_consumable and priority_corrected."""
        rec = Recommendation(
            site_id="site-002",
            action_type="hvac_setpoint_change",
            is_consumable=True,
            priority_corrected=True,
            priority_reason="matched consumable item 'soap dispenser'",
        )
        assert rec.is_consumable is True
        assert rec.priority_corrected is True
        assert rec.priority_reason == "matched consumable item 'soap dispenser'"
