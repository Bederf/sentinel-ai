"""Site-specific Telegram technician document intake flow.

This flow collects the same required metadata used by the technician
document upload processor and then hands the Telegram file off to that
processor. It does not write raw Concept documents.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from app.config.settings import settings
from app.database.repositories.service_record_repository import ServiceRecordRepository
from app.database.repositories.site_repository import SiteRepository
from app.database.repositories.telegram_document_intake_repository import get_telegram_document_intake_repository
from app.database.repositories.technician_repository import get_technician_repository
from app.services.equipment_reference_resolver import resolve_equipment_reference
from app.services.telegram_conversation_manager import get_conversation_manager
from app.services.telegram_intent_classifier import TelegramIntent
from app.services.telegram_message_sender import InlineButton, InlineKeyboard, get_telegram_sender
from app.services.technician_document_upload_service import (
    TECHNICIAN_CATEGORIES,
    TECHNICIAN_DOCUMENT_NAMES,
    TECHNICIAN_SUB_CLASSES,
    InMemoryUploadFile,
    process_technician_document_upload,
)

logger = logging.getLogger(__name__)


class TelegramDocumentIntakeService:
    """Orchestrate the Telegram metadata capture flow for technician uploads."""

    def __init__(self) -> None:
        self._site_repository = SiteRepository()
        self._service_record_repository = ServiceRecordRepository()
        self._technician_repository = get_technician_repository()
        self._intake_repository = get_telegram_document_intake_repository()

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

        prefilled_equipment = await self._resolve_prefilled_equipment_code(chat_id)
        stage = "awaiting_document_name" if prefilled_equipment else "awaiting_equipment"

        session = manager.create_session(chat_id, TelegramIntent.DOCUMENT_INTAKE, "document_intake")
        session.answers = {
            "stage": stage,
            "intake_id": str(intake_record["id"]),
            "site_id": site_id,
            "site_name": site_name,
            "telegram_file_id": telegram_file_id,
            "telegram_user_id": telegram_user_id,
            "received_at": datetime.utcnow().isoformat() + "Z",
            "equipment_id": prefilled_equipment or "",
            "document_name": "",
            "document_sub_class": "",
            "category_discipline": "",
            "document_creation_date": "",
            "trigger_date": "",
        }
        manager.update_session(session)

        prompt = (
            "I received a document for <b>{site_name}</b>.\n\n"
            "Reply with the exact equipment code for this document, for example "
            "<code>S002-CHILLER-B1-001</code>."
            if not prefilled_equipment
            else self._build_stage_prompt("awaiting_document_name", session.answers)
        )
        await sender.send_text(chat_id, prompt.format(site_name=site_name))
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
        value = text.strip()

        if stage == "awaiting_equipment":
            equipment = await self._resolve_equipment_code(value, str(session.answers.get("site_id") or ""))
            if not equipment:
                await sender.send_text(
                    chat_id,
                    "That equipment code was not recognised. Send the exact code, for example <code>S002-CHILLER-B1-001</code>.",
                )
                return True
            session.answers["equipment_id"] = equipment["code"]
            session.answers["equipment_name"] = equipment.get("name") or equipment["code"]
            session.answers["equipment_type"] = equipment.get("type") or "unknown"
            session.answers["stage"] = "awaiting_document_name"
            manager.update_session(session)
            await sender.send_text(chat_id, self._build_stage_prompt("awaiting_document_name", session.answers))
            return True

        if stage == "awaiting_document_name":
            if value not in TECHNICIAN_DOCUMENT_NAMES:
                await sender.send_text(
                    chat_id,
                    "That document name is not valid. Example: <code>Chiller Major Service</code>.",
                )
                return True
            session.answers["document_name"] = value
            session.answers["stage"] = "awaiting_document_sub_class"
            manager.update_session(session)
            await sender.send_text(chat_id, self._build_stage_prompt("awaiting_document_sub_class", session.answers))
            return True

        if stage == "awaiting_document_sub_class":
            if value not in TECHNICIAN_SUB_CLASSES:
                await sender.send_text(
                    chat_id,
                    "That document sub-class is not valid. Example: <code>HVAC</code>.",
                )
                return True
            session.answers["document_sub_class"] = value
            session.answers["stage"] = "awaiting_category_discipline"
            manager.update_session(session)
            await sender.send_text(chat_id, self._build_stage_prompt("awaiting_category_discipline", session.answers))
            return True

        if stage == "awaiting_category_discipline":
            if value not in TECHNICIAN_CATEGORIES:
                await sender.send_text(
                    chat_id,
                    "That category discipline is not valid. Example: <code>Preventive Maintenance</code>.",
                )
                return True
            session.answers["category_discipline"] = value
            session.answers["stage"] = "awaiting_document_creation_date"
            manager.update_session(session)
            await sender.send_text(
                chat_id, self._build_stage_prompt("awaiting_document_creation_date", session.answers)
            )
            return True

        if stage == "awaiting_document_creation_date":
            creation_date = self._validate_iso_date(value, "document creation date")
            if not creation_date:
                await sender.send_text(chat_id, "Send the creation date as <code>YYYY-MM-DD</code>.")
                return True
            session.answers["document_creation_date"] = creation_date
            session.answers["stage"] = "awaiting_trigger_date"
            manager.update_session(session)
            await sender.send_text(chat_id, self._build_stage_prompt("awaiting_trigger_date", session.answers))
            return True

        if stage == "awaiting_trigger_date":
            trigger_date = self._validate_iso_date(value, "trigger date")
            if not trigger_date:
                await sender.send_text(chat_id, "Send the trigger date as <code>YYYY-MM-DD</code>.")
                return True
            if trigger_date < str(session.answers.get("document_creation_date") or ""):
                await sender.send_text(chat_id, "The trigger date cannot be before the document creation date.")
                return True
            session.answers["trigger_date"] = trigger_date
            session.answers["stage"] = "awaiting_confirmation"
            manager.update_session(session)
            await sender.send_text(
                chat_id,
                self._build_confirmation_message(session.answers),
                keyboard=self._confirmation_keyboard(),
            )
            return True

        return False

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
            await sender.send_text(chat_id, "This document intake session has expired. Please send the document again.")
            return True

        try:
            _, action, value = callback_data.split(":", 2)
        except ValueError:
            await sender.send_text(chat_id, "That document action was invalid. Please send the document again.")
            manager.end_session(chat_id)
            return True

        if action == "confirm" and value == "cancel":
            self._intake_repository.update(
                str(session.answers.get("intake_id") or ""),
                {
                    "intake_status": "cancelled",
                    "equipment_id": session.answers.get("equipment_id") or "",
                    "document_name": session.answers.get("document_name") or "",
                    "document_sub_class": session.answers.get("document_sub_class") or "",
                    "category_discipline": session.answers.get("category_discipline") or "",
                },
            )
            manager.end_session(chat_id)
            await sender.send_text(chat_id, "Document intake cancelled. Send the document again when you are ready.")
            return True

        if action == "confirm" and value == "save":
            session.answers["stage"] = "processing"
            manager.update_session(session)
            await sender.send_text(chat_id, "Saving document with the technician upload processor...")

            try:
                downloaded = await self._download_telegram_file(str(session.answers["telegram_file_id"]))
                file_name = Path(downloaded.telegram_file_path).name or f"{session.answers['document_name']}.bin"
                upload_file = InMemoryUploadFile(
                    filename=file_name,
                    content=downloaded.file_bytes,
                    content_type=downloaded.mime_type,
                )
                result = await process_technician_document_upload(
                    file=upload_file,
                    site_id=str(session.answers["site_id"]),
                    equipment_id=str(session.answers["equipment_id"]),
                    document_name=str(session.answers["document_name"]),
                    document_sub_class=str(session.answers["document_sub_class"]),
                    category_discipline=str(session.answers["category_discipline"]),
                    document_creation_date=str(session.answers["document_creation_date"]),
                    trigger_date=str(session.answers["trigger_date"]),
                    uploaded_by_user_id=telegram_user_id,
                    user_role="operator",
                    title=str(session.answers["document_name"]),
                )
            except Exception as exc:
                logger.error("Telegram document intake save failed: %s", exc, exc_info=True)
                self._intake_repository.update(
                    str(session.answers.get("intake_id") or ""),
                    {
                        "intake_status": "failed",
                        "equipment_id": session.answers.get("equipment_id") or "",
                        "document_name": session.answers.get("document_name") or "",
                        "document_sub_class": session.answers.get("document_sub_class") or "",
                        "category_discipline": session.answers.get("category_discipline") or "",
                        "document_creation_date": session.answers.get("document_creation_date") or "",
                        "trigger_date": session.answers.get("trigger_date") or "",
                        "error_message": str(exc),
                    },
                )
                manager.end_session(chat_id)
                await sender.send_text(
                    chat_id,
                    "The document could not be processed. Please try again later or resend the file.",
                )
                return True

            self._intake_repository.update(
                str(session.answers.get("intake_id") or ""),
                {
                    "intake_status": "saved",
                    "equipment_id": session.answers.get("equipment_id") or "",
                    "document_name": session.answers.get("document_name") or "",
                    "document_sub_class": session.answers.get("document_sub_class") or "",
                    "category_discipline": session.answers.get("category_discipline") or "",
                    "document_creation_date": session.answers.get("document_creation_date") or "",
                    "trigger_date": session.answers.get("trigger_date") or "",
                    "uploaded_document_id": result.get("document_id"),
                    "uploaded_storage_path": result.get("storage_path"),
                },
            )
            manager.end_session(chat_id)
            await sender.send_text(
                chat_id,
                "Document saved.\n\n"
                f"Site: {result['site_id']}\n"
                f"Equipment: {result['document_sub_class']} / {result['document_name']}\n"
                f"Document ID: {result.get('document_id')}\n"
                f"Storage: {result.get('storage_path')}",
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

    async def _resolve_prefilled_equipment_code(self, chat_id: str) -> str | None:
        record = await self._resolve_active_service_record(chat_id)
        if not record:
            return None
        equipment_id = str(record.get("equipment_id") or "").strip()
        if not equipment_id:
            return None
        equipment = await self._service_record_repository.get_equipment_by_id(equipment_id)
        if equipment and equipment.get("code"):
            return str(equipment["code"])
        return equipment_id

    async def _resolve_active_service_record(self, chat_id: str) -> dict[str, Any] | None:
        try:
            records = await self._service_record_repository.list({"telegram_chat_id": chat_id})
        except Exception as exc:
            logger.warning("Unable to query service records for chat %s: %s", chat_id, exc)
            return None

        active_statuses = {"notified", "in_progress", "data_collection", "complete", "scheduled"}
        active_records = [row for row in records if str(row.get("status") or "") in active_statuses]
        if not active_records:
            return None

        active_records.sort(key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""), reverse=True)
        return active_records[0]

    async def _resolve_equipment_code(self, reference: str, site_id: str) -> dict[str, Any] | None:
        if not reference:
            return None
        try:
            return await resolve_equipment_reference(reference, site_id=site_id)
        except Exception as exc:
            logger.warning("Equipment resolution failed for %s: %s", reference, exc)
            return None

    async def _download_telegram_file(self, telegram_file_id: str) -> Any:
        token = (settings.telegram_bot_token or "").strip()
        if not token:
            raise ValueError("telegram_bot_token is not configured")

        base_url = f"https://api.telegram.org/bot{token}"
        file_url_root = f"https://api.telegram.org/file/bot{token}"

        async with httpx.AsyncClient(timeout=20) as client:
            metadata_response = await client.get(f"{base_url}/getFile", params={"file_id": telegram_file_id})
            metadata_response.raise_for_status()
            metadata_payload = metadata_response.json()
            if not metadata_payload.get("ok") or not metadata_payload.get("result", {}).get("file_path"):
                raise ValueError("Telegram did not return a file path")

            telegram_file_path = metadata_payload["result"]["file_path"]
            content_response = await client.get(f"{file_url_root}/{telegram_file_path}")
            content_response.raise_for_status()

        file_extension = Path(telegram_file_path).suffix.lower() or ".jpg"
        return type(
            "DownloadedTelegramFile",
            (),
            {
                "file_bytes": content_response.content,
                "file_extension": file_extension,
                "telegram_file_path": telegram_file_path,
                "mime_type": content_response.headers.get("content-type"),
            },
        )()

    def _validate_iso_date(self, value: str, field_name: str) -> str | None:
        try:
            return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
        except Exception:
            logger.warning("Invalid %s: %s", field_name, value)
            return None

    def _confirmation_keyboard(self) -> InlineKeyboard:
        return InlineKeyboard(
            rows=[
                [
                    InlineButton("Save", "docintake:confirm:save"),
                    InlineButton("Cancel", "docintake:confirm:cancel"),
                ]
            ]
        )

    def _build_stage_prompt(self, stage: str, answers: dict[str, Any]) -> str:
        if stage == "awaiting_document_name":
            return (
                f"Building: {answers.get('site_name', '')}\n"
                f"Equipment: {answers.get('equipment_id', '')}\n\n"
                "Reply with the technician document name, for example <code>Chiller Major Service</code>."
            )
        if stage == "awaiting_document_sub_class":
            return (
                "Reply with the document sub-class.\n"
                "Examples: <code>HVAC</code>, <code>Electrical</code>, <code>Fire</code>."
            )
        if stage == "awaiting_category_discipline":
            return "Reply with the category discipline.\nExample: <code>Preventive Maintenance</code>."
        if stage == "awaiting_document_creation_date":
            return "Reply with the document creation date in <code>YYYY-MM-DD</code> format."
        if stage == "awaiting_trigger_date":
            return "Reply with the trigger date in <code>YYYY-MM-DD</code> format."
        return "Continue."

    def _build_confirmation_message(self, answers: dict[str, Any]) -> str:
        return (
            "Please confirm before save:\n\n"
            f"Building: {answers.get('site_name', '')}\n"
            f"Equipment: {answers.get('equipment_id', '')}\n"
            f"Document name: {answers.get('document_name', '')}\n"
            f"Sub-class: {answers.get('document_sub_class', '')}\n"
            f"Category: {answers.get('category_discipline', '')}\n"
            f"Creation date: {answers.get('document_creation_date', '')}\n"
            f"Trigger date: {answers.get('trigger_date', '')}"
        )


_telegram_document_intake_service: TelegramDocumentIntakeService | None = None


def get_telegram_document_intake_service() -> TelegramDocumentIntakeService:
    global _telegram_document_intake_service
    if _telegram_document_intake_service is None:
        _telegram_document_intake_service = TelegramDocumentIntakeService()
    return _telegram_document_intake_service
