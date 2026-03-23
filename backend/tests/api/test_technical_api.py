"""Tests for technical support API surfaces."""

import pytest
from unittest.mock import patch

from app.services.hybrid_query_service import HybridContext


class DummyHybridService:
    """Minimal HybridQueryService replacement for tests."""

    async def query(
        self,
        *,
        equipment_id=None,
        bacnet_ref=None,
        question=None,
        include_documents=None,
        include_telemetry=None,
        include_ml=None,
        include_points=None,
        include_decision_memory=None,
        include_active_events=None,
    ) -> HybridContext:
        ctx = HybridContext(
            equipment_id=equipment_id or "S002-CHILLER-B1-001",
            equipment_type="Chiller",
            site_id="site-002",
        )
        ctx.sources_used = ["document_rag"]
        ctx.retrieval_telemetry = {
            "trace_id": "trace-123",
            "retrieval_path": "canonical_doc_rag",
            "query_time_ms": 38,
            "top_k_requested": 5,
            "hit_count": 2,
            "used_fallback": "ocr_fallback",
            "fallback_reason": "low-text PDF",
        }
        return ctx


@pytest.mark.asyncio
async def test_hybrid_context_endpoint_returns_telemetry(client, auth_headers_admin):
    payload = {
        "site_id": "site-002",
        "equipment_id": "S002-CHILLER-B1-001",
        "question": "What did the last inspection say?",
    }

    with patch("app.services.hybrid_query_service.get_hybrid_query_service", return_value=DummyHybridService()):
        response = await client.post("/api/technical/hybrid-context", json=payload, headers=auth_headers_admin)

    assert response.status_code == 200
    data = response.json()

    telemetry = data["retrievalTelemetry"]
    assert telemetry["trace_id"] == "trace-123"
    assert telemetry["retrieval_path"] == "canonical_doc_rag"
    assert telemetry["hit_count"] == 2
    assert telemetry["used_fallback"] == "ocr_fallback"
    assert telemetry["fallback_reason"] == "low-text PDF"

    context_telemetry = data["context"]["retrievalTelemetry"]
    assert context_telemetry["top_k_requested"] == 5
    assert context_telemetry["query_time_ms"] == 38
