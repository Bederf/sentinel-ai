"""
Tests for ManualUploadAdapter — Phase 179-02.
"""

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

from app.models.document_record import DocumentRecord, DocumentType, ExtractionStatus
from app.models.document_source import DocumentSource, SourceSystem
from app.services.document_adapter_manual import _DOCUMENT_NAME_TO_SOURCE, ManualUploadAdapter


class TestManualUploadAdapterInit:
    """Task 4a: Test __init__ sets self.db and self.source_system."""

    def test_init_sets_db(self):
        with patch("app.services.document_source_adapter._get_supabase") as mock_get:
            mock_get.return_value = MagicMock()
            adapter = ManualUploadAdapter()
            assert adapter.db is mock_get.return_value

    def test_source_system_is_manual_upload(self):
        with patch("app.services.document_source_adapter._get_supabase") as mock_get:
            mock_get.return_value = MagicMock()
            adapter = ManualUploadAdapter()
            assert adapter.source_system == SourceSystem.MANUAL_UPLOAD

    def test_adapter_table_default(self):
        with patch("app.services.document_source_adapter._get_supabase") as mock_get:
            mock_get.return_value = MagicMock()
            adapter = ManualUploadAdapter()
            assert adapter.adapter_table == "document_connector_sync"


class TestDocumentNameToSourceLookup:
    """Task 4e: Test _DOCUMENT_NAME_TO_SOURCE lookup (B6 fix)."""

    def test_chiller_major_service_maps_to_service_report(self):
        assert _DOCUMENT_NAME_TO_SOURCE.get("Chiller Major Service") == DocumentSource.SERVICE_REPORT

    def test_fire_pump_inspection_maps_to_inspection(self):
        assert _DOCUMENT_NAME_TO_SOURCE.get("Fire Pump System Inspection") == DocumentSource.INSPECTION

    def test_certificate_of_compliance_maps_to_certificate(self):
        assert _DOCUMENT_NAME_TO_SOURCE.get("Certificate of Compliance (COC)") == DocumentSource.CERTIFICATE

    def test_earth_leakage_test_maps_to_test_report(self):
        assert _DOCUMENT_NAME_TO_SOURCE.get("Earth Leakage Test") == DocumentSource.TEST_REPORT

    def test_unknown_document_name_returns_none(self):
        assert _DOCUMENT_NAME_TO_SOURCE.get("Some Random Document Name") is None

    def test_all_technician_document_names_have_lookup_entry(self):
        """Every TECHNICIAN_DOCUMENT_NAMES value should be in the lookup (B6 fix)."""
        TECHNICIAN_DOCUMENT_NAMES = {
            "Roof Guarantee Certificate",
            "Warranties",
            "Air-Handler Unit (AHU) Major Service",
            "Air-Handler Unit (AHU) Minor Service",
            "Air-Handler Unit (AHU) Weekly Inspection",
            "Cooling Tower (CT) Major Service",
            "Cooling Tower (CT) Minor Service",
            "Cooling Tower (CT) Weekly Inspection",
            "Chiller Major Service",
            "Chiller Minor Service",
            "Chiller Weekly Inspection",
            "Kitchen Canopy Manual Service",
            "Building Management System (BMS) Service",
            "Distribution Boards (DB) Maintenance",
            "Transformer Service",
            "Fire Pump System Inspection",
            "Generator Major Service",
            "Generator Minor Service",
            "Generator Weekly Test",
            "Lift Service",
            "Lift test Report",
            "Escalator Monthly Service",
            "Solar PV Weekly Inspection",
            "UPS Weekly Inspection",
            "Waste Management Service",
            "Structural Integrity Report",
            "Certificate of Compliance (COC)",
            "Earth Leakage Test",
            "Plumbing Certificate of Compliance",
            "Electrical Equipment Certificates",
            "Smoke Detectors Service",
            "ASIB Certificate",
            "Portable Electrical Tool Inspection",
            "Potable Water Test Results",
            "Pressure Vessel Test Certificate",
            "Spillage Incidents Report",
            "Water Consumption Reports",
            "Building Inspection Report",
            "Occupational Hygiene Surveys",
            "Waste disposal certificates",
            "Audit Reports",
            "BSI Audit certificate",
        }
        missing = [n for n in TECHNICIAN_DOCUMENT_NAMES if n not in _DOCUMENT_NAME_TO_SOURCE]
        assert missing == [], f"Missing lookup entries for: {missing}"


