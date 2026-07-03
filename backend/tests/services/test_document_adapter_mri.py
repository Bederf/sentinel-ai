"""
Tests for ConceptMRIAdapter — Phase 179-03.

Tests cover:
    - __init__ sets self.db and self.client
    - source_system == SourceSystem.CONCEPT_MRI
    - normalise() maps FIELD_MAP fields to DocumentRecord correctly
    - _map_document_type: known values return correct DocumentType, unknown returns UNKNOWN
    - _parse_date: valid ISO date returns date, invalid returns None
    - _resolve_site delegates to site_resolver or returns UNKNOWN
    - fetch_new_documents calls client.fetch_documents and normalises each result
    - get_document_file delegates to client.get_document_file
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.document_record import DocumentRecord, DocumentType, ExtractionStatus
from app.models.document_source import SourceSystem
from app.services.document_indexing_service import IndexingStatus
from app.services.document_adapter_mri import FIELD_MAP, ConceptMRIAdapter


class TestConceptMRIAdapterInit:
    """Test __init__ sets self.db and self.client, source_system is CONCEPT_MRI."""

    def test_init_sets_db(self):
        with patch("app.services.document_source_adapter._get_supabase") as mock_get:
            mock_get.return_value = MagicMock()
            adapter = ConceptMRIAdapter()
            assert adapter.db is mock_get.return_value

    def test_init_sets_client(self):
        with (
            patch("app.services.document_source_adapter._get_supabase"),
            patch("app.services.document_adapter_mri.MRIDocumentClient") as MockClient,
        ):
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance
            adapter = ConceptMRIAdapter()
            assert adapter.client is mock_instance

    def test_source_system_is_concept_mri(self):
        with patch("app.services.document_source_adapter._get_supabase"):
            adapter = ConceptMRIAdapter()
            assert adapter.source_system == SourceSystem.CONCEPT_MRI

    def test_adapter_table_default(self):
        with patch("app.services.document_source_adapter._get_supabase"):
            adapter = ConceptMRIAdapter()
            assert adapter.adapter_table == "document_connector_sync"


class TestConceptMRIAdapterNormalise:
    """Test normalise() maps FIELD_MAP fields to DocumentRecord correctly."""

    def get_normaliser(self):
        """Return a ConceptMRIAdapter with mocked site_resolver."""
        with patch("app.services.document_source_adapter._get_supabase"):
            adapter = ConceptMRIAdapter()
        return adapter

    def test_normalise_maps_source_system(self):
        adapter = self.get_normaliser()
        raw = {
            FIELD_MAP["DocumentId"]: "DOC-001",
            FIELD_MAP["DocumentUrl"]: "https://mri.example.com/doc/DOC-001",
            FIELD_MAP["Site"]: "site-002",
            FIELD_MAP["EquipmentDescription"]: "Chiller 1",
            FIELD_MAP["DocumentType"]: "Service Report",
            FIELD_MAP["Category"]: "HVAC",
            FIELD_MAP["DocumentCreationDate"]: "2026-03-15",
            FIELD_MAP["TriggerDate"]: "2026-04-01",
            FIELD_MAP["ContractorVendor"]: "XYZ Services",
            FIELD_MAP["Author"]: "John Tech",
            FIELD_MAP["Notes"]: "Annual service completed",
        }
        with patch.object(adapter, "_resolve_site", return_value="site-002"):
            record = adapter.normalise(raw)
        assert record.source_system == SourceSystem.CONCEPT_MRI

    def test_normalise_maps_document_id(self):
        adapter = self.get_normaliser()
        raw = {FIELD_MAP["DocumentId"]: "DOC-123", FIELD_MAP["DocumentUrl"]: None}
        with patch.object(adapter, "_resolve_site", return_value="site-002"):
            record = adapter.normalise(raw)
        assert record.source_document_id == "DOC-123"

    def test_normalise_maps_source_url(self):
        adapter = self.get_normaliser()
        raw = {
            FIELD_MAP["DocumentId"]: "DOC-001",
            FIELD_MAP["DocumentUrl"]: "https://mri.example.com/doc/DOC-001",
        }
        with patch.object(adapter, "_resolve_site", return_value="site-002"):
            record = adapter.normalise(raw)
        assert record.source_url == "https://mri.example.com/doc/DOC-001"

    def test_normalise_maps_equipment_description(self):
        adapter = self.get_normaliser()
        raw = {
            FIELD_MAP["DocumentId"]: "DOC-001",
            FIELD_MAP["DocumentUrl"]: None,
            FIELD_MAP["EquipmentDescription"]: "AHU-001",
        }
        with patch.object(adapter, "_resolve_site", return_value="site-002"):
            record = adapter.normalise(raw)
        assert record.equipment_description == "AHU-001"

    def test_normalise_maps_discipline(self):
        adapter = self.get_normaliser()
        raw = {
            FIELD_MAP["DocumentId"]: "DOC-001",
            FIELD_MAP["DocumentUrl"]: None,
            FIELD_MAP["Category"]: "Electrical",
        }
        with patch.object(adapter, "_resolve_site", return_value="site-002"):
            record = adapter.normalise(raw)
        assert record.discipline == "Electrical"

    def test_normalise_maps_contractor_vendor(self):
        adapter = self.get_normaliser()
        raw = {
            FIELD_MAP["DocumentId"]: "DOC-001",
            FIELD_MAP["DocumentUrl"]: None,
            FIELD_MAP["ContractorVendor"]: "ABC Contractors",
        }
        with patch.object(adapter, "_resolve_site", return_value="site-002"):
            record = adapter.normalise(raw)
        assert record.contractor_vendor == "ABC Contractors"

    def test_normalise_maps_uploaded_by(self):
        adapter = self.get_normaliser()
        raw = {
            FIELD_MAP["DocumentId"]: "DOC-001",
            FIELD_MAP["DocumentUrl"]: None,
            FIELD_MAP["Author"]: "Jane Doe",
        }
        with patch.object(adapter, "_resolve_site", return_value="site-002"):
            record = adapter.normalise(raw)
        assert record.uploaded_by == "Jane Doe"

    def test_normalise_sets_extraction_status_pending(self):
        adapter = self.get_normaliser()
        raw = {FIELD_MAP["DocumentId"]: "DOC-001", FIELD_MAP["DocumentUrl"]: None}
        with patch.object(adapter, "_resolve_site", return_value="site-002"):
            record = adapter.normalise(raw)
        assert record.extraction_status == ExtractionStatus.PENDING

    def test_normalise_sets_needs_human_review_false(self):
        adapter = self.get_normaliser()
        raw = {FIELD_MAP["DocumentId"]: "DOC-001", FIELD_MAP["DocumentUrl"]: None}
        with patch.object(adapter, "_resolve_site", return_value="site-002"):
            record = adapter.normalise(raw)
        assert record.needs_human_review is False

    def test_normalise_sets_empty_raw_file_path(self):
        adapter = self.get_normaliser()
        raw = {FIELD_MAP["DocumentId"]: "DOC-001", FIELD_MAP["DocumentUrl"]: None}
        with patch.object(adapter, "_resolve_site", return_value="site-002"):
            record = adapter.normalise(raw)
        assert record.raw_file_path == ""

    def test_normalise_handles_missing_optional_fields(self):
        adapter = self.get_normaliser()
        raw = {FIELD_MAP["DocumentId"]: "DOC-001"}
        with patch.object(adapter, "_resolve_site", return_value="site-002"):
            record = adapter.normalise(raw)
        assert record.source_document_id == "DOC-001"
        assert record.source_url is None
        assert record.equipment_description is None
        assert record.discipline is None
        assert record.contractor_vendor is None


class TestMapDocumentType:
    """Test _map_document_type maps MRI raw strings to DocumentType enum."""

    def get_adapter(self):
        with patch("app.services.document_source_adapter._get_supabase"):
            return ConceptMRIAdapter()

    @pytest.mark.parametrize(
        "raw_value,expected_type",
        [
            ("Service Report", DocumentType.SERVICE_REPORT),
            ("Inspection", DocumentType.INSPECTION),
            ("Certificate", DocumentType.CERTIFICATE),
            ("Test Report", DocumentType.TEST_REPORT),
        ],
    )
    def test_known_types_return_correct_document_type(self, raw_value, expected_type):
        adapter = self.get_adapter()
        result = adapter._map_document_type(raw_value)
        assert result == expected_type

    def test_unknown_type_returns_unknown(self):
        adapter = self.get_adapter()
        result = adapter._map_document_type("Random Document Type")
        assert result == DocumentType.UNKNOWN

    def test_none_returns_unknown(self):
        adapter = self.get_adapter()
        result = adapter._map_document_type(None)
        assert result == DocumentType.UNKNOWN

    def test_empty_string_returns_unknown(self):
        adapter = self.get_adapter()
        result = adapter._map_document_type("")
        assert result == DocumentType.UNKNOWN


class TestParseDate:
    """Test _parse_date parses ISO date strings correctly."""

    def get_adapter(self):
        with patch("app.services.document_source_adapter._get_supabase"):
            return ConceptMRIAdapter()

    def test_valid_iso_date_returns_date(self):
        adapter = self.get_adapter()
        result = adapter._parse_date("2026-03-15")
        assert result == date(2026, 3, 15)

    def test_valid_date_with_time_returns_date_only(self):
        adapter = self.get_adapter()
        result = adapter._parse_date("2026-03-15T10:30:00")
        assert result == date(2026, 3, 15)

    def test_none_returns_none(self):
        adapter = self.get_adapter()
        result = adapter._parse_date(None)
        assert result is None

    def test_empty_string_returns_none(self):
        adapter = self.get_adapter()
        result = adapter._parse_date("")
        assert result is None

    def test_invalid_format_returns_none_with_warning(self, caplog):
        adapter = self.get_adapter()
        with caplog.at_level("WARNING"):
            result = adapter._parse_date("not-a-date")
        assert result is None
        assert "unparseable date" in caplog.text


class TestResolveSite:
    """Test _resolve_site resolves raw site name/ID to canonical site_id."""

    def get_adapter(self):
        with patch("app.services.document_source_adapter._get_supabase"):
            return ConceptMRIAdapter()

    def test_resolve_site_returns_registered_site_id(self):
        adapter = self.get_adapter()
        with patch(
            "app.core.site_resolver.get_registered_site_ids",
            return_value=["site-001", "site-002"],
        ):
            result = adapter._resolve_site("site-002")
        assert result == "site-002"

    def test_resolve_site_case_insensitive(self):
        adapter = self.get_adapter()
        with patch(
            "app.core.site_resolver.get_registered_site_ids",
            return_value=["site-001", "site-002"],
        ):
            result = adapter._resolve_site("SITE-002")
        assert result == "site-002"

    def test_resolve_site_returns_unknown_when_no_match(self):
        adapter = self.get_adapter()
        with (
            patch(
                "app.core.site_resolver.get_registered_site_ids",
                return_value=["site-001", "site-002"],
            ),
            patch("app.core.site_resolver.get_registered_sites", return_value=[]),
        ):
            result = adapter._resolve_site("unknown-site")
        assert result == "UNKNOWN"

    def test_resolve_site_none_returns_unknown(self):
        adapter = self.get_adapter()
        result = adapter._resolve_site(None)
        assert result == "UNKNOWN"

    def test_resolve_site_empty_returns_unknown(self):
        adapter = self.get_adapter()
        result = adapter._resolve_site("")
        assert result == "UNKNOWN"


class TestFetchNewDocuments:
    """Test fetch_new_documents calls client and normalises results."""

    def get_adapter_with_mock_client(self):
        with patch("app.services.document_source_adapter._get_supabase"):
            adapter = ConceptMRIAdapter()
        return adapter

    def test_fetch_new_documents_calls_client_fetch_documents(self):
        adapter = self.get_adapter_with_mock_client()
        mock_raw = [
            {
                FIELD_MAP["DocumentId"]: "DOC-001",
                FIELD_MAP["DocumentUrl"]: "https://mri.example.com/doc/1",
                FIELD_MAP["Site"]: "site-002",
                FIELD_MAP["DocumentType"]: "Service Report",
                FIELD_MAP["DocumentCreationDate"]: "2026-03-15",
            }
        ]
        adapter.client.fetch_documents = AsyncMock(return_value=mock_raw)
        import asyncio

        result = asyncio.run(adapter.fetch_new_documents(since=None, site_id="site-002"))
        adapter.client.fetch_documents.assert_called_once_with(None, limit=None)
        assert len(result) == 1
        assert result[0].source_document_id == "DOC-001"
        assert result[0].document_type == DocumentType.SERVICE_REPORT

    def test_fetch_new_documents_normalises_all_records(self):
        adapter = self.get_adapter_with_mock_client()
        mock_raw = [
            {
                FIELD_MAP["DocumentId"]: "DOC-001",
                FIELD_MAP["DocumentUrl"]: None,
                FIELD_MAP["Site"]: "site-002",
                FIELD_MAP["DocumentType"]: "Service Report",
                FIELD_MAP["DocumentCreationDate"]: "2026-03-15",
            },
            {
                FIELD_MAP["DocumentId"]: "DOC-002",
                FIELD_MAP["DocumentUrl"]: None,
                FIELD_MAP["Site"]: "site-002",
                FIELD_MAP["DocumentType"]: "Inspection",
                FIELD_MAP["DocumentCreationDate"]: "2026-03-20",
            },
        ]
        adapter.client.fetch_documents = AsyncMock(return_value=mock_raw)
        import asyncio

        result = asyncio.run(adapter.fetch_new_documents(since=None, site_id="site-002"))
        assert len(result) == 2
        assert result[0].document_type == DocumentType.SERVICE_REPORT
        assert result[1].document_type == DocumentType.INSPECTION

    def test_fetch_new_documents_passes_limit_and_slices_results(self):
        adapter = self.get_adapter_with_mock_client()
        mock_raw = [
            {
                FIELD_MAP["DocumentId"]: "DOC-001",
                FIELD_MAP["DocumentUrl"]: None,
                FIELD_MAP["Site"]: "site-002",
                FIELD_MAP["DocumentType"]: "Service Report",
            },
            {
                FIELD_MAP["DocumentId"]: "DOC-002",
                FIELD_MAP["DocumentUrl"]: None,
                FIELD_MAP["Site"]: "site-002",
                FIELD_MAP["DocumentType"]: "Inspection",
            },
            {
                FIELD_MAP["DocumentId"]: "DOC-003",
                FIELD_MAP["DocumentUrl"]: None,
                FIELD_MAP["Site"]: "site-002",
                FIELD_MAP["DocumentType"]: "Certificate",
            },
        ]
        adapter.client.fetch_documents = AsyncMock(return_value=mock_raw)
        import asyncio

        result = asyncio.run(adapter.fetch_new_documents(since=None, site_id="site-002", limit=2))
        adapter.client.fetch_documents.assert_called_once_with(None, limit=2)
        assert [record.source_document_id for record in result] == ["DOC-001", "DOC-002"]


class TestGetDocumentFile:
    """Test get_document_file delegates to client.get_document_file."""

    def get_adapter_with_mock_client(self):
        with patch("app.services.document_source_adapter._get_supabase"):
            adapter = ConceptMRIAdapter()
        return adapter

    @pytest.mark.asyncio
    async def test_get_document_file_returns_bytes(self):
        adapter = self.get_adapter_with_mock_client()
        mock_bytes = b"PDF content here"
        adapter.client.get_document_file = AsyncMock(return_value=mock_bytes)
        result = await adapter.get_document_file("DOC-001")
        adapter.client.get_document_file.assert_called_once_with("DOC-001")
        assert result == mock_bytes


class TestRunSyncIndexesFiles:
    """Test MRI sync owns file fetch and delegates indexing to DocumentIndexingService."""

    def get_adapter_with_mock_client(self):
        with patch("app.services.document_source_adapter._get_supabase"):
            adapter = ConceptMRIAdapter()
        return adapter

    @pytest.mark.asyncio
    async def test_run_sync_fetches_file_bytes_and_calls_indexing_service(self):
        adapter = self.get_adapter_with_mock_client()
        record = DocumentRecord(
            source_system=SourceSystem.CONCEPT_MRI,
            source_document_id="MRI-001",
            site_id="site-002",
            document_type=DocumentType.SERVICE_REPORT,
            equipment_description="generator",
            raw_file_path="",
        )

        indexer = MagicMock()
        indexer.index_document = AsyncMock(return_value=MagicMock(status=IndexingStatus.COMPLETE, chunks=2, error=None))

        with (
            patch.object(adapter, "_get_last_sync", return_value=None),
            patch.object(adapter, "fetch_new_documents", AsyncMock(return_value=[record])),
            patch.object(adapter, "_upsert", AsyncMock(return_value="11111111-1111-1111-1111-111111111111")),
            patch.object(adapter, "_resolve_asset_id", AsyncMock(return_value="S002-GEN-001")),
            patch.object(adapter, "get_document_file", AsyncMock(return_value=b"%PDF service report")) as get_file,
            patch.object(adapter, "_update_sync_state") as update_sync,
            patch("app.services.document_adapter_mri.DocumentIndexingService", return_value=indexer),
        ):
            result = await adapter.run_sync(site_id="site-002")

        assert result == {"synced": 1, "failed": 0, "errors": []}
        get_file.assert_awaited_once_with("MRI-001")
        indexer.index_document.assert_awaited_once()
        call = indexer.index_document.await_args.kwargs
        assert str(call["document_id"]) == "11111111-1111-1111-1111-111111111111"
        assert call["file_bytes"] == b"%PDF service report"
        assert call["doc_class"] == "site"
        assert call["asset_id"] == "S002-GEN-001"
        assert call["source_system"] == "concept_mri"
        update_sync.assert_called_once_with("site-002", 1, 0, 0)

    @pytest.mark.asyncio
    async def test_initial_run_sync_limits_documents_before_indexing(self):
        adapter = self.get_adapter_with_mock_client()
        records = [
            DocumentRecord(
                source_system=SourceSystem.CONCEPT_MRI,
                source_document_id=f"MRI-00{i}",
                site_id="site-002",
                document_type=DocumentType.SERVICE_REPORT,
                equipment_description="generator",
                raw_file_path="",
            )
            for i in range(1, 4)
        ]

        async def fake_fetch_new_documents(*, since, site_id, limit):
            assert since is None
            assert site_id == "site-002"
            assert limit == 2
            return records[:limit]

        indexer = MagicMock()
        indexer.index_document = AsyncMock(return_value=MagicMock(status=IndexingStatus.COMPLETE, chunks=2, error=None))

        with (
            patch.object(adapter, "_get_last_sync", return_value=None),
            patch.object(adapter, "fetch_new_documents", AsyncMock(side_effect=fake_fetch_new_documents)),
            patch.object(
                adapter,
                "_upsert",
                AsyncMock(
                    side_effect=[
                        "11111111-1111-1111-1111-111111111111",
                        "22222222-2222-2222-2222-222222222222",
                    ]
                ),
            ),
            patch.object(adapter, "_resolve_asset_id", AsyncMock(return_value="S002-GEN-001")),
            patch.object(adapter, "get_document_file", AsyncMock(return_value=b"%PDF service report")) as get_file,
            patch.object(adapter, "_update_sync_state") as update_sync,
            patch("app.services.document_adapter_mri.DocumentIndexingService", return_value=indexer),
            patch("app.services.document_adapter_mri.settings.mri_document_initial_sync_limit", 2),
            patch("app.services.document_adapter_mri.settings.mri_document_per_document_delay_seconds", 0),
        ):
            result = await adapter.run_sync(site_id="site-002")

        assert result == {"synced": 2, "failed": 0, "errors": []}
        assert get_file.await_count == 2
        assert indexer.index_document.await_count == 2
        update_sync.assert_called_once_with("site-002", 2, 0, 0)
