"""Telegram Conversation Flow Handlers.

All conversation flows: client complaint, technician checklist,
WO update, ad-hoc fault, and unknown/orientation.
"""

from __future__ import annotations

import contextlib
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.services.issue_classifier import (
    DISCIPLINE_TO_CATEGORY,
    classify_issue,
    extract_area_from_message,
    extract_floor_from_message,
)
from app.services.telegram_conversation_manager import (
    ConversationSession,
    get_conversation_manager,
)
from app.services.telegram_intent_classifier import TelegramIntent
from app.services.telegram_message_sender import (
    InlineButton,
    InlineKeyboard,
    get_telegram_sender,
    TelegramMessageSender,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Voice Response Integration
# ---------------------------------------------------------------------------

_VOICE_COORDINATOR: Optional["VoiceResponseCoordinator"] = None


def _get_voice_coordinator():
    """Lazy-load VoiceResponseCoordinator from sentry tools."""
    global _VOICE_COORDINATOR
    if _VOICE_COORDINATOR is None:
        try:
            sentry_tools = Path("/home/bederf/.sentry/tools")
            if sentry_tools.exists():
                sys.path.insert(0, str(sentry_tools))
                from voice_response import VoiceResponseCoordinator

                _VOICE_COORDINATOR = VoiceResponseCoordinator()
                logger.info("VoiceResponseCoordinator loaded successfully")
            else:
                logger.warning("Sentry tools not found at %s", sentry_tools)
        except Exception as e:
            logger.warning("Failed to load VoiceResponseCoordinator: %s", e)
    return _VOICE_COORDINATOR


async def _send_response(
    chat_id: str,
    text: str,
    sender: TelegramMessageSender,
    keyboard: InlineKeyboard | None = None,
    force_voice: bool = False,
    user_message: str = "",
) -> None:
    """Send a response, using voice if a trigger is detected or force_voice=True.

    Args:
        chat_id: Target Telegram chat ID
        text: Response text
        sender: TelegramMessageSender instance
        keyboard: Optional inline keyboard
        force_voice: If True, always generate voice (for auto-voice responses)
        user_message: The user's original message text to check for voice triggers
    """
    coordinator = _get_voice_coordinator()

    voice_params: dict = {}
    should_use_voice = force_voice

    if coordinator and not force_voice:
        # Try to get user's original message from active session
        if not user_message:
            try:
                from app.services.telegram_conversation_manager import get_conversation_manager
                session = get_conversation_manager().get_session(chat_id)
                if session:
                    user_message = session.answers.get("original_text", "") or ""
            except Exception:
                pass
        trigger_text = user_message or text
        analysis = coordinator.analyze_message_for_voice(trigger_text)
        should_use_voice = analysis.get("should_use_voice", False)
        voice_params = analysis.get("voice_params", {})

    if should_use_voice and coordinator:
        voice_name = voice_params.get("voice_name")
        audio_path = coordinator.get_voice_response(text, voice_name=voice_name)

        if audio_path and not isinstance(audio_path, dict):
            try:
                await sender.send_voice(chat_id, audio_path, caption=text[:200])
                logger.debug("Voice response sent for chat %s", chat_id)
                return
            except Exception as e:
                logger.warning("Voice send failed, falling back to text: %s", e)

    # Fallback to text
    await sender.send_text(chat_id, text, keyboard=keyboard)

# ---------------------------------------------------------------------------
# Category mapping for complaint buttons
# ---------------------------------------------------------------------------
_COMPLAINT_CATEGORIES = {
    "hvac": "Temperature / HVAC",
    "plumbing": "Water / Plumbing",
    "electrical": "Lighting / Electrical",
    "noise": "Noise",
    "access": "Access / Door",
    "other": "Other",
}

_DURATION_MAP = {
    "just_started": "Just started",
    "a_few_hours": "A few hours",
    "since_yesterday": "Since yesterday",
    "several_days": "Several days",
}

# AHU checklist questions
_AHU_CHECKLIST = [
    {
        "key": "filter",
        "question": "1/6 -- Filter Condition?",
        "options": [
            ("Good", "inspect:filter:good"),
            ("Dirty", "inspect:filter:dirty"),
            ("Blocked", "inspect:filter:blocked"),
        ],
        "icons": ["good", "warn", "critical"],
    },
    {
        "key": "pressure_drop",
        "question": "2/6 -- Filter Pressure Drop?",
        "options": [
            ("Normal", "inspect:pressure:normal"),
            ("High", "inspect:pressure:high"),
            ("Very High", "inspect:pressure:very_high"),
        ],
        "icons": ["good", "warn", "critical"],
    },
    {
        "key": "fan_vibration",
        "question": "3/6 -- Fan Vibration?",
        "options": [
            ("Good", "inspect:vibration:good"),
            ("Moderate", "inspect:vibration:moderate"),
            ("Excessive", "inspect:vibration:excessive"),
        ],
        "icons": ["good", "warn", "critical"],
    },
    {
        "key": "belt",
        "question": "4/6 -- Belt Condition?",
        "options": [
            ("Good", "inspect:belt:good"),
            ("Worn", "inspect:belt:worn"),
            ("Cracked", "inspect:belt:cracked"),
        ],
        "icons": ["good", "warn", "critical"],
    },
    {
        "key": "coil",
        "question": "5/6 -- Coil Condition? Please send a photo.",
        "options": [
            ("No photo available", "inspect:coil:no_photo"),
        ],
        "icons": ["skip"],
        "free_text_ok": True,
    },
    {
        "key": "damper",
        "question": "6/6 -- Damper Operation?",
        "options": [
            ("Normal", "inspect:damper:normal"),
            ("Sticky", "inspect:damper:sticky"),
            ("Stuck", "inspect:damper:stuck"),
        ],
        "icons": ["good", "warn", "critical"],
    },
]

# Follow-up questions for non-Good answers
_FOLLOWUPS = {
    "filter:dirty": {
        "question": "Restricting airflow yet?",
        "options": [
            ("Yes - change soon", "inspect:filter_detail:change_soon"),
            ("Not yet", "inspect:filter_detail:not_yet"),
        ],
    },
    "filter:blocked": {
        "question": "Can you replace now?",
        "options": [
            ("Yes", "inspect:filter_detail:replacing"),
            ("Need parts - raise WO", "inspect:filter_detail:need_parts"),
        ],
    },
    "fan_vibration:moderate": {
        "question": "Source?",
        "options": [
            ("Fan shaft", "inspect:vibration_detail:fan_shaft"),
            ("Motor", "inspect:vibration_detail:motor"),
            ("Can't tell", "inspect:vibration_detail:unknown"),
        ],
    },
    "fan_vibration:excessive": {
        "question": "Unit running?",
        "options": [
            ("Yes - shutting down", "inspect:vibration_detail:shutting_down"),
            ("Already off", "inspect:vibration_detail:already_off"),
        ],
    },
    "belt:worn": {
        "question": "Type of wear?",
        "options": [
            ("Surface", "inspect:belt_detail:surface"),
            ("Cracking", "inspect:belt_detail:cracking"),
            ("Separated", "inspect:belt_detail:separated"),
        ],
    },
    "belt:cracked": {
        "question": "Separated from pulley?",
        "options": [
            ("Yes", "inspect:belt_detail:separated"),
            ("No", "inspect:belt_detail:not_separated"),
        ],
    },
    "damper:sticky": {
        "question": "Actuator linkage connected?",
        "options": [
            ("Yes", "inspect:damper_detail:linkage_yes"),
            ("No", "inspect:damper_detail:linkage_no"),
            ("Obscured", "inspect:damper_detail:linkage_obscured"),
        ],
    },
    "damper:stuck": {
        "question": "Stuck position?",
        "options": [
            ("Open", "inspect:damper_detail:stuck_open"),
            ("Closed", "inspect:damper_detail:stuck_closed"),
            ("Mid", "inspect:damper_detail:stuck_mid"),
        ],
    },
}

# Priority mapping for non-Good checklist answers
_CHECKLIST_PRIORITY = {
    "blocked": "critical",
    "excessive": "critical",
    "separated": "critical",
    "stuck": "critical",
    "very_high": "critical",
    "dirty": "high",
    "moderate": "high",
    "cracked": "high",
    "worn": "high",
    "sticky": "high",
    "high": "high",
}

# Equipment ID extraction pattern
_EQUIPMENT_ID_RE = re.compile(r"(S\d{3}-[A-Z]+-[A-Z0-9]+-\d{3})", re.IGNORECASE)
_WO_RE = re.compile(r"(WO-\d{4}-\d{4})", re.IGNORECASE)


# ===================================================================
# Client Complaint Flow
# ===================================================================


async def handle_client_complaint(
    chat_id: str,
    text: str,
    callback_data: str | None = None,
    message_id: int | None = None,
) -> None:
    """4-step client complaint flow."""
    mgr = get_conversation_manager()
    sender = get_telegram_sender()
    session = mgr.get_session(chat_id)

    # Step 0: Start
    if session is None or session.flow != "client_complaint":
        session = mgr.create_session(chat_id, TelegramIntent.CLIENT_COMPLAINT, "client_complaint")
        # Try to pre-classify from the original message
        if text:
            classification = classify_issue(text)
            if classification:
                session.answers["original_text"] = text
                session.answers["category"] = DISCIPLINE_TO_CATEGORY.get(classification["discipline"], "general")
                session.answers["sub_category"] = classification.get("sub_category", "")
                session.answers["discipline"] = classification["discipline"]
                session.answers["priority"] = classification.get("priority", "medium")
                session.current_step = 1
                mgr.update_session(session)
                # Skip category selection, ask for location
                await _send_response(
                    chat_id,
                    f"Got it -- <b>{classification['sub_category']}</b>.\n\nWhich floor or area is this on?",
                    sender,
                )
                return

        kb = InlineKeyboard(
            rows=[
                [
                    InlineButton("Temperature", "complaint:category:hvac"),
                    InlineButton("Water / Plumbing", "complaint:category:plumbing"),
                ],
                [
                    InlineButton("Lighting", "complaint:category:electrical"),
                    InlineButton("Noise", "complaint:category:noise"),
                ],
                [
                    InlineButton("Access / Door", "complaint:category:access"),
                    InlineButton("Other", "complaint:category:other"),
                ],
            ]
        )
        session.answers["original_text"] = text or ""
        mgr.update_session(session)
        await _send_response(
            chat_id,
            "Hi! I've picked up your message. What best describes the issue?",
            sender,
            keyboard=kb,
        )
        return

    # Step 1: Category received
    if session.current_step == 0:
        category = None
        if callback_data and callback_data.startswith("complaint:category:"):
            category = callback_data.split(":")[-1]
            # Remove buttons from previous message
            if message_id:
                await sender.edit_message_reply_markup(chat_id, message_id)
        elif text:
            # Text fallback: try to match category
            text_lower = text.lower()
            for key, label in _COMPLAINT_CATEGORIES.items():
                if key in text_lower or label.lower() in text_lower:
                    category = key
                    break

        if not category:
            await _send_response(
                chat_id,
                "I didn't catch that. Please tap a button or type the category (e.g. 'plumbing', 'electrical').",
                sender,
            )
            return

        session.answers["category"] = category
        session.current_step = 1
        mgr.update_session(session)
        await _send_response(chat_id, "Which floor or area is this on?", sender)
        return

    # Step 2: Location received
    if session.current_step == 1:
        if not text:
            await _send_response(chat_id, "Please type the floor or area (e.g. 'Level 2', 'kitchen').", sender)
            return

        floor = extract_floor_from_message(text)
        area = extract_area_from_message(text)
        session.answers["location_text"] = text
        if floor:
            session.answers["floor"] = floor
        if area:
            session.answers["area"] = area
        session.current_step = 2
        mgr.update_session(session)

        kb = InlineKeyboard(
            rows=[
                [
                    InlineButton("Just started", "complaint:duration:just_started"),
                    InlineButton("A few hours", "complaint:duration:a_few_hours"),
                ],
                [
                    InlineButton("Since yesterday", "complaint:duration:since_yesterday"),
                    InlineButton("Several days", "complaint:duration:several_days"),
                ],
            ]
        )
        await _send_response(chat_id, "How long has this been happening?", sender, keyboard=kb)
        return

    # Step 3: Duration received
    if session.current_step == 2:
        duration = None
        if callback_data and callback_data.startswith("complaint:duration:"):
            duration = callback_data.split(":")[-1]
            if message_id:
                await sender.edit_message_reply_markup(chat_id, message_id)
        elif text:
            text_lower = text.lower()
            for key in _DURATION_MAP:
                if key.replace("_", " ") in text_lower:
                    duration = key
                    break
            if not duration:
                if "just" in text_lower or "now" in text_lower:
                    duration = "just_started"
                elif "hour" in text_lower:
                    duration = "a_few_hours"
                elif "yesterday" in text_lower:
                    duration = "since_yesterday"
                elif "day" in text_lower or "week" in text_lower:
                    duration = "several_days"

        if not duration:
            await _send_response(chat_id, "Please tap a button or describe how long this has been going on.", sender)
            return

        session.answers["duration"] = duration
        session.current_step = 3
        mgr.update_session(session)

        kb = InlineKeyboard(
            rows=[
                [InlineButton("Skip", "complaint:photo:skip")],
            ]
        )
        await _send_response(chat_id, "Can you send a photo? (Optional)", sender, keyboard=kb)
        return

    # Step 4: Photo or skip -> create WO
    if session.current_step == 3:
        if callback_data and "photo:skip" in callback_data and message_id:
            await sender.edit_message_reply_markup(chat_id, message_id)

        # Determine priority from duration
        duration = session.answers.get("duration", "just_started")
        if duration in ("since_yesterday", "several_days"):
            priority = session.answers.get("priority", "high")
        else:
            priority = session.answers.get("priority", "medium")

        # Create WO via call-log endpoint logic
        wo_code = await _create_complaint_wo(session, priority)

        if wo_code:
            await _send_response(
                chat_id,
                f"Logged! Ref: <b>{wo_code}</b>\n"
                f"Issue: {session.answers.get('category', 'general').title()}\n"
                f"Location: {session.answers.get('location_text', 'Not specified')}\n"
                "Our team has been notified.",
                sender,
            )
        else:
            await _send_response(
                chat_id,
                "Your report has been logged.\n"
                f"Issue: {session.answers.get('category', 'general').title()}\n"
                f"Location: {session.answers.get('location_text', 'Not specified')}\n"
                "Our team has been notified.",
                sender,
            )

        mgr.end_session(chat_id)
        return


# ===================================================================
# Technician Report / Checklist Flow
# ===================================================================


async def handle_technician_report(
    chat_id: str,
    text: str,
    callback_data: str | None = None,
    message_id: int | None = None,
) -> None:
    """Equipment inspection checklist flow."""
    mgr = get_conversation_manager()
    sender = get_telegram_sender()
    session = mgr.get_session(chat_id)

    # Extract equipment ID from text if no session
    if session is None or session.flow != "technician_report":
        equipment_id = None
        if text:
            m = _EQUIPMENT_ID_RE.search(text)
            if m:
                equipment_id = m.group(1).upper()

        if not equipment_id:
            session = mgr.create_session(chat_id, TelegramIntent.TECHNICIAN_REPORT, "technician_report")
            session.current_step = -1  # waiting for equipment ID
            mgr.update_session(session)
            await _send_response(
                chat_id,
                "Which equipment are you inspecting? Please provide the equipment code (e.g. S002-AHU-L2-001).",
                sender,
            )
            return

        session = mgr.create_session(
            chat_id,
            TelegramIntent.TECHNICIAN_REPORT,
            "technician_report",
            equipment_id=equipment_id,
        )
        session.current_step = 0
        session.checklist_type = "ahu"  # Default to AHU checklist for now
        mgr.update_session(session)
        await _send_checklist_question(chat_id, session, 0)
        return

    # Waiting for equipment ID
    if session.current_step == -1:
        if not text:
            await _send_response(chat_id, "Please type the equipment code.", sender)
            return

        m = _EQUIPMENT_ID_RE.search(text)
        if not m:
            await _send_response(
                chat_id,
                "I couldn't find an equipment code in that. Please use the format S002-AHU-L2-001.",
                sender,
            )
            return

        session.equipment_id = m.group(1).upper()
        session.current_step = 0
        session.checklist_type = "ahu"
        mgr.update_session(session)
        await _send_checklist_question(chat_id, session, 0)
        return

    # Handle checklist answers
    checklist = _AHU_CHECKLIST
    current_q_index = session.current_step

    # Check if we're in a follow-up
    if session.answers.get("_awaiting_followup"):
        followup_key = session.answers["_awaiting_followup"]
        value = None

        if callback_data:
            # Extract value from callback: inspect:{key}_detail:{value}
            parts = callback_data.split(":")
            if len(parts) >= 3:
                value = parts[-1]
            if message_id:
                await sender.edit_message_reply_markup(chat_id, message_id)
        elif text:
            value = text.strip()

        if value:
            detail_key = followup_key.split(":")[0] + "_detail"
            session.answers[detail_key] = value
            del session.answers["_awaiting_followup"]

            # Create WO for non-Good finding
            base_key = followup_key.split(":")[0]
            base_value = followup_key.split(":")[1]
            wo_priority = _CHECKLIST_PRIORITY.get(base_value, "high")
            wo_code = await _create_inspection_wo(session, base_key, base_value, wo_priority)
            if wo_code:
                session.wo_codes.append(wo_code)

            # Move to next question
            session.current_step += 1
            mgr.update_session(session)

            if session.current_step < len(checklist):
                await _send_checklist_question(chat_id, session, session.current_step)
            else:
                await _send_inspection_summary(chat_id, session)
                mgr.end_session(chat_id)
        return

    if current_q_index >= len(checklist):
        await _send_inspection_summary(chat_id, session)
        mgr.end_session(chat_id)
        return

    q = checklist[current_q_index]
    value = None

    if callback_data:
        parts = callback_data.split(":")
        if len(parts) >= 3:
            value = parts[-1]
        if message_id:
            await sender.edit_message_reply_markup(chat_id, message_id)
    elif text:
        # Text fallback: match option labels
        text_lower = text.lower()
        for label, cb in q["options"]:
            if label.lower() in text_lower:
                value = cb.split(":")[-1]
                break
        if not value:
            value = text.strip()

    if not value:
        await _send_checklist_question(chat_id, session, current_q_index)
        return

    # Store answer
    session.answers[q["key"]] = value

    # Check for follow-up
    followup_key = f"{q['key']}:{value}"
    if followup_key in _FOLLOWUPS:
        followup = _FOLLOWUPS[followup_key]
        session.answers["_awaiting_followup"] = followup_key
        mgr.update_session(session)

        kb = InlineKeyboard(rows=[[InlineButton(label, cb) for label, cb in followup["options"]]])
        await _send_response(chat_id, followup["question"], sender, keyboard=kb)
        return

    # Non-Good answer without follow-up: auto-create WO
    if value not in ("good", "normal", "no_photo"):
        wo_priority = _CHECKLIST_PRIORITY.get(value, "high")
        wo_code = await _create_inspection_wo(session, q["key"], value, wo_priority)
        if wo_code:
            session.wo_codes.append(wo_code)

    # Move to next question
    session.current_step += 1
    mgr.update_session(session)

    if session.current_step < len(checklist):
        await _send_checklist_question(chat_id, session, session.current_step)
    else:
        await _send_inspection_summary(chat_id, session)
        mgr.end_session(chat_id)


async def _send_checklist_question(chat_id: str, session: ConversationSession, index: int) -> None:
    """Send a single checklist question with inline keyboard."""
    sender = get_telegram_sender()
    q = _AHU_CHECKLIST[index]

    kb = InlineKeyboard(rows=[[InlineButton(label, cb) for label, cb in q["options"]]])

    header = f"<b>{session.equipment_id}</b>\n\n" if index == 0 else ""
    await _send_response(chat_id, f"{header}{q['question']}", sender, keyboard=kb)


async def _send_inspection_summary(chat_id: str, session: ConversationSession) -> None:
    """Send final inspection summary."""
    sender = get_telegram_sender()
    checklist = _AHU_CHECKLIST

    lines = [f"Inspection Complete -- <b>{session.equipment_id}</b>\n"]
    critical_count = 0
    advisory_count = 0

    for q in checklist:
        value = session.answers.get(q["key"], "?")
        if value in ("good", "normal"):
            lines.append(f"  {q['key'].replace('_', ' ').title()}: Good")
        elif value in ("no_photo",):
            lines.append(f"  {q['key'].replace('_', ' ').title()}: No photo")
        else:
            detail = session.answers.get(f"{q['key']}_detail", "")
            detail_str = f" ({detail})" if detail else ""
            priority = _CHECKLIST_PRIORITY.get(value, "high")
            if priority == "critical":
                lines.append(f"  {q['key'].replace('_', ' ').title()}: {value}{detail_str}")
                critical_count += 1
            else:
                lines.append(f"  {q['key'].replace('_', ' ').title()}: {value}{detail_str}")
                advisory_count += 1

    lines.append("")
    lines.append(f"  {critical_count} Critical  |  {advisory_count} Advisory")

    if session.wo_codes:
        lines.append("\nWork Orders Raised:")
        for code in session.wo_codes:
            lines.append(f"  {code}")

    await _send_response(chat_id, "\n".join(lines), sender)


# ===================================================================
# WO Update Flow (stateless)
# ===================================================================


async def handle_wo_update(
    chat_id: str,
    text: str,
    callback_data: str | None = None,
    message_id: int | None = None,
) -> None:
    """WO status update flow."""
    mgr = get_conversation_manager()
    sender = get_telegram_sender()
    session = mgr.get_session(chat_id)

    # Handle callback from status buttons
    if callback_data and callback_data.startswith("wo:status:"):
        status_value = callback_data.split(":")[-1]
        if message_id:
            await sender.edit_message_reply_markup(chat_id, message_id)

        if session and session.wo_id:
            await _update_wo_status(session.wo_id, status_value)
            status_label = {
                "completed": "Completed",
                "in_progress": "Still in progress",
                "blocked": "Blocked",
            }.get(status_value, status_value)

            await _send_response(
                chat_id,
                f"<b>{session.wo_id}</b> updated to: {status_label}",
                sender,
            )
            mgr.end_session(chat_id)
        return

    # Handle "Create Work Order" button from advisory notifications
    if callback_data and callback_data.startswith("wo:rec_id:"):
        rec_uuid = callback_data.split(":")[-1]
        if message_id:
            await sender.edit_message_reply_markup(chat_id, message_id)
        await _handle_create_wo_from_rec(chat_id, rec_uuid, sender)
        return

    # Extract WO number
    wo_match = _WO_RE.search(text or "")
    if not wo_match:
        await _send_response(
            chat_id,
            "I couldn't find a work order number. Please include the WO reference (e.g. WO-2026-0045).",
            sender,
        )
        return

    wo_code = wo_match.group(1).upper()
    wo_data = await _lookup_wo(wo_code)

    if not wo_data:
        await _send_response(chat_id, f"Work order <b>{wo_code}</b> not found.", sender)
        return

    # Check if text contains "done"/"completed"
    text_lower = (text or "").lower()
    has_done = any(kw in text_lower for kw in ("done", "completed", "finished", "complete"))

    if has_done:
        # Quick complete
        await _update_wo_status(wo_code, "completed")
        await _send_response(chat_id, f"<b>{wo_code}</b> marked as completed.", sender)
        return

    # Show WO summary with status buttons
    session = mgr.create_session(chat_id, TelegramIntent.WO_UPDATE, "wo_update")
    session.wo_id = wo_code
    mgr.update_session(session)

    summary = (
        f"<b>{wo_code}</b>\n\n"
        f"Title: {wo_data.get('title', 'N/A')}\n"
        f"Status: {wo_data.get('status', 'N/A')}\n"
        f"Priority: {wo_data.get('priority', 'N/A')}\n"
        f"Assigned: {wo_data.get('assigned_to', 'Unassigned')}\n"
    )

    kb = InlineKeyboard(
        rows=[
            [
                InlineButton("Completed", "wo:status:completed"),
                InlineButton("Still in progress", "wo:status:in_progress"),
                InlineButton("Blocked", "wo:status:blocked"),
            ],
        ]
    )
    await _send_response(chat_id, summary, sender, keyboard=kb)


# ===================================================================
# Advisory WO Creation (from "Create Work Order" button on advisory notifications)
# ===================================================================


async def _handle_create_wo_from_rec(chat_id: str, rec_uuid: str, sender) -> None:
    """Create a work order from an advisory recommendation's UUID."""
    from app.database.repositories.work_order_repository import WorkOrderRepository

    sb = get_supabase_client()
    if not sb:
        await _send_response(chat_id, "Database unavailable. Please try again.", sender)
        return

    # Load the recommendation record
    rec_result = sb.table("recommendations").select("*").eq("id", rec_uuid).execute()
    if not rec_result.data:
        await _send_response(chat_id, "Recommendation not found. It may have already been actioned.", sender)
        return

    rec = rec_result.data[0]
    target = rec.get("target_equipment", "")
    action = rec.get("action") or {}
    point = action.get("point", "") or rec.get("action_type", "adjustment")
    value = action.get("value", "")
    reason = rec.get("reason", "") or rec.get("description", "")
    priority = rec.get("priority", "medium")

    # Build description from recommendation
    description = (
        f"SENTINEL Advisory — AI Optimization Recommendation\n\n"
        f"Equipment: {target}\n"
        f"Action: Set {point} to {value}\n\n"
        f"Reason: {reason[:500]}\n\n"
        f"Recommendation ID: {rec_uuid}"
    )

    wo_data = {
        "title": f"AI Optimization: {target} — {point}",
        "description": description,
        "priority": priority,
        "status": "scheduled",
        "created_by": "sentinel:telegram:advisory_wo",
        "equipment_id": target,
        "recommendation_id": rec_uuid,
    }

    repo = WorkOrderRepository()
    created = repo.create_work_order(wo_data)
    if not created:
        await _send_response(chat_id, "Failed to create work order. Please try again.", sender)
        return

    wo_code = created.get("code") or created.get("id", "unknown")
    await _send_response(
        chat_id,
        f"Work order <b>{wo_code}</b> created for {target}.\n"
        "A technician will be assigned shortly.",
        sender,
    )


# ===================================================================
# Ad-Hoc Fault Flow
# ===================================================================


async def handle_adhoc_fault(
    chat_id: str,
    text: str,
    callback_data: str | None = None,  # noqa: ARG001
    message_id: int | None = None,  # noqa: ARG001
) -> None:
    """2-step ad-hoc fault flow."""
    mgr = get_conversation_manager()
    sender = get_telegram_sender()
    session = mgr.get_session(chat_id)

    if session is None or session.flow != "ad_hoc_fault":
        session = mgr.create_session(chat_id, TelegramIntent.AD_HOC_FAULT, "ad_hoc_fault")
        session.answers["original_text"] = text or ""
        mgr.update_session(session)
        await _send_response(chat_id, "Where is this? (floor, area, or desk number)", sender)
        return

    # Step 1: Location received -> create WO
    if not text:
        await _send_response(chat_id, "Please type the location.", sender)
        return

    floor = extract_floor_from_message(text)
    area = extract_area_from_message(text)
    session.answers["location_text"] = text
    if floor:
        session.answers["floor"] = floor
    if area:
        session.answers["area"] = area

    original = session.answers.get("original_text", "")
    classification = classify_issue(original)
    category = "general"
    if classification:
        category = DISCIPLINE_TO_CATEGORY.get(classification["discipline"], "general")

    wo_code = await _create_complaint_wo(session, "medium", category_override=category)

    if wo_code:
        await _send_response(
            chat_id,
            f"Logged! Work order <b>{wo_code}</b> created.\nLocation: {text}\n\nSomeone will look into it.",
            sender,
        )
    else:
        await _send_response(
            chat_id,
            f"Logged your report for: {text}\nA work order will be created shortly.",
            sender,
        )

    mgr.end_session(chat_id)


# ===================================================================
# Unknown Intent / Orientation Menu
# ===================================================================


async def handle_unknown(
    chat_id: str,
    text: str,  # noqa: ARG001
    callback_data: str | None = None,  # noqa: ARG001
    message_id: int | None = None,  # noqa: ARG001
) -> None:
    """Show orientation menu."""
    sender = get_telegram_sender()

    kb = InlineKeyboard(
        rows=[
            [InlineButton("Report a problem", "menu:start:complaint")],
            [InlineButton("Equipment info", "menu:start:inspection")],
            [InlineButton("Check work order", "menu:start:wo_check")],
        ]
    )
    await _send_response(
        chat_id,
        "Hi! How can I help?\n\nTap an option below or describe your issue.",
        sender,
        keyboard=kb,
    )


# Ghost Room Confirm Buttons Handler
# ===================================================================


async def handle_ghost_room(
    chat_id: str,
    text: str,
    callback_data: str | None = None,
    message_id: int | None = None,
) -> None:
    """Handle ghost room confirm-buttons: ghost:occupied:{id} or ghost:empty:{id}."""
    from app.services import occupancy_store

    sender = get_telegram_sender()

    if not callback_data:
        await _send_response(chat_id, "Invalid button press.", sender)
        return

    parts = callback_data.split(":")
    if len(parts) != 3 or parts[0] != "ghost":
        await _send_response(chat_id, "Unknown ghost room action.", sender)
        return

    action, finding_id = parts[1], parts[2]

    # Look up finding
    finding = occupancy_store.get_ghost_finding_by_id(finding_id)
    if not finding:
        await _send_response(chat_id, "Finding not found or already resolved.", sender)
        return

    confirmed_by = f"telegram:{chat_id}"

    if action == "occupied":
        updated = occupancy_store.update_ghost_finding_status(
            finding_id,
            "verified_occupied",
            inspected_by=confirmed_by,
            response_message_id=str(message_id) if message_id else None,
            response_text="Room confirmed occupied via Telegram button",
        )
        status_text = "occupied"
    else:
        updated = occupancy_store.update_ghost_finding_status(
            finding_id,
            "confirmed_empty",
            inspected_by=confirmed_by,
            response_message_id=str(message_id) if message_id else None,
            response_text="Room confirmed empty via Telegram button",
        )
        status_text = "empty"

    if updated is None:
        await _send_response(chat_id, f"{finding.room_code} was already resolved.", sender)
        return

    # Update inline buttons to show selection
    kb = InlineKeyboard(rows=[[InlineButton(f"✓ {status_text.capitalize()}", callback_data)]])
    if message_id:
        try:
            await sender.edit_message_reply_markup(chat_id, message_id, keyboard=kb)
        except Exception:
            pass  # Button may already be stale

    # Remove keyboard and confirm
    with contextlib.suppress(Exception):
        await sender.edit_message_reply_markup(chat_id, message_id, keyboard=None)

    await _send_response(
        chat_id,
        f"Recorded: {finding.room_code} marked {status_text}. Thank you!",
        sender,
    )

    # Mark related signal resolved
    try:
        from app.models.space_occupancy import GhostBookingFinding
        from app.services.ghost_room_notifier import _resolve_related_ghost_signal

        gf = GhostBookingFinding(**vars(finding))
        gf.status = updated.status
        _resolve_related_ghost_signal(gf, resolution_state="resolved")
    except Exception as exc:
        logger.warning("Failed to resolve ghost signal: %s", exc)


async def handle_focus_room(
    chat_id: str,
    text: str,
    callback_data: str | None = None,
    message_id: int | None = None,
) -> None:
    """Handle focus room confirm-buttons: focus:occupied:{room_code} or focus:empty:{room_code}."""
    sender = get_telegram_sender()

    if not callback_data:
        await _send_response(chat_id, "Invalid button press.", sender)
        return

    parts = callback_data.split(":")
    if len(parts) != 3 or parts[0] != "focus":
        await _send_response(chat_id, "Unknown focus room action.", sender)
        return

    action, room_code = parts[1], parts[2]

    confirmed_by = f"telegram:{chat_id}"

    if action == "occupied":
        from app.services import occupancy_store

        active = occupancy_store.get_active_session(room_code)
        if active:
            occupancy_store.extend_overstay_grace(active.session_id, 10)
            logger.info(
                "Overstay grace +10min via concierge confirm: room=%s session=%s",
                room_code, active.session_id,
            )
        status_text = "occupied"
    else:
        # Room is now empty — close the session, turn off the relay.
        from datetime import datetime

        from app.services import occupancy_store
        from app.services.focus_room_relay_service import sync_focus_room_relay
        from app.services.space_mqtt_listener import get_node_room_mapping

        mapping = get_node_room_mapping()
        resolved_site = "site-002"
        for _node_id, node in mapping.items():
            if node.get("room_code") == room_code and node.get("site_id"):
                resolved_site = node["site_id"]
                break

        active = occupancy_store.get_active_session(room_code)
        if active:
            occupancy_store.close_session(active.session_id, datetime.utcnow())
            logger.info("Focus session closed via concierge confirm: room=%s session=%s", room_code, active.session_id)

        sync_focus_room_relay(site_id=resolved_site, room_code=room_code)
        status_text = "empty"

    # Update inline buttons to show selection
    kb = InlineKeyboard(rows=[[InlineButton(f"✓ {status_text.capitalize()}", callback_data)]])
    if message_id:
        try:
            await sender.edit_message_reply_markup(chat_id, message_id, keyboard=kb)
        except Exception:
            pass

    with contextlib.suppress(Exception):
        await sender.edit_message_reply_markup(chat_id, message_id, keyboard=None)

    await _send_response(
        chat_id,
        f"Recorded: {room_code} marked {status_text}. Thank you!",
        sender,
    )


# ===================================================================
# Router
# ===================================================================


async def route_to_handler(
    intent: TelegramIntent,
    chat_id: str,
    text: str,
    callback_data: str | None = None,
    message_id: int | None = None,
) -> None:
    """Route to the correct flow handler based on intent."""
    # Store user's message text for voice trigger detection in _send_response
    try:
        mgr = get_conversation_manager()
        session = mgr.get_session(chat_id)
        if session and text and not session.answers.get("original_text"):
            session.answers["original_text"] = text
    except Exception:
        pass

    handlers = {
        TelegramIntent.CLIENT_COMPLAINT: handle_client_complaint,
        TelegramIntent.TECHNICIAN_REPORT: handle_technician_report,
        TelegramIntent.WO_UPDATE: handle_wo_update,
        TelegramIntent.CHECKLIST_REPLY: _handle_checklist_reply,
        TelegramIntent.AD_HOC_FAULT: handle_adhoc_fault,
        TelegramIntent.GHOST_ROOM: handle_ghost_room,
        TelegramIntent.FOCUS_ROOM: handle_focus_room,
        TelegramIntent.STAFF_STATUS: _handle_staff_wo_status,
        TelegramIntent.UNKNOWN: handle_unknown,
    }
    handler = handlers.get(intent, handle_unknown)
    await handler(chat_id, text, callback_data, message_id)


async def _handle_checklist_reply(
    chat_id: str,
    text: str,
    callback_data: str | None = None,
    message_id: int | None = None,
) -> None:
    """Route checklist reply to the active session's flow handler."""
    mgr = get_conversation_manager()
    session = mgr.get_session(chat_id)

    if not session:
        # Session expired
        sender = get_telegram_sender()
        await _send_response(
            chat_id,
            "Your previous session has expired. Let's start fresh.",
            sender,
        )
        await handle_unknown(chat_id, text, callback_data, message_id)
        return

    flow_handlers = {
        "client_complaint": handle_client_complaint,
        "technician_report": handle_technician_report,
        "wo_update": handle_wo_update,
        "ad_hoc_fault": handle_adhoc_fault,
    }
    handler = flow_handlers.get(session.flow, handle_unknown)
    await handler(chat_id, text, callback_data, message_id)


# ===================================================================
# Internal helpers — WO creation & lookup
# ===================================================================


async def _create_complaint_wo(
    session: ConversationSession,
    priority: str,
    category_override: str | None = None,
) -> str | None:
    """Create a work order from a client complaint session and notify technician."""
    try:
        from app.database.repositories.work_order_repository import WorkOrderRepository
        from app.database.supabase_client import get_supabase_client
        from app.services.sentry_integration.work_order_notifier import WorkOrderNotifier

        wo_repo = WorkOrderRepository()
        category = category_override or session.answers.get("category", "general")
        location = session.answers.get("location_text", "Not specified")
        floor = session.answers.get("floor", "")
        original = session.answers.get("original_text", "")
        sub_category = session.answers.get("sub_category", "")

        title = sub_category or f"{category.title()} issue reported"
        description = (
            f"Reported via Telegram conversation.\n"
            f"Original message: {original}\n"
            f"Category: {category}\n"
            f"Location: {location}\n"
            f"Floor: {floor}"
        )

        wo_data = {
            "title": title,
            "description": description,
            "priority": "urgent" if priority == "critical" else priority,
            "status": "scheduled",
            "created_by": f"sentry:telegram:{session.chat_id}",
        }

        created = await wo_repo.create_work_order(wo_data)
        if not created:
            return None

        wo_code = created.get("code")
        wo_uuid = created.get("id")
        equipment_code = created.get("equipment_code", "") or wo_data.get("equipment_code", "")

        # Extract desk number from location for Info button zone lookup
        desk_number = ""
        if not equipment_code:
            import re
            m = re.search(r"(?:desk|Desk)\s*(\d{3})", location)
            if m:
                desk_number = m.group(1)

        # Look up technician by category / specialty for site-002
        tech = None
        try:
            sb = get_supabase_client()
            if sb:
                site_result = sb.table("sites").select("id").eq("code", "site-002").execute()
                if site_result.data:
                    site_id = site_result.data[0]["id"]

                    # Try site_technicians specialty match (if table exists)
                    try:
                        tech_result = (
                            sb.table("site_technicians")
                            .select("specialty, technicians(id, name, email, phone, telegram_id)")
                            .eq("site_id", site_id)
                            .eq("specialty", category)
                            .eq("is_primary", True)
                            .execute()
                        )
                        if tech_result.data:
                            tech = tech_result.data[0].get("technicians", {})

                        # Fallback: general specialty
                        if not tech and category != "general":
                            tech_result = (
                                sb.table("site_technicians")
                                .select("specialty, technicians(id, name, email, phone, telegram_id)")
                                .eq("site_id", site_id)
                                .eq("specialty", "general")
                                .eq("is_primary", True)
                                .execute()
                            )
                            if tech_result.data:
                                tech = tech_result.data[0].get("technicians", {})
                    except Exception:
                        pass  # site_technicians may not exist

                    # Last resort: any active technician with a Telegram ID
                    if not tech:
                        try:
                            tech_result = sb.table("technicians").select(
                                "id, name, email, phone, telegram_id"
                            ).eq("active", True).execute()
                            with_telegram = [t for t in (tech_result.data or []) if t.get("telegram_id")]
                            if with_telegram:
                                tech = with_telegram[0]
                        except Exception:
                            pass
        except Exception as e:
            logger.warning("Complaint WO technician lookup failed: %s", e)

        # Notify technician
        if tech and tech.get("telegram_id"):
            try:
                notifier = WorkOrderNotifier()
                await notifier.notify_technician({
                    "code": wo_code,
                    "work_order_id": str(wo_uuid) if wo_uuid else wo_code,
                    "equipment_code": equipment_code,
                    "equipment_id": equipment_code or f"site-002",
                    "equipment_name": title,
                    "site_id": "site-002",
                    "technician_id": tech.get("telegram_id"),
                    "technician_name": tech.get("name", "Technician"),
                    "service_type": "callout",
                    "criticality": priority.upper(),
                    "problem_description": description,
                    "desk_number": desk_number,
                })
            except Exception as e:
                logger.warning("Complaint WO notification failed: %s", e)

        # Email facilities desk
        await _email_facilities_desk(wo_code, title, category, location, priority, description)

        return wo_code
    except Exception as e:
        logger.error("Failed to create complaint WO: %s", e, exc_info=True)

    return None


async def _create_inspection_wo(
    session: ConversationSession,
    component: str,
    finding: str,
    priority: str,
) -> str | None:
    """Create a work order from a checklist finding."""
    try:
        from app.database.repositories.work_order_repository import WorkOrderRepository

        wo_repo = WorkOrderRepository()
        detail = session.answers.get(f"{component}_detail", "")
        detail_str = f" ({detail})" if detail else ""

        wo_data = {
            "site_id": "site-002",
            "equipment_code": session.equipment_id,
            "title": f"{component.replace('_', ' ').title()}: {finding}{detail_str}",
            "description": (
                f"Found during inspection of {session.equipment_id}.\n"
                f"Component: {component}\n"
                f"Condition: {finding}{detail_str}\n"
                f"Inspector: chat {session.chat_id}"
            ),
            "priority": "urgent" if priority == "critical" else priority,
            "status": "scheduled",
            "created_by": f"sentry:inspection:{session.chat_id}",
        }

        created = await wo_repo.create_work_order(wo_data)
        if created:
            return created.get("code")
    except Exception as e:
        logger.error("Failed to create inspection WO: %s", e, exc_info=True)

    return None


async def _lookup_wo(wo_code: str) -> dict | None:
    """Look up a work order by code."""
    try:
        from app.database.repositories.work_order_repository import WorkOrderRepository

        wo_repo = WorkOrderRepository()
        result = await wo_repo.get_work_order_by_code(wo_code)
        return result
    except Exception as e:
        logger.warning("WO lookup failed for %s: %s", wo_code, e)
        return None


async def _update_wo_status(wo_code: str, new_status: str) -> bool:
    """Update work order status by code (lookup ID first)."""
    try:
        from app.database.repositories.work_order_repository import WorkOrderRepository

        wo_repo = WorkOrderRepository()
        wo = await wo_repo.get_work_order_by_code(wo_code)
        if not wo:
            logger.warning("WO %s not found for status update", wo_code)
            return False

        update_data = {"status": new_status}
        if new_status == "completed":
            update_data["completed_at"] = datetime.utcnow().isoformat()
        await wo_repo.update_work_order(wo["id"], update_data)

        # Notify staff reporter when WO is completed
        if new_status == "completed":
            created_by = wo.get("created_by", "")
            if created_by and "sentry:call_log:" in created_by:
                reporter_telegram_id = created_by.split("sentry:call_log:")[-1].split(":")[0].strip()
                if reporter_telegram_id:
                    _notify_reporter_completed.delay(wo_code, reporter_telegram_id, wo.get("title", "Your report"))

        return True
    except Exception as e:
        logger.warning("WO status update failed for %s: %s", wo_code, e)
        return False


def _notify_reporter_completed(wo_code: str, reporter_telegram_id: str, title: str) -> None:
    """Send Telegram message to staff reporter when their WO is resolved."""
    try:
        from app.services.notification_providers import TelegramProvider

        provider = TelegramProvider()
        if not provider.is_enabled():
            return

        msg = (
            f"✅ Your report has been resolved.\n"
            f"Ref: {wo_code}\n"
            f"Issue: {title}\n\n"
            f"If you need any follow-up, message me again."
        )
        # Fire-and-forget — TelegramProvider.send is sync but we don't need to await
        provider.send(reporter_telegram_id, "Work Order Resolved", msg)
    except Exception as e:
        logger.warning("Failed to notify reporter %s for WO %s: %s", reporter_telegram_id, wo_code, e)


async def _handle_staff_wo_status(
    chat_id: str,
    text: str,
    callback_data: str | None = None,
    message_id: int | None = None,
) -> None:
    """Handle /status_WO-{code} — staff follow-up on their own reported WO."""
    import httpx
    from app.services.telegram_message_sender import get_telegram_sender

    sender = get_telegram_sender()

    # Extract WO code from message (e.g., "/status_WO-2026-0004" -> "WO-2026-0004")
    m = re.match(r"^/status_WO[-_]\s*([A-Za-z0-9][\w-]*)\s*$", text.strip(), re.DOTALL)
    if not m:
        await _send_response(chat_id, "Usage: /status_WO-{code} (e.g. /status_WO-2026-0004)", sender)
        return

    raw_code = m.group(1).strip()
    # Normalize: "2026-0004" -> "WO-2026-0004", "WO-2026-0004" -> "WO-2026-0004"
    if raw_code.startswith("WO-"):
        wo_code = raw_code
    else:
        wo_code = f"WO-{raw_code}"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{settings.api_base_url}/api/sentry/wo-status",
                params={"code": wo_code},
                headers={
                    "X-Sentry-API-Key": settings.sentry_bot_api_key or "",
                    "X-Sentry-Secret": settings.sentry_webhook_secret or "",
                },
            )
        if resp.status_code == 200:
            data = resp.json()
        else:
            data = {}
    except Exception:
        data = {}

    if not data.get("found"):
        await _send_response(
            chat_id,
            f"Couldn't find work order `{wo_code}`. Please check the reference number and try again.",
            sender,
        )
        return

    status = data.get("status", "unknown")
    priority = data.get("priority", "")
    category = data.get("category", "")
    title = data.get("title", "")
    notes = data.get("notes", "")
    assigned_to = data.get("assigned_to", "")
    created_at = data.get("created_at", "")
    updated_at = data.get("updated_at", "")
    completed_at = data.get("completed_at", "")

    status_emoji = {"completed": "✅", "in_progress": "🔄", "scheduled": "📋", "blocked": "⛔"}.get(
        status, "📋"
    )

    lines = [
        f"{status_emoji} Work Order {wo_code}",
        "",
        f"**Status:** {status.title()}",
    ]
    if priority:
        lines.append(f"**Priority:** {priority.title()}")
    if category:
        lines.append(f"**Category:** {category}")
    if title:
        lines.append(f"**Issue:** {title}")
    if assigned_to:
        lines.append(f"**Assigned to:** {assigned_to}")
    if created_at:
        lines.append(f"**Created:** {created_at[:16] if len(created_at) > 16 else created_at}")
    if updated_at:
        lines.append(f"**Updated:** {updated_at[:16] if len(updated_at) > 16 else updated_at}")
    if completed_at:
        lines.append(f"**Completed:** {completed_at[:16] if len(completed_at) > 16 else completed_at}")
    if notes:
        lines.append(f"**Notes:** {notes}")

    await _send_response(chat_id, "\n".join(lines), sender)


