"""
Migration test harness for Phase 155-01: Correlation Schema.

Validates that all tables, enums, constraints, indexes, triggers,
and seed data are correct. Green = schema is ready for Phase 155-02.

Requires local Supabase running at localhost:55322.
"""

import os
import uuid

import psycopg2
import psycopg2.extras
import pytest

DB_DSN = os.environ.get(
    "CORRELATION_TEST_DSN",
    "postgresql://postgres:postgres@localhost:55322/postgres",
)


@pytest.fixture(scope="module")
def conn():
    """Shared DB connection for all tests in module."""
    connection = psycopg2.connect(DB_DSN)
    connection.autocommit = True
    yield connection
    connection.close()


@pytest.fixture(scope="module")
def cur(conn):
    """Shared cursor with dict-like rows."""
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    yield cursor
    cursor.close()


# ============================================================================
# 1. All 9 tables exist
# ============================================================================

EXPECTED_TABLES = [
    "email_thread",
    "signal",
    "issue_cluster",
    "issue_classification",
    "entity",
    "relationship",
    "issue_evidence",
    "role_assignment",
    "dashboard_card",
]


@pytest.mark.parametrize("table", EXPECTED_TABLES)
def test_table_exists(cur, table):
    cur.execute(
        "SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = %s",
        (table,),
    )
    assert cur.fetchone() is not None, f"Table '{table}' does not exist"


# ============================================================================
# 2. All 14 enums present
# ============================================================================

EXPECTED_ENUMS = [
    "source_module_enum",
    "signal_type_enum",
    "signal_subtype_enum",
    "severity_enum",
    "resolution_state_enum",
    "cluster_state_enum",
    "escalation_level_enum",
    "classification_domain_enum",
    "entity_type_enum",
    "node_type_enum",
    "edge_type_enum",
    "role_type_enum",
    "contradiction_rule_enum",
    "site_resolution_status_enum",
]


@pytest.mark.parametrize("enum_name", EXPECTED_ENUMS)
def test_enum_exists(cur, enum_name):
    cur.execute("SELECT 1 FROM pg_type WHERE typname = %s", (enum_name,))
    assert cur.fetchone() is not None, f"Enum '{enum_name}' does not exist"


# ============================================================================
# 3. Fairlands seed data
# ============================================================================


def test_fairlands_seed_count(cur):
    cur.execute("SELECT count(*) AS cnt FROM role_assignment")
    row = cur.fetchone()
    assert row["cnt"] >= 4, f"Expected >= 4 personas, got {row['cnt']}"


def test_thandi_uuid(cur):
    cur.execute("SELECT id FROM role_assignment WHERE person_name = 'Thandi Dineka'")
    row = cur.fetchone()
    assert row is not None, "Thandi Dineka not found"
    assert str(row["id"]) == "10000000-0000-0000-0000-000000000001"


def test_thandi_role_and_domains(cur):
    cur.execute(
        "SELECT role_type, location_scope, issue_domains FROM role_assignment WHERE person_name = 'Thandi Dineka'"
    )
    row = cur.fetchone()
    assert row["role_type"] == "concierge"
    assert row["location_scope"] == "Fairlands/*/*/*"
    domains = row["issue_domains"]
    assert "space_optimisation" in domains
    assert "workplace_experience" in domains


# ============================================================================
# 4. Signal table accepts known signal_type values
# ============================================================================


def test_signal_insert_complaint_email(cur, conn):
    sig_id = uuid.uuid4()
    cur.execute(
        """
        INSERT INTO signal (id, source_module, signal_type, severity, location_ref)
        VALUES (%s, 'email_helpdesk', 'complaint_email', 'medium', 'Fairlands/FA1/1Q4/MR10')
        RETURNING id
        """,
        (str(sig_id),),
    )
    row = cur.fetchone()
    assert row is not None
    # Cleanup
    cur.execute("DELETE FROM signal WHERE id = %s", (str(sig_id),))


def test_signal_insert_escalation_email(cur, conn):
    sig_id = uuid.uuid4()
    cur.execute(
        """
        INSERT INTO signal (id, source_module, signal_type, severity, location_ref)
        VALUES (%s, 'email_escalation', 'escalation_email', 'high', 'Fairlands/FA2/2Q1/TR03')
        RETURNING id
        """,
        (str(sig_id),),
    )
    row = cur.fetchone()
    assert row is not None
    cur.execute("DELETE FROM signal WHERE id = %s", (str(sig_id),))


# ============================================================================
# 5. FK constraints: signal.issue_cluster_id -> issue_cluster.id
# ============================================================================


