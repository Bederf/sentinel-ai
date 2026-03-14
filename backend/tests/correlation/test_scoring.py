"""
Tests for weighted scoring formula (Phase 156-02).

Tests pure scoring logic (no DB required) plus DB-backed entity helpers.
"""

from __future__ import annotations

import os
import uuid

import pytest

from app.services.correlation.scoring import (
    CORRELATION_THRESHOLD,
    ScoringResult,
    _location_similarity,
    _severity_alignment_score,
    _shared_entity_ratio,
    _time_proximity_score,
    _type_compatibility_score,
    get_entity_count,
    get_shared_entities,
    score_signal_pair,
)

# ============================================================================
# 1. Location similarity
# ============================================================================


class TestLocationSimilarity:
    def test_exact_room_match(self):
        score, label = _location_similarity("Fairlands/FA1/1Q4/MR10", "Fairlands/FA1/1Q4/MR10")
        assert score == 1.0
        assert label == "exact"

    def test_same_floor_quadrant(self):
        score, label = _location_similarity("Fairlands/FA1/1Q4/MR10", "Fairlands/FA1/1Q4/MR11")
        assert score == 0.85
        assert label == "floor"

    def test_same_building(self):
        score, label = _location_similarity("Fairlands/FA1/1Q4/MR10", "Fairlands/FA1/2Q1/MR03")
        assert score == 0.65
        assert label == "building"

    def test_same_campus_only(self):
        score, label = _location_similarity("Fairlands/FA1/1Q4/MR10", "Fairlands/FA2/2Q1/MR03")
        assert score == 0.40
        assert label == "campus"

    def test_no_match(self):
        score, label = _location_similarity("Fairlands/FA1/1Q4/MR10", "Other/OT1/1Q1/MR01")
        assert score == 0.0
        assert label == "none"

    def test_wildcard_match_all(self):
        score, label = _location_similarity("Fairlands/FA1/1Q4/MR10", "Fairlands/*/*/*")
        assert score == 1.0
        assert label == "exact"

    def test_wildcard_partial(self):
        score, label = _location_similarity("Fairlands/FA1/1Q4/MR10", "Fairlands/FA1/1Q4/*")
        assert score == 1.0
        assert label == "exact"

    def test_wildcard_building_mismatch(self):
        # Fairlands matches, FA2 != FA1, but * matches 1Q4, * matches MR10
        score, label = _location_similarity("Fairlands/FA1/1Q4/MR10", "Fairlands/FA2/*/*")
        assert score == 0.85
        assert label == "floor"


# ============================================================================
# 2. Shared entity ratio
# ============================================================================


class TestSharedEntityRatio:
    def test_no_entities_either_side(self):
        assert _shared_entity_ratio([], 0, 0) == 0.0

    def test_no_shared_entities(self):
        assert _shared_entity_ratio([], 3, 4) == 0.0

    def test_some_shared(self):
        ratio = _shared_entity_ratio(["Thandi Dineka", "Block booking"], 4, 6)
        assert abs(ratio - 2 / 6) < 0.001

    def test_case_insensitive_dedup(self):
        ratio = _shared_entity_ratio(["thandi dineka", "Thandi Dineka", "THANDI DINEKA"], 3, 3)
        # Only 1 distinct entity
        assert abs(ratio - 1 / 3) < 0.001

    def test_all_shared(self):
        ratio = _shared_entity_ratio(["A", "B", "C"], 3, 3)
        assert ratio == 1.0


# ============================================================================
# 3. Time proximity
# ============================================================================


class TestTimeProximity:
    def test_zero_days(self):
        assert _time_proximity_score(0.0) == 1.0

    def test_thirty_days(self):
        assert abs(_time_proximity_score(30.0) - 0.5) < 0.001

    def test_sixty_days(self):
        assert _time_proximity_score(60.0) == 0.0

    def test_beyond_sixty(self):
        assert _time_proximity_score(90.0) == 0.0

    def test_half_day(self):
        assert abs(_time_proximity_score(0.5) - (1.0 - 0.5 / 60.0)) < 0.001


# ============================================================================
# 4. Type compatibility
# ============================================================================


class TestTypeCompatibility:
    def test_complaint_escalation(self):
        assert _type_compatibility_score("complaint_email", "escalation_email") == 0.95

    def test_bidirectional(self):
        assert _type_compatibility_score("escalation_email", "complaint_email") == 0.95

    def test_same_type(self):
        assert _type_compatibility_score("complaint_email", "complaint_email") == 0.90

    def test_unlisted_pair_default(self):
        assert _type_compatibility_score("unknown_type", "other_type") == 0.40

    def test_resolution_complaint_low(self):
        assert _type_compatibility_score("resolution_email", "complaint_email") == 0.30