async def _notify_manager_of_complaint_wo(
    wo_code: str,
    title: str,
    category: str,
    location: str,
    priority: str,
    wo_uuid: str | None,
) -> None:
    """Send Telegram notification to FM/manager when a complaint WO is created.

    Manager is the FM bot (@bederf_bot) — sent directly via Telegram Bot API,
    not through Sentry CLI (which routes through technician account).
    """
    from app.config.settings import settings
    from app.services.notification_providers import TelegramProvider

    fm_chat_id = str(getattr(settings, "sentinel_fm_chat_id", "") or "").strip()
    if not fm_chat_id:
        fm_chat_id = str(getattr(settings, "telegram_alert_chat_id", "") or "").strip()
    if not fm_chat_id:
        logger.warning("[COMPLAINT-WO] No FM chat ID configured — skipping manager notification")
        return

    pri_label = priority.upper()
    msg = (
        f"📋 New work order: <b>{wo_code}</b>\n"
        f"Issue: {title}\n"
        f"Location: {location}\n"
        f"Category: {category}\n"
        f"Priority: {pri_label}\n"
        f"Source: Staff complaint via Telegram"
    )

    provider = TelegramProvider()
    if not provider.is_enabled():
        logger.warning("[COMPLAINT-WO] Telegram provider not enabled — skipping FM notification")
        return

    try:
        result = await provider.send(recipient=fm_chat_id, title=f"Work Order {wo_code}", body=msg)
        if result.success:
            logger.info("[COMPLAINT-WO] FM notification sent for %s", wo_code)
        else:
            logger.warning("[COMPLAINT-WO] FM notification failed for %s: %s", wo_code, result.error_message)
    except Exception as e:
        logger.warning("[COMPLAINT-WO] FM notification error for %s: %s", wo_code, e)



