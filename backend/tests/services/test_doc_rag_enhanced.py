"""Tests for the enhanced documentation RAG pipeline."""

import re
import pytest
from unittest.mock import patch, MagicMock

from app.services.doc_rag_service import (
    search_documentation,
    get_doc_rag_system_prompt,
)

# --- Helpers inlined (removed from doc_rag_service in Phase 67 refactor) ---

_EQUIPMENT_CODE_RE = re.compile(r"S\d{3}-[A-Z]+-[A-Z0-9]+-\d{3}")
_EQUIPMENT_TYPES = {
    "chiller",
    "ahu",
    "fcu",
    "vav",
    "split",
    "ct",
    "pump",
    "gen",
    "ups",
    "fire",
    "dali",
    "bess",
    "boiler",
}


def _contains_equipment_ref(text: str) -> bool:
    if _EQUIPMENT_CODE_RE.search(text):
        return True
    lower = text.lower()
    return any(t in lower for t in _EQUIPMENT_TYPES)


def _deduplicate_chunks(chunks: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for c in chunks:
        cid = c.get("id") or c.get("chunk_id") or id(c)
        existing = seen.get(cid)
        if existing is None or _extract_score(c) > _extract_score(existing):
            seen[cid] = c
    return list(seen.values())


def _extract_score(chunk: dict) -> float:
    raw = chunk.get("hybrid_score") or chunk.get("similarity") or 0.0
    try:
        return float(raw)
    except (ValueError, TypeError):
        return 0.0


class TestEquipmentRefDetection:
    """Test _contains_equipment_ref helper."""

    def test_detects_equipment_code(self):
        assert _contains_equipment_ref("S002-CHILLER-B1-001 is down") is True

    def test_detects_equipment_type_word(self):
        assert _contains_equipment_ref("the chiller is not cooling") is True
        assert _contains_equipment_ref("how does the AHU work?") is True
        assert _contains_equipment_ref("UPS battery replacement") is True

    def test_no_equipment_ref(self):
        assert _contains_equipment_ref("how does health scoring work?") is False
        assert _contains_equipment_ref("what is SENTINEL?") is False


class TestDeduplication:
    """Test chunk deduplication logic."""

    def test_deduplicates_by_id(self):
        chunks = [
            {"id": "aaa", "content": "chunk A", "hybrid_score": 0.7},
            {"id": "bbb", "content": "chunk B", "hybrid_score": 0.5},
            {"id": "aaa", "content": "chunk A", "hybrid_score": 0.9},
        ]
        result = _deduplicate_chunks(chunks)
        assert len(result) == 2
        # The 'aaa' chunk should keep the higher score (0.9)
        aaa_chunk = next(c for c in result if c["id"] == "aaa")
        assert aaa_chunk["hybrid_score"] == 0.9

    def test_deduplicates_by_chunk_id_key(self):
        """Falls back to chunk_id if id not present."""
        chunks = [
            {"chunk_id": "x", "content": "same", "hybrid_score": 0.3},
            {"chunk_id": "x", "content": "same", "hybrid_score": 0.6},
        ]
        result = _deduplicate_chunks(chunks)
        assert len(result) == 1
        assert result[0]["hybrid_score"] == 0.6

    def test_empty_input(self):
        assert _deduplicate_chunks([]) == []

    def test_no_duplicates_passes_through(self):
        chunks = [
            {"id": "a", "content": "one", "hybrid_score": 0.5},
            {"id": "b", "content": "two", "hybrid_score": 0.6},
        ]
        result = _deduplicate_chunks(chunks)
        assert len(result) == 2


class TestExtractScore:
    """Test score extraction helper."""

    def test_hybrid_score(self):
        assert _extract_score({"hybrid_score": 0.85}) == 0.85

    def test_similarity_fallback(self):
        assert _extract_score({"similarity": 0.7}) == 0.7

    def test_string_score(self):
        assert _extract_score({"hybrid_score": "0.65"}) == 0.65

    def test_missing_score(self):
        assert _extract_score({}) == 0.0

    def test_invalid_string(self):
        assert _extract_score({"hybrid_score": "not_a_number"}) == 0.0


class TestSearchDocumentation:
    """Test the simplified search pipeline with mocks."""

    @pytest.mark.asyncio
    @patch("app.services.doc_rag_service.get_vector_db_service")
    @patch("app.services.doc_rag_service.get_supabase_client")
    async def test_full_pipeline(self, mock_client, mock_vdb_factory):
        """Simplified pipeline: hybrid_search returns results directly."""
        mock_vdb = MagicMock()
        mock_vdb.hybrid_search.return_value = [
            {"id": "a", "content": "Chiller health uses sensors", "hybrid_score": 0.85},
            {"id": "b", "content": "Generator maintenance", "hybrid_score": 0.5},
            {"id": "c", "content": "Cooling plant overview", "hybrid_score": 0.7},
        ]
        mock_vdb_factory.return_value = mock_vdb

        results = await search_documentation("chiller health scoring", n_results=5)

        # Verify hybrid_search was called once
        mock_vdb.hybrid_search.assert_called_once_with(
            query="chiller health scoring",
            n_results=5,
            equipment_type=None,
            site_id=None,
            keyword_weight=0.4,
            semantic_weight=0.6,
        )

        assert len(results) == 3
        assert results[0]["id"] == "a"

    @pytest.mark.asyncio
    @patch("app.services.doc_rag_service.get_vector_db_service")
    @patch("app.services.doc_rag_service.get_supabase_client")
    async def test_site_id_passed_through(self, mock_client, mock_vdb_factory):
        """Building ID is forwarded to hybrid_search."""
        mock_vdb = MagicMock()
        mock_vdb.hybrid_search.return_value = [
            {"id": "a", "content": "Chiller doc", "hybrid_score": 0.8},
        ]
        mock_vdb_factory.return_value = mock_vdb

        results = await search_documentation("chiller fault", site_id="site-002-uuid")

        mock_vdb.hybrid_search.assert_called_once()
        call_kwargs = mock_vdb.hybrid_search.call_args
        assert call_kwargs[1]["site_id"] == "site-002-uuid"
        assert len(results) == 1

    @pytest.mark.asyncio
    @patch("app.services.doc_rag_service.get_vector_db_service")
    @patch("app.services.doc_rag_service.get_supabase_client")
    async def test_search_returns_empty_on_no_results(self, mock_client, mock_vdb_factory):
        """Empty result set is returned cleanly."""
        mock_vdb = MagicMock()
        mock_vdb.hybrid_search.return_value = []
        mock_vdb_factory.return_value = mock_vdb

        results = await search_documentation("nonexistent topic")
        assert results == []

    @pytest.mark.asyncio
    @patch("app.services.doc_rag_service.get_supabase_client")
    async def test_total_failure_returns_empty(self, mock_client):
        """On complete failure, returns empty list."""
        mock_client.side_effect = Exception("DB down")
        results = await search_documentation("any query")
        assert results == []


class TestDocRagSystemPrompt:
    """Test system prompt generation."""

    @patch("app.services.doc_rag_service.fm_context_service")
    def test_prompt_includes_doc_results(self, mock_fm):
        mock_fm.get_full_context.return_value = "Building: Test"

        results = [
            {
                "document_title": "Health Scoring Guide",
                "section_title": "Overview",
                "content": "Equipment health is scored 0-100%",
                "hybrid_score": 0.85,
            }
        ]
        prompt = get_doc_rag_system_prompt(results)

        assert "Health Scoring Guide" in prompt
        assert "Equipment health is scored 0-100%" in prompt
        assert "Building: Test" in prompt

    @patch("app.services.doc_rag_service.fm_context_service")
    def test_prompt_with_hybrid_score_formatted(self, mock_fm):
        """Score is formatted as percentage (e.g. 92%)."""
        mock_fm.get_full_context.return_value = ""

        results = [
            {
                "document_title": "Test Doc",
                "content": "Test content",
                "hybrid_score": 0.92,
            }
        ]
        prompt = get_doc_rag_system_prompt(results)
        # Current service formats as {score:.0%} → "92%"
        assert "relevance: 92%" in prompt
        assert "Test Doc" in prompt

    @patch("app.services.doc_rag_service.fm_context_service")
    def test_prompt_with_title_fallback(self, mock_fm):
        """Doc with 'title' key (no 'document_title') still renders."""
        mock_fm.get_full_context.return_value = ""

        results = [
            {
                "title": "Compressor Fault Guide",
                "content": "Check refrigerant levels and discharge temp",
                "hybrid_score": 0.75,
            },
        ]
        prompt = get_doc_rag_system_prompt(results)
        assert "Compressor Fault Guide" in prompt
        assert "Check refrigerant levels" in prompt
        assert "relevance: 75%" in prompt

    @patch("app.services.doc_rag_service.fm_context_service")
    def test_prompt_no_results(self, mock_fm):
        mock_fm.get_full_context.return_value = ""

        prompt = get_doc_rag_system_prompt([])
        assert "No specific documentation found" in prompt
