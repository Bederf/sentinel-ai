"""Tests for the Decision Memory Service.

Phase 145: Decision Memory Layer.
"""

import pytest

from app.models.decision_memory import (
    DecisionOutcome,
    DecisionPattern,
    DecisionRecord,
)
from app.services.decision_memory_service import (
    DecisionMemoryService,
    reset_decision_memory_service,
)


@pytest.fixture(autouse=True)
def _reset_decision_memory(tmp_path):
    """Reset singleton and module-level paths before each test to prevent state pollution."""
    import app.services.decision_memory_service as mod

    orig_data_dir = mod.DATA_DIR
    orig_records = mod.RECORDS_FILE
    orig_patterns = mod.PATTERNS_FILE

    reset_decision_memory_service()
    mod.DATA_DIR = tmp_path
    mod.RECORDS_FILE = tmp_path / "decision_records.json"
    mod.PATTERNS_FILE = tmp_path / "decision_patterns.json"
    (tmp_path / "decision_records.json").write_text("[]")
    (tmp_path / "decision_patterns.json").write_text("[]")

    yield

    # Restore original paths so other test modules aren't affected
    reset_decision_memory_service()
    mod.DATA_DIR = orig_data_dir
    mod.RECORDS_FILE = orig_records
    mod.PATTERNS_FILE = orig_patterns


@pytest.fixture
def svc(tmp_path):
    """Create a fresh service with temporary storage."""
    reset_decision_memory_service()
    service = DecisionMemoryService()
    # Paths already redirected by autouse _reset_decision_memory fixture
    service._loaded = False
    return service


# -----------------------------------------------------------------
# Record Creation
# -----------------------------------------------------------------


class TestRecordDecision:
    @pytest.mark.asyncio
    async def test_record_creates_with_correct_fields(self, svc):
        record = await svc.record_decision(
            event_type="temperature_deviation",
            equipment_id="S002-CHILLER-B1-001",
            equipment_type="CHILLER",
            site_id="site-002",
            diagnosis="condenser fouling",
            diagnosis_confidence=0.85,
            action_type="work_order",
        )
        assert record.record_id.startswith("DM-")
        assert record.event_type == "temperature_deviation"
        assert record.equipment_id == "S002-CHILLER-B1-001"
        assert record.diagnosis == "condenser fouling"
        assert record.outcome == DecisionOutcome.PENDING

    @pytest.mark.asyncio
    async def test_season_auto_detected(self, svc):
        record = await svc.record_decision(
            event_type="test",
            equipment_id="S002-FCU-101",
            equipment_type="FCU",
            site_id="site-002",
            diagnosis="test",
        )
        assert record.season in ("summer", "autumn", "winter", "spring")

    @pytest.mark.asyncio
    async def test_time_of_day_auto_detected(self, svc):
        record = await svc.record_decision(
            event_type="test",
            equipment_id="S002-FCU-101",
            equipment_type="FCU",
            site_id="site-002",
            diagnosis="test",
        )
        assert record.time_of_day in ("morning", "afternoon", "evening", "night")


# -----------------------------------------------------------------
# Outcome Recording
# -----------------------------------------------------------------


class TestRecordOutcome:
    @pytest.mark.asyncio
    async def test_record_outcome_resolved(self, svc):
        record = await svc.record_decision(
            event_type="temperature_deviation",
            equipment_id="S002-CHILLER-B1-001",
            equipment_type="CHILLER",
            site_id="site-002",
            diagnosis="condenser fouling",
            action_type="tube_cleaning",
        )

        updated = await svc.record_outcome(
            record.record_id,
            DecisionOutcome.RESOLVED,
            outcome_details="Pressure normalized after cleaning",
        )
        assert updated.outcome == DecisionOutcome.RESOLVED
        assert updated.resolution_time_minutes is not None
        assert updated.resolution_time_minutes >= 0

    @pytest.mark.asyncio
    async def test_outcome_not_found(self, svc):
        result = await svc.record_outcome("NONEXISTENT", DecisionOutcome.RESOLVED)
        assert result is None


# -----------------------------------------------------------------
# Pattern Extraction
# -----------------------------------------------------------------


