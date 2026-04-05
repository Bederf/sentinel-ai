"""
Tests for DocumentRecord Pydantic model and related enums.
Phase 179-01: document-source-enums-model-and-adapter-abc
"""

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from app.models.document_record import DocumentRecord, DocumentType, ExtractionStatus
from app.models.document_source import DocumentSource, SourceSystem


class TestDocumentSourceEnum:
    """DocumentSource enum — what the document IS."""

    def test_values(self):
        assert DocumentSource.SERVICE_REPORT.value == "service_report"
        assert DocumentSource.INSPECTION.value == "inspection"
        assert DocumentSource.CERTIFICATE.value == "certificate"
        assert DocumentSource.TEST_REPORT.value == "test_report"
        assert DocumentSource.MANUAL.value == "manual"
        assert DocumentSource.UNKNOWN.value == "unknown"

    def test_count(self):
        assert len(DocumentSource) == 6

    def test_is_string_enum(self):
        assert isinstance(DocumentSource.SERVICE_REPORT, str)
        assert DocumentSource.SERVICE_REPORT == "service_report"


class TestSourceSystemEnum:
    """SourceSystem enum — where the document CAME FROM."""

    def test_values(self):
        assert SourceSystem.CONCEPT_MRI.value == "concept_mri"
        assert SourceSystem.SHAREPOINT.value == "sharepoint"
        assert SourceSystem.MANUAL_UPLOAD.value == "manual_upload"

    def test_count(self):
        assert len(SourceSystem) == 3

    def test_is_string_enum(self):
        assert isinstance(SourceSystem.CONCEPT_MRI, str)
        assert SourceSystem.CONCEPT_MRI == "concept_mri"


class TestDocumentTypeEnum:
    """DocumentType enum — mirrors DocumentSource values."""

    def test_values_match_document_source(self):
        for ds in DocumentSource:
            assert hasattr(DocumentType, ds.name)
            assert DocumentType[ds.name].value == ds.value

    def test_count(self):
        assert len(DocumentType) == len(DocumentSource)


class TestExtractionStatusEnum:
    """ExtractionStatus enum."""

    def test_values(self):
        assert ExtractionStatus.PENDING.value == "pending"
        assert ExtractionStatus.EXTRACTED.value == "extracted"
        assert ExtractionStatus.FAILED.value == "failed"
        assert ExtractionStatus.QUARANTINED.value == "quarantined"

    def test_count(self):
        assert len(ExtractionStatus) == 4


class TestDocumentRecordRequiredFields:
    """DocumentRecord required fields."""

    def test_minimal_valid(self):
        record = DocumentRecord(
            source_system=SourceSystem.CONCEPT_MRI,
            site_id="S002",
            raw_file_path="documents/mri/WO-12345.pdf",
        )
        assert record.source_system == SourceSystem.CONCEPT_MRI
        assert record.site_id == "S002"
        assert record.raw_file_path == "documents/mri/WO-12345.pdf"
        assert record.source_document_id is None
        assert record.document_type == DocumentType.UNKNOWN
        assert record.extraction_status == ExtractionStatus.PENDING
        assert record.needs_human_review is False
        assert record.review_flags == []

    def test_raw_file_path_required(self):
        with pytest.raises(ValidationError):
            DocumentRecord(source_system=SourceSystem.CONCEPT_MRI, site_id="S002")

    def test_source_system_required(self):
        with pytest.raises(ValidationError):
            DocumentRecord(site_id="S002", raw_file_path="test.pdf")


