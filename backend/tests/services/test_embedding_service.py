"""Tests for provider-backed embedding service routing."""

import pytest

from app.services.embedding_service import EmbeddingService, VoyageAPIProvider, VoyageNanoLocalProvider


class _RecordingProvider:
    provider_name = "recording"
    model_name = "recording-model"
    dimension = 1024
    supports_contextualized = True

    def __init__(self):
        self.calls = []

    def warmup(self):
        self.calls.append(("warmup", None))

    def embed_text(self, text, input_type=None):
        self.calls.append(("text", text, input_type))
        return [1.0 if input_type == "query" else 2.0]

    def embed_batch(self, texts, batch_size=32, input_type=None):
        self.calls.append(("batch", list(texts), batch_size, input_type))
        return [[float(i)] for i, _ in enumerate(texts)]

    def contextualized_embed_groups(self, grouped_texts, input_type="document"):
        self.calls.append(("contextualized", grouped_texts, input_type))
        return [[[float(i)] for i, _ in enumerate(group)] for group in grouped_texts]


def test_embedding_service_routes_query_and_document_input_types():
    provider = _RecordingProvider()
    svc = EmbeddingService(provider=provider)

    assert svc.embed_query("unique query text for voyage routing") == [1.0]
    assert svc.embed_document("unique document text for voyage routing") == [2.0]

    assert ("text", "unique query text for voyage routing", "query") in provider.calls
    assert ("text", "unique document text for voyage routing", "document") in provider.calls
    assert svc.get_embedding_dimension() == 1024


def test_embedding_service_batches_document_embeddings():
    provider = _RecordingProvider()
    svc = EmbeddingService(provider=provider)

    assert svc.embed_documents(["a", "b"]) == [[0.0], [1.0]]

    assert provider.calls == [("batch", ["a", "b"], 32, "document")]


def test_embedding_service_provider_info_is_non_secret():
    provider = _RecordingProvider()
    svc = EmbeddingService(provider=provider)

    assert svc.provider_info() == {
        "provider": "recording",
        "model": "recording-model",
        "dimension": 1024,
        "contextualized": True,
    }


def test_voyage_api_provider_uses_configured_model_dimension_and_input_type():
    class _Result:
        embeddings = [[0.1, 0.2]]

    class _Client:
        def __init__(self):
            self.kwargs = None

        def embed(self, texts, **kwargs):
            self.kwargs = {"texts": texts, **kwargs}
            return _Result()

    provider = VoyageAPIProvider(
        api_key="test-key",
        model_name="voyage-4",
        context_model_name="voyage-context-4",
        dimension=1024,
    )
    client = _Client()
    provider._client = client

    assert provider.embed_batch(["BMS network topology"], input_type="query") == [[0.1, 0.2]]
    assert client.kwargs == {
        "texts": ["BMS network topology"],
        "model": "voyage-4",
        "input_type": "query",
        "output_dimension": 1024,
    }


def test_voyage_api_provider_records_embedding_usage(monkeypatch):
    class _Result:
        embeddings = [[0.1, 0.2]]
        total_tokens = 42

    class _Client:
        def embed(self, texts, **_kwargs):
            del texts
            return _Result()

    class _UsageTracker:
        def __init__(self):
            self.records = []

        def record(self, **kwargs):
            self.records.append(kwargs)

    tracker = _UsageTracker()

    import app.services.ai_usage_tracker as usage_module

    monkeypatch.setattr(usage_module, "usage_tracker", tracker)

    provider = VoyageAPIProvider(
        api_key="test-key",
        model_name="voyage-4",
        context_model_name="voyage-context-4",
        dimension=1024,
    )
    provider._client = _Client()

    assert provider.embed_batch(["BMS network topology"], input_type="query") == [[0.1, 0.2]]
    assert tracker.records == [
        {
            "provider": "voyage",
            "model": "voyage-4",
            "input_tokens": 42,
            "output_tokens": 0,
            "source": "rag_embedding",
            "site_id": "system",
            "task_class": "embedding",
            "feature": "rag_embedding_query",
        }
    ]


def test_voyage_api_provider_splits_large_batches():
    class _Result:
        def __init__(self, embeddings):
            self.embeddings = embeddings

    class _Client:
        def __init__(self):
            self.batch_sizes = []

        def embed(self, texts, **_kwargs):
            self.batch_sizes.append(len(texts))
            return _Result([[float(len(self.batch_sizes))] for _ in texts])

    provider = VoyageAPIProvider(
        api_key="test-key",
        model_name="voyage-4",
        context_model_name="voyage-context-4",
        dimension=1024,
    )
    provider._client = _Client()

    result = provider.embed_batch([f"text-{i}" for i in range(1201)], batch_size=1000, input_type="document")

    assert provider._client.batch_sizes == [500, 500, 201]
    assert len(result) == 1201


def test_voyage_contextualized_provider_preserves_group_order():
    class _ContextResult:
        def __init__(self, index, embeddings):
            self.index = index
            self.embeddings = embeddings

    class _Result:
        results = [
            _ContextResult(1, [[20.0]]),
            _ContextResult(0, [[10.0], [11.0]]),
        ]

    class _Client:
        def contextualized_embed(self, **kwargs):
            self.kwargs = kwargs
            return _Result()

    provider = VoyageAPIProvider(
        api_key="test-key",
        model_name="voyage-4",
        context_model_name="voyage-context-4",
        dimension=1024,
    )
    provider._client = _Client()

    result = provider.contextualized_embed_groups([["a1", "a2"], ["b1"]])

    assert result == [[[10.0], [11.0]], [[20.0]]]
    assert provider._client.kwargs["inputs"] == [["a1", "a2"], ["b1"]]
    assert provider._client.kwargs["model"] == "voyage-context-4"
    assert provider._client.kwargs["input_type"] == "document"


def test_voyage_nano_local_provider_stub_exists():
    provider = VoyageNanoLocalProvider(dimension=1024)

    assert provider.provider_name == "voyage_nano_local"
    assert provider.model_name == "voyage-4-nano"
    assert provider.dimension == 1024
    with pytest.raises(RuntimeError, match="Jetson/edge stub"):
        provider.embed_text("query", input_type="query")
