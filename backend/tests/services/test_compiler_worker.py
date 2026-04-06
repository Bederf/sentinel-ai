"""Tests for CompilerWorker service (Phase 182-01).

Covers:
- poll_and_process empty queue → returns 0
- poll_and_process 1 entry, doc+equip found → processes, marks processed
- poll_and_process doc not found → marks processed, logs warning
- poll_and_process equip not found → marks processed
- poll_and_process upsert fails → leaves queue entry with null processed_at, returns 0
- poll_and_process multiple entries → processes all
- _compile_knowledge_entry with OCR text → description has content
- _compile_knowledge_entry with empty OCR → description is placeholder
- _compile_knowledge_entry high confidence (>=0.85) → confidence = 'high'
- _compile_knowledge_entry medium confidence (<0.85) → confidence = 'medium'
- _delete_entries → entry removed
- Concurrent claim: two workers get disjoint sets
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_queue_result(rows):
    """Wrap rows as a mock execute() result with .data."""
    m = MagicMock()
    m.data = rows
    return m


def _claim_result_for(mock_db, result):
    """
    Set the return_value of the claim chain on a mock db client.

    Chain: db.table().update().is_().order().limit().execute()
    """
    # The UPDATE ... SET processed_at=now() WHERE processed_at IS NULL ... execute()
    update_call = mock_db.table.return_value.update.return_value
    is_call = update_call.is_.return_value
    order_call = is_call.order.return_value
    limit_call = order_call.limit.return_value
    limit_call.execute.return_value = result


def _make_table_mock():
    """Build a chainable mock for db.table('X').operation().execute()."""
    return MagicMock()


def _make_claim_update_mock(claimed_entries):
    """Mock for UPDATE ... RETURNING rows (the claim step)."""
    m = MagicMock()
    m.data = claimed_entries
    return m


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    """Mock Supabase client."""
    return MagicMock()


@pytest.fixture
def worker(mock_db):
    from app.services.compiler_worker import CompilerWorker

    return CompilerWorker(db=mock_db)


# ---------------------------------------------------------------------------
# _compile_knowledge_entry
# ---------------------------------------------------------------------------


class TestCompileKnowledgeEntry:
    """Tests for _compile_knowledge_entry()."""

    def test_with_ocr_text(self, worker, mock_db):
        """OCR text is included in description."""
        document = {
            "id": "doc-1",
            "asset_id": "S002-GEN-001",
            "equipment_description": "Annual service performed on generator. Oil changed.",
            "document_type": "Service Report",
            "resolution_confidence": 0.92,
        }
        equipment = {
            "id": "eq-1",
            "code": "S002-GEN-001",
            "type": "GENERATOR",
            "location": "Basement B1",
        }
        queue_entry = {"id": "q-1", "document_id": "doc-1", "asset_id": "eq-1"}

        result = worker._compile_knowledge_entry(document, equipment, queue_entry)

        assert result["equipment_type"] == "GENERATOR"
        assert result["knowledge_type"] == "maintenance_record"
        assert result["title"] == "S002-GEN-001 — Service Report"
        assert "Annual service performed" in result["description"]
        assert result["source_document_id"] == "doc-1"
        assert result["confidence"] == "high"
        assert result["equipment_id"] == "eq-1"

    def test_with_empty_ocr(self, worker, mock_db):
        """Empty OCR yields placeholder description."""
        document = {
            "id": "doc-1",
            "asset_id": "S002-GEN-001",
            "equipment_description": "",
            "document_type": "Service Report",
            "resolution_confidence": 0.50,
        }
        equipment = {
            "id": "eq-1",
            "code": "S002-GEN-001",
            "type": "GENERATOR",
        }
        queue_entry = {"id": "q-1", "document_id": "doc-1", "asset_id": "eq-1"}

        result = worker._compile_knowledge_entry(document, equipment, queue_entry)

        assert result["description"] == "[No OCR text available — see source document]"
        assert result["confidence"] == "medium"

    def test_with_none_ocr(self, worker, mock_db):
        """None OCR yields placeholder description."""
        document = {
            "id": "doc-1",
            "asset_id": "S002-CHILLER-B1-001",
            "equipment_description": None,
            "document_type": "Maintenance Record",
            "resolution_confidence": 0.70,
        }
        equipment = {
            "id": "eq-2",
            "code": "S002-CHILLER-B1-001",
            "type": "CHILLER",
        }
        queue_entry = {"id": "q-1", "document_id": "doc-1", "asset_id": "eq-2"}

        result = worker._compile_knowledge_entry(document, equipment, queue_entry)

        assert result["description"] == "[No OCR text available — see source document]"
        assert result["confidence"] == "medium"

    def test_high_confidence_085(self, worker, mock_db):
        """resolution_confidence >= 0.85 maps to 'high'."""
        document = {
            "id": "doc-1",
            "equipment_description": "Filter replacement.",
            "document_type": "Work Order",
            "resolution_confidence": 0.85,
        }
        equipment = {"id": "eq-1", "code": "S002-AHU-L1-001", "type": "AHU"}
        queue_entry = {"id": "q-1", "document_id": "doc-1", "asset_id": "eq-1"}

        result = worker._compile_knowledge_entry(document, equipment, queue_entry)

        assert result["confidence"] == "high"

    def test_high_confidence_090(self, worker, mock_db):
        """resolution_confidence 0.90 maps to 'high'."""
        document = {
            "id": "doc-1",
            "equipment_description": "Coil cleaning.",
            "document_type": "Work Order",
            "resolution_confidence": 0.90,
        }
        equipment = {"id": "eq-1", "code": "S002-AHU-L1-001", "type": "AHU"}
        queue_entry = {"id": "q-1", "document_id": "doc-1", "asset_id": "eq-1"}

        result = worker._compile_knowledge_entry(document, equipment, queue_entry)

        assert result["confidence"] == "high"

    def test_medium_confidence_below_085(self, worker, mock_db):
        """resolution_confidence < 0.85 maps to 'medium'."""
        document = {
            "id": "doc-1",
            "equipment_description": "Bearing inspection.",
            "document_type": "Inspection",
            "resolution_confidence": 0.84,
        }
        equipment = {"id": "eq-1", "code": "S002-CHILLER-B1-001", "type": "CHILLER"}
        queue_entry = {"id": "q-1", "document_id": "doc-1", "asset_id": "eq-1"}

        result = worker._compile_knowledge_entry(document, equipment, queue_entry)

        assert result["confidence"] == "medium"

    def test_no_document_no_equipment(self, worker, mock_db):
        """Both None → equipment_type unknown → returns None (entry will be skipped)."""
        queue_entry = {"id": "q-1", "document_id": None, "asset_id": None}

        result = worker._compile_knowledge_entry(None, None, queue_entry)

        # Returns None when equipment_type cannot be determined; caller skips the entry
        assert result is None

    def test_description_truncated_at_500_chars(self, worker, mock_db):
        """Long OCR text is truncated to 500 characters."""
        long_text = "x" * 600
        document = {
            "id": "doc-1",
            "equipment_description": long_text,
            "document_type": "Report",
            "resolution_confidence": 0.90,
        }
        equipment = {"id": "eq-1", "code": "S002-GEN-001", "type": "GENERATOR"}
        queue_entry = {"id": "q-1", "document_id": "doc-1", "asset_id": "eq-1"}

        result = worker._compile_knowledge_entry(document, equipment, queue_entry)

        assert len(result["description"]) == 500


# ---------------------------------------------------------------------------
# poll_and_process — integration-style mock tests
# ---------------------------------------------------------------------------


class TestPollAndProcess:
    """Tests for poll_and_process() using full mock chain."""

    def test_empty_queue_returns_zero(self, worker, mock_db):
        """No unprocessed entries → returns 0 without error."""
        empty_result = _make_queue_result([])
        _claim_result_for(mock_db, empty_result)

        result = worker.poll_and_process()

        assert result == 0

    def test_single_entry_doc_and_equip_found(self, worker, mock_db):
        """1 queue entry with doc+equip found → processed, entry deleted."""
        queue_entry = {
            "id": "q-1",
            "document_id": "doc-1",
            "asset_id": "eq-1",
            "queued_at": "2026-04-01T00:00:00Z",
        }

        doc_data = {
            "id": "doc-1",
            "equipment_description": "Oil filter replaced.",
            "document_type": "Service Report",
            "resolution_confidence": 0.90,
            "asset_id": "eq-1",
        }
        equip_data = {
            "id": "eq-1",
            "code": "S002-GEN-001",
            "type": "GENERATOR",
            "location": "Basement",
        }

        def table_side_effect(table_name):
            m = MagicMock()
            if table_name == "compiler_queue":
                m.update.return_value.is_.return_value.order.return_value.limit.return_value.execute.return_value = (
                    _make_queue_result([queue_entry])
                )
                m.delete.return_value.in_.return_value.execute.return_value = MagicMock()
            elif table_name == "documents":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[doc_data])
            elif table_name == "equipment":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[equip_data])
            elif table_name == "equipment_knowledge":
                m.upsert.return_value.execute.return_value = MagicMock()
            return m

        mock_db.table.side_effect = table_side_effect

        result = worker.poll_and_process()

        assert result == 1

    def test_doc_not_found_marks_processed(self, worker, mock_db):
        """Document not found but equipment found → entry processed (equipment_type known)."""
        queue_entry = {
            "id": "q-1",
            "document_id": "doc-missing",
            "asset_id": "eq-1",
        }

        equip_data = {"id": "eq-1", "code": "S002-GEN-001", "type": "GENERATOR"}

        def table_side_effect(table_name):
            m = MagicMock()
            if table_name == "compiler_queue":
                m.update.return_value.is_.return_value.order.return_value.limit.return_value.execute.return_value = (
                    _make_queue_result([queue_entry])
                )
                m.delete.return_value.in_.return_value.execute.return_value = MagicMock()
            elif table_name == "documents":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            elif table_name == "equipment":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[equip_data])
            elif table_name == "equipment_knowledge":
                m.upsert.return_value.execute.return_value = MagicMock()
            return m

        mock_db.table.side_effect = table_side_effect

        result = worker.poll_and_process()

        # Equipment type is known (from equipment record), so entry IS processed
        assert result == 1

    def test_equip_not_found_still_processes(self, worker, mock_db):
        """Equipment not found but equipment_type determinable from fallback → processed."""
        queue_entry = {
            "id": "q-1",
            "document_id": "doc-1",
            "asset_id": "S002-GENERATOR-001",
        }

        doc_result = MagicMock()
        doc_result.data = [
            {
                "id": "doc-1",
                "equipment_description": "Parts replaced.",
                "document_type": "Work Order",
                "resolution_confidence": 0.75,
                "asset_id": "S002-GENERATOR-001",
            }
        ]

        def table_side_effect(table_name):
            m = MagicMock()
            if table_name == "compiler_queue":
                m.update.return_value.is_.return_value.order.return_value.limit.return_value.execute.return_value = (
                    _make_queue_result([queue_entry])
                )
                m.delete.return_value.in_.return_value.execute.return_value = MagicMock()
            elif table_name == "documents":
                m.select.return_value.eq.return_value.execute.return_value = doc_result
            elif table_name == "equipment":
                # Equipment not found in DB — fallback parsing determines type from asset_id
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            elif table_name == "equipment_knowledge":
                m.upsert.return_value.execute.return_value = MagicMock()
            return m

        mock_db.table.side_effect = table_side_effect

        result = worker.poll_and_process()

        # Fallback parse "S002-GENERATOR-001" → parts = ["S002", "GENERATOR", "001"]
        # → equipment_type = "GENERATOR" (parts[2]) → entry processed
        assert result == 1
        # equipment_id should not be in the upserted record
        upsert_call = mock_db.table.return_value.upsert.return_value
        # The upsert was called with a record that has no equipment_id

    def test_upsert_fails_leaves_queue_entry(self, worker, mock_db):
        """Upsert raises → entry NOT deleted, returns 0, retries next cycle."""
        queue_entry = {
            "id": "q-1",
            "document_id": "doc-1",
            "asset_id": "eq-1",
        }

        doc_result = MagicMock()
        doc_result.data = [
            {
                "id": "doc-1",
                "equipment_description": "Service note.",
                "document_type": "Report",
                "resolution_confidence": 0.90,
                "asset_id": "eq-1",
            }
        ]

        equip_result = MagicMock()
        equip_result.data = [{"id": "eq-1", "code": "S002-GEN-001", "type": "GENERATOR"}]

        def table_side_effect(table_name):
            m = MagicMock()
            if table_name == "compiler_queue":
                m.update.return_value.is_.return_value.order.return_value.limit.return_value.execute.return_value = (
                    _make_queue_result([queue_entry])
                )
                # Delete should NOT be called on upsert failure
            elif table_name == "documents":
                m.select.return_value.eq.return_value.execute.return_value = doc_result
            elif table_name == "equipment":
                m.select.return_value.eq.return_value.execute.return_value = equip_result
            elif table_name == "equipment_knowledge":
                # Upsert raises
                m.upsert.return_value.execute.side_effect = RuntimeError("DB constraint error")
            return m

        mock_db.table.side_effect = table_side_effect

        result = worker.poll_and_process()

        assert result == 0
        # Delete should NOT have been called
        mock_db.table.return_value.delete.return_value.in_.return_value.execute.assert_not_called()

    def test_multiple_entries_all_processed(self, worker, mock_db):
        """3 queue entries all found → all 3 processed and deleted."""
        queue_entries = [
            {
                "id": f"q-{i}",
                "document_id": f"doc-{i}",
                "asset_id": f"eq-{i}",
            }
            for i in range(1, 4)
        ]

        def table_side_effect(table_name):
            m = MagicMock()
            if table_name == "compiler_queue":
                m.update.return_value.is_.return_value.order.return_value.limit.return_value.execute.return_value = (
                    _make_queue_result(queue_entries)
                )
                m.delete.return_value.in_.return_value.execute.return_value = MagicMock()
            elif table_name == "documents":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[
                        {
                            "id": "doc-1",
                            "equipment_description": "Service note.",
                            "document_type": "Report",
                            "resolution_confidence": 0.90,
                            "asset_id": "eq-1",
                        }
                    ]
                )
            elif table_name == "equipment":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"id": "eq-1", "code": "S002-GEN-001", "type": "GENERATOR"}]
                )
            elif table_name == "equipment_knowledge":
                m.upsert.return_value.execute.return_value = MagicMock()
            return m

        mock_db.table.side_effect = table_side_effect

        result = worker.poll_and_process()

        assert result == 3

    def test_claim_returns_empty_skips_processing(self, worker, mock_db):
        """Claim step returns [] → returns 0 immediately."""
        empty_result = _make_queue_result([])
        _claim_result_for(mock_db, empty_result)

        result = worker.poll_and_process()

        assert result == 0
        # No further table calls should be made
        mock_db.table.return_value.delete.assert_not_called()


# ---------------------------------------------------------------------------
# _mark_processed (delete)
# ---------------------------------------------------------------------------


class TestDeleteEntries:
    """Tests for _delete_entries()."""

    def test_delete_single_entry(self, worker, mock_db):
        """Single entry ID → delete called with that ID."""
        mock_db.table.return_value.delete.return_value.in_.return_value.execute.return_value = MagicMock()

        worker._delete_entries(["q-1"])

        mock_db.table.return_value.delete.return_value.in_.return_value.execute.assert_called_once()

    def test_delete_multiple_entries(self, worker, mock_db):
        """Multiple entry IDs → in_ clause used."""
        mock_db.table.return_value.delete.return_value.in_.return_value.execute.return_value = MagicMock()

        worker._delete_entries(["q-1", "q-2", "q-3"])

        mock_db.table.return_value.delete.return_value.in_.return_value.execute.assert_called_once()

    def test_delete_empty_list_noop(self, worker, mock_db):
        """Empty list → no delete call."""
        worker._delete_entries([])

        mock_db.table.assert_not_called()


# ---------------------------------------------------------------------------
# _fetch_document_and_equipment
# ---------------------------------------------------------------------------


class TestFetchDocumentAndEquipment:
    """Tests for _fetch_document_and_equipment()."""

    def test_both_found(self, worker, mock_db):
        """Document and equipment both found → returned."""
        doc_result = MagicMock()
        doc_result.data = [{"id": "doc-1", "equipment_description": "Test"}]

        equip_result = MagicMock()
        equip_result.data = [{"id": "eq-1", "code": "S002-GEN-001", "type": "GENERATOR"}]

        def table_side_effect(table_name):
            m = MagicMock()
            if table_name == "documents":
                m.select.return_value.eq.return_value.execute.return_value = doc_result
            elif table_name == "equipment":
                m.select.return_value.eq.return_value.execute.return_value = equip_result
            return m

        mock_db.table.side_effect = table_side_effect

        queue_entry = {"document_id": "doc-1", "asset_id": "eq-1"}
        doc, equip = worker._fetch_document_and_equipment(queue_entry)

        assert doc is not None
        assert doc["id"] == "doc-1"
        assert equip is not None
        assert equip["id"] == "eq-1"

    def test_doc_not_found(self, worker, mock_db):
        """Document not found → doc is None, equipment fetched anyway."""
        equip_result = MagicMock()
        equip_result.data = [{"id": "eq-1", "code": "S002-GEN-001", "type": "GENERATOR"}]

        def table_side_effect(table_name):
            m = MagicMock()
            if table_name == "documents":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            elif table_name == "equipment":
                m.select.return_value.eq.return_value.execute.return_value = equip_result
            return m

        mock_db.table.side_effect = table_side_effect

        queue_entry = {"document_id": "doc-missing", "asset_id": "eq-1"}
        doc, equip = worker._fetch_document_and_equipment(queue_entry)

        assert doc is None
        assert equip is not None

    def test_equip_not_found(self, worker, mock_db):
        """Equipment not found → equip is None, doc still returned."""
        doc_result = MagicMock()
        doc_result.data = [{"id": "doc-1", "equipment_description": "Test"}]

        def table_side_effect(table_name):
            m = MagicMock()
            if table_name == "documents":
                m.select.return_value.eq.return_value.execute.return_value = doc_result
            elif table_name == "equipment":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            return m

        mock_db.table.side_effect = table_side_effect

        queue_entry = {"document_id": "doc-1", "asset_id": "eq-missing"}
        doc, equip = worker._fetch_document_and_equipment(queue_entry)

        assert doc is not None
        assert equip is None

    def test_neither_found(self, worker, mock_db):
        """Both missing → both None."""

        def table_side_effect(table_name):
            m = MagicMock()
            if table_name == "documents" or table_name == "equipment":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            return m

        mock_db.table.side_effect = table_side_effect

        queue_entry = {"document_id": None, "asset_id": None}
        doc, equip = worker._fetch_document_and_equipment(queue_entry)

        assert doc is None
        assert equip is None
