"""Tests for the intent recognition classifier (Phase 44-03)."""

import pytest

from ml.conversation.intent import ClassifiedQuery, Intent, IntentClassifier


@pytest.fixture
def classifier():
    return IntentClassifier()


class TestIntentClassification:
    """Test intent classification for various query types."""

    def test_why_prediction_intent(self, classifier):
        result = classifier.classify("Why is S002-CHILLER-B1-001 predicted to fail?")
        assert result.intent == Intent.WHY_PREDICTION
        assert result.confidence >= 0.85

    def test_why_prediction_root_cause(self, classifier):
        result = classifier.classify("What is the root cause of the chiller issue?")
        assert result.intent == Intent.WHY_PREDICTION

    def test_why_prediction_degrading(self, classifier):
        result = classifier.classify("Why is the AHU health score declining?")
        assert result.intent == Intent.WHY_PREDICTION

    def test_maintenance_due_intent(self, classifier):
        result = classifier.classify("When is maintenance due for S002-AHU-L2-001?")
        assert result.intent == Intent.MAINTENANCE_DUE
        assert result.confidence >= 0.85

    def test_maintenance_should_replace(self, classifier):
        result = classifier.classify("Should we replace the pump?")
        assert result.intent == Intent.MAINTENANCE_DUE

    def test_maintenance_remaining_life(self, classifier):
        result = classifier.classify("How long will the chiller last?")
        assert result.intent == Intent.MAINTENANCE_DUE

    def test_maintenance_spare_parts(self, classifier):
        result = classifier.classify("What spare parts do we need for the generator?")
        assert result.intent == Intent.MAINTENANCE_DUE

    def test_compare_equipment_intent(self, classifier):
        result = classifier.classify("Compare S002-CHILLER-B1-001 vs S002-CHILLER-B1-002")
        assert result.intent == Intent.COMPARE_EQUIPMENT
        assert len(result.equipment_ids) == 2

    def test_compare_which_better(self, classifier):
        result = classifier.classify("Which chiller is healthier?")
        assert result.intent == Intent.COMPARE_EQUIPMENT

    def test_show_trends_intent(self, classifier):
        result = classifier.classify("Show trends for S002-FCU-L1-A over the last 7 days")
        assert result.intent == Intent.SHOW_TRENDS

    def test_show_trends_performance(self, classifier):
        result = classifier.classify("How has the chiller performed over the last month?")
        assert result.intent == Intent.SHOW_TRENDS

    def test_show_trends_degradation(self, classifier):
        result = classifier.classify("Show the degradation curve for S002-PUMP-B1-CHW1")
        assert result.intent == Intent.SHOW_TRENDS

    def test_explain_anomaly_intent(self, classifier):
        result = classifier.classify("What's the anomaly on S002-PUMP-B1-CHW1?")
        assert result.intent == Intent.EXPLAIN_ANOMALY

    def test_explain_anomaly_spike(self, classifier):
        result = classifier.classify("There's a spike in chiller vibration readings")
        assert result.intent == Intent.EXPLAIN_ANOMALY

    def test_explain_anomaly_unusual(self, classifier):
        result = classifier.classify("Unusual reading on the AHU temperature sensor")
        assert result.intent == Intent.EXPLAIN_ANOMALY

    def test_equipment_status_intent(self, classifier):
        result = classifier.classify("What's the status of S002-AHU-L2-001?")
        assert result.intent == Intent.EQUIPMENT_STATUS

    def test_equipment_status_health(self, classifier):
        result = classifier.classify("Health score for S002-FCU-L1-A")
        assert result.intent == Intent.EQUIPMENT_STATUS

    def test_equipment_status_how_doing(self, classifier):
        result = classifier.classify("How is the chiller doing?")
        assert result.intent == Intent.EQUIPMENT_STATUS

    def test_general_query_fallback(self, classifier):
        result = classifier.classify("Tell me about the building")
        assert result.intent == Intent.GENERAL_QUERY
        assert result.confidence == 0.50

    def test_general_query_unrecognized(self, classifier):
        result = classifier.classify("Hello")
        assert result.intent == Intent.GENERAL_QUERY


class TestEntityExtraction:
    """Test equipment ID and entity extraction."""

    def test_extract_single_equipment_id(self, classifier):
        result = classifier.classify("Status of S002-CHILLER-B1-001")
        assert "S002-CHILLER-B1-001" in result.equipment_ids

    def test_extract_multiple_equipment_ids(self, classifier):
        result = classifier.classify("Compare S002-CHILLER-B1-001 vs S002-CHILLER-B1-002")
        assert len(result.equipment_ids) == 2
        assert "S002-CHILLER-B1-001" in result.equipment_ids
        assert "S002-CHILLER-B1-002" in result.equipment_ids

    def test_extract_equipment_type_chiller(self, classifier):
        result = classifier.classify("How is the chiller performing?")
        assert result.equipment_type == "chiller"

    def test_extract_equipment_type_ahu(self, classifier):
        result = classifier.classify("What's wrong with the air handling unit?")
        assert result.equipment_type == "ahu"

    def test_extract_equipment_type_generator(self, classifier):
        result = classifier.classify("When should we service the generator?")
        assert result.equipment_type == "generator"

    def test_extract_equipment_type_pump(self, classifier):
        result = classifier.classify("Show pump trends")
        assert result.equipment_type == "pump"

    def test_extract_equipment_type_dali(self, classifier):
        result = classifier.classify("Status of the DALI controller")
        assert result.equipment_type == "dali"

    def test_no_equipment_type(self, classifier):
        result = classifier.classify("What needs attention today?")
        assert result.equipment_type is None

    def test_extract_time_range_days(self, classifier):
        result = classifier.classify("Show trends for the last 30 days")
        assert result.time_range is not None
        assert "30" in result.time_range

    def test_extract_time_range_week(self, classifier):
        result = classifier.classify("Performance over the past week")
        assert result.time_range == "7d"

    def test_extract_time_range_month(self, classifier):
        result = classifier.classify("How has it changed over the last month")
        assert result.time_range == "30d"

    def test_no_time_range(self, classifier):
        result = classifier.classify("What is the status of the chiller?")
        assert result.time_range is None

    def test_equipment_id_case_insensitive(self, classifier):
        result = classifier.classify("Check s002-chiller-b1-001")
        assert "S002-CHILLER-B1-001" in result.equipment_ids

    def test_confidence_boost_with_equipment(self, classifier):
        """Confidence should be boosted when equipment context is present."""
        without = classifier.classify("Show me some trends")
        with_eq = classifier.classify("Show me trends for S002-CHILLER-B1-001")
        assert with_eq.confidence > without.confidence


class TestClassifiedQuery:
    """Test ClassifiedQuery dataclass."""

    def test_default_values(self):
        q = ClassifiedQuery(
            intent=Intent.GENERAL_QUERY,
            confidence=0.5,
            original_query="test",
        )
        assert q.equipment_ids == []
        assert q.equipment_type is None
        assert q.time_range is None

    def test_all_fields(self):
        q = ClassifiedQuery(
            intent=Intent.WHY_PREDICTION,
            confidence=0.95,
            equipment_ids=["S002-CHILLER-B1-001"],
            equipment_type="chiller",
            time_range="7d",
            original_query="Why is the chiller failing?",
        )
        assert q.intent == Intent.WHY_PREDICTION
        assert q.confidence == 0.95
        assert len(q.equipment_ids) == 1
