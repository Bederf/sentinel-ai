"""Embedding service using sentence-transformers (local, no API costs).

Includes LRU cache for query embeddings (inspired by AimTheLaw's
QueryEmbeddingCache pattern — 60-80% hit rate on repeated queries).
"""

import hashlib
import logging
import time
from collections import OrderedDict
from threading import Lock
from typing import List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Embedding cache — LRU with adaptive TTL
# ---------------------------------------------------------------------------

_CACHE_MAX_SIZE = 2000
_CACHE_DEFAULT_TTL = 3600  # 1 hour
_CACHE_MAX_TTL = 86400  # 24 hours


class _EmbeddingCache:
    """Thread-safe LRU cache for query embeddings.

    Repeated queries (building managers ask similar questions) get a
    cache hit instead of re-encoding.  Adaptive TTL: frequently accessed
    entries live longer.
    """

    def __init__(self, max_size: int = _CACHE_MAX_SIZE):
        self._cache: OrderedDict[str, tuple[List[float], float, int]] = OrderedDict()
        self._max_size = max_size
        self._lock = Lock()
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _key(text: str) -> str:
        return hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()

    def get(self, text: str) -> List[float] | None:
        key = self._key(text)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None
            embedding, expire_at, access_count = entry
            if time.monotonic() > expire_at:
                # Expired
                del self._cache[key]
                self._misses += 1
                return None
            # Hit — bump access count and extend TTL adaptively
            self._hits += 1
            new_ttl = min(_CACHE_DEFAULT_TTL * (1 + access_count), _CACHE_MAX_TTL)
            self._cache[key] = (embedding, time.monotonic() + new_ttl, access_count + 1)
            self._cache.move_to_end(key)
            return embedding

    def put(self, text: str, embedding: List[float]) -> None:
        key = self._key(text)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            elif len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)  # evict LRU
            self._cache[key] = (embedding, time.monotonic() + _CACHE_DEFAULT_TTL, 1)

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total else 0.0

    @property
    def size(self) -> int:
        return len(self._cache)


# Module-level cache instance (shared across all EmbeddingService users)
_embedding_cache = _EmbeddingCache()


# ---------------------------------------------------------------------------
# Embedding service
# ---------------------------------------------------------------------------


class EmbeddingService:
    """Generate embeddings using all-MiniLM-L6-v2 (384 dimensions)."""

    def __init__(self):
        self._model = None

    @property
    def model(self):
        if self._model is None:
            logger.info("Loading embedding model: all-MiniLM-L6-v2")
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("Embedding model loaded successfully")
        return self._model

    def warmup(self) -> None:
        """Pre-load the model so first real query doesn't pay the cost."""
        _ = self.model

    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text (with LRU cache)."""
        # Skip cache for very short strings (not meaningful queries)
        if len(text) > 10:
            cached = _embedding_cache.get(text)
            if cached is not None:
                return cached

        embedding = self.model.encode(text, normalize_embeddings=True).tolist()

        if len(text) > 10:
            _embedding_cache.put(text, embedding)

        return embedding

    def embed_batch(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """Generate embeddings for multiple texts efficiently."""
        if not texts:
            return []

        embeddings = self.model.encode(
            texts, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=len(texts) > 100
        )
        return embeddings.tolist()

    def get_embedding_dimension(self) -> int:
        """Return the embedding dimension (384 for MiniLM)."""
        return 384

    def get_cache_stats(self) -> dict:
        """Return cache performance stats."""
        return {
            "cache_size": _embedding_cache.size,
            "cache_max": _CACHE_MAX_SIZE,
            "hit_rate": round(_embedding_cache.hit_rate, 3),
        }


# Singleton instance
_embedding_service = None


def get_embedding_service() -> EmbeddingService:
    """Get singleton embedding service instance."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
