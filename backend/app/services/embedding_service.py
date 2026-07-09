"""Provider-backed embedding service for SENTINEL document intelligence.

Includes LRU cache for query embeddings (inspired by AimTheLaw's
QueryEmbeddingCache pattern — 60-80% hit rate on repeated queries).
"""

import hashlib
import logging
import os
import time
from collections import OrderedDict
from threading import Lock
from typing import Literal, Protocol

logger = logging.getLogger(__name__)

EmbeddingInputType = Literal["query", "document"] | None

# ---------------------------------------------------------------------------
# Embedding cache — LRU with adaptive TTL
# ---------------------------------------------------------------------------

_CACHE_MAX_SIZE = 2000
_CACHE_DEFAULT_TTL = 3600  # 1 hour
_CACHE_MAX_TTL = 86400  # 24 hours


class _EmbeddingCache:
    """Thread-safe LRU cache for query embeddings."""

    def __init__(self, max_size: int = _CACHE_MAX_SIZE):
        self._cache: OrderedDict[str, tuple[list[float], float, int]] = OrderedDict()
        self._max_size = max_size
        self._lock = Lock()
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _key(namespace: str, text: str) -> str:
        raw_key = f"{namespace}\0{text}"
        return hashlib.md5(raw_key.encode(), usedforsecurity=False).hexdigest()

    def get(self, namespace: str, text: str) -> list[float] | None:
        key = self._key(namespace, text)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None
            embedding, expire_at, access_count = entry
            if time.monotonic() > expire_at:
                del self._cache[key]
                self._misses += 1
                return None

            self._hits += 1
            new_ttl = min(_CACHE_DEFAULT_TTL * (1 + access_count), _CACHE_MAX_TTL)
            self._cache[key] = (embedding, time.monotonic() + new_ttl, access_count + 1)
            self._cache.move_to_end(key)
            return embedding

    def put(self, namespace: str, text: str, embedding: list[float]) -> None:
        key = self._key(namespace, text)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            elif len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)
            self._cache[key] = (embedding, time.monotonic() + _CACHE_DEFAULT_TTL, 1)

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total else 0.0

    @property
    def size(self) -> int:
        return len(self._cache)


_embedding_cache = _EmbeddingCache()


class EmbeddingProvider(Protocol):
    """Provider contract used by RAG ingestion and query-time retrieval."""

    provider_name: str
    model_name: str
    dimension: int
    supports_contextualized: bool

    def warmup(self) -> None: ...

    def embed_text(self, text: str, input_type: EmbeddingInputType = None) -> list[float]: ...

    def embed_batch(
        self,
        texts: list[str],
        batch_size: int = 32,
        input_type: EmbeddingInputType = None,
    ) -> list[list[float]]: ...

    def contextualized_embed_groups(
        self,
        grouped_texts: list[list[str]],
        input_type: EmbeddingInputType = "document",
    ) -> list[list[list[float]]]: ...


class MiniLMLocalProvider:
    """Local MiniLM provider retained as a fallback until Voyage is enabled."""

    provider_name = "minilm_local"
    model_name = "all-MiniLM-L6-v2"
    dimension = 384
    supports_contextualized = False

    def __init__(self):
        self._model = None

    @property
    def model(self):
        if self._model is None:
            logger.info("Loading embedding model: %s", self.model_name)
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
            logger.info("Embedding model loaded successfully")
        return self._model

    def warmup(self) -> None:
        _ = self.model

    def embed_text(self, text: str, input_type: EmbeddingInputType = None) -> list[float]:
        del input_type
        return self.model.encode(text, normalize_embeddings=True).tolist()

    def embed_batch(
        self,
        texts: list[str],
        batch_size: int = 32,
        input_type: EmbeddingInputType = None,
    ) -> list[list[float]]:
        del input_type
        if not texts:
            return []

        embeddings = self.model.encode(
            texts, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=len(texts) > 100
        )
        return embeddings.tolist()

    def contextualized_embed_groups(
        self,
        grouped_texts: list[list[str]],
        input_type: EmbeddingInputType = "document",
    ) -> list[list[list[float]]]:
        del grouped_texts, input_type
        raise RuntimeError("MiniLM provider does not support contextualized embeddings")