class TestNormaliseUpload:
    """Task 4b/d: Test normalise_upload maps form data to DocumentRecord correctly."""

    def setup_method(self):
        self.mock_get = patch("app.services.document_source_adapter._get_supabase").start()
        self.mock_get.return_value = MagicMock()
        self.adapter = ManualUploadAdapter()

    def test_maps_source_system_manual_upload(self):
        response = {"document_id": "doc-123", "storage_path": "uploads/doc.pdf"}
        form = {
            "equipment_id": "EQ-001",
            "document_name": "Chiller Major Service",
            "document_sub_class": "HVAC",
            "category_discipline": "Preventive Maintenance",
            "document_creation_date": "2025-01-15",
            "trigger_date": "2025-04-15",
            "title": "Q1 Service",
            "uploaded_by_user_id": "user-456",
        }
        record = self.adapter.normalise_upload(response, form, "S002")
        assert record.source_system == SourceSystem.MANUAL_UPLOAD

    def test_maps_source_document_id(self):
        response = {"document_id": "doc-123", "storage_path": "uploads/doc.pdf"}
        form = {
            "equipment_id": "EQ-001",
            "document_name": "Chiller Major Service",
            "document_sub_class": "HVAC",
            "category_discipline": "Preventive Maintenance",
            "document_creation_date": "2025-01-15",
            "trigger_date": "2025-04-15",
            "title": "Q1 Service",
            "uploaded_by_user_id": "user-456",
        }
        record = self.adapter.normalise_upload(response, form, "S002")
        assert record.source_document_id == "doc-123"

    def test_maps_asset_id(self):
        response = {"document_id": "doc-123", "storage_path": "uploads/doc.pdf"}
        form = {
            "equipment_id": "EQ-001",
            "document_name": "Chiller Major Service",
            "document_sub_class": "HVAC",
            "category_discipline": "Preventive Maintenance",
            "document_creation_date": "2025-01-15",
            "trigger_date": "2025-04-15",
            "title": "Q1 Service",
            "uploaded_by_user_id": "user-456",
        }
        record = self.adapter.normalise_upload(response, form, "S002")
        assert record.asset_id == "EQ-001"

    def test_maps_site_id_from_resolved_parameter(self):
        """site_id must come from resolved parameter, not form_data (prevents override)."""
        response = {"document_id": "doc-123", "storage_path": "uploads/doc.pdf"}
        form = {
            "equipment_id": "EQ-001",
            "document_name": "Chiller Major Service",
            "document_sub_class": "HVAC",
            "category_discipline": "Preventive Maintenance",
            "document_creation_date": "2025-01-15",
            "trigger_date": "2025-04-15",
            "title": "Q1 Service",
            "uploaded_by_user_id": "user-456",
            "site_id": "S001",  # attempt to override — must be ignored
        }
        record = self.adapter.normalise_upload(response, form, "S002")
        assert record.site_id == "S002"

    def test_document_name_lookup_service_report(self):
        """document_name 'Chiller Major Service' maps to SERVICE_REPORT via B6 lookup."""
        response = {"document_id": "doc-123", "storage_path": "uploads/doc.pdf"}
        form = {
            "equipment_id": "EQ-001",
            "document_name": "Chiller Major Service",
            "document_sub_class": "HVAC",
            "category_discipline": "Preventive Maintenance",
            "document_creation_date": "2025-01-15",
            "trigger_date": "2025-04-15",
            "title": None,
            "uploaded_by_user_id": "user-456",
        }
        record = self.adapter.normalise_upload(response, form, "S002")
        assert record.document_type == DocumentType.SERVICE_REPORT

    def test_document_name_lookup_certificate(self):
        """document_name 'Certificate of Compliance (COC)' maps to CERTIFICATE via B6 lookup."""
        response = {"document_id": "doc-456", "storage_path": "uploads/coc.pdf"}
        form = {
            "equipment_id": "EQ-001",
            "document_name": "Certificate of Compliance (COC)",
            "document_sub_class": "Electrical",
            "category_discipline": "Compliance",
            "document_creation_date": "2025-01-15",
            "trigger_date": "2025-04-15",
            "title": None,
            "uploaded_by_user_id": "user-456",
        }
        record = self.adapter.normalise_upload(response, form, "S002")
        assert record.document_type == DocumentType.CERTIFICATE

    def test_unknown_document_name_maps_to_unknown(self):
        """Unknown document_name falls back to UNKNOWN (no ValueError — B6 fix)."""
        response = {"document_id": "doc-789", "storage_path": "uploads/unknown.pdf"}
        form = {
            "equipment_id": "EQ-001",
            "document_name": "Not A Real Document Type",
            "document_sub_class": "General",
            "category_discipline": "General Facilities",
            "document_creation_date": "2025-01-15",
            "trigger_date": "2025-04-15",
            "title": None,
            "uploaded_by_user_id": "user-456",
        }
        # Must not raise ValueError
        record = self.adapter.normalise_upload(response, form, "S002")
        assert record.document_type == DocumentType.UNKNOWN

    def test_parses_document_date_correctly(self):
        response = {"document_id": "doc-123", "storage_path": "uploads/doc.pdf"}
        form = {
            "equipment_id": "EQ-001",
            "document_name": "Chiller Major Service",
            "document_sub_class": "HVAC",
            "category_discipline": "Preventive Maintenance",
            "document_creation_date": "2025-03-20",
            "trigger_date": "2025-06-20",
            "title": None,
            "uploaded_by_user_id": "user-456",
        }
        record = self.adapter.normalise_upload(response, form, "S002")
        assert record.document_date == date(2025, 3, 20)
        assert record.trigger_date == date(2025, 6, 20)

    def test_parses_trigger_date_correctly(self):
        response = {"document_id": "doc-123", "storage_path": "uploads/doc.pdf"}
        form = {
            "equipment_id": "EQ-001",
            "document_name": "Chiller Major Service",
            "document_sub_class": "HVAC",
            "category_discipline": "Preventive Maintenance",
            "document_creation_date": "2025-01-15",
            "trigger_date": "2025-07-01",
            "title": None,
            "uploaded_by_user_id": "user-456",
        }
        record = self.adapter.normalise_upload(response, form, "S002")
        assert record.trigger_date == date(2025, 7, 1)

    def test_tech_notes_from_title(self):
        response = {"document_id": "doc-123", "storage_path": "uploads/doc.pdf"}
        form = {
            "equipment_id": "EQ-001",
            "document_name": "Chiller Major Service",
            "document_sub_class": "HVAC",
            "category_discipline": "Preventive Maintenance",
            "document_creation_date": "2025-01-15",
            "trigger_date": "2025-04-15",
            "title": "Q1 Chiller Service — compressor check",
            "uploaded_by_user_id": "user-456",
        }
        record = self.adapter.normalise_upload(response, form, "S002")
        assert record.tech_notes == "Q1 Chiller Service — compressor check"

    def test_tech_notes_none_when_no_title(self):
        response = {"document_id": "doc-123", "storage_path": "uploads/doc.pdf"}
        form = {
            "equipment_id": "EQ-001",
            "document_name": "Chiller Major Service",
            "document_sub_class": "HVAC",
            "category_discipline": "Preventive Maintenance",
            "document_creation_date": "2025-01-15",
            "trigger_date": "2025-04-15",
            "title": None,
            "uploaded_by_user_id": "user-456",
        }
        record = self.adapter.normalise_upload(response, form, "S002")
        assert record.tech_notes is None

    def test_extraction_status_extracted(self):
        """Existing upload_technician_document does OCR synchronously, so EXTRACTED."""
        response = {"document_id": "doc-123", "storage_path": "uploads/doc.pdf"}
        form = {
            "equipment_id": "EQ-001",
            "document_name": "Chiller Major Service",
            "document_sub_class": "HVAC",
            "category_discipline": "Preventive Maintenance",
            "document_creation_date": "2025-01-15",
            "trigger_date": "2025-04-15",
            "title": None,
            "uploaded_by_user_id": "user-456",
        }
        record = self.adapter.normalise_upload(response, form, "S002")
        assert record.extraction_status == ExtractionStatus.EXTRACTED

    def test_uploaded_by_from_form_data(self):
        response = {"document_id": "doc-123", "storage_path": "uploads/doc.pdf"}
        form = {
            "equipment_id": "EQ-001",
            "document_name": "Chiller Major Service",
            "document_sub_class": "HVAC",
            "category_discipline": "Preventive Maintenance",
            "document_creation_date": "2025-01-15",
            "trigger_date": "2025-04-15",
            "title": None,
            "uploaded_by_user_id": "tech-789",
        }
        record = self.adapter.normalise_upload(response, form, "S002")
        assert record.uploaded_by == "tech-789"

    def test_source_url_is_none_for_manual_upload(self):
        response = {"document_id": "doc-123", "storage_path": "uploads/doc.pdf"}
        form = {
            "equipment_id": "EQ-001",
            "document_name": "Chiller Major Service",
            "document_sub_class": "HVAC",
            "category_discipline": "Preventive Maintenance",
            "document_creation_date": "2025-01-15",
            "trigger_date": "2025-04-15",
            "title": None,
            "uploaded_by_user_id": "user-456",
        }
        record = self.adapter.normalise_upload(response, form, "S002")
        assert record.source_url is None

    def test_raw_file_path_from_storage_path(self):
        response = {"document_id": "doc-123", "storage_path": "uploads/my-report.pdf"}
        form = {
            "equipment_id": "EQ-001",
            "document_name": "Chiller Major Service",
            "document_sub_class": "HVAC",
            "category_discipline": "Preventive Maintenance",
            "document_creation_date": "2025-01-15",
            "trigger_date": "2025-04-15",
            "title": None,
            "uploaded_by_user_id": "user-456",
        }
        record = self.adapter.normalise_upload(response, form, "S002")
        assert record.raw_file_path == "uploads/my-report.pdf"


