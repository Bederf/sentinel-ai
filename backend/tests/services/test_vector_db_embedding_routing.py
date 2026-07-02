"""Tests for VectorDB embedding routing and contextualized chunk flattening."""

import pytest

from app.config.settings import settings
from app.services.vector_db import VectorDBService


class _DummyClient:
    pass


class _FakeEmbeddingService:
    def __init__(self):
        self.calls = []

    def embed_documents(self, texts):
        self.calls.append(("documents", list(texts)))
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

    assert fake.calls == [("documents", ["a1", "b1"])]
    assert result == [[0.0], [1.0]]


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
