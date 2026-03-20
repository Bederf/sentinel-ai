from __future__ import annotations

import json

import pytest

from app.services.concept_raw_document_service import ConceptRawDocumentService


@pytest.mark.asyncio
async def test_save_telegram_document_writes_raw_file_and_index(tmp_path, monkeypatch):
    service = ConceptRawDocumentService(
        raw_root=tmp_path / "raw",
        index_path=tmp_path / "concept_raw_documents_index.json",
    )

    async def fake_download(_telegram_file_id: str):
        from app.services.concept_raw_document_service import DownloadedTelegramFile

        return DownloadedTelegramFile(
            file_bytes=b"fake-image-bytes",
            file_extension=".jpg",
            telegram_file_path="photos/test-file.jpg",
            mime_type="image/jpeg",
        )

    service._download_telegram_file = fake_download  # type: ignore[method-assign]

    async def fake_scan(**kwargs):
        return type(
            "ScanResult",
            (),
            {
                "allowed": True,
                "trust_level": "STANDARD",
                "file_hash": "hash-123",
                "detected_type": "JPEG",
                "rejection_reason": None,
            },
        )()

    monkeypatch.setattr(
        "app.services.concept_raw_document_service.validate_and_scan_upload",
        fake_scan,
    )

    result = await service.save_telegram_document(
        site_id="site-002",
        site_name="Centre Court",
        equipment_type="generator",
        document_type="service_sheet",
        telegram_file_id="telegram-file-123",
        telegram_user_id="tg-user-1",
        telegram_chat_id="chat-1",
        received_at="2026-03-17T10:15:00Z",
        notes="Quarterly service",
    )

    assert result["status"] == "saved"
    assert result["site_id"] == "site-002"
    assert result["site_name"] == "Centre Court"
    assert result["concept_path"] == "Centre Court/Generator/Service Sheet"
    assert result["file_name"] == "CENTRE-COURT_GENERATOR_SERVICE-SHEET_2026-03-17.jpg"
    assert result["file_hash"] == "hash-123"

    stored_path = tmp_path / "raw" / "centre-court" / "generator" / "service-sheet" / result["file_name"]
    assert stored_path.read_bytes() == b"fake-image-bytes"

    index_rows = json.loads((tmp_path / "concept_raw_documents_index.json").read_text(encoding="utf-8"))
    assert len(index_rows) == 1
    assert index_rows[0]["site_id"] == "site-002"
    assert index_rows[0]["telegram_file_id"] == "telegram-file-123"
    assert index_rows[0]["concept_path"] == "Centre Court/Generator/Service Sheet"
    assert index_rows[0]["file_hash"] == "hash-123"