def test_signal_fk_to_issue_cluster(cur):
    # Create cluster first
    cluster_id = uuid.uuid4()
    cur.execute(
        "INSERT INTO issue_cluster (id, title) VALUES (%s, 'Test cluster') RETURNING id",
        (str(cluster_id),),
    )

    # Create signal referencing it
    sig_id = uuid.uuid4()
    cur.execute(
        """
        INSERT INTO signal (id, source_module, signal_type, severity, location_ref, issue_cluster_id)
        VALUES (%s, 'manual_entry', 'manual_observation', 'low', 'Fairlands/FA1/1Q1/MR01', %s)
        RETURNING id
        """,
        (str(sig_id), str(cluster_id)),
    )
    assert cur.fetchone() is not None

    # Cleanup
    cur.execute("DELETE FROM signal WHERE id = %s", (str(sig_id),))
    cur.execute("DELETE FROM issue_cluster WHERE id = %s", (str(cluster_id),))


# ============================================================================
# 6. Generated column: issue_cluster.duration_days (via trigger)
# ============================================================================


def test_duration_days_computed(cur):
    cluster_id = uuid.uuid4()
    cur.execute(
        """
        INSERT INTO issue_cluster (id, title, first_seen_at)
        VALUES (%s, 'Duration test', now() - interval '10 days')
        RETURNING duration_days
        """,
        (str(cluster_id),),
    )
    row = cur.fetchone()
    # Should be approximately 10 (could be 9 or 10 depending on exact timing)
    assert row["duration_days"] >= 9, f"Expected ~10 days, got {row['duration_days']}"
    assert row["duration_days"] <= 11

    cur.execute("DELETE FROM issue_cluster WHERE id = %s", (str(cluster_id),))


# ============================================================================
# 7. CHECK constraints
# ============================================================================


def test_confidence_bounds_rejected(cur):
    """Confidence > 1 should be rejected."""
    with pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            """
            INSERT INTO signal (id, source_module, signal_type, severity, location_ref, confidence)
            VALUES (%s, 'manual_entry', 'manual_observation', 'low', 'Test/X/1Q1/MR01', 1.50)
            """,
            (str(uuid.uuid4()),),
        )
    cur.execute("ROLLBACK")


def test_is_managed_true_without_site_rejected(cur):
    """is_managed=true with site_id=NULL must be rejected."""
    with pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            """
            INSERT INTO signal (id, source_module, signal_type, severity, location_ref, is_managed, site_id)
            VALUES (%s, 'manual_entry', 'manual_observation', 'low', 'Test/X/1Q1/MR01', true, NULL)
            """,
            (str(uuid.uuid4()),),
        )
    cur.execute("ROLLBACK")


def test_is_managed_false_without_site_accepted(cur):
    """is_managed=false with site_id=NULL should succeed."""
    sig_id = uuid.uuid4()
    cur.execute(
        """
        INSERT INTO signal (id, source_module, signal_type, severity, location_ref, is_managed, site_id)
        VALUES (%s, 'manual_entry', 'manual_observation', 'low', 'Test/X/1Q1/MR01', false, NULL)
        RETURNING id
        """,
        (str(sig_id),),
    )
    assert cur.fetchone() is not None
    cur.execute("DELETE FROM signal WHERE id = %s", (str(sig_id),))


# ============================================================================
# 8. Self-referential FK: signal.parent_signal_id -> signal.id
# ============================================================================


def test_self_referential_parent_signal(cur):
    parent_id = uuid.uuid4()
    child_id = uuid.uuid4()

    cur.execute(
        """
        INSERT INTO signal (id, source_module, signal_type, severity, location_ref)
        VALUES (%s, 'email_helpdesk', 'complaint_email', 'medium', 'Fairlands/FA1/1Q4/MR10')
        """,
        (str(parent_id),),
    )

    cur.execute(
        """
        INSERT INTO signal (id, source_module, signal_type, severity, location_ref, parent_signal_id, emits_multiple)
        VALUES (%s, 'email_helpdesk', 'escalation_email', 'high', 'Fairlands/FA1/1Q4/MR10', %s, true)
        RETURNING id
        """,
        (str(child_id), str(parent_id)),
    )
    assert cur.fetchone() is not None

    cur.execute("DELETE FROM signal WHERE id = %s", (str(child_id),))
    cur.execute("DELETE FROM signal WHERE id = %s", (str(parent_id),))


# ============================================================================
# 9-11. Multi-site signal insertion tests
# ============================================================================


def test_signal_null_site_unresolved(cur):
    """Signal with site_id=NULL and site_resolution_status='unresolved' inserts OK."""
    sig_id = uuid.uuid4()
    cur.execute(
        """
        INSERT INTO signal (id, source_module, signal_type, severity, location_ref,
                           site_id, is_managed, site_resolution_status)
        VALUES (%s, 'manual_entry', 'manual_observation', 'low', 'Unknown/X/1Q1/MR01',
                NULL, false, 'unresolved')
        RETURNING id
        """,
        (str(sig_id),),
    )
    assert cur.fetchone() is not None
    cur.execute("DELETE FROM signal WHERE id = %s", (str(sig_id),))