class VoyageAPIProvider:
    """Voyage API provider for VPS/document-ingestion deployments."""

    provider_name = "voyage_api"
    supports_contextualized = True

    def __init__(
        self,
        *,
        api_key: str,
        model_name: str,
        context_model_name: str,
        dimension: int,
    ):
        self.api_key = api_key
        self.model_name = model_name
        self.context_model_name = context_model_name
        self.dimension = dimension
        self._client = None

    @property
    def client(self):
        if self._client is None:
            try:
                import voyageai
            except ImportError as exc:
                raise RuntimeError(
                    "EMBEDDING_PROVIDER=voyage_api requires the optional 'voyageai' package. "
                    "Install it only after dependency approval."
                ) from exc

            effective_key = self.api_key or os.getenv("VOYAGE_API_KEY", "")
            self._client = voyageai.Client(api_key=effective_key) if effective_key else voyageai.Client()
        return self._client

    @staticmethod
    def _response_tokens(result) -> int:
        usage = getattr(result, "usage", None)
        if isinstance(usage, dict):
            return int(usage.get("total_tokens") or usage.get("tokens") or 0)
        usage_tokens = getattr(usage, "total_tokens", None) if usage is not None else None
        return int(getattr(result, "total_tokens", usage_tokens) or 0)

    def _record_usage(self, *, model: str, tokens: int, input_type: EmbeddingInputType) -> None:
        if tokens <= 0:
            return
        try:
            from app.services.ai_usage_tracker import usage_tracker

            usage_tracker.record(
                provider="voyage",
                model=model,
                input_tokens=tokens,
                output_tokens=0,
                source="rag_embedding",
                site_id="system",
                task_class="embedding",
                feature=f"rag_embedding_{input_type or 'none'}",
            )
        except Exception:
            logger.debug("Failed to record Voyage embedding usage", exc_info=True)

    def warmup(self) -> None:
        _ = self.client

    def embed_text(self, text: str, input_type: EmbeddingInputType = None) -> list[float]:
        return self.embed_batch([text], input_type=input_type)[0]

    def embed_batch(
        self,
        texts: list[str],
        batch_size: int = 32,
        input_type: EmbeddingInputType = None,
    ) -> list[list[float]]:
        if not texts:
            return []

        effective_batch_size = max(1, min(batch_size, 500))
        embeddings: list[list[float]] = []
        for start in range(0, len(texts), effective_batch_size):
            batch = texts[start : start + effective_batch_size]
            result = self.client.embed(
                batch,
                model=self.model_name,
                input_type=input_type,
                output_dimension=self.dimension,
            )
            self._record_usage(model=self.model_name, tokens=self._response_tokens(result), input_type=input_type)
            embeddings.extend(result.embeddings)
        return embeddings

    def contextualized_embed_groups(
        self,
        grouped_texts: list[list[str]],
        input_type: EmbeddingInputType = "document",
    ) -> list[list[list[float]]]:
        if not grouped_texts:
            return []

        result = self.client.contextualized_embed(
            inputs=grouped_texts,
            model=self.context_model_name,
            input_type=input_type,
            output_dimension=self.dimension,
        )
        self._record_usage(
            model=self.context_model_name,
            tokens=self._response_tokens(result),
            input_type=input_type,
        )
        results_by_index = {item.index: item.embeddings for item in result.results}
        return [results_by_index[i] for i in range(len(grouped_texts))]


class VoyageNanoLocalProvider:
    """Jetson/edge placeholder for open-weight `voyage-4-nano` local inference."""

    provider_name = "voyage_nano_local"
    model_name = "voyage-4-nano"
    supports_contextualized = False

    def __init__(self, *, dimension: int):
        self.dimension = dimension

    def _not_ready(self) -> RuntimeError:
        return RuntimeError(
            "VoyageNanoLocalProvider is a Jetson/edge stub. Wire the HuggingFace transformers "
            "runtime in the Jetson deployment phase before enabling EMBEDDING_PROVIDER=voyage_nano_local."
        )

    def warmup(self) -> None:
        raise self._not_ready()

    def embed_text(self, text: str, input_type: EmbeddingInputType = None) -> list[float]:
        del text, input_type
        raise self._not_ready()

    def embed_batch(
        self,
        texts: list[str],
        batch_size: int = 32,
        input_type: EmbeddingInputType = None,
    ) -> list[list[float]]:
        del texts, batch_size, input_type
        raise self._not_ready()

    def contextualized_embed_groups(
        self,
        grouped_texts: list[list[str]],
        input_type: EmbeddingInputType = "document",
    ) -> list[list[list[float]]]:
        del grouped_texts, input_type
        raise self._not_ready()


