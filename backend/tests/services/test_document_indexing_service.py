from uuid import UUID, uuid4

import pytest

from app.services.document_indexing_service import DocumentIndexingService, IndexingStatus


class _FakeQuery:
    def __init__(self, db, table_name):
        self.db = db
        self.table_name = table_name
        self.operation = None
        self.payload = None
        self.filters = []

    def update(self, payload):
        self.operation = "update"
        self.payload = payload
        return self

    def delete(self):
        self.operation = "delete"
        return self

    def select(self, *_args):
        self.operation = "select"
        return self

    def eq(self, key, value):
        self.filters.append(("eq", key, value))
        return self

    def in_(self, key, value):
        self.filters.append(("in", key, value))
        return self

    def lt(self, key, value):
        self.filters.append(("lt", key, value))
        return self

    def execute(self):
        if self.operation == "update":
            self.db.updates.append((self.table_name, self.payload, self.filters))
            return type("Result", (), {"data": []})()
        if self.operation == "delete":
            self.db.deletes.append((self.table_name, self.filters))
            return type("Result", (), {"data": []})()
        if self.operation == "select":
            return type("Result", (), {"data": self.db.select_rows})()
        return type("Result", (), {"data": []})()


class _FakeDB:
    def __init__(self, select_rows=None):
        self.updates = []
        self.deletes = []
        self.select_rows = select_rows or []

    def table(self, table_name):
        return _FakeQuery(self, table_name)


class _FakeVectorDB:
    def __init__(self):
        self.calls = []

    def chunk_and_embed_markdown(self, *, document_id, doc_class):
        self.calls.append((document_id, doc_class))
        return 2


@pytest.mark.asyncio
async def test_site_document_without_asset_quarantines():
    db = _FakeDB()
    vector_db = _FakeVectorDB()
    service = DocumentIndexingService(db=db, vector_db=vector_db)
    document_id = uuid4()

    result = await service.index_document(
        document_id=document_id,
        file_bytes=b"service report text",
        doc_class="site",
        asset_id=None,
        source_system="concept_mri",
    )

    assert result.status == IndexingStatus.QUARANTINE
    assert vector_db.calls == []
    assert db.updates[-1][1]["indexing_status"] == "quarantine"
    assert "asset_id" in db.updates[-1][1]["indexing_error"]


@pytest.mark.asyncio
async def test_extraction_failure_marks_failed():
    db = _FakeDB()
    service = DocumentIndexingService(db=db, vector_db=_FakeVectorDB())
    document_id = uuid4()

    result = await service.index_document(
        document_id=document_id,
        file_bytes=b"",
        doc_class="system",
    )

    assert result.status == IndexingStatus.FAILED
    assert db.updates[-1][1]["indexing_status"] == "failed"
    assert "empty" in db.updates[-1][1]["indexing_error"]


@pytest.mark.asyncio
async def test_successful_index_deletes_old_chunks_before_embedding():
    db = _FakeDB()
    vector_db = _FakeVectorDB()
    service = DocumentIndexingService(db=db, vector_db=vector_db)
    document_id = uuid4()

    result = await service.index_document(
        document_id=document_id,
        file_bytes=b"# Service Report\n\nGenerator serviced.",
        doc_class="site",
        asset_id="S002-GEN-B1-001",
        source_system="concept_mri",
    )

    assert result.status == IndexingStatus.COMPLETE
    assert result.chunks == 2
    assert db.deletes == [("document_chunks", [("eq", "document_id", str(document_id))])]
    assert vector_db.calls == [(str(document_id), "site")]
    statuses = [payload["indexing_status"] for _, payload, _ in db.updates if "indexing_status" in payload]
    assert statuses == ["extracting", "embedding"]


def test_stuck_document_sweep_marks_transient_rows_failed():
    stuck_id = uuid4()
    db = _FakeDB(select_rows=[{"id": str(stuck_id), "indexing_status": "extracting"}])
    service = DocumentIndexingService(db=db, vector_db=_FakeVectorDB())

    count = service.sweep_stuck_documents(older_than_minutes=30)

    assert count == 1
    assert db.updates[-1][1]["indexing_status"] == "failed"
    assert "stuck in extracting" in db.updates[-1][1]["indexing_error"]


def test_indexing_result_requires_uuid():
    document_id = UUID("11111111-1111-1111-1111-111111111111")
    db = _FakeDB()
    service = DocumentIndexingService(db=db, vector_db=_FakeVectorDB())

    assert service._status_value(IndexingStatus.PENDING) == "pending"
    assert str(document_id) == "11111111-1111-1111-1111-111111111111"
