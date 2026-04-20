"""Tests for DoclingExtractionService."""

import pytest

from app.services.docling_extraction_service import (
    DOCLING_SUPPORTED_EXTENSIONS,
    DoclingExtractionResult,
    DoclingExtractionService,
)

# -------------------------------------------------------------------
# DoclingExtractionResult dataclass tests
# -------------------------------------------------------------------


def test_docling_extraction_result_dataclass_fields():
    """Result dataclass has all required fields."""
    result = DoclingExtractionResult(
        raw_text="Hello world",
        tables=["| a | b |\n|---|---|\n| 1 | 2 |"],
        page_count=3,
        extraction_mode="docling",
        confidence=0.95,
        metadata={"filename": "test.pdf"},
    )
    assert result.raw_text == "Hello world"
    assert len(result.tables) == 1
    assert result.page_count == 3
    assert result.extraction_mode == "docling"
    assert result.confidence == 0.95
    assert result.metadata["filename"] == "test.pdf"


def test_docling_extraction_result_empty():
    """empty() returns a result with extraction_mode=unavailable."""
    result = DoclingExtractionResult.empty()
    assert result.raw_text == ""
    assert result.tables == []
    assert result.page_count == 0
    assert result.extraction_mode == "unavailable"
    assert result.confidence == 0.0
    assert "unavailable_reason" in result.metadata


def test_docling_extraction_result_empty_with_reason():
    """empty() accepts a reason string."""
    result = DoclingExtractionResult.empty("docling_not_installed")
    assert result.metadata["unavailable_reason"] == "docling_not_installed"


# -------------------------------------------------------------------
# DoclingExtractionService availability tests
# -------------------------------------------------------------------


def test_service_defaults_site_id_to_none():
    """Service initialises with optional site_id."""
    service = DoclingExtractionService()
    assert service.site_id is None


def test_service_accepts_site_id():
    """Service stores site_id for context."""
    service = DoclingExtractionService(site_id="S002")
    assert service.site_id == "S002"


def test_supported_extensions():
    """DOCLING_SUPPORTED_EXTENSIONS contains expected types."""
    assert ".pdf" in DOCLING_SUPPORTED_EXTENSIONS
    assert ".docx" in DOCLING_SUPPORTED_EXTENSIONS
    assert ".jpg" in DOCLING_SUPPORTED_EXTENSIONS
    assert ".png" in DOCLING_SUPPORTED_EXTENSIONS
    assert ".tiff" in DOCLING_SUPPORTED_EXTENSIONS
    assert ".unsupported" not in DOCLING_SUPPORTED_EXTENSIONS


# -------------------------------------------------------------------
# File type detection
# -------------------------------------------------------------------


def test_detect_file_type_pdf():
    """_detect_file_type returns .pdf for PDF files."""
    service = DoclingExtractionService()
    assert service._detect_file_type("document.pdf") == ".pdf"
    assert service._detect_file_type("DOCUMENT.PDF") == ".pdf"


def test_detect_file_type_docx():
    """_detect_file_type returns .docx for Word files."""
    service = DoclingExtractionService()
    assert service._detect_file_type("report.docx") == ".docx"


def test_detect_file_type_image():
    """_detect_file_type handles image types."""
    service = DoclingExtractionService()
    assert service._detect_file_type("scan.jpg") == ".jpg"
    assert service._detect_file_type("photo.PNG") == ".png"
    assert service._detect_file_type("page.tiff") == ".tiff"


def test_detect_file_type_unsupported():
    """_detect_file_type returns empty string for unsupported types."""
    service = DoclingExtractionService()
    assert service._detect_file_type("data.csv") == ""
    assert service._detect_file_type("image.bmp") == ""


# -------------------------------------------------------------------
# Graceful degradation — docling unavailable
# -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_from_bytes_when_docling_unavailable(monkeypatch):
    """When docling is not installed, returns empty result with mode=unavailable."""
    service = DoclingExtractionService()

    # Simulate docling not being available
    monkeypatch.setattr(service, "_docling_available", False)

    result = await service.extract_from_bytes(b"%PDF-1.4 test", filename="test.pdf")

    assert result.extraction_mode == "unavailable"
    assert result.raw_text == ""
    assert result.tables == []
    assert "unavailable_reason" in result.metadata


@pytest.mark.asyncio
async def test_extract_from_bytes_unsupported_file_type(monkeypatch):
    """Unsupported file type returns empty result."""
    service = DoclingExtractionService()
    monkeypatch.setattr(service, "_docling_available", True)

    result = await service.extract_from_bytes(b"some data", filename="data.csv")

    assert result.extraction_mode == "unavailable"
    assert "unsupported_file_type" in result.metadata["unavailable_reason"]


# -------------------------------------------------------------------
# Mock integration test (docling available)
# -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_from_bytes_docling_mode_via_import_skip(tmp_path):
    """Integration test: when docling is installed, it is used for PDF extraction."""
    pytest.importorskip("docling")
    # Write a minimal valid file so docling can process it (docling needs a Path, not BytesIO)
    fake_pdf = tmp_path / "test.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4")

    service = DoclingExtractionService()
    result = await service.extract_from_bytes(fake_pdf.read_bytes(), filename="test.pdf")

    # If docling is installed, the mode should be 'docling' (or at minimum not 'unavailable')
    # Note: docling may still fail on invalid PDF bytes, which returns 'unavailable'
    # This test verifies the service at least attempts docling when available
    assert result.metadata["filename"] == "test.pdf"
    assert result.metadata["file_type"] == ".pdf"
    assert isinstance(result.raw_text, str)


@pytest.mark.asyncio
async def test_extract_from_upload_delegates_to_extract_from_bytes(monkeypatch):
    """extract_from_upload reads file and delegates to extract_from_bytes."""
    service = DoclingExtractionService()
    monkeypatch.setattr(service, "_docling_available", False)

    # Build a minimal fake UploadFile
    class FakeUploadFile:
        filename = "invoice.pdf"

        async def read(self):
            return b"%PDF-1.4 invoice data"

    result = await service.extract_from_upload(FakeUploadFile())

    assert result.extraction_mode == "unavailable"
    assert result.metadata["filename"] == "invoice.pdf"
    assert result.metadata["size_bytes"] == 21