class EmbeddingService:
    """Generate embeddings through the configured provider."""

    def __init__(self, provider: EmbeddingProvider | None = None):
        self.provider = provider or self._build_provider()

    def _build_provider(self) -> EmbeddingProvider:
        from app.config.settings import settings

        provider_name = settings.embedding_provider.strip().lower()
        if provider_name == "voyage_api":
            return VoyageAPIProvider(
                api_key=settings.voyage_api_key,
                model_name=settings.voyage_embed_model,
                context_model_name=settings.voyage_context_model,
                dimension=settings.embedding_dimension,
            )
        if provider_name == "voyage_nano_local":
            return VoyageNanoLocalProvider(dimension=settings.embedding_dimension)
        if provider_name in {"minilm", "minilm_local", "sentence_transformers"}:
            return MiniLMLocalProvider()
        raise ValueError(f"Unsupported EMBEDDING_PROVIDER: {settings.embedding_provider}")

    def _cache_namespace(self, input_type: EmbeddingInputType) -> str:
        return (
            f"{self.provider.provider_name}:{self.provider.model_name}:{self.provider.dimension}:{input_type or 'none'}"
        )

    def provider_info(self) -> dict[str, object]:
        """Return non-secret active provider details for startup and diagnostics."""
        return {
            "provider": self.provider.provider_name,
            "model": self.provider.model_name,
            "dimension": self.provider.dimension,
            "contextualized": self.provider.supports_contextualized,
        }

    def warmup(self) -> None:
        logger.info(
            "Embedding provider active: provider=%s model=%s dimension=%s contextualized=%s",
            self.provider.provider_name,
            self.provider.model_name,
            self.provider.dimension,
            self.provider.supports_contextualized,
        )
        self.provider.warmup()

    def embed_text(self, text: str, input_type: EmbeddingInputType = None) -> list[float]:
        namespace = self._cache_namespace(input_type)
        if len(text) > 10:
            cached = _embedding_cache.get(namespace, text)
            if cached is not None:
                return cached

        embedding = self.provider.embed_text(text, input_type=input_type)

        if len(text) > 10:
            _embedding_cache.put(namespace, text, embedding)

        return embedding

    def embed_query(self, text: str) -> list[float]:
        """Embed query-time text using retrieval query semantics."""
        return self.embed_text(text, input_type="query")

    def embed_document(self, text: str) -> list[float]:
        """Embed document/chunk text using retrieval document semantics."""
        return self.embed_text(text, input_type="document")

    def embed_batch(
        self,
        texts: list[str],
        batch_size: int = 32,
        input_type: EmbeddingInputType = None,
    ) -> list[list[float]]:
        return self.provider.embed_batch(texts, batch_size=batch_size, input_type=input_type)

    def embed_documents(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        return self.embed_batch(texts, batch_size=batch_size, input_type="document")

    def embed_contextualized_documents(self, grouped_texts: list[list[str]]) -> list[list[list[float]]]:
        if not self.provider.supports_contextualized:
            raise RuntimeError(f"{self.provider.provider_name} does not support contextualized embeddings")
        return self.provider.contextualized_embed_groups(grouped_texts, input_type="document")

    def get_embedding_dimension(self) -> int:
        return self.provider.dimension

    def get_cache_stats(self) -> dict:
        """Return cache performance stats."""
        return {
            **self.provider_info(),
            "cache_size": _embedding_cache.size,
            "cache_max": _CACHE_MAX_SIZE,
            "hit_rate": round(_embedding_cache.hit_rate, 3),
        }


_embedding_service = None


def get_embedding_service() -> EmbeddingService:
    """Get singleton embedding service instance."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
