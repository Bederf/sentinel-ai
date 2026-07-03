"""Tests for resumable corpus re-embedding sweep."""

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from backend.scripts import reembed_document_corpus as sweep
else:
    from scripts import reembed_document_corpus as sweep


class _Result:
    def __init__(self, data=None):
        self.data = data or []


class _Query:
    def __init__(self, table, data):
        self.table = table
        self.data = data
        self.deleted = []

    def select(self, _fields):
        return self

    @property
    def not_(self):
        return self

    def is_(self, _field, _value):
        return self

    def order(self, _field):
        return self

    def eq(self, field, value):
        if field == "document_id":
            self.deleted.append(value)
        return self

    def limit(self, _limit):
        return self

    def delete(self):
        return self

    def execute(self):
        return _Result(self.data)


class _Client:
    def __init__(self, rows):
        self.rows = rows
        self.deleted_documents = []

    def table(self, name):
        query = _Query(name, self.rows if name == "documents" else [])
        original_execute = query.execute

        def execute():
            self.deleted_documents.extend(query.deleted)
            return original_execute()

        query.execute = execute
        return query


class _VectorDB:
    def __init__(self, fail_on=None):
        self.fail_on = fail_on
        self.embedded = []

    def chunk_and_embed_markdown(self, *, document_id, doc_class, doc_title, doc_type):
        del doc_title, doc_type
        assert doc_class in {"system", "site"}
        if document_id == self.fail_on:
            raise RuntimeError("boom")
        self.embedded.append(document_id)
        return 3


def test_reembed_documents_skips_completed_checkpoint(monkeypatch, tmp_path: Path):
    rows = [
        {"id": "doc-1", "title": "Done", "document_type": "manual", "full_text": "abc"},
        {"id": "doc-2", "title": "Todo", "document_type": "manual", "full_text": "def"},
    ]
    client = _Client(rows)
    vector_db = _VectorDB()
    checkpoint = {"completed": {"documents:doc-1": {"chunks": 1}}, "failed": {}}
    checkpoint_file = tmp_path / "checkpoint.json"

    monkeypatch.setattr(sweep, "get_vector_db_service", lambda _client: vector_db)

    chunks = sweep._reembed_documents(
        client,
        document_id=None,
        limit=None,
        execute=True,
        checkpoint=checkpoint,
        checkpoint_file=checkpoint_file,
    )

    assert chunks == 3
    assert vector_db.embedded == ["doc-2"]
    assert "documents:doc-2" in checkpoint["completed"]
    assert checkpoint_file.exists()


def test_reembed_documents_records_failure_before_reraising(monkeypatch, tmp_path: Path):
    rows = [{"id": "doc-47", "title": "Fails", "document_type": "manual", "full_text": "abc"}]
    client = _Client(rows)
    vector_db = _VectorDB(fail_on="doc-47")
    checkpoint: dict[str, dict[str, Any]] = {"completed": {}, "failed": {}}
    checkpoint_file = tmp_path / "checkpoint.json"

    monkeypatch.setattr(sweep, "get_vector_db_service", lambda _client: vector_db)

    with pytest.raises(RuntimeError, match="boom"):
        sweep._reembed_documents(
            client,
            document_id=None,
            limit=None,
            execute=True,
            checkpoint=checkpoint,
            checkpoint_file=checkpoint_file,
        )

    assert "documents:doc-47" in checkpoint["failed"]
    assert checkpoint_file.exists()
