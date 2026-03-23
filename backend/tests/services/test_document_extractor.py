"""Tests for PDF native extraction with OCR fallback."""

from app.services import document_extractor


def test_pdf_extraction_uses_native_when_text_is_sufficient(monkeypatch):
    monkeypatch.setattr(
        document_extractor,
        "extract_text_from_pdf",
        lambda _bytes: "A" * (document_extractor.PDF_LOW_TEXT_THRESHOLD + 25),
    )
    monkeypatch.setattr(
        document_extractor,
        "_extract_text_from_pdf_ocr",
        lambda _bytes: "OCR should not be used",
    )

    text, metadata = document_extractor.extract_text_from_pdf_with_fallback(b"%PDF-1.4")
    assert len(text) > document_extractor.PDF_LOW_TEXT_THRESHOLD
    assert metadata["ocr_used"] is False
    assert metadata["extraction_mode"] == "native"


def test_pdf_extraction_uses_ocr_on_low_native_text(monkeypatch):
    monkeypatch.setattr(
        document_extractor,
        "extract_text_from_pdf",
        lambda _bytes: "short",
    )
    monkeypatch.setattr(
        document_extractor,
        "_extract_text_from_pdf_ocr",
        lambda _bytes: "Recovered OCR text from scanned PDF.",
    )

    text, metadata = document_extractor.extract_text_from_pdf_with_fallback(b"%PDF-1.4")
    assert "Recovered OCR text" in text
    assert metadata["ocr_used"] is True
    assert metadata["extraction_mode"] == "ocr_fallback"
    assert metadata["fallback_reason"] == "low_native_text_pdf"


def test_pdf_extraction_keeps_native_when_ocr_unavailable(monkeypatch):
    monkeypatch.setattr(
        document_extractor,
        "extract_text_from_pdf",
        lambda _bytes: "tiny",
    )
    monkeypatch.setattr(
        document_extractor,
        "_extract_text_from_pdf_ocr",
        lambda _bytes: "",
    )

    text, metadata = document_extractor.extract_text_from_pdf_with_fallback(b"%PDF-1.4")
    assert text == "tiny"
    assert metadata["ocr_used"] is False
    assert metadata["extraction_mode"] == "native_low_text_no_ocr"