class TestDocumentRecordAllFields:
    """DocumentRecord with all fields populated."""

    def test_full_record(self):
        record = DocumentRecord(
            source_system=SourceSystem.CONCEPT_MRI,
            source_document_id="WO-12345",
            source_url="https://mri.example.com/WO/12345",
            site_id="S002",
            asset_id="550e8400-e29b-41d4-a716-446655440000",
            equipment_description="York YCIV 450 chiller",
            document_type=DocumentType.SERVICE_REPORT,
            sub_class="chiller",
            discipline="HVAC",
            document_date=date(2025, 11, 15),
            trigger_date=date(2025, 12, 1),
            upload_date=datetime(2025, 11, 20, 14, 30, 0),
            contractor_vendor="CoolingTech (Pty) Ltd",
            technician_name="J. Smith",
            uploaded_by="admin@sentinel-ai.co.za",
            raw_file_path="documents/mri/WO-12345.pdf",
            ocr_text="Service report for chiller maintenance...",
            tech_notes="Replaced compressor shaft seal. System running OK.",
            extraction_status=ExtractionStatus.EXTRACTED,
            needs_human_review=False,
            review_flags=[],
        )
        assert record.source_document_id == "WO-12345"
        assert record.asset_id == "550e8400-e29b-41d4-a716-446655440000"
        assert record.document_type == DocumentType.SERVICE_REPORT
        assert record.discipline == "HVAC"
        assert record.document_date == date(2025, 11, 15)
        assert record.extraction_status == ExtractionStatus.EXTRACTED

    def test_review_flags(self):
        record = DocumentRecord(
            source_system=SourceSystem.SHAREPOINT,
            site_id="S002",
            raw_file_path="documents/cert/COC-001.pdf",
            needs_human_review=True,
            review_flags=["expired_coc", "missing_signature"],
        )
        assert record.needs_human_review is True
        assert record.review_flags == ["expired_coc", "missing_signature"]


class TestDocumentRecordDefaults:
    """DocumentRecord default values."""

    def test_source_document_id_defaults_to_none(self):
        record = DocumentRecord(
            source_system=SourceSystem.MANUAL_UPLOAD,
            site_id="S002",
            raw_file_path="test.pdf",
        )
        assert record.source_document_id is None

    def test_document_type_defaults_to_unknown(self):
        record = DocumentRecord(
            source_system=SourceSystem.MANUAL_UPLOAD,
            site_id="S002",
            raw_file_path="test.pdf",
        )
        assert record.document_type == DocumentType.UNKNOWN

    def test_extraction_status_defaults_to_pending(self):
        record = DocumentRecord(
            source_system=SourceSystem.MANUAL_UPLOAD,
            site_id="S002",
            raw_file_path="test.pdf",
        )
        assert record.extraction_status == ExtractionStatus.PENDING

    def test_needs_human_review_defaults_to_false(self):
        record = DocumentRecord(
            source_system=SourceSystem.MANUAL_UPLOAD,
            site_id="S002",
            raw_file_path="test.pdf",
        )
        assert record.needs_human_review is False

    def test_review_flags_defaults_to_empty_list(self):
        record = DocumentRecord(
            source_system=SourceSystem.MANUAL_UPLOAD,
            site_id="S002",
            raw_file_path="test.pdf",
        )
        assert record.review_flags == []


class TestDocumentRecordDateParsing:
    """Test date/datetime field parsing."""

    def test_document_date_accepts_date_object(self):
        record = DocumentRecord(
            source_system=SourceSystem.CONCEPT_MRI,
            site_id="S002",
            raw_file_path="test.pdf",
            document_date=date(2025, 6, 1),
        )
        assert record.document_date == date(2025, 6, 1)

    def test_upload_date_accepts_datetime_object(self):
        record = DocumentRecord(
            source_system=SourceSystem.CONCEPT_MRI,
            site_id="S002",
            raw_file_path="test.pdf",
            upload_date=datetime(2025, 6, 1, 10, 0, 0),
        )
        assert record.upload_date == datetime(2025, 6, 1, 10, 0, 0)


class TestDocumentRecordSourceSystemField:
    """Test that source_system field accepts SourceSystem enum values."""

    def test_source_system_accepts_enum(self):
        record = DocumentRecord(
            source_system=SourceSystem.CONCEPT_MRI,
            site_id="S002",
            raw_file_path="test.pdf",
        )
        assert record.source_system == SourceSystem.CONCEPT_MRI

    def test_source_system_accepts_string_value(self):
        record = DocumentRecord(
            source_system="concept_mri",
            site_id="S002",
            raw_file_path="test.pdf",
        )
        assert record.source_system == SourceSystem.CONCEPT_MRI

    def test_source_system_rejects_invalid(self):
        with pytest.raises(ValidationError):
            DocumentRecord(
                source_system="invalid_source",
                site_id="S002",
                raw_file_path="test.pdf",
            )
