"""Tests for cross-encoder reranker service."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.services.reranker_service import RerankerService, get_reranker_service


@pytest.fixture
def reranker():
    """Create a fresh RerankerService instance (not singleton)."""
    return RerankerService()


@pytest.fixture
def sample_chunks():
    """Sample document chunks for reranking."""
    return [
        {"id": "a", "content": "Chiller health scoring uses real-time sensor data", "hybrid_score": 0.7},
        {"id": "b", "content": "Generator maintenance schedule for diesel gensets", "hybrid_score": 0.8},
        {"id": "c", "content": "Chiller plant operates with staged loading", "hybrid_score": 0.6},
        {"id": "d", "content": "Solar panel cleaning best practices", "hybrid_score": 0.5},
        {"id": "e", "content": "Equipment health thresholds: 0-50 critical, 50-70 warning", "hybrid_score": 0.65},
    ]


class TestRerankerService:
    """Tests for RerankerService."""

    def test_rerank_empty_list(self, reranker):
        """Empty input returns empty output."""
        result = reranker.rerank("test query", [])
        assert result == []

    def test_rerank_single_chunk(self, reranker):
        """Single chunk returned as-is without model loading."""
        chunks = [{"id": "x", "content": "some content"}]
        result = reranker.rerank("query", chunks)
        assert len(result) == 1
        assert result[0]["id"] == "x"

    @patch("app.services.reranker_service.RerankerService._get_model")
    def test_rerank_sorts_by_score(self, mock_get_model, reranker, sample_chunks):
        """Chunks are sorted by cross-encoder score descending."""
        mock_model = MagicMock()
        # Assign scores: a=0.9, b=0.1, c=0.8, d=0.05, e=0.7
        mock_model.predict.return_value = np.array([0.9, 0.1, 0.8, 0.05, 0.7])
        mock_get_model.return_value = mock_model

        result = reranker.rerank("chiller health scoring", sample_chunks, top_k=3)

        assert len(result) == 3
        assert result[0]["id"] == "a"  # score 0.9
        assert result[1]["id"] == "c"  # score 0.8
        assert result[2]["id"] == "e"  # score 0.7
        # Each result should have rerank_score
        assert "rerank_score" in result[0]
        assert result[0]["rerank_score"] == pytest.approx(0.9)

    @patch("app.services.reranker_service.RerankerService._get_model")
    def test_rerank_respects_top_k(self, mock_get_model, reranker, sample_chunks):
        """top_k limits the number of returned results."""
        mock_model = MagicMock()
        mock_model.predict.return_value = np.array([0.5, 0.4, 0.3, 0.2, 0.1])
        mock_get_model.return_value = mock_model

        result = reranker.rerank("query", sample_chunks, top_k=2)
        assert len(result) == 2

    @patch("app.services.reranker_service.RerankerService._get_model")
    def test_rerank_preserves_chunk_fields(self, mock_get_model, reranker):
        """All original chunk fields are preserved in output."""
        mock_model = MagicMock()
        mock_model.predict.return_value = np.array([0.5, 0.3])
        mock_get_model.return_value = mock_model

        chunks = [
            {"id": "1", "content": "test", "document_title": "Doc A", "section_title": "Intro"},
            {"id": "2", "content": "test2", "document_title": "Doc B", "section_title": "Setup"},
        ]
        result = reranker.rerank("query", chunks)

        assert result[0]["document_title"] == "Doc A"
        assert result[0]["section_title"] == "Intro"
        assert result[1]["document_title"] == "Doc B"

    @patch("app.services.reranker_service.RerankerService._get_model")
    def test_rerank_fallback_on_model_error(self, mock_get_model, reranker, sample_chunks):
        """On model failure, returns original order truncated to top_k."""
        mock_get_model.side_effect = RuntimeError("Model load failed")

        result = reranker.rerank("query", sample_chunks, top_k=3)

        # Should return first 3 in original order (graceful fallback)
        assert len(result) == 3
        assert result[0]["id"] == "a"
        assert result[1]["id"] == "b"
        assert result[2]["id"] == "c"

    @patch("app.services.reranker_service.RerankerService._get_model")
    def test_rerank_fallback_on_predict_error(self, mock_get_model, reranker, sample_chunks):
        """On predict failure, returns original order."""
        mock_model = MagicMock()
        mock_model.predict.side_effect = ValueError("Bad input")
        mock_get_model.return_value = mock_model

        result = reranker.rerank("query", sample_chunks, top_k=3)
        assert len(result) == 3

    def test_singleton_returns_same_instance(self):
        """get_reranker_service returns a singleton."""
        import app.services.reranker_service as mod

        mod._reranker_service = None
        s1 = get_reranker_service()
        s2 = get_reranker_service()
        assert s1 is s2
        mod._reranker_service = None  # cleanup

    @patch("app.services.reranker_service.RerankerService._get_model")
    def test_rerank_handles_missing_content_key(self, mock_get_model, reranker):
        """Chunks without 'content' key use empty string."""
        mock_model = MagicMock()
        mock_model.predict.return_value = np.array([0.5, 0.3])
        mock_get_model.return_value = mock_model

        chunks = [
            {"id": "1"},  # no content key
            {"id": "2", "content": "has content"},
        ]
        result = reranker.rerank("query", chunks)
        assert len(result) == 2
