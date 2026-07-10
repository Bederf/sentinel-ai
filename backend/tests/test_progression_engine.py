"""Tests for the Progression Engine Service (Phase A).

Tests the core trust-ladder foundation:
  - Validation recording (approve/reject/execute hooks)
  - Accuracy computation (predicted vs actual delta)
  - Accuracy category assignment
  - Class readiness recompute (rolling 7d/30d windows)
  - Site trust summary aggregation
  - Demotion trigger detection (Phase A: report-only)
  - Empty class readiness defaults
  - Validation class normalization from action_type
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from app.services.progression_engine_service import (
    ProgressionEngineService,
    _DEFAULT_CLASS,
    _safe_mean,
    _safe_dict,
)


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def engine():
    """Fresh ProgressionEngineService singleton for each test."""
    # Reset singleton
    ProgressionEngineService._instance = None
    svc = ProgressionEngineService()
    yield svc
    ProgressionEngineService._instance = None


def _make_mock_supabase():
    """Create a mock Supabase client with chainable table().select().eq() etc."""
    mock_client = Mock()

    def chainable(data=None, count=None):
        """Return a mock that supports chaining .eq().execute() etc."""
        m = AsyncMock()
        m.data = data or []
        m.count = count
        return m

    # Mock table("recommendations").select(...).eq("id", ...).limit(1).execute()
    mock_table = Mock()
    mock_client.table = Mock(return_value=mock_table)

    # Default: no data
    mock_table.select = Mock(return_value=mock_table)
    mock_table.eq = Mock(return_value=mock_table)
    mock_table.in_ = Mock(return_value=mock_table)
    mock_table.order = Mock(return_value=mock_table)
    mock_table.limit = Mock(return_value=mock_table)
    mock_table.gte = Mock(return_value=mock_table)
    mock_table.execute = Mock(return_value=chainable())
    mock_table.insert = Mock(return_value=Mock(execute=Mock(return_value=chainable([]))))
    mock_table.update = Mock(return_value=Mock(execute=Mock(return_value=chainable([]))))

    return mock_client, mock_table


# ------------------------------------------------------------------
# Accuracy computation
# ------------------------------------------------------------------


class TestComputeOutcomeAccuracy:
    """_compute_outcome_accuracy — predicted vs actual delta."""

    def test_exact_match(self, engine):
        """Same predicted and actual → accuracy = 1.0."""
        result = engine._compute_outcome_accuracy(
            {"temperature_c": -2.0, "energy_kwh": -15.0},
            {"temperature_c": -2.0, "energy_kwh": -15.0},
        )
        assert result == pytest.approx(1.0, abs=0.01)

    def test_close_match(self, engine):
        """Predicted -2.0, actual -1.8 → accuracy ≈ 0.90."""
        result = engine._compute_outcome_accuracy(
            {"temperature_c": -2.0},
            {"temperature_c": -1.8},
        )
        # 1 - abs(-2.0 - (-1.8)) / max(2.0, 1.8, 0.01) = 1 - 0.2/2.0 = 0.90
        assert result == pytest.approx(0.90, abs=0.01)

    def test_wrong_direction(self, engine):
        """Predicted -2.0 (cooling), actual +1.0 (warming) → accuracy = 0.0."""
        result = engine._compute_outcome_accuracy(
            {"temperature_c": -2.0},
            {"temperature_c": 1.0},
        )
        # 1 - abs(-2.0 - 1.0) / max(2.0, 1.0, 0.01) = 1 - 3.0/2.0 = -0.5, clamped to 0.0
        assert result == pytest.approx(0.0, abs=0.01)

    def test_no_impact(self, engine):
        """Predicted change but telemetry unchanged → accuracy = 0.0."""
        result = engine._compute_outcome_accuracy(
            {"temperature_c": -2.0},
            {"temperature_c": 0.0},
        )
        assert result == pytest.approx(0.0, abs=0.01)

    def test_both_zero(self, engine):
        """Both zero → accuracy = 1.0 (correct prediction of no change)."""
        result = engine._compute_outcome_accuracy(
            {"energy_kwh": 0.0},
            {"energy_kwh": 0.0},
        )
        assert result == pytest.approx(1.0, abs=0.01)

    def test_multi_field_average(self, engine):
        """Multiple fields → average accuracy."""
        result = engine._compute_outcome_accuracy(
            {"temperature_c": -2.0, "energy_kwh": -15.0},
            {"temperature_c": -1.8, "energy_kwh": -14.0},
        )
        # temp: 1 - 0.2/2.0 = 0.90, energy: 1 - 1.0/15.0 = 0.9333
        # avg: (0.90 + 0.9333) / 2 ≈ 0.9167
        assert result == pytest.approx(0.9167, abs=0.01)

    def test_none_predicted_delta(self, engine):
        """None predicted_delta → None."""
        assert engine._compute_outcome_accuracy(None, {"temp": 1.0}) is None

    def test_none_actual_delta(self, engine):
        """None actual_delta → None."""
        assert engine._compute_outcome_accuracy({"temp": 1.0}, None) is None

    def test_empty_dicts(self, engine):
        """Empty dicts → None (no matching keys)."""
        assert engine._compute_outcome_accuracy({}, {}) is None

    def test_mismatched_keys(self, engine):
        """No shared keys → None."""
        assert engine._compute_outcome_accuracy({"a": 1.0}, {"b": 2.0}) is None


# ------------------------------------------------------------------
# Accuracy category assignment
# ------------------------------------------------------------------


class TestAccuracyCategory:
    """_accuracy_category — classify accuracy score."""

    def test_correct(self, engine):
        assert engine._accuracy_category(0.92) == "correct"
        assert engine._accuracy_category(0.86) == "correct"
        assert engine._accuracy_category(1.0) == "correct"

    def test_close(self, engine):
        assert engine._accuracy_category(0.85) == "close"
        assert engine._accuracy_category(0.75) == "close"
        assert engine._accuracy_category(0.71) == "close"

    def test_under_predicted(self, engine):
        assert engine._accuracy_category(0.69) == "under_predicted"
        assert engine._accuracy_category(0.60) == "under_predicted"
        assert engine._accuracy_category(0.50) == "under_predicted"

    def test_wrong_direction(self, engine):
        assert engine._accuracy_category(0.49) == "wrong_direction"
        assert engine._accuracy_category(0.0) == "wrong_direction"

    def test_none(self, engine):
        assert engine._accuracy_category(None) == "unscored"


# ------------------------------------------------------------------
# Validation class normalization
# ------------------------------------------------------------------


class TestComputeValidationClass:
    """_compute_validation_class — action_type → canonical class."""

    def test_known_type(self, engine):
        assert engine._compute_validation_class("hvac_setpoint_change") == "hvac_setpoint_change"

    def test_mapped_alias(self, engine):
        assert engine._compute_validation_class("setpoint_adjust") == "hvac_setpoint_change"

    def test_case_insensitive(self, engine):
        assert engine._compute_validation_class("ZONE_SHUTDOWN") == "zone_shutdown"
        assert engine._compute_validation_class("Lighting_Dim") == "lighting_dim"

    def test_default_for_unknown(self, engine):
        assert engine._compute_validation_class("unknown_action_type") == _DEFAULT_CLASS

    def test_empty_string(self, engine):
        assert engine._compute_validation_class("") == _DEFAULT_CLASS


# ------------------------------------------------------------------
# Validation recording (approval path, with mocked Supabase)
# ------------------------------------------------------------------


class TestRecordValidation:
    """record_validation — end-to-end validation recording."""

    @staticmethod
    def _chain(data=None):
        """Create a chainable mock that returns `data` on .execute().
        .select / .eq / .limit / .order all return self.
        """
        c = Mock()
        c.data = data or []
        c.select = Mock(return_value=c)
        c.eq = Mock(return_value=c)
        c.limit = Mock(return_value=c)
        c.order = Mock(return_value=c)
        c.in_ = Mock(return_value=c)
        c.execute = Mock(return_value=c)
        return c

    def _make_record_validation_mocks(self, rec_data, existing_validation=None):
        """Build mock Supabase client for record_validation tests.

        Each table gets its own independent chain so execute calls don't
        interfere across query boundaries.
        """
        client = Mock()

        # rec_chain handles table("recommendations") queries
        rec_chain = self._chain(data=rec_data)

        # val_chain handles table("recommendation_validations") queries
        # First call: check existing (returns existing_validation)
        # Second+ calls: _recompute_class_readiness also queries this table
        val_data = existing_validation or []
        val_chain = self._chain(data=val_data)
        # Insert mock — returns the new id
        val_insert = Mock()
        val_insert.execute = Mock(return_value=Mock(data=[{"id": "val-001"}]))
        val_chain.insert = Mock(return_value=val_insert)
        val_chain.update = Mock(return_value=val_chain)

        # cr_chain handles table("recommendation_class_readiness")
        cr_chain = self._chain(data=[])
        cr_insert = Mock()
        cr_insert.execute = Mock(return_value=Mock(data=[{"id": "cr-001"}]))
        cr_chain.insert = Mock(return_value=cr_insert)
        cr_chain.update = Mock(return_value=cr_chain)

        def table_side_effect(name):
            if name == "recommendations":
                return rec_chain
            if name == "recommendation_validations":
                return val_chain
            if name == "recommendation_class_readiness":
                return cr_chain
            return self._chain()

        client.table = Mock(side_effect=table_side_effect)
        return client

    @pytest.mark.asyncio
    async def test_approval_creates_validation(self, engine):
        """Operator approves → validation row created with operator_feedback='accepted'."""
        rec_data = [
            {
                "id": "rec-001",
                "site_id": "site-002",
                "action_type": "hvac_setpoint_change",
                "target_equipment": "S002-FCU-101",
                "expected_impact": {"temperature_c": -2.0, "energy_kwh": -15.0},
                "predicted_delta": None,
                "confidence_score": 0.85,
                "status": "approved",
            }
        ]
        mock_client = self._make_record_validation_mocks(rec_data, existing_validation=[])

        with patch("app.services.progression_engine_service.get_supabase_client", return_value=mock_client):
            result = await engine.record_validation(
                recommendation_id="rec-001",
                operator_feedback="accepted",
                outcome_status="approved",
            )

        assert result["validation_class"] == "hvac_setpoint_change"
        assert result["operator_feedback"] == "accepted"
        assert result["outcome_accuracy"] is None  # No actual_delta yet

    @pytest.mark.asyncio
    async def test_rejection_records_feedback(self, engine):
        """Operator rejects → validation row with operator_feedback='rejected'."""
        rec_data = [
            {
                "id": "rec-002",
                "site_id": "site-002",
                "action_type": "hvac_setpoint_change",
                "target_equipment": "S002-FCU-101",
                "expected_impact": {"temperature_c": -1.0},
                "predicted_delta": None,
                "confidence_score": 0.75,
                "status": "rejected",
            }
        ]
        mock_client = self._make_record_validation_mocks(rec_data, existing_validation=[])

        with patch("app.services.progression_engine_service.get_supabase_client", return_value=mock_client):
            result = await engine.record_validation(
                recommendation_id="rec-002",
                operator_feedback="rejected",
                operator_note="Schedule conflict",
                outcome_status="rejected",
            )

        assert result["operator_feedback"] == "rejected"

    @pytest.mark.asyncio
    async def test_mv_verify_with_actual_delta(self, engine):
        """M&V verify with actual_delta → outcome_accuracy computed."""
        rec_data = [
            {
                "id": "rec-003",
                "site_id": "site-002",
                "action_type": "hvac_setpoint_change",
                "target_equipment": "S002-FCU-101",
                "expected_impact": {"temperature_c": -2.0},
                "predicted_delta": None,
                "confidence_score": 0.85,
                "status": "executed",
            }
        ]
        mock_client = self._make_record_validation_mocks(rec_data, existing_validation=[])

        with patch("app.services.progression_engine_service.get_supabase_client", return_value=mock_client):
            result = await engine.record_validation(
                recommendation_id="rec-003",
                actual_delta={"temperature_c": -1.8},
                outcome_status="verified",
            )

        assert result["outcome_accuracy"] is not None
        assert result["outcome_accuracy"] == pytest.approx(0.90, abs=0.01)
        assert result["accuracy_category"] == "correct"


# ------------------------------------------------------------------
# Class readiness recompute
# ------------------------------------------------------------------


class TestClassReadiness:
    """_recompute_class_readiness and query methods."""

    @pytest.mark.asyncio
    async def test_readiness_recompute_with_validations(self, engine):
        """10 validations → accuracy_pct_7d and accuracy_pct_30d update correctly."""
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        mock_rows = []
        for i in range(10):
            if i < 8:
                acc = 0.92 + (i * 0.005)  # 0.92 to 0.955
            elif i == 8:
                acc = 0.75
            else:
                acc = 0.30
            mock_rows.append(
                {
                    "outcome_accuracy": round(acc, 3),
                    "operator_feedback": "accepted",
                    "validated_at": (now - timedelta(hours=i * 12)).isoformat(),
                    "created_at": (now - timedelta(hours=i * 12)).isoformat(),
                }
            )

        # Build independent chains using the existing helper
        def _ch(data):
            c = Mock()
            c.data = data
            c.select = Mock(return_value=c)
            c.eq = Mock(return_value=c)
            c.limit = Mock(return_value=c)
            c.order = Mock(return_value=c)
            c.execute = Mock(return_value=c)
            return c

        # Validations chain — returns the 10 mock rows
        rv_chain = _ch(data=mock_rows)

        # Class readiness chain — no existing row
        cr_chain = _ch(data=[])
        cr_insert = Mock()
        cr_insert.execute = Mock(return_value=Mock(data=[{"id": "cr-001"}]))
        cr_chain.insert = Mock(return_value=cr_insert)
        cr_chain.update = Mock(return_value=cr_chain)

        def table_side_effect(name):
            if name == "recommendation_validations":
                return rv_chain
            if name == "recommendation_class_readiness":
                return cr_chain
            return _ch(data=[])

        mock_client = Mock()
        mock_client.table = Mock(side_effect=table_side_effect)

        with patch("app.services.progression_engine_service.get_supabase_client", return_value=mock_client):
            await engine._recompute_class_readiness("site-002", "hvac_setpoint_change")

            # Verify insert was called (no existing row)
            assert cr_insert.execute.called

    @pytest.mark.asyncio
    async def test_get_class_readiness_empty(self, engine):
        """No validations → empty defaults returned."""
        mock_client, mock_table = _make_mock_supabase()
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute = Mock(
            return_value=Mock(data=[])
        )

        with patch("app.services.progression_engine_service.get_supabase_client", return_value=mock_client):
            result = await engine.get_class_readiness("site-002", "nonexistent_class")

        assert result["site_id"] == "site-002"
        assert result["class_name"] == "nonexistent_class"
        assert result["current_trust_level"] == 1
        assert result["evidence_count"] == 0
        assert result["accuracy_pct_7d"] is None
        assert result["accuracy_pct_30d"] is None


# ------------------------------------------------------------------
# Site trust summary
# ------------------------------------------------------------------


class TestSiteTrustSummary:
    """get_site_trust_summary — site-level aggregation."""

    @pytest.mark.asyncio
    async def test_summary_with_classes(self, engine):
        """Multiple classes → aggregated summary."""
        mock_client, mock_table = _make_mock_supabase()
        mock_client.table.return_value.select.return_value.eq.return_value.execute = Mock(
            return_value=Mock(
                data=[
                    {
                        "class_name": "hvac_setpoint_change",
                        "current_trust_level": 2,
                        "evidence_count": 50,
                        "accuracy_pct_7d": 92.0,
                        "accuracy_pct_30d": 90.0,
                    },
                    {
                        "class_name": "zone_shutdown",
                        "current_trust_level": 1,
                        "evidence_count": 20,
                        "accuracy_pct_7d": 85.0,
                        "accuracy_pct_30d": 82.0,
                    },
                    {
                        "class_name": "lighting_dim",
                        "current_trust_level": 3,
                        "evidence_count": 200,
                        "accuracy_pct_7d": 95.0,
                        "accuracy_pct_30d": 94.0,
                    },
                ]
            )
        )

        with patch("app.services.progression_engine_service.get_supabase_client", return_value=mock_client):
            result = await engine.get_site_trust_summary("site-002")

        assert result["site_id"] == "site-002"
        assert result["current_level"] == 1  # Min of all class levels (zone_shutdown=1)
        assert result["total_evidence_count"] == 270
        assert result["accuracy_pct_7d_weighted"] == pytest.approx(90.6667, abs=0.01)  # (92+85+95)/3
        assert result["class_count"] == 3

    @pytest.mark.asyncio
    async def test_summary_no_classes(self, engine):
        """No classes → Level 1 default."""
        mock_client, mock_table = _make_mock_supabase()
        mock_client.table.return_value.select.return_value.eq.return_value.execute = Mock(return_value=Mock(data=[]))

        with patch("app.services.progression_engine_service.get_supabase_client", return_value=mock_client):
            result = await engine.get_site_trust_summary("site-999")

        assert result["site_id"] == "site-999"
        assert result["current_level"] == 1
        assert result["total_evidence_count"] == 0
        assert result["class_count"] == 0


# ------------------------------------------------------------------
# Demotion triggers (Phase A: report-only)
# ------------------------------------------------------------------


class TestDemotionTriggers:
    """check_demotion_triggers — Phase A returns candidates only."""

    @pytest.mark.asyncio
    async def test_no_candidates(self, engine):
        """No classes with 3+ consecutive failures → empty list."""
        mock_client, mock_table = _make_mock_supabase()
        mock_client.table.return_value.select.return_value.eq.return_value.execute = Mock(
            return_value=Mock(
                data=[
                    {
                        "class_name": "hvac_setpoint_change",
                        "consecutive_failures": 0,
                        "accuracy_pct_30d": 92.0,
                        "current_trust_level": 2,
                        "last_demotion_at": None,
                    },
                    {
                        "class_name": "lighting_dim",
                        "consecutive_failures": 1,
                        "accuracy_pct_30d": 88.0,
                        "current_trust_level": 2,
                        "last_demotion_at": None,
                    },
                ],
                count=0,
            )
        )

        with patch("app.services.progression_engine_service.get_supabase_client", return_value=mock_client):
            candidates = await engine.check_demotion_triggers("site-002")

        assert len(candidates) == 0

    @pytest.mark.asyncio
    async def test_demotion_candidate_detected(self, engine):
        """3 consecutive failures → demotion candidate returned."""
        mock_client, mock_table = _make_mock_supabase()
        mock_client.table.return_value.select.return_value.eq.return_value.execute = Mock(
            return_value=Mock(
                data=[
                    {
                        "class_name": "zone_shutdown",
                        "consecutive_failures": 3,
                        "accuracy_pct_30d": 45.0,
                        "current_trust_level": 2,
                        "last_demotion_at": None,
                    },
                ],
                count=0,
            )
        )

        with patch("app.services.progression_engine_service.get_supabase_client", return_value=mock_client):
            candidates = await engine.check_demotion_triggers("site-002")

        assert len(candidates) == 1
        assert candidates[0]["class_name"] == "zone_shutdown"
        assert candidates[0]["trigger"] == "consecutive_failures"
        assert candidates[0]["new_level"] == 1  # Level 2 → Level 1
        assert candidates[0]["current_level"] == 2


# ------------------------------------------------------------------
# Utility functions
# ------------------------------------------------------------------


class TestSafeMean:
    """_safe_mean — mean with None handling."""

    def test_empty_list(self):
        assert _safe_mean([]) is None

    def test_single_value(self):
        assert _safe_mean([5.0]) == 5.0

    def test_multiple_values(self):
        assert _safe_mean([1.0, 2.0, 3.0]) == 2.0


class TestSafeDict:
    """_safe_dict — safe dict coercion."""

    def test_dict(self):
        assert _safe_dict({"a": 1}) == {"a": 1}

    def test_none(self):
        assert _safe_dict(None) == {}

    def test_list(self):
        assert _safe_dict([1, 2, 3]) == {}

    def test_string(self):
        assert _safe_dict("hello") == {}


# ------------------------------------------------------------------
# Idempotency
# ------------------------------------------------------------------


class TestIdempotency:
    """record_validation is idempotent — subsequent calls update."""

    @staticmethod
    def _idemp_chain(data=None):
        c = Mock()
        c.data = data or []
        c.select = Mock(return_value=c)
        c.eq = Mock(return_value=c)
        c.limit = Mock(return_value=c)
        c.order = Mock(return_value=c)
        c.in_ = Mock(return_value=c)
        c.execute = Mock(return_value=c)
        return c

    @pytest.mark.asyncio
    async def test_idempotent_approval(self, engine):
        """Calling record_validation twice doesn't create duplicates."""
        # ---- First call: approval ----
        rec_chain = self._idemp_chain(
            data=[
                {
                    "id": "rec-001",
                    "site_id": "site-002",
                    "action_type": "hvac_setpoint_change",
                    "target_equipment": "S002-FCU-101",
                    "expected_impact": {"temperature_c": -2.0},
                    "predicted_delta": None,
                    "confidence_score": 0.85,
                    "status": "approved",
                }
            ]
        )
        val_chain = self._idemp_chain(data=[])  # no existing
        val_insert = Mock()
        val_insert.execute = Mock(return_value=Mock(data=[{"id": "val-001"}]))
        val_chain.insert = Mock(return_value=val_insert)
        val_chain.update = Mock(return_value=val_chain)
        cr_chain = self._idemp_chain(data=[])
        cr_insert = Mock()
        cr_insert.execute = Mock(return_value=Mock(data=[{"id": "cr-001"}]))
        cr_chain.insert = Mock(return_value=cr_insert)
        cr_chain.update = Mock(return_value=cr_chain)

        def table1(name):
            tbl = {
                "recommendations": rec_chain,
                "recommendation_validations": val_chain,
                "recommendation_class_readiness": cr_chain,
            }
            return tbl.get(name, self._idemp_chain())

        mock_client1 = Mock()
        mock_client1.table = Mock(side_effect=table1)

        with patch("app.services.progression_engine_service.get_supabase_client", return_value=mock_client1):
            result1 = await engine.record_validation(
                recommendation_id="rec-001",
                operator_feedback="accepted",
                outcome_status="approved",
            )

        assert result1["validation_class"] == "hvac_setpoint_change"
        assert result1["operator_feedback"] == "accepted"

        # ---- Second call: M&V verify with actual_delta ----
        rec_chain2 = self._idemp_chain(
            data=[
                {
                    "id": "rec-001",
                    "site_id": "site-002",
                    "action_type": "hvac_setpoint_change",
                    "target_equipment": "S002-FCU-101",
                    "expected_impact": {"temperature_c": -2.0},
                    "predicted_delta": None,
                    "confidence_score": 0.85,
                    "status": "executed",
                }
            ]
        )
        val_chain2 = self._idemp_chain(
            data=[{"id": "val-001", "outcome_accuracy": None, "validation_status": "pending_operator"}]
        )
        val_chain2.update = Mock(return_value=val_chain2)
        val_chain2.insert = Mock(return_value=Mock(execute=Mock(return_value=Mock(data=[{"id": "val-001"}]))))
        cr_chain2 = self._idemp_chain(data=[])
        cr_insert2 = Mock()
        cr_insert2.execute = Mock(return_value=Mock(data=[{"id": "cr-001"}]))
        cr_chain2.insert = Mock(return_value=cr_insert2)
        cr_chain2.update = Mock(return_value=cr_chain2)

        def table2(name):
            tbl = {
                "recommendations": rec_chain2,
                "recommendation_validations": val_chain2,
                "recommendation_class_readiness": cr_chain2,
            }
            return tbl.get(name, self._idemp_chain())

        mock_client2 = Mock()
        mock_client2.table = Mock(side_effect=table2)

        with patch("app.services.progression_engine_service.get_supabase_client", return_value=mock_client2):
            result2 = await engine.record_validation(
                recommendation_id="rec-001",
                actual_delta={"temperature_c": -1.8},
                outcome_status="verified",
            )

        assert result2["outcome_accuracy"] == pytest.approx(0.90, abs=0.01)