# ============================================================================
# 5. Severity alignment
# ============================================================================


class TestSeverityAlignment:
    def test_same_severity(self):
        assert _severity_alignment_score("medium", "medium") == 1.0

    def test_one_apart(self):
        assert _severity_alignment_score("medium", "high") == 0.75

    def test_two_apart(self):
        assert _severity_alignment_score("low", "high") == 0.50

    def test_three_apart(self):
        assert _severity_alignment_score("low", "critical") == 0.25


# ============================================================================
# 6. Full signal pair scoring
# ============================================================================


class TestScoreSignalPair:
    def test_two_complaints_same_campus_no_entities(self):
        """Signals 1 and 2: same campus, different buildings, 7 days, no shared entities."""
        anchor = {
            "id": "a1",
            "signal_type": "complaint_email",
            "severity": "medium",
            "location_ref": "Fairlands/FA1/1Q4/MR10",
        }
        candidate = {
            "id": "a2",
            "signal_type": "complaint_email",
            "severity": "medium",
            "location_ref": "Fairlands/FA2/2Q1/MR03",
        }
        result = score_signal_pair(
            anchor,
            candidate,
            shared_entities=[],
            days_between=7.0,
            anchor_entity_count=3,
            candidate_entity_count=3,
        )
        assert isinstance(result, ScoringResult)
        # location=0.40 * 0.30 = 0.12
        # entity=0.0 * 0.25 = 0.0
        # time=(1-7/60) * 0.20 ≈ 0.176
        # type=0.90 * 0.15 = 0.135
        # severity=1.0 * 0.10 = 0.10
        # total ≈ 0.531
        assert 0.45 <= result.score <= 0.65, f"Score {result.score} not in expected range"
        assert result.evidence_basis  # non-empty string

    def test_complaint_escalation_shared_topic_above_threshold(self):
        """Signals 1 and 5: complaint + escalation, 29 days, shared topic."""
        anchor = {
            "id": "a1",
            "signal_type": "complaint_email",
            "severity": "medium",
            "location_ref": "Fairlands/FA1/1Q4/MR10",
        }
        candidate = {
            "id": "a5",
            "signal_type": "escalation_email",
            "severity": "high",
            "location_ref": "Fairlands/*/*/*",
        }
        result = score_signal_pair(
            anchor,
            candidate,
            shared_entities=["Room availability"],
            days_between=29.0,
            anchor_entity_count=3,
            candidate_entity_count=3,
        )
        # location: wildcard = 1.0 * 0.30 = 0.30
        # entity: 1/3 * 0.25 ≈ 0.083
        # time: (1 - 29/60) * 0.20 ≈ 0.103
        # type: 0.95 * 0.15 = 0.1425
        # severity: 0.75 * 0.10 = 0.075
        # total ≈ 0.703
        assert result.above_threshold, f"Expected above threshold, got {result.score}"
        assert result.score > 0.55

    def test_thandi_signals_high_score(self):
        """Signals 3 and 7: both from Thandi, same location, shared entity."""
        anchor = {
            "id": "a3",
            "signal_type": "observation_email",
            "severity": "low",
            "location_ref": "Fairlands/FA1/1Q4/*",
        }
        candidate = {
            "id": "a7",
            "signal_type": "observation_email",
            "severity": "medium",
            "location_ref": "Fairlands/FA1/1Q4/*",
        }
        result = score_signal_pair(
            anchor,
            candidate,
            shared_entities=["Thandi Dineka", "Block booking"],
            days_between=26.0,
            anchor_entity_count=3,
            candidate_entity_count=3,
        )
        # location: exact(wildcard match) 1.0 * 0.30 = 0.30
        # entity: 2/3 * 0.25 ≈ 0.167
        # time: (1 - 26/60) * 0.20 ≈ 0.113
        # type: 0.85 * 0.15 = 0.1275
        # severity: 0.75 * 0.10 = 0.075
        # total ≈ 0.783
        assert result.score > 0.70, f"Expected > 0.70, got {result.score}"
        assert result.above_threshold

    def test_evidence_basis_format(self):
        """Evidence basis should contain all 5 component labels."""
        anchor = {
            "signal_type": "complaint_email",
            "severity": "medium",
            "location_ref": "Fairlands/FA1/1Q4/MR10",
        }
        candidate = {
            "signal_type": "complaint_email",
            "severity": "medium",
            "location_ref": "Fairlands/FA1/1Q4/MR10",
        }
        result = score_signal_pair(anchor, candidate, [], 0.0, 0, 0)
        assert "location=" in result.evidence_basis
        assert "entity=" in result.evidence_basis
        assert "time=" in result.evidence_basis
        assert "type=" in result.evidence_basis
        assert "severity=" in result.evidence_basis

    def test_threshold_constant(self):
        assert CORRELATION_THRESHOLD == 0.55


