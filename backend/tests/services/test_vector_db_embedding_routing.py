"""Tests for VectorDB embedding routing and contextualized chunk flattening."""

import pytest

from app.config.settings import settings
from app.services.vector_db import VectorDBService


class _DummyClient:
    pass


class _FakeEmbeddingService:
    def __init__(self):
        self.calls = []

    def embed_documents(self, texts, batch_size=32):
        self.calls.append(("documents", list(texts), batch_size))
        return [[float(i)] for i, _ in enumerate(texts)]

    def embed_contextualized_documents(self, grouped_texts):
        self.calls.append(("contextualized", grouped_texts))
        return [
            [[101.0], [102.0]],
            [[201.0]],
        ]

    def embed_query(self, text):
        self.calls.append(("query", text))
        return [9.0]

    def embed_document(self, text):
        self.calls.append(("document", text))
        return [7.0]


def test_contextualized_chunk_embedding_groups_by_document_and_flattens_in_input_order(monkeypatch):
    svc = VectorDBService(_DummyClient())
    fake = _FakeEmbeddingService()
    svc._embedding_service = fake
    monkeypatch.setattr(settings, "embedding_contextualized_enabled", True)

    result = svc._embed_chunk_texts(
        [
            {"document_id": "doc-a", "text": "a1"},
            {"document_id": "doc-b", "text": "b1"},
            {"document_id": "doc-a", "text": "a2"},
        ]
    )

    assert fake.calls == [("contextualized", [["a1", "a2"], ["b1"]])]
    assert result == [[101.0], [201.0], [102.0]]


def test_contextualized_chunk_embedding_rejects_orphaned_results(monkeypatch):
    class _BadEmbeddingService(_FakeEmbeddingService):
        def embed_contextualized_documents(self, grouped_texts):
            return [[[1.0]]]

    svc = VectorDBService(_DummyClient())
    svc._embedding_service = _BadEmbeddingService()
    monkeypatch.setattr(settings, "embedding_contextualized_enabled", True)

    with pytest.raises(ValueError, match="chunk count mismatch"):
        svc._embed_chunk_texts(
            [
                {"document_id": "doc-a", "text": "a1"},
                {"document_id": "doc-a", "text": "a2"},
            ]
        )


def test_chunk_embedding_uses_standard_document_embeddings_when_contextualized_disabled(monkeypatch):
    svc = VectorDBService(_DummyClient())
    fake = _FakeEmbeddingService()
    svc._embedding_service = fake
    monkeypatch.setattr(settings, "embedding_contextualized_enabled", False)

    result = svc._embed_chunk_texts(
        [
            {"document_id": "doc-a", "text": "a1"},
            {"document_id": "doc-b", "text": "b1"},
        ]
    )

    assert fake.calls == [("documents", ["a1", "b1"], 500)]
    assert result == [[0.0], [1.0]]


def test_chunk_record_marks_system_docs_by_source():
    svc = VectorDBService(_DummyClient())

    record = svc._build_chunk_record(
        document={
            "source": "system_docs",
            "title": "Architecture",
            "equipment_type": "general",
            "document_type": "system_documentation",
        },
        document_id="11111111-1111-1111-1111-111111111111",
        chunk_index=0,
        chunk={"content": "System architecture", "section": "Overview"},
        embedding=[0.1],
        doc_class="system",
    )

    assert record["doc_class"] == "system"


def test_chunk_record_marks_non_system_docs_as_site():
    svc = VectorDBService(_DummyClient())

    record = svc._build_chunk_record(
        document={
            "source": "service_history",
            "title": "Generator Service",
            "equipment_type": "generator",
            "document_type": "service_report",
        },
        document_id="11111111-1111-1111-1111-111111111111",
        chunk_index=0,
        chunk={"content": "Generator service report", "section": "Findings"},
        embedding=[0.1],
        doc_class="site",
    )

    assert record["doc_class"] == "site"


def test_chunk_record_rejects_missing_or_invalid_doc_class():
    svc = VectorDBService(_DummyClient())

    with pytest.raises(ValueError, match="doc_class"):
        svc._build_chunk_record(
            document={
                "source": "system_docs",
                "title": "Architecture",
                "equipment_type": "general",
                "document_type": "system_documentation",
            },
            document_id="11111111-1111-1111-1111-111111111111",
            chunk_index=0,
            chunk={"content": "System architecture", "section": "Overview"},
            embedding=[0.1],
            doc_class="",
        )


@pytest.mark.asyncio
async def test_hyde_embeds_hypothetical_answer_as_document(monkeypatch):
    async def _fake_call(**_kwargs):
        return "A BMS network topology document would describe bridge connection architecture."

    from app.services.model_gateway import model_gateway

    monkeypatch.setattr(model_gateway, "call", _fake_call)

    svc = VectorDBService(_DummyClient())
    fake = _FakeEmbeddingService()
    svc._embedding_service = fake

    assert await svc._hyde_embed("BMS network topology") == [7.0]
    assert fake.calls == [
        ("document", "A BMS network topology document would describe bridge connection architecture.")
    ]
