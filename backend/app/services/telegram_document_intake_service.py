"""Guided Telegram document intake flow for raw Concept uploads."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from app.database.repositories.service_record_repository import ServiceRecordRepository
from app.database.repositories.site_repository import SiteRepository
from app.database.repositories.technician_repository import get_technician_repository
from app.database.repositories.telegram_document_intake_repository import get_telegram_document_intake_repository
from app.services.concept_raw_document_service import get_concept_raw_document_service
from app.services.telegram_conversation_manager import get_conversation_manager
from app.services.telegram_intent_classifier import TelegramIntent
from app.services.telegram_message_sender import InlineButton, InlineKeyboard, get_telegram_sender

logger = logging.getLogger(__name__)

EQUIPMENT_OPTIONS = [
    ("Generator", "generator"),
    ("Lift", "lift"),
    ("HVAC", "hvac"),
    ("Pump", "pump"),
    ("Electrical panel", "electrical_panel"),
    ("Fire system", "fire_system"),
    ("Other", "other"),
]

DOCUMENT_OPTIONS = [
    ("Service sheet", "service_sheet"),
    ("Job card", "job_card"),
    ("Inspection sheet", "inspection_sheet"),
    ("Certificate", "certificate"),
    ("Maintenance report", "maintenance_report"),
    ("Commissioning sheet", "commissioning_sheet"),
    ("Other", "other"),
]

EQUIPMENT_LABELS = {value: label for label, value in EQUIPMENT_OPTIONS}
DOCUMENT_LABELS = {value: label for label, value in DOCUMENT_OPTIONS}


class TelegramDocumentIntakeService:
    """Orchestrate the guided metadata capture flow for Telegram-uploaded photos."""

    def __init__(self) -> None:
        self._site_repository = SiteRepository()
        self._service_record_repository = ServiceRecordRepository()
        self._technician_repository = get_technician_repository()
        self._intake_repository = get_telegram_document_intake_repository()
        self._concept_service = get_concept_raw_document_service()

    async def start_intake(
        self,
        *,
        chat_id: str,
        telegram_user_id: str,
        telegram_file_id: str,
    ) -> bool:
        sender = get_telegram_sender()
        manager = get_conversation_manager()

        try:
            site_id, site_name = await self._resolve_site_context(telegram_user_id)
        except ValueError:
            await sender.send_text(
                chat_id,
                (
                    "Your Telegram account is not linked to a building site yet. "
                    "Please contact an administrator before filing documents."
                ),
            )
            return False

        intake_record = self._intake_repository.create(
            {
                "source": "telegram_sentry",
                "chat_id": chat_id,
                "telegram_user_id": telegram_user_id,
                "telegram_file_id": telegram_file_id,
                "site_id": site_id,
                "site_name": site_name,
                "intake_status": "metadata_pending",
                "received_at": datetime.utcnow().isoformat() + "Z",
            }
        )
        session = manager.create_session(chat_id, TelegramIntent.DOCUMENT_INTAKE, "document_intake")
        session.answers = {
            "stage": "awaiting_equipment_type",
            "intake_id": str(intake_record["id"]),
            "site_id": site_id,
            "site_name": site_name,
            "telegram_file_id": telegram_file_id,
            "telegram_user_id": telegram_user_id,
            "received_at": datetime.utcnow().isoformat() + "Z",
            "notes": "",
        }
        manager.update_session(session)

        await sender.send_text(
            chat_id,
            f"I received a document for <b>{site_name}</b>. Let's file it correctly.\n\n"
            "What type of equipment is this for?",
            keyboard=self._equipment_keyboard(),
        )
        return True

    async def handle_text(
        self,
        *,
        chat_id: str,
        telegram_user_id: str,
        text: str,
    ) -> bool:
        sender = get_telegram_sender()
        manager = get_conversation_manager()
        session = manager.get_session(chat_id)
        if not session or session.flow != "document_intake":
            return False

        stage = str(session.answers.get("stage") or "")
        if stage != "awaiting_notes":
            await sender.send_text(chat_id, "Use the buttons to continue the document intake flow.")
            return True

        session.answers["notes"] = text.strip()
        session.answers["stage"] = "awaiting_confirmation"
        manager.update_session(session)

        await sender.send_text(
            chat_id,
            self._build_confirmation_message(session.answers),
            keyboard=self._confirmation_keyboard(),
        )
        return True

    async def handle_callback(
        self,
        *,
        chat_id: str,
        telegram_user_id: str,
        callback_data: str,
    ) -> bool:
        sender = get_telegram_sender()
        manager = get_conversation_manager()
        session = manager.get_session(chat_id)
        if not session or session.flow != "document_intake":
            await sender.send_text(chat_id, "This document intake session has expired. Please send the photo again.")
            return True

        try:
            _, action, value = callback_data.split(":", 2)
        except ValueError:
            await sender.send_text(chat_id, "That document action was invalid. Please send the photo again.")
            manager.end_session(chat_id)
            return True

        if action == "equipment":
            if value not in EQUIPMENT_LABELS:
                await sender.send_text(chat_id, "That equipment type was not recognised.")
                return True
            session.answers["equipment_type"] = value
            session.answers["stage"] = "awaiting_document_type"
            manager.update_session(session)
            await sender.send_text(chat_id, "What type of record is this?", keyboard=self._document_keyboard())
            return True

        if action == "document":
            if value not in DOCUMENT_LABELS:
                await sender.send_text(chat_id, "That document type was not recognised.")
                return True
            session.answers["document_type"] = value
            session.answers["stage"] = "awaiting_notes"
            manager.update_session(session)
            await sender.send_text(
                chat_id,
                "Any extra notes?\n\nReply with one message, or tap Skip.",
                keyboard=self._notes_keyboard(),
            )
            return True

        if action == "notes" and value == "skip":
            session.answers["notes"] = ""
            session.answers["stage"] = "awaiting_confirmation"
            manager.update_session(session)
            await sender.send_text(
                chat_id,
                self._build_confirmation_message(session.answers),
                keyboard=self._confirmation_keyboard(),
            )
            return True

        if action == "confirm" and value == "cancel":
            self._intake_repository.update(
                str(session.answers.get("intake_id") or ""),
                {
                    "intake_status": "cancelled",
                    "equipment_type": session.answers.get("equipment_type"),
                    "document_type": session.answers.get("document_type"),
                    "notes": session.answers.get("notes") or "",
                },
            )
            manager.end_session(chat_id)
            await sender.send_text(chat_id, "Document intake cancelled. Send the photo again when you are ready.")
            return True

        if action == "confirm" and value == "save":
            session.answers["stage"] = "processing"
            manager.update_session(session)
            await sender.send_text(chat_id, "Saving raw file to Concept...")

            try:
                active_service_record = await self._resolve_active_service_record(chat_id)
                result = await self._concept_service.save_telegram_document(
                    site_id=str(session.answers["site_id"]),
                    site_name=str(session.answers["site_name"]),
                    equipment_type=str(session.answers["equipment_type"]),
                    document_type=str(session.answers["document_type"]),
                    telegram_file_id=str(session.answers["telegram_file_id"]),
                    telegram_user_id=telegram_user_id,
                    telegram_chat_id=chat_id,
                    received_at=str(session.answers["received_at"]),
                    equipment_id=(active_service_record or {}).get("equipment_id"),
                    work_order_id=(active_service_record or {}).get("work_order_id"),
                    notes=str(session.answers.get("notes") or ""),
                )
            except Exception as exc:
                logger.error("Telegram document intake save failed: %s", exc, exc_info=True)
                self._intake_repository.update(
                    str(session.answers.get("intake_id") or ""),
                    {
                        "intake_status": "failed",
                        "equipment_type": session.answers.get("equipment_type"),
                        "document_type": session.answers.get("document_type"),
                        "notes": session.answers.get("notes") or "",
                        "error_message": str(exc),
                    },
                )
                manager.end_session(chat_id)
                await sender.send_text(
                    chat_id,
                    "The document could not be saved to Concept. Please try again later or resend the photo.",
                )
                return True

            self._intake_repository.update(
                str(session.answers.get("intake_id") or ""),
                {
                    "intake_status": "saved",
                    "equipment_type": session.answers.get("equipment_type"),
                    "document_type": session.answers.get("document_type"),
                    "notes": session.answers.get("notes") or "",
                    "concept_document_id": result["concept_document_id"],
                    "concept_path": result["concept_path"],
                    "file_name": result["file_name"],
                    "file_hash": result.get("file_hash"),
                    "scan_detected_type": result.get("scan_detected_type"),
                    "scan_trust_level": result.get("scan_trust_level"),
                    "equipment_id": (active_service_record or {}).get("equipment_id"),
                    "work_order_id": (active_service_record or {}).get("work_order_id"),
                    "supabase_document_id": result.get("supabase_document_id"),
                },
            )
            manager.end_session(chat_id)
            await sender.send_text(
                chat_id,
                "Document saved.\n\n"
                f"Building: {result['site_name']}\n"
                f"Path: {result['concept_path']}\n"
                f"File: {result['file_name']}\n"
                f"Reference: {result['concept_document_id']}",
            )
            return True

        await sender.send_text(chat_id, "That action was not recognised for this document intake session.")
        return True

    async def _resolve_site_context(self, telegram_user_id: str) -> tuple[str, str]:
        technician = await self._technician_repository.get_technician_by_telegram_id(telegram_user_id)
        if not technician:
            raise ValueError(f"No technician mapped to Telegram user {telegram_user_id}")

        site_id = str((technician or {}).get("site_id") or "").strip()
        if not site_id:
            raise ValueError(f"Technician {telegram_user_id} has no primary site assignment")

        site_name = str((technician or {}).get("site_name") or "").strip()
        if not site_name:
            site = self._site_repository.get_by_id(site_id)
            site_name = str((site or {}).get("name") or "").strip()
        if not site_name:
            raise ValueError(f"Site {site_id} could not be resolved")

        return site_id, site_name

    async def _resolve_active_service_record(self, chat_id: str) -> dict[str, Any] | None:
        """Resolve the latest active service record for this Telegram chat."""
        try:
            records = await self._service_record_repository.list({"telegram_chat_id": chat_id})
        except Exception as exc:
            logger.warning("Unable to query service records for chat %s: %s", chat_id, exc)
            return None

        active_statuses = {"notified", "in_progress", "data_collection", "complete"}
        active_records = [row for row in records if str(row.get("status") or "") in active_statuses]
        if not active_records:
            return None

        active_records.sort(key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""), reverse=True)
        return active_records[0]

    def _equipment_keyboard(self) -> InlineKeyboard:
        rows = []
        for index in range(0, len(EQUIPMENT_OPTIONS), 2):
            pair = EQUIPMENT_OPTIONS[index : index + 2]
            rows.append([InlineButton(label, f"docintake:equipment:{value}") for label, value in pair])
        return InlineKeyboard(rows=rows)

    def _document_keyboard(self) -> InlineKeyboard:
        rows = []
        for index in range(0, len(DOCUMENT_OPTIONS), 2):
            pair = DOCUMENT_OPTIONS[index : index + 2]
            rows.append([InlineButton(label, f"docintake:document:{value}") for label, value in pair])
        return InlineKeyboard(rows=rows)

    def _notes_keyboard(self) -> InlineKeyboard:
        return InlineKeyboard(rows=[[InlineButton("Skip", "docintake:notes:skip")]])

    def _confirmation_keyboard(self) -> InlineKeyboard:
        return InlineKeyboard(
            rows=[
                [
                    InlineButton("Save to Concept", "docintake:confirm:save"),
                    InlineButton("Cancel", "docintake:confirm:cancel"),
                ]
            ]
        )

    def _build_confirmation_message(self, answers: dict[str, Any]) -> str:
        notes = str(answers.get("notes") or "").strip() or "None"
        return (
            "Please confirm before save:\n\n"
            f"Building: {answers.get('site_name', '')}\n"
            f"Equipment type: {EQUIPMENT_LABELS.get(str(answers.get('equipment_type')), 'Unknown')}\n"
            f"Document type: {DOCUMENT_LABELS.get(str(answers.get('document_type')), 'Unknown')}\n"
            f"Notes: {notes}"
        )


_telegram_document_intake_service: TelegramDocumentIntakeService | None = None


def get_telegram_document_intake_service() -> TelegramDocumentIntakeService:
    global _telegram_document_intake_service
    if _telegram_document_intake_service is None:
        _telegram_document_intake_service = TelegramDocumentIntakeService()
    return _telegram_document_intake_service