# ============================================================================
# 7. DB-backed entity helpers (requires Supabase)
# ============================================================================

DB_DSN = os.environ.get(
    "CORRELATION_TEST_DSN",
    "postgresql://postgres:postgres@localhost:55322/postgres",
)


@pytest.fixture(scope="module")
def db_conn():
    """Shared DB connection for entity helper tests."""
    import psycopg2

    try:
        connection = psycopg2.connect(DB_DSN)
        connection.autocommit = True
        yield connection
        connection.close()
    except psycopg2.OperationalError:
        pytest.skip("Supabase not available at localhost:55322")


class TestEntityHelpers:
    def test_get_shared_entities(self, db_conn):
        """Insert two signals with overlapping entities, verify shared lookup."""
        import psycopg2.extras

        cur = db_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        sig_a = uuid.uuid4()
        sig_b = uuid.uuid4()
        ent_ids = [uuid.uuid4() for _ in range(4)]

        try:
            # Insert two signals
            for sig_id in [sig_a, sig_b]:
                cur.execute(
                    """
                    INSERT INTO signal (id, source_module, signal_type, severity, location_ref)
                    VALUES (%s, 'manual_entry', 'manual_observation', 'low', 'Test/X/1Q1/MR01')
                    """,
                    (str(sig_id),),
                )

            # Signal A entities: "Alice", "Block booking"
            cur.execute(
                "INSERT INTO entity (id, signal_id, entity_type, entity_value) VALUES (%s, %s, 'person', 'Alice')",
                (str(ent_ids[0]), str(sig_a)),
            )
            cur.execute(
                "INSERT INTO entity (id, signal_id, entity_type, entity_value) "
                "VALUES (%s, %s, 'booking_ref', 'Block booking')",
                (str(ent_ids[1]), str(sig_a)),
            )

            # Signal B entities: "alice" (different case), "Bob"
            cur.execute(
                "INSERT INTO entity (id, signal_id, entity_type, entity_value) VALUES (%s, %s, 'person', 'alice')",
                (str(ent_ids[2]), str(sig_b)),
            )
            cur.execute(
                "INSERT INTO entity (id, signal_id, entity_type, entity_value) VALUES (%s, %s, 'person', 'Bob')",
                (str(ent_ids[3]), str(sig_b)),
            )

            shared = get_shared_entities(db_conn, sig_a, sig_b)
            assert len(shared) == 1
            assert shared[0] == "alice"  # lower-cased

        finally:
            for eid in ent_ids:
                cur.execute("DELETE FROM entity WHERE id = %s", (str(eid),))
            for sid in [sig_a, sig_b]:
                cur.execute("DELETE FROM signal WHERE id = %s", (str(sid),))
            cur.close()

    def test_get_entity_count(self, db_conn):
        """Count entities for a signal."""
        import psycopg2.extras

        cur = db_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        sig_id = uuid.uuid4()
        ent_ids = [uuid.uuid4() for _ in range(3)]

        try:
            cur.execute(
                """
                INSERT INTO signal (id, source_module, signal_type, severity, location_ref)
                VALUES (%s, 'manual_entry', 'manual_observation', 'low', 'Test/X/1Q1/MR01')
                """,
                (str(sig_id),),
            )
            for i, eid in enumerate(ent_ids):
                cur.execute(
                    "INSERT INTO entity (id, signal_id, entity_type, entity_value) VALUES (%s, %s, 'person', %s)",
                    (str(eid), str(sig_id), f"Person{i}"),
                )

            count = get_entity_count(db_conn, sig_id)
            assert count == 3

        finally:
            for eid in ent_ids:
                cur.execute("DELETE FROM entity WHERE id = %s", (str(eid),))
            cur.execute("DELETE FROM signal WHERE id = %s", (str(sig_id),))
            cur.close()

    def test_get_entity_count_no_entities(self, db_conn):
        """Signal with no entities returns 0."""
        import psycopg2.extras

        cur = db_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        sig_id = uuid.uuid4()

        try:
            cur.execute(
                """
                INSERT INTO signal (id, source_module, signal_type, severity, location_ref)
                VALUES (%s, 'manual_entry', 'manual_observation', 'low', 'Test/X/1Q1/MR01')
                """,
                (str(sig_id),),
            )
            count = get_entity_count(db_conn, sig_id)
            assert count == 0
        finally:
            cur.execute("DELETE FROM signal WHERE id = %s", (str(sig_id),))
            cur.close()
