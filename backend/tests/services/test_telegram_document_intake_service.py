from __future__ import annotations

import pytest

from app.services.telegram_conversation_manager import get_conversation_manager
from app.services.telegram_document_intake_service import get_telegram_document_intake_service


class FakeSender:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_text(self, chat_id: str, text: str, keyboard=None, parse_mode: str = "HTML") -> dict:
        self.messages.append(
            {
                "chat_id": chat_id,
                "text": text,
                "keyboard": keyboard,
                "parse_mode": parse_mode,
            }
        )
        return {"ok": True}


class FakeUploadProcessor:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "site_id": kwargs["site_id"],
            "document_sub_class": kwargs["document_sub_class"],
            "document_name": kwargs["document_name"],
            "document_id": "doc-123",
            "storage_path": "site-uuid/test-file.pdf",
        }


@pytest.mark.asyncio
async def test_document_intake_flow_collects_metadata_and_processes_upload(monkeypatch):
    service = get_telegram_document_intake_service()
    sender = FakeSender()
    manager = get_conversation_manager()
    manager.end_session("chat-123")
    intake_updates: list[tuple[str, dict]] = []
    processor = FakeUploadProcessor()

    async def fake_resolve_site(_telegram_user_id: str):
        return "site-002", "Centre Court"

    async def fake_resolve_equipment(reference: str, site_id: str | None = None):
        assert reference == "S002-CHILLER-B1-001"
        return {"code": "S002-CHILLER-B1-001", "name": "Main Chiller 1", "type": "chiller"}

    async def fake_download(_telegram_file_id: str):
        return type(
            "DownloadedTelegramFile",
            (),
            {
                "file_bytes": b"fake-image-bytes",
                "telegram_file_path": "photos/test-file.jpg",
                "mime_type": "image/jpeg",
            },
        )()

    class FakeIntakeRepository:
        def create(self, record):
            return {"id": "intake-123", **record}

        def update(self, intake_id, payload):
            intake_updates.append((intake_id, payload))
            return {"id": intake_id, **payload}

    monkeypatch.setattr("app.services.telegram_document_intake_service.get_telegram_sender", lambda: sender)
    monkeypatch.setattr(service, "_resolve_site_context", fake_resolve_site)

    async def fake_active_record(_chat_id: str):
        return None

    monkeypatch.setattr(service, "_resolve_active_service_record", fake_active_record)
    monkeypatch.setattr(
        "app.services.telegram_document_intake_service.resolve_equipment_reference", fake_resolve_equipment
    )
    monkeypatch.setattr(service, "_download_telegram_file", fake_download)
    monkeypatch.setattr(service, "_intake_repository", FakeIntakeRepository())
    monkeypatch.setattr(
        "app.services.telegram_document_intake_service.process_technician_document_upload",
        processor,
    )

    started = await service.start_intake(chat_id="chat-123", telegram_user_id="tg-123", telegram_file_id="file-123")
    assert started is True
    assert "Reply with the exact equipment code" in sender.messages[-1]["text"]

    await service.handle_text(chat_id="chat-123", telegram_user_id="tg-123", text="S002-CHILLER-B1-001")
    assert "Chiller Major Service" in sender.messages[-1]["text"]

    await service.handle_text(chat_id="chat-123", telegram_user_id="tg-123", text="Chiller Major Service")
    assert "document sub-class" in sender.messages[-1]["text"].lower()

    await service.handle_text(chat_id="chat-123", telegram_user_id="tg-123", text="HVAC")
    assert "category discipline" in sender.messages[-1]["text"].lower()

    await service.handle_text(chat_id="chat-123", telegram_user_id="tg-123", text="Preventive Maintenance")
    assert "document creation date" in sender.messages[-1]["text"].lower()

    await service.handle_text(chat_id="chat-123", telegram_user_id="tg-123", text="2026-03-17")
    assert "trigger date" in sender.messages[-1]["text"].lower()

    await service.handle_text(chat_id="chat-123", telegram_user_id="tg-123", text="2026-03-18")
    assert "Please confirm before save:" in sender.messages[-1]["text"]

    await service.handle_callback(
        chat_id="chat-123",
        telegram_user_id="tg-123",
        callback_data="docintake:confirm:save",
    )

    assert sender.messages[-1]["text"].startswith("Document saved.")
    assert manager.get_session("chat-123") is None
    assert intake_updates[-1][0] == "intake-123"
    assert intake_updates[-1][1]["intake_status"] == "saved"
    assert processor.calls[-1]["equipment_id"] == "S002-CHILLER-B1-001"
    assert processor.calls[-1]["document_name"] == "Chiller Major Service"
    assert processor.calls[-1]["document_sub_class"] == "HVAC"
    assert processor.calls[-1]["category_discipline"] == "Preventive Maintenance"


@pytest.mark.asyncio
async def test_document_intake_requires_site_mapping(monkeypatch):
    service = get_telegram_document_intake_service()
    sender = FakeSender()
    manager = get_conversation_manager()
    manager.end_session("chat-no-site")

    async def fake_resolve(_telegram_user_id: str):
        raise ValueError("no site")

    monkeypatch.setattr("app.services.telegram_document_intake_service.get_telegram_sender", lambda: sender)
    monkeypatch.setattr(service, "_resolve_site_context", fake_resolve)

    started = await service.start_intake(
        chat_id="chat-no-site",
        telegram_user_id="tg-404",
        telegram_file_id="file-404",
    )

    assert started is False
    assert "not linked to a building site" in sender.messages[-1]["text"]
    assert manager.get_session("chat-no-site") is None