def test_signal_unmanaged_inserts_ok(cur):
    """Signal with is_managed=false does not block insertion."""
    sig_id = uuid.uuid4()
    cur.execute(
        """
        INSERT INTO signal (id, source_module, signal_type, severity, location_ref, is_managed)
        VALUES (%s, 'external_api', 'external_event', 'low', 'Other/X/1Q1/MR01', false)
        RETURNING id
        """,
        (str(sig_id),),
    )
    assert cur.fetchone() is not None
    cur.execute("DELETE FROM signal WHERE id = %s", (str(sig_id),))


def test_signal_site_fk_works(cur):
    """Signal with valid site_id FK works when site exists."""
    # Get an existing site
    cur.execute("SELECT id FROM sites LIMIT 1")
    site_row = cur.fetchone()
    if site_row is None:
        pytest.skip("No sites in database")

    sig_id = uuid.uuid4()
    cur.execute(
        """
        INSERT INTO signal (id, source_module, signal_type, severity, location_ref,
                           site_id, is_managed, site_resolution_status)
        VALUES (%s, 'manual_entry', 'manual_observation', 'low', 'Fairlands/FA1/1Q1/MR01',
                %s, true, 'resolved_managed')
        RETURNING id
        """,
        (str(sig_id), str(site_row["id"])),
    )
    assert cur.fetchone() is not None
    cur.execute("DELETE FROM signal WHERE id = %s", (str(sig_id),))


# ============================================================================
# 12. email_thread 1:N signal
# ============================================================================


def test_email_thread_one_to_many(cur):
    """Create thread, create 2 signals pointing to it, verify both link correctly."""
    thread_id = uuid.uuid4()
    cur.execute(
        """
        INSERT INTO email_thread (id, thread_hash, subject, participants)
        VALUES (%s, 'hash-test-123', 'Room booking issue', ARRAY['alice@test.com', 'bob@test.com'])
        RETURNING id
        """,
        (str(thread_id),),
    )

    sig1_id = uuid.uuid4()
    sig2_id = uuid.uuid4()

    cur.execute(
        """
        INSERT INTO signal (id, source_module, signal_type, severity, location_ref, email_thread_id)
        VALUES (%s, 'email_helpdesk', 'complaint_email', 'medium', 'Fairlands/FA1/1Q4/MR10', %s)
        """,
        (str(sig1_id), str(thread_id)),
    )
    cur.execute(
        """
        INSERT INTO signal (id, source_module, signal_type, severity, location_ref, email_thread_id)
        VALUES (%s, 'email_escalation', 'escalation_email', 'high', 'Fairlands/FA1/1Q4/MR10', %s)
        """,
        (str(sig2_id), str(thread_id)),
    )

    # Verify both signals link to the same thread
    cur.execute(
        "SELECT count(*) AS cnt FROM signal WHERE email_thread_id = %s",
        (str(thread_id),),
    )
    assert cur.fetchone()["cnt"] == 2

    # Cleanup
    cur.execute("DELETE FROM signal WHERE email_thread_id = %s", (str(thread_id),))
    cur.execute("DELETE FROM email_thread WHERE id = %s", (str(thread_id),))


# ============================================================================
# 13. Cosine ivfflat index on signal.embedding
# ============================================================================


def test_cosine_ivfflat_index_exists(cur):
    cur.execute(
        """
        SELECT indexname, indexdef FROM pg_indexes
        WHERE tablename = 'signal' AND indexname = 'idx_signal_embedding'
        """
    )
    row = cur.fetchone()
    assert row is not None, "idx_signal_embedding index not found"
    assert "vector_cosine_ops" in row["indexdef"], f"Expected cosine ops, got: {row['indexdef']}"


# ============================================================================
# 14. first_seen_at DESC index on issue_cluster
# ============================================================================


def test_first_seen_at_desc_index(cur):
    cur.execute(
        """
        SELECT indexname, indexdef FROM pg_indexes
        WHERE tablename = 'issue_cluster' AND indexname = 'idx_issue_cluster_first_seen_at'
        """
    )
    row = cur.fetchone()
    assert row is not None, "idx_issue_cluster_first_seen_at index not found"
    assert "DESC" in row["indexdef"].upper() or "desc" in row["indexdef"], (
        f"Expected DESC ordering, got: {row['indexdef']}"
    )


# ============================================================================
# 15. Site deletion cleanup trigger
# ============================================================================


def test_cleanup_trigger_exists(cur):
    cur.execute("SELECT tgname FROM pg_trigger WHERE tgname = 'trg_cleanup_orphaned_site_refs'")
    row = cur.fetchone()
    assert row is not None, "trg_cleanup_orphaned_site_refs trigger not found"


# ============================================================================
# Bonus: no_self_loop constraint on relationship
# ============================================================================


def test_relationship_no_self_loop(cur):
    """Self-referencing relationship should be rejected."""
    node_id = uuid.uuid4()
    with pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            """
            INSERT INTO relationship (id, source_id, target_id, source_type, target_type, edge_type)
            VALUES (%s, %s, %s, 'signal', 'signal', 'related_to')
            """,
            (str(uuid.uuid4()), str(node_id), str(node_id)),
        )
    cur.execute("ROLLBACK")
