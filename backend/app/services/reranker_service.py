"""Cross-encoder reranking service for RAG results.

Uses a lightweight cross-encoder model to rescore document chunks
against the original query, improving retrieval precision over
initial hybrid search scores.
"""

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

RERANK_TIMEOUT_SECONDS = 10
DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class RerankerService:
    """Cross-encoder reranking for RAG document chunks."""

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self._model = None
        self._model_name = model_name

    def _get_model(self):
        """Lazy-load cross-encoder model on first use."""
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder

                logger.info(f"Loading cross-encoder model: {self._model_name}")
                self._model = CrossEncoder(self._model_name)
                logger.info("Cross-encoder model loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load cross-encoder model: {e}")
                raise
        return self._model

    def rerank(
        self,
        query: str,
        chunks: list[dict[str, Any]],
        top_k: int = 8,
    ) -> list[dict[str, Any]]:
        """Score and rerank chunks by semantic relevance to query.

        Args:
            query: The original user query
            chunks: List of document chunk dicts (must have 'content' key)
            top_k: Number of top results to return

        Returns:
            Top-k chunks sorted by cross-encoder score, each with
            'rerank_score' added. Falls back to original order on error.
        """
        if not chunks:
            return []

        if len(chunks) <= 1:
            return chunks[:top_k]

        try:
            start = time.monotonic()
            model = self._get_model()

            # Build [query, content] pairs for the cross-encoder
            pairs = [[query, chunk.get("content", "")] for chunk in chunks]

            # Batch predict scores
            scores = model.predict(pairs)

            elapsed = time.monotonic() - start
            if elapsed > RERANK_TIMEOUT_SECONDS:
                logger.warning(
                    f"Reranking took {elapsed:.1f}s (>{RERANK_TIMEOUT_SECONDS}s) " f"for {len(chunks)} chunks"
                )

            # Attach scores and sort descending
            scored = []
            for chunk, score in zip(chunks, scores):
                enriched = dict(chunk)
                enriched["rerank_score"] = float(score)
                scored.append(enriched)

            scored.sort(key=lambda c: c["rerank_score"], reverse=True)

            logger.debug(
                f"Reranked {len(chunks)} chunks in {elapsed:.3f}s, " f"top score: {scored[0]['rerank_score']:.4f}"
            )

            return scored[:top_k]

        except Exception as e:
            logger.error(f"Reranking failed, returning original order: {e}")
            return chunks[:top_k]


# Singleton instance
_reranker_service: RerankerService | None = None


def get_reranker_service() -> RerankerService:
    """Get singleton reranker service instance."""
    global _reranker_service
    if _reranker_service is None:
        _reranker_service = RerankerService()
    return _reranker_service