class TestPatternExtraction:
    @pytest.mark.asyncio
    async def test_pattern_extracted_with_threshold(self, svc):
        """3+ resolved records with same diagnosis should create a pattern."""
        for i in range(3):
            record = await svc.record_decision(
                event_type="temperature_deviation",
                equipment_id=f"S002-CHILLER-B1-00{i + 1}",
                equipment_type="CHILLER",
                site_id="site-002",
                diagnosis="condenser fouling",
                action_type="tube_cleaning",
            )
            await svc.record_outcome(record.record_id, DecisionOutcome.RESOLVED)

        pattern = await svc.get_recommended_action("temperature_deviation", "CHILLER")
        assert pattern is not None
        assert pattern.likely_diagnosis == "condenser fouling"
        assert pattern.success_rate == 1.0
        assert pattern.total_occurrences == 3

    @pytest.mark.asyncio
    async def test_no_pattern_below_threshold(self, svc):
        """<3 records should not create a pattern."""
        for i in range(2):
            record = await svc.record_decision(
                event_type="energy_spike",
                equipment_id=f"S002-AHU-B1-00{i + 1}",
                equipment_type="AHU",
                site_id="site-002",
                diagnosis="damper stuck",
                action_type="damper_reset",
            )
            await svc.record_outcome(record.record_id, DecisionOutcome.RESOLVED)

        pattern = await svc.get_recommended_action("energy_spike", "AHU")
        assert pattern is None

    @pytest.mark.asyncio
    async def test_pattern_confidence_from_success_rate(self, svc):
        """Pattern confidence should reflect success rate."""
        for i in range(4):
            record = await svc.record_decision(
                event_type="pressure_anomaly",
                equipment_id=f"S002-CHILLER-B1-00{i + 1}",
                equipment_type="CHILLER",
                site_id="site-002",
                diagnosis="refrigerant leak",
                action_type="recharge",
            )
            # 3 resolved, 1 ineffective
            outcome = DecisionOutcome.RESOLVED if i < 3 else DecisionOutcome.INEFFECTIVE
            await svc.record_outcome(record.record_id, outcome)

        pattern = await svc.get_recommended_action("pressure_anomaly", "CHILLER")
        assert pattern is not None
        assert pattern.success_rate == 0.75

    @pytest.mark.asyncio
    async def test_bad_outcomes_prevent_pattern(self, svc):
        """Low success rate should not produce a pattern."""
        for i in range(4):
            record = await svc.record_decision(
                event_type="sensor_failure",
                equipment_id=f"S002-FCU-10{i + 1}",
                equipment_type="FCU",
                site_id="site-002",
                diagnosis="calibration drift",
                action_type="recalibrate",
            )
            # Only 1 resolved out of 4 = 25% success rate (below 50%)
            outcome = DecisionOutcome.RESOLVED if i == 0 else DecisionOutcome.INEFFECTIVE
            await svc.record_outcome(record.record_id, outcome)

        pattern = await svc.get_recommended_action("sensor_failure", "FCU")
        assert pattern is None


# -----------------------------------------------------------------
# Query
# -----------------------------------------------------------------


class TestQuery:
    @pytest.mark.asyncio
    async def test_find_similar_decisions(self, svc):
        await svc.record_decision(
            event_type="temperature_deviation",
            equipment_id="S002-CHILLER-B1-001",
            equipment_type="CHILLER",
            site_id="site-002",
            diagnosis="condenser fouling",
            action_type="tube_cleaning",
        )
        r = await svc.record_decision(
            event_type="temperature_deviation",
            equipment_id="S002-CHILLER-B1-001",
            equipment_type="CHILLER",
            site_id="site-002",
            diagnosis="low refrigerant",
            action_type="recharge",
        )
        await svc.record_outcome(r.record_id, DecisionOutcome.RESOLVED)

        results = await svc.find_similar_decisions(
            event_type="temperature_deviation",
            equipment_type="CHILLER",
            equipment_id="S002-CHILLER-B1-001",
        )
        # Should find the resolved one (pending are excluded)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_get_decision_stats(self, svc):
        record = await svc.record_decision(
            event_type="test",
            equipment_id="S002-FCU-101",
            equipment_type="FCU",
            site_id="site-002",
            diagnosis="test diagnosis",
        )
        await svc.record_outcome(record.record_id, DecisionOutcome.RESOLVED)

        stats = await svc.get_decision_stats()
        assert stats["total_records"] == 1
        assert stats["outcome_distribution"]["resolved"] == 1


# -----------------------------------------------------------------
# Prompt Formatting
# -----------------------------------------------------------------


class TestFormatForPrompt:
    def test_format_patterns(self, svc):
        pattern = DecisionPattern(
            event_type="temperature_deviation",
            equipment_type="CHILLER",
            likely_diagnosis="condenser fouling",
            diagnosis_confidence=0.85,
            recommended_action="tube_cleaning",
            total_occurrences=10,
            resolved_count=8,
            success_rate=0.8,
            avg_resolution_time_minutes=120.0,
        )
        text = svc.format_for_prompt(patterns=[pattern])
        assert "condenser fouling" in text
        assert "tube_cleaning" in text
        assert "85%" in text

    def test_format_records(self, svc):
        record = DecisionRecord(
            event_type="test",
            equipment_id="S002-FCU-101",
            diagnosis="fan belt worn",
            action_type="belt_replacement",
            outcome=DecisionOutcome.RESOLVED,
        )
        text = svc.format_for_prompt(records=[record])
        assert "fan belt worn" in text
        assert "belt_replacement" in text

    def test_format_empty(self, svc):
        text = svc.format_for_prompt()
        assert text == ""


# -----------------------------------------------------------------
# Serialization
# -----------------------------------------------------------------


class TestSerialization:
    def test_decision_record_roundtrip(self):
        record = DecisionRecord(
            event_type="temperature_deviation",
            equipment_id="S002-CHILLER-B1-001",
            diagnosis="condenser fouling",
            outcome=DecisionOutcome.RESOLVED,
        )
        d = record.to_dict()
        restored = DecisionRecord.from_dict(d)
        assert restored.event_type == record.event_type
        assert restored.outcome == DecisionOutcome.RESOLVED

    def test_decision_pattern_roundtrip(self):
        pattern = DecisionPattern(
            event_type="test",
            equipment_type="CHILLER",
            likely_diagnosis="fouling",
            success_rate=0.9,
        )
        d = pattern.to_dict()
        restored = DecisionPattern.from_dict(d)
        assert restored.event_type == "test"
        assert restored.success_rate == 0.9