class TestFetchNewDocuments:
    """Task 4c: Test fetch_new_documents returns list of DocumentRecord."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_column_missing(self):
        """B1 fix: gracefully returns [] when source_system column missing."""
        with patch("app.services.document_source_adapter._get_supabase") as mock_get:
            mock_get.return_value = MagicMock()
            adapter = ManualUploadAdapter()
            with patch.object(adapter, "_columns_exist", return_value=False):
                result = await adapter.fetch_new_documents(since=None, site_id=None)
                assert result == []

    @pytest.mark.asyncio
    async def test_returns_list_of_document_records(self):
        with patch("app.services.document_source_adapter._get_supabase") as mock_get:
            mock_db = MagicMock()
            mock_get.return_value = mock_db
            mock_row_data = {
                "id": "doc-001",
                "source_document_id": "doc-001",
                "source_system": "manual_upload",
                "site_id": "S002",
                "document_type": "service_report",
                "keywords": [
                    "equipment_id:EQ-001",
                    "document_creation_date:2025-01-15",
                    "trigger_date:2025-04-15",
                    "uploaded_by_user_id:user-456",
                ],
                "source_url": None,
                "source_file_path": "uploads/doc.pdf",
                "title": "Q1 Service",
            }
            (
                mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value
            ).data = [mock_row_data]
            adapter = ManualUploadAdapter()
            with patch.object(adapter, "_columns_exist", return_value=True):
                result = await adapter.fetch_new_documents(since=None, site_id="S002")
            assert len(result) == 1
            assert isinstance(result[0], DocumentRecord)
            assert result[0].source_system == SourceSystem.MANUAL_UPLOAD
            assert result[0].source_document_id == "doc-001"
            assert result[0].asset_id == "EQ-001"

    @pytest.mark.asyncio
    async def test_filters_by_site_id_when_provided(self):
        with patch("app.services.document_source_adapter._get_supabase") as mock_get:
            mock_db = MagicMock()
            mock_get.return_value = mock_db
            mock_table = MagicMock()
            mock_db.table.return_value = mock_table
            mock_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            adapter = ManualUploadAdapter()
            with patch.object(adapter, "_columns_exist", return_value=True):
                await adapter.fetch_new_documents(since=None, site_id="S002")
            # Verify eq("site_id", "S002") was called
            mock_db.table.assert_called_with("documents")

    @pytest.mark.asyncio
    async def test_filters_by_since_when_provided(self):
        with patch("app.services.document_source_adapter._get_supabase") as mock_get:
            mock_db = MagicMock()
            mock_get.return_value = mock_db
            gte_execute = MagicMock(data=[])
            mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = (
                gte_execute
            )
            adapter = ManualUploadAdapter()
            since = datetime(2025, 1, 1)
            with patch.object(adapter, "_columns_exist", return_value=True):
                await adapter.fetch_new_documents(since=since, site_id=None)
            mock_db.table.return_value.select.return_value.eq.return_value.gte.assert_called()


class TestGetDocumentFile:
    """Task 4c: Test get_document_file returns bytes."""

    def test_returns_bytes_from_storage(self):
        with patch("app.services.document_source_adapter._get_supabase") as mock_get:
            mock_db = MagicMock()
            mock_get.return_value = mock_db
            mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"source_file_path": "uploads/report.pdf"}]
            )
            mock_storage = MagicMock()
            mock_db.storage = mock_storage
            mock_bucket = MagicMock()
            mock_storage.from_.return_value = mock_bucket
            mock_bucket.download.return_value = b"PDF bytes here"
            adapter = ManualUploadAdapter()
            result = adapter.get_document_file("doc-123")
            assert result == b"PDF bytes here"

    def test_raises_file_not_found_when_doc_not_found(self):
        with patch("app.services.document_source_adapter._get_supabase") as mock_get:
            mock_db = MagicMock()
            mock_get.return_value = mock_db
            mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            adapter = ManualUploadAdapter()
            with pytest.raises(FileNotFoundError):
                adapter.get_document_file("nonexistent-doc")


class TestUpsertIdempotency:
    """Task 4d: Test _upsert is idempotent (B1 fix + ON CONFLICT)."""

    @pytest.mark.asyncio
    async def test_upsert_calls_db_execute_with_upsert(self):
        with patch("app.services.document_source_adapter._get_supabase") as mock_get:
            mock_db = MagicMock()
            mock_get.return_value = mock_db
            mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock(data=[{"id": "doc-123"}])
            adapter = ManualUploadAdapter()
            with (
                patch.object(adapter, "_columns_exist", return_value=True),
                patch.object(adapter, "_resolve_site_uuid", return_value="site-uuid"),
            ):
                record = DocumentRecord(
                    source_system=SourceSystem.MANUAL_UPLOAD,
                    source_document_id="doc-123",
                    site_id="S002",
                    raw_file_path="uploads/doc.pdf",
                    document_type=DocumentType.SERVICE_REPORT,
                )
                result = await adapter._upsert(record)
            assert result == "doc-123"
            mock_db.table.return_value.upsert.assert_called()
            upsert_payload = mock_db.table.return_value.upsert.call_args.args[0]
            assert upsert_payload["code"] == "MANUAL-UPLOAD-DOC-123"
            assert upsert_payload["document_type"] == "service_report"
            assert upsert_payload["equipment_type"] == "general"
            assert upsert_payload["source"] == "user_upload"
            assert upsert_payload["site_id"] == "site-uuid"
            assert upsert_payload["source_system"] == "manual_upload"
            assert upsert_payload["source_document_id"] == "doc-123"

    @pytest.mark.asyncio
    async def test_upsert_idempotent_same_source_document_id(self):
        """Calling _upsert twice with same source_document_id is not an error (ON CONFLICT)."""
        with patch("app.services.document_source_adapter._get_supabase") as mock_get:
            mock_db = MagicMock()
            mock_get.return_value = mock_db
            mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock(data=[{"id": "doc-123"}])
            adapter = ManualUploadAdapter()
            record = DocumentRecord(
                source_system=SourceSystem.MANUAL_UPLOAD,
                source_document_id="doc-123",
                site_id="S002",
                raw_file_path="uploads/doc.pdf",
                document_type=DocumentType.SERVICE_REPORT,
            )
            with (
                patch.object(adapter, "_columns_exist", return_value=True),
                patch.object(adapter, "_resolve_site_uuid", return_value="site-uuid"),
            ):
                result1 = await adapter._upsert(record)
                result2 = await adapter._upsert(record)
            assert result1 == "doc-123"
            assert result2 == "doc-123"

    @pytest.mark.asyncio
    async def test_b1_upsert_graceful_noop_when_columns_missing(self):
        """B1 fix: _upsert returns '' when required columns missing (no 500)."""
        with patch("app.services.document_source_adapter._get_supabase") as mock_get:
            mock_db = MagicMock()
            mock_get.return_value = mock_db
            adapter = ManualUploadAdapter()
            with patch.object(adapter, "_columns_exist", return_value=False):
                record = DocumentRecord(
                    source_system=SourceSystem.MANUAL_UPLOAD,
                    source_document_id="doc-123",
                    site_id="S002",
                    raw_file_path="uploads/doc.pdf",
                    document_type=DocumentType.SERVICE_REPORT,
                )
                result = await adapter._upsert(record)
            assert result == ""
            # db.execute should NOT have been called
            mock_db.table.return_value.upsert.return_value.execute.assert_not_called()
