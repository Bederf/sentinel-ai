from __future__ import annotations

import pytest

from app.services.telegram_document_intake_service import get_telegram_document_intake_service
from app.services.telegram_conversation_manager import get_conversation_manager


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


class FakeConceptService:
    async def save_telegram_document(self, **kwargs):
        return {
            "status": "saved",
            "concept_document_id": "concept_raw_test123",
            "site_id": kwargs["site_id"],
            "site_name": kwargs["site_name"],
            "concept_path": "Centre Court/Generator/Service Sheet",
            "file_name": "CENTRE-COURT_GENERATOR_SERVICE-SHEET_2026-03-17.jpg",
            "file_hash": "hash-123",
            "scan_detected_type": "JPEG",
            "scan_trust_level": "STANDARD",
        }


@pytest.mark.asyncio
async def test_document_intake_flow_collects_metadata_and_saves(monkeypatch):
    service = get_telegram_document_intake_service()
    sender = FakeSender()
    manager = get_conversation_manager()
    manager.end_session("chat-123")
    intake_updates: list[tuple[str, dict]] = []

    async def fake_resolve(_telegram_user_id: str):
        return "site-002", "Centre Court"

    class FakeIntakeRepository:
        def create(self, record):
            return {"id": "intake-123", **record}

        def update(self, intake_id, payload):
            intake_updates.append((intake_id, payload))
            return {"id": intake_id, **payload}

    monkeypatch.setattr("app.services.telegram_document_intake_service.get_telegram_sender", lambda: sender)
    monkeypatch.setattr(service, "_resolve_site_context", fake_resolve)
    monkeypatch.setattr(service, "_concept_service", FakeConceptService())
    monkeypatch.setattr(service, "_intake_repository", FakeIntakeRepository())

    started = await service.start_intake(chat_id="chat-123", telegram_user_id="tg-123", telegram_file_id="file-123")
    assert started is True
    assert "What type of equipment is this for?" in sender.messages[-1]["text"]

    await service.handle_callback(
        chat_id="chat-123",
        telegram_user_id="tg-123",
        callback_data="docintake:equipment:generator",
    )
    assert sender.messages[-1]["text"] == "What type of record is this?"

    await service.handle_callback(
        chat_id="chat-123",
        telegram_user_id="tg-123",
        callback_data="docintake:document:service_sheet",
    )
    assert "Any extra notes?" in sender.messages[-1]["text"]

    await service.handle_text(
        chat_id="chat-123",
        telegram_user_id="tg-123",
        text="Quarterly service. Gen 2.",
    )
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
