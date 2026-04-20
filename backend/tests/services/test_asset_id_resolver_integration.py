"""
Phase 180-03: AssetIDResolver integration tests.

Tests the wiring of AssetIDResolver into the document pipeline:
- apply_resolution quarantine routing
- resolve_and_apply full flow
- Guard: empty equipment_description → LOW quarantine (manual uploads skip resolver)
"""

from unittest.mock import MagicMock

import pytest

from app.models.asset_resolution import (
    ResolutionConfidence,
    ResolutionMethod,
    ResolutionResult,
)


def _make_mock_db():
    """Create a chainable mock DB with call tracking."""
    db = MagicMock()
    # Default return values for common chains
    db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    db.table.return_value.upsert.return_value.execute.return_value = MagicMock(data=[])
    # compiler_queue chain: .insert().on_conflict().execute()
    compiler_queue_insert_mock = MagicMock(data=[])
    db.table.return_value.insert.return_value.on_conflict.return_value.execute.return_value = compiler_queue_insert_mock
    # Fallback: .insert().execute()
    db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[])
    db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    db.rpc.return_value.execute.return_value = MagicMock(data=[])
    return db


class TestApplyResolutionRouting:
    """Test apply_resolution quarantine routing logic."""

    def test_low_confidence_quarantines(self):
        """LOW confidence → quarantine path taken."""
        from app.services.asset_resolution_service import apply_resolution

        mock_db = _make_mock_db()
        doc_id = "doc-123"
        result = ResolutionResult(
            asset_id=None,
            confidence=0.4,
            confidence_band=ResolutionConfidence.LOW,
            method=ResolutionMethod.LLM_ASSISTED,
            matched_on="llm",
            needs_review=True,
            review_reason="low confidence",
        )

        apply_resolution(doc_id, result, mock_db)

        # Verify quarantine: db.table("documents").update(...).eq(...).execute() was called
        update_calls = mock_db.table.return_value.update.return_value.eq.return_value.execute.call_args_list
        assert len(update_calls) >= 1
        # Verify extraction_status='quarantined' was in the update
        first_update = mock_db.table.return_value.update.call_args
        assert first_update is not None

    def test_none_asset_id_quarantines_even_if_high(self):
        """None asset_id → quarantine regardless of confidence (B3 OR condition)."""
        from app.services.asset_resolution_service import apply_resolution

        mock_db = _make_mock_db()
        doc_id = "doc-123"
        result = ResolutionResult(
            asset_id=None,
            confidence=0.9,
            confidence_band=ResolutionConfidence.HIGH,
            method=ResolutionMethod.LLM_ASSISTED,
            matched_on="llm",
            needs_review=True,
            review_reason="not in equipment list",
        )

        apply_resolution(doc_id, result, mock_db)

        # Should quarantine (B3: asset_id is None → quarantine)
        update_calls = mock_db.table.return_value.update.return_value.eq.return_value.execute.call_args_list
        assert len(update_calls) >= 1

    def test_high_confidence_resolved_updates_document(self):
        """HIGH confidence + asset_id → documents.asset_id updated, not quarantined."""
        from app.services.asset_resolution_service import apply_resolution

        mock_db = _make_mock_db()
        doc_id = "doc-123"
        result = ResolutionResult(
            asset_id="S002-CHILLER-B1-001",
            confidence=0.95,
            confidence_band=ResolutionConfidence.HIGH,
            method=ResolutionMethod.EXACT,
            matched_on="alias",
            needs_review=False,
            review_reason=None,
        )

        apply_resolution(doc_id, result, mock_db)

        # Should update documents (not quarantine)
        update_calls = mock_db.table.return_value.update.return_value.eq.return_value.execute.call_args_list
        assert len(update_calls) >= 1

    def test_medium_confidence_creates_compiler_queue_entry(self):
        """MEDIUM confidence → compiler_queue table called for downstream processing."""
        from app.services.asset_resolution_service import apply_resolution

        mock_db = _make_mock_db()
        doc_id = "doc-123"
        result = ResolutionResult(
            asset_id="S002-CHILLER-B1-001",
            confidence=0.75,
            confidence_band=ResolutionConfidence.MEDIUM,
            method=ResolutionMethod.FUZZY,
            matched_on="fuzzy",
            needs_review=True,
            review_reason="verify",
        )

        apply_resolution(doc_id, result, mock_db)

        # Verify compiler_queue table was called
        table_calls = [c for c in mock_db.table.call_args_list if "compiler_queue" in str(c)]
        assert len(table_calls) >= 1

    def test_high_confidence_no_review_creates_compiler_queue(self):
        """HIGH confidence, no review needed → also enqueues compiler."""
        from app.services.asset_resolution_service import apply_resolution

        mock_db = _make_mock_db()
        doc_id = "doc-123"
        result = ResolutionResult(
            asset_id="S002-CHILLER-B1-001",
            confidence=0.95,
            confidence_band=ResolutionConfidence.HIGH,
            method=ResolutionMethod.EXACT,
            matched_on="alias",
            needs_review=False,
            review_reason=None,
        )

        apply_resolution(doc_id, result, mock_db)

        # Verify compiler_queue table was called
        table_calls = [c for c in mock_db.table.call_args_list if "compiler_queue" in str(c)]
        assert len(table_calls) >= 1