async def _email_facilities_desk(
    wo_code: str,
    title: str,
    category: str,
    location: str,
    priority: str,
    description: str,
) -> None:
    """Send email to facilities desk when a complaint work order is created.

    Uses the native SMTP notification service (workorder@sentinel-ai.co.za).
    """
    facilities_email = "facilities@sentinel-ai.co.za"
    subject = f"New Work Order: {wo_code} — {title}"
    body = (
        f"New work order logged via Sentinel Staff Bot.\n\n"
        f"WO Reference: {wo_code}\n"
        f"Issue: {title}\n"
        f"Category: {category}\n"
        f"Location: {location}\n"
        f"Priority: {priority.upper()}\n"
        f"Status: OPEN (pending technician assignment)\n\n"
        f"Description:\n{description}\n\n"
        f"---\n"
        f"SENTINEL BMS Intelligence\n"
        f"Report: https://bms.sentinel-ai.co.za/work-orders/{wo_code}"
    )

    try:
        from app.services.email_reply_service import get_email_reply_service

        email_svc = get_email_reply_service()
        if not email_svc.is_configured():
            logger.warning("[COMPLAINT-WO] Email service not configured — skipping facilities email")
            return

        # Reuse the same SMTP path as WO email notifications
        from app.services.sentry_integration.work_order_notifier import WorkOrderNotifier
        notifier = WorkOrderNotifier()
        sent = await notifier._send_email_via_native_smtp(
            to_email=facilities_email,
            subject=subject,
            body=body,
        )
        if sent:
            logger.info("[COMPLAINT-WO] Facilities email sent for %s", wo_code)
        else:
            logger.warning("[COMPLAINT-WO] Facilities email returned False for %s", wo_code)
    except Exception as e:
        logger.warning("[COMPLAINT-WO] Facilities email failed for %s: %s", wo_code, e)
