"""
Tests for Phase 180-02: asset_resolution_service + LLM stage.

Covers:
- apply_resolution: quarantine for LOW/none asset_id
- apply_resolution: resolved updates documents table
- apply_resolution: compiler_queue entry on resolved
- resolve_and_apply: full document_id → resolve → apply pipeline
- LLM resolution: verify prompt construction and JSON parsing via gateway injection
- LLM failure: gateway raises → returns UNRESOLVED, quarantine
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.asset_resolution import (
    ResolutionConfidence,
    ResolutionMethod,
    ResolutionResult,
)
from app.services.asset_id_resolver import AssetIDResolver
from app.services.asset_resolution_service import apply_resolution


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def mock_db():
    """Minimal async-style mock matching self.db.table().execute() pattern."""
    return MagicMock()


@pytest.fixture
def equipment_data():
    return [
        {
            "code": "S002-CHILLER-B1-001",
            "type": "CHILLER",
            "manufacturer": "Carrier",
            "model": "30XA4525",
            "display_name": "Chiller B1 — Primary",
        },
        {
            "code": "S002-AHU-001",
            "type": "AHU",
            "manufacturer": "Johnson Controls",
            "model": "YMEA45",
            "display_name": "AHU-1 — Lobby",
        },
    ]


# --------------------------------------------------------------------------- #
# apply_resolution — quarantine tests
# --------------------------------------------------------------------------- #


class TestApplyResolutionQuarantine:
    """B3 FIX: quarantine if asset_id is None OR confidence_band is LOW (OR, not AND)."""

    def test_medium_confidence_needs_review_is_resolved_not_quarantined(self, mock_db):
        """MEDIUM band → NOT quarantined; goes to resolved path with needs_human_review=True."""
        result = ResolutionResult(
            asset_id="S002-CHILLER-B1-001",
            confidence=0.62,
            confidence_band=ResolutionConfidence.MEDIUM,
            method=ResolutionMethod.FUZZY,
            matched_on="display_name",
            needs_review=True,
            review_reason="fuzzy match below HIGH threshold",
        )
        mock_table = mock_db.table.return_value
        mock_update = MagicMock()
        mock_table.update.return_value = mock_update
        mock_update.eq.return_value = mock_update
        mock_update.execute.return_value = MagicMock()

        apply_resolution("doc-uuid-1", result, mock_db)

        mock_table.update.assert_called_once()
        call_args = mock_table.update.call_args[0][0]
        assert call_args["extraction_status"] == "resolved"
        assert call_args["asset_id"] == "S002-CHILLER-B1-001"

    def test_none_asset_id_quarantined(self, mock_db):
        """asset_id=None → quarantined regardless of confidence."""
        result = ResolutionResult(
            asset_id=None,
            confidence=0.0,
            confidence_band=ResolutionConfidence.LOW,
            method=ResolutionMethod.UNRESOLVED,
            matched_on=None,
            needs_review=True,
            review_reason="no match found",
        )
        mock_table = mock_db.table.return_value
        mock_update = MagicMock()
        mock_table.update.return_value = mock_update
        mock_update.eq.return_value = mock_update
        mock_update.execute.return_value = MagicMock()

        apply_resolution("doc-uuid-none", result, mock_db)

        call_args = mock_table.update.call_args[0][0]
        assert call_args["extraction_status"] == "quarantined"
        assert call_args["needs_human_review"] is True

    def test_low_confidence_band_quarantined(self, mock_db):
        """confidence_band=LOW → quarantined even with an asset_id present."""
        result = ResolutionResult(
            asset_id="S002-CHILLER-B1-001",
            confidence=0.45,
            confidence_band=ResolutionConfidence.LOW,
            method=ResolutionMethod.LLM_ASSISTED,
            matched_on="llm",
            needs_review=True,
            review_reason="llm returned low confidence",
        )
        mock_table = mock_db.table.return_value
        mock_update = MagicMock()
        mock_table.update.return_value = mock_update
        mock_update.eq.return_value = mock_update
        mock_update.execute.return_value = MagicMock()

        apply_resolution("doc-uuid-low", result, mock_db)

        call_args = mock_table.update.call_args[0][0]
        assert call_args["extraction_status"] == "quarantined"

    def test_high_confidence_no_review_not_quarantined(self, mock_db):
        """HIGH confidence, no review needed → asset_id set, NOT quarantined."""
        result = ResolutionResult(
            asset_id="S002-CHILLER-B1-001",
            confidence=0.95,
            confidence_band=ResolutionConfidence.HIGH,
            method=ResolutionMethod.EXACT,
            matched_on="alias",
            needs_review=False,
            review_reason=None,
        )
        mock_table = mock_db.table.return_value
        mock_update = MagicMock()
        mock_table.update.return_value = mock_update
        mock_update.eq.return_value = mock_update
        mock_update.execute.return_value = MagicMock()

        apply_resolution("doc-uuid-high", result, mock_db)

        call_args = mock_table.update.call_args[0][0]
        assert call_args["extraction_status"] == "resolved"
        assert call_args["asset_id"] == "S002-CHILLER-B1-001"
        assert call_args["resolution_method"] == "exact"
        assert call_args["resolution_confidence"] == 0.95
        assert call_args["needs_human_review"] is False


# --------------------------------------------------------------------------- #
# apply_resolution — compiler_queue tests
# --------------------------------------------------------------------------- #


class TestApplyResolutionCompilerQueue:
    """Resolved + (not needs_review OR MEDIUM) → compiler_queue entry created."""

    def test_high_confidence_no_review_enqueues(self, mock_db):
        """HIGH + no review needed → enqueue compiler."""
        result = ResolutionResult(
            asset_id="S002-CHILLER-B1-001",
            confidence=0.90,
            confidence_band=ResolutionConfidence.HIGH,
            method=ResolutionMethod.EXACT,
            matched_on="alias",
            needs_review=False,
            review_reason=None,
        )
        mock_table = mock_db.table.return_value
        mock_update = MagicMock()
        mock_table.update.return_value = mock_update
        mock_update.eq.return_value = mock_update
        mock_update.execute.return_value = MagicMock()

        mock_insert = MagicMock()
        mock_on_conflict = MagicMock()
        mock_insert.on_conflict.return_value = mock_on_conflict
        mock_on_conflict.execute.return_value = MagicMock()
        mock_db.table.return_value.insert.return_value = mock_insert

        apply_resolution("doc-uuid-enqueue-1", result, mock_db)

        mock_db.table.return_value.insert.assert_called()
        ins_call = mock_db.table.return_value.insert.call_args[0][0]
        assert ins_call["asset_id"] == "S002-CHILLER-B1-001"
        assert ins_call["trigger_event"] == "asset_resolved"

    def test_medium_confidence_needs_review_enqueues(self, mock_db):
        """MEDIUM band + needs_review=True → enqueue compiler (MEDIUM satisfies condition)."""
        result = ResolutionResult(
            asset_id="S002-AHU-001",
            confidence=0.70,
            confidence_band=ResolutionConfidence.MEDIUM,
            method=ResolutionMethod.FUZZY,
            matched_on="display_name",
            needs_review=True,
            review_reason="fuzzy match below HIGH threshold",
        )
        mock_table = mock_db.table.return_value
        mock_update = MagicMock()
        mock_table.update.return_value = mock_update
        mock_update.eq.return_value = mock_update
        mock_update.execute.return_value = MagicMock()

        mock_insert = MagicMock()
        mock_on_conflict = MagicMock()
        mock_insert.on_conflict.return_value = mock_on_conflict
        mock_insert.execute.return_value = MagicMock()
        mock_db.table.return_value.insert.return_value = mock_insert

        apply_resolution("doc-uuid-enqueue-2", result, mock_db)

        mock_db.table.return_value.insert.assert_called()

    def test_high_confidence_needs_review_does_not_enqueue(self, mock_db):
        """HIGH + needs_review=True → NOT enqueued (not needs_review condition fails)."""
        result = ResolutionResult(
            asset_id="S002-CHILLER-B1-001",
            confidence=0.90,
            confidence_band=ResolutionConfidence.HIGH,
            method=ResolutionMethod.LLM_ASSISTED,
            matched_on="llm",
            needs_review=True,
            review_reason="llm reason",
        )
        mock_table = mock_db.table.return_value
        mock_update = MagicMock()
        mock_table.update.return_value = mock_update
        mock_update.eq.return_value = mock_update
        mock_update.execute.return_value = MagicMock()

        mock_insert = MagicMock()
        mock_on_conflict = MagicMock()
        mock_insert.on_conflict.return_value = mock_on_conflict
        mock_on_conflict.execute.return_value = MagicMock()
        mock_db.table.return_value.insert.return_value = mock_insert

        apply_resolution("doc-uuid-noenqueue", result, mock_db)

        # not True = False; False OR False = False → no enqueue
        mock_db.table.return_value.insert.assert_not_called()


# --------------------------------------------------------------------------- #
# LLM resolution tests — use gateway= injection
# --------------------------------------------------------------------------- #


class TestLLMResolution:
    """Stage 4 — _llm_resolve with injected mock gateway (no patching needed)."""

    def _make_async_gateway(self, response_text: str):
        """Return a mock gateway whose call() async method returns response_text."""
        mock = MagicMock()
        async def fake_call(**kwargs):
            return response_text
        mock.call = fake_call
        return mock

    def _make_failing_gateway(self, exc: Exception):
        """Return a mock gateway whose call() async method raises exc."""
        mock = MagicMock()
        async def fake_call(**kwargs):
            raise exc
        mock.call = fake_call
        return mock

    def test_llm_resolve_returns_asset_id(self, mock_db, equipment_data):
        """Valid LLM JSON response with valid asset_id → LLM_ASSISTED result."""
        mock_gw = self._make_async_gateway(
            '{"asset_id": "S002-CHILLER-B1-001", "confidence": 0.82, "reason": "matched on chiller model"}'
        )

        mock_exec = MagicMock()
        mock_exec.data = equipment_data
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = mock_exec
        mock_db.table.return_value = mock_table

        resolver = AssetIDResolver(db=mock_db, site_id="site-002")

        import asyncio
        result = resolver._llm_resolve(
            "Primary chiller for building B1",
            equipment_data,
            "maint_work_order",
            gateway=mock_gw,
        )
        resolved = asyncio.get_event_loop().run_until_complete(result)

        assert resolved.method == ResolutionMethod.LLM_ASSISTED
        assert resolved.asset_id == "S002-CHILLER-B1-001"
        assert resolved.confidence == pytest.approx(0.82)
        assert resolved.confidence_band == ResolutionConfidence.MEDIUM
        assert resolved.needs_review is True
        assert resolved.matched_on == "llm"

    def test_llm_resolve_invalid_asset_id_quarantined(self, mock_db, equipment_data):
        """LLM returns asset_id not in equipment list → quarantined."""
        mock_gw = self._make_async_gateway(
            '{"asset_id": "S002-BOGUS-999", "confidence": 0.90, "reason": "close match"}'
        )

        mock_exec = MagicMock()
        mock_exec.data = equipment_data
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = mock_exec
        mock_db.table.return_value = mock_table

        resolver = AssetIDResolver(db=mock_db, site_id="site-002")

        import asyncio
        result = resolver._llm_resolve("some equipment", equipment_data, None, gateway=mock_gw)
        resolved = asyncio.get_event_loop().run_until_complete(result)

        assert resolved.asset_id is None
        assert resolved.needs_review is True
        assert "invalid asset_id" in resolved.review_reason

    def test_llm_resolve_null_asset_id_quarantined(self, mock_db, equipment_data):
        """LLM returns null asset_id → quarantined (LOW confidence)."""
        mock_gw = self._make_async_gateway(
            '{"asset_id": null, "confidence": 0.30, "reason": "no match found"}'
        )

        mock_exec = MagicMock()
        mock_exec.data = equipment_data
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = mock_exec
        mock_db.table.return_value = mock_table

        resolver = AssetIDResolver(db=mock_db, site_id="site-002")

        import asyncio
        result = resolver._llm_resolve("unknown equipment xyz", equipment_data, "work_order", gateway=mock_gw)
        resolved = asyncio.get_event_loop().run_until_complete(result)

        assert resolved.asset_id is None
        assert resolved.confidence_band == ResolutionConfidence.LOW

    def test_llm_resolve_json_decode_error_returns_unresolved(self, mock_db, equipment_data):
        """model_gateway returns invalid JSON → UNRESOLVED, quarantined."""
        mock_gw = self._make_async_gateway("this is not JSON {{{")

        mock_exec = MagicMock()
        mock_exec.data = equipment_data
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = mock_exec
        mock_db.table.return_value = mock_table

        resolver = AssetIDResolver(db=mock_db, site_id="site-002")

        import asyncio
        result = resolver._llm_resolve("chiller unit", equipment_data, None, gateway=mock_gw)
        resolved = asyncio.get_event_loop().run_until_complete(result)

        assert resolved.method == ResolutionMethod.UNRESOLVED
        assert resolved.asset_id is None
        assert resolved.needs_review is True
        assert "llm stage failed" in resolved.review_reason

    def test_llm_gateway_raises_returns_unresolved(self, mock_db, equipment_data):
        """model_gateway.call raises → returns UNRESOLVED, quarantined."""
        mock_gw = self._make_failing_gateway(RuntimeError("network error"))

        mock_exec = MagicMock()
        mock_exec.data = equipment_data
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = mock_exec
        mock_db.table.return_value = mock_table

        resolver = AssetIDResolver(db=mock_db, site_id="site-002")

        import asyncio
        result = resolver._llm_resolve("chiller unit", equipment_data, None, gateway=mock_gw)
        resolved = asyncio.get_event_loop().run_until_complete(result)

        assert resolved.method == ResolutionMethod.UNRESOLVED
        assert resolved.needs_review is True
        assert "network error" in resolved.review_reason

    def test_llm_esc_prevents_brace_injection(self, mock_db, equipment_data):
        """Equipment description with braces → braces escaped as {{}} in prompt string."""
        response = '{"asset_id": "S002-CHILLER-B1-001", "confidence": 0.85, "reason": "ok"}'
        call_args_container = []

        async def tracking_call(**kwargs):
            call_args_container.append(kwargs)
            return response

        mock_gw = MagicMock()
        mock_gw.call = tracking_call

        mock_exec = MagicMock()
        mock_exec.data = equipment_data
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = mock_exec
        mock_db.table.return_value = mock_table

        resolver = AssetIDResolver(db=mock_db, site_id="site-002")

        import asyncio
        result = resolver._llm_resolve(
            "Chiller {B1} compressor {unit}",
            equipment_data,
            "maint_work_order",
            gateway=mock_gw,
        )
        resolved = asyncio.get_event_loop().run_until_complete(result)

        # Verify braces are doubled in the prompt (B6 fix: _esc replaces { with {{)
        assert len(call_args_container) == 1
        prompt_content = call_args_container[0]["messages"][0]["content"]
        # After _esc: {{B1}} stays as {{B1}} in the plain string
        assert "{{B1}}" in prompt_content
        assert "{{unit}}" in prompt_content
        assert resolved.asset_id == "S002-CHILLER-B1-001"

    def test_llm_esc_escapes_doc_type_braces(self, mock_db, equipment_data):
        """Document type with braces → braces escaped in prompt."""
        response = '{"asset_id": "S002-AHU-001", "confidence": 0.75, "reason": "ok"}'
        call_args_container = []

        async def tracking_call(**kwargs):
            call_args_container.append(kwargs)
            return response

        mock_gw = MagicMock()
        mock_gw.call = tracking_call

        mock_exec = MagicMock()
        mock_exec.data = equipment_data
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = mock_exec
        mock_db.table.return_value = mock_table

        resolver = AssetIDResolver(db=mock_db, site_id="site-002")

        import asyncio
        result = resolver._llm_resolve(
            "Air handler unit",
            equipment_data,
            "maint_{work}_order",
            gateway=mock_gw,
        )
        resolved = asyncio.get_event_loop().run_until_complete(result)

        assert len(call_args_container) == 1
        prompt_content = call_args_container[0]["messages"][0]["content"]
        # _esc converts {work} to {{work}} in the document_type field
        assert "{{work}}" in prompt_content
        assert resolved.asset_id == "S002-AHU-001"


# --------------------------------------------------------------------------- #
# resolve_and_apply tests
# --------------------------------------------------------------------------- #


class TestResolveAndApply:
    """Full pipeline: fetch document → resolve → apply_resolution."""

    @pytest.mark.asyncio
    async def test_resolve_and_apply_full_flow(self, mock_db, equipment_data):
        """Document found → LLM resolves → apply_resolution called."""
        # Use a description that WON'T fuzzy-match so LLM stage is reached
        doc_record = {
            "id": "doc-123",
            "equipment_description": "ZB-9000 controller module for BAS integration panel",
            "document_type": "maint_work_order",
        }

        def make_table_side_effect(name):
            mock_t = MagicMock()
            if name == "documents":
                mock_select = MagicMock()
                mock_select.select.return_value = mock_select
                mock_select.eq.return_value = mock_select
                mock_select.execute.return_value = MagicMock(data=[doc_record])
                mock_t.select.return_value = mock_select
            elif name == "equipment":
                mock_select = MagicMock()
                mock_select.select.return_value = mock_select
                mock_select.eq.return_value = mock_select
                mock_select.execute.return_value = MagicMock(data=equipment_data)
                mock_t.select.return_value = mock_select
            return mock_t

        mock_db.table.side_effect = make_table_side_effect

        mock_update = MagicMock()
        mock_db.table.return_value.update.return_value = mock_update
        mock_update.eq.return_value = mock_update
        mock_update.execute.return_value = MagicMock()

        response = '{"asset_id": "S002-CHILLER-B1-001", "confidence": 0.90, "reason": ""}'
        mock_gw = MagicMock()
        async def fake_call(**kwargs):
            return response
        mock_gw.call = fake_call

        resolver = AssetIDResolver(db=mock_db, site_id="site-002")
        result = await resolver.resolve_and_apply("doc-123", gateway=mock_gw)

        assert result.asset_id == "S002-CHILLER-B1-001"
        assert result.method == ResolutionMethod.LLM_ASSISTED

    @pytest.mark.asyncio
    async def test_resolve_and_apply_document_not_found(self, mock_db):
        """Document not found → UNRESOLVED returned, no apply called."""
        def make_table_side_effect(name):
            mock_t = MagicMock()
            mock_select = MagicMock()
            mock_select.select.return_value = mock_select
            mock_select.eq.return_value = mock_select
            mock_select.execute.return_value = MagicMock(data=[])
            mock_t.select.return_value = mock_select
            return mock_t

        mock_db.table.side_effect = make_table_side_effect

        resolver = AssetIDResolver(db=mock_db, site_id="site-002")
        result = await resolver.resolve_and_apply("doc-nonexistent")

        assert result.asset_id is None
        assert result.method == ResolutionMethod.UNRESOLVED
        assert "not found" in result.review_reason


# --------------------------------------------------------------------------- #
# Integration: resolve() calls _llm_resolve when stage 3 misses
# --------------------------------------------------------------------------- #


class TestResolveIntegration:
    """resolve() async → calls _llm_resolve when stages 1-3 all miss."""

    @pytest.mark.asyncio
    async def test_resolve_calls_llm_when_fuzzy_misses(self, mock_db, equipment_data):
        """Best fuzzy score < 0.60 → Stage 4 called via gateway injection."""
        def make_table_side_effect(name):
            mock_t = MagicMock()
            if name == "equipment":
                mock_select = MagicMock()
                mock_select.select.return_value = mock_select
                mock_select.eq.return_value = mock_select
                mock_select.execute.return_value = MagicMock(data=equipment_data)
                mock_t.select.return_value = mock_select
            elif name == "documents":
                mock_select = MagicMock()
                mock_select.select.return_value = mock_select
                mock_select.eq.return_value = mock_select
                mock_select.execute.return_value = MagicMock(data=[])
                mock_t.select.return_value = mock_select
            return mock_t

        mock_db.table.side_effect = make_table_side_effect

        mock_update = MagicMock()
        mock_db.table.return_value.update.return_value = mock_update
        mock_update.eq.return_value = mock_update
        mock_update.execute.return_value = MagicMock()

        response = '{"asset_id": "S002-AHU-001", "confidence": 0.75, "reason": "partial match"}'
        mock_gw = MagicMock()
        async def fake_call(**kwargs):
            return response
        mock_gw.call = fake_call

        resolver = AssetIDResolver(db=mock_db, site_id="site-002")

        # Description that won't fuzzy-match
        result = await resolver.resolve(
            "Compressor unit XYZ xyz unknown", "work_order", gateway=mock_gw
        )

        assert result.method == ResolutionMethod.LLM_ASSISTED
        assert result.asset_id == "S002-AHU-001"
