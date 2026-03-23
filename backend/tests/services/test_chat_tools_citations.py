"""Tests for citation grounding in chat document result assembly."""

from app.services.chat_tools import _format_doc_results


def test_format_doc_results_includes_grounded_citations():
    results = [
        {
            "document_title": "Chiller SOP",
            "content": "Step 1 isolate power and verify pressure.",
            "hybrid_score": 0.8123,
            "grounding": {
                "document_id": "doc-111",
                "chunk_id": "chunk-222",
                "section_title": "Safety",
                "page_number": 4,
                "source": "user_upload",
                "document_title": "Chiller SOP",
            },
        }
    ]

    payload = _format_doc_results(results, "chiller safety steps")
    assert payload["success"] is True
    assert payload["count"] == 1
    assert payload["results"][0]["title"] == "Chiller SOP"
    citation = payload["results"][0]["citation"]
    assert citation["document_id"] == "doc-111"
    assert citation["chunk_id"] == "chunk-222"
    assert citation["section_title"] == "Safety"
    assert citation["page_number"] == 4
    assert payload["citations"][0]["chunk_id"] == "chunk-222"