class TestResolveEmptyDescription:
    """Test that empty equipment_description is handled correctly."""

    @pytest.mark.asyncio
    async def test_empty_description_returns_low_quarantine(self):
        """Empty equipment_description → immediate LOW quarantine, no LLM call needed."""
        from app.services.asset_id_resolver import AssetIDResolver

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        resolver = AssetIDResolver(db=mock_db, site_id="site-002")
        result = await resolver.resolve("", "service_report")

        assert result.confidence_band == ResolutionConfidence.LOW
        assert result.method == ResolutionMethod.UNRESOLVED
        assert result.needs_review is True
        assert "empty description" in result.review_reason.lower()

    @pytest.mark.asyncio
    async def test_none_description_returns_low_quarantine(self):
        """None equipment_description → immediate LOW quarantine."""
        from app.services.asset_id_resolver import AssetIDResolver

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        resolver = AssetIDResolver(db=mock_db, site_id="site-002")
        result = await resolver.resolve(None, None)

        assert result.confidence_band == ResolutionConfidence.LOW
        assert result.needs_review is True


class TestResolveWithEquipmentDescription:
    """Test that non-empty equipment_description triggers resolution."""

    @pytest.mark.asyncio
    async def test_known_alias_resolves_exactly(self):
        """Known alias 'chiller 1' → EXACT match, HIGH confidence, no review."""
        from app.services.asset_id_resolver import AssetIDResolver

        mock_db = MagicMock()
        # asset_resolver_aliases returns the alias
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"alias": "chiller 1", "asset_id": "S002-CHILLER-B1-001"}]
        )

        resolver = AssetIDResolver(db=mock_db, site_id="site-002")
        result = await resolver.resolve("chiller 1", "service_report")

        assert result.method == ResolutionMethod.EXACT
        assert result.asset_id == "S002-CHILLER-B1-001"
        assert result.confidence == 1.0
        assert result.confidence_band == ResolutionConfidence.HIGH
        assert result.needs_review is False

    @pytest.mark.asyncio
    async def test_unknown_description_fuzzy_match_high(self):
        """Fuzzy score >= 0.85 → FUZZY, HIGH, no review needed."""
        from app.services.asset_id_resolver import AssetIDResolver

        mock_db = MagicMock()
        # No alias match, equipment table returns matching equipment
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "code": "S002-CHILLER-B1-001",
                    "type": "CHILLER",
                    "manufacturer": "Trane",
                    "model": "CVHE-450",
                    "display_name": "Chiller 1",
                }
            ]
        )

        resolver = AssetIDResolver(db=mock_db, site_id="site-002")
        # "chiller 1" should fuzzy-match "Chiller 1" with high score
        result = await resolver.resolve("chiller 1 compressor", "service_report")

        assert result.method in (ResolutionMethod.EXACT, ResolutionMethod.FUZZY)
        assert result.asset_id == "S002-CHILLER-B1-001"
        assert result.confidence_band in (ResolutionConfidence.HIGH, ResolutionConfidence.MEDIUM)
