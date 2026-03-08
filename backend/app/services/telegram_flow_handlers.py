"""Telegram Conversation Flow Handlers.

All conversation flows: client complaint, technician checklist,
WO update, ad-hoc fault, and unknown/orientation.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

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
)

logger = logging.getLogger(__name__)

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
                await sender.send_text(
                    chat_id,
                    f"Got it -- <b>{classification['sub_category']}</b>.\n\nWhich floor or area is this on?",
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
        await sender.send_text(
            chat_id,
            "Hi! I've picked up your message. What best describes the issue?",
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
            await sender.send_text(
                chat_id,
                "I didn't catch that. Please tap a button or type the category (e.g. 'plumbing', 'electrical').",
            )
            return

        session.answers["category"] = category
        session.current_step = 1
        mgr.update_session(session)
        await sender.send_text(chat_id, "Which floor or area is this on?")
        return

    # Step 2: Location received
    if session.current_step == 1:
        if not text:
            await sender.send_text(chat_id, "Please type the floor or area (e.g. 'Level 2', 'kitchen').")
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
        await sender.send_text(chat_id, "How long has this been happening?", keyboard=kb)
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
            await sender.send_text(chat_id, "Please tap a button or describe how long this has been going on.")
            return

        session.answers["duration"] = duration
        session.current_step = 3
        mgr.update_session(session)

        kb = InlineKeyboard(
            rows=[
                [InlineButton("Skip", "complaint:photo:skip")],
            ]
        )
        await sender.send_text(chat_id, "Can you send a photo? (Optional)", keyboard=kb)
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
            await sender.send_text(
                chat_id,
                f"Work order <b>{wo_code}</b> created.\n\n"
                f"Category: {session.answers.get('category', 'general')}\n"
                f"Location: {session.answers.get('location_text', 'Not specified')}\n"
                f"Priority: {priority}\n\n"
                "A technician will be assigned shortly.",
            )
        else:
            await sender.send_text(
                chat_id,
                "Your report has been logged. A work order will be created shortly.\n\n"
                f"Category: {session.answers.get('category', 'general')}\n"
                f"Location: {session.answers.get('location_text', 'Not specified')}",
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
            await sender.send_text(
                chat_id,
                "Which equipment are you inspecting? Please provide the equipment code (e.g. S002-AHU-L2-001).",
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
            await sender.send_text(chat_id, "Please type the equipment code.")
            return

        m = _EQUIPMENT_ID_RE.search(text)
        if not m:
            await sender.send_text(
                chat_id,
                "I couldn't find an equipment code in that. Please use the format S002-AHU-L2-001.",
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
        await sender.send_text(chat_id, followup["question"], keyboard=kb)
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
    await sender.send_text(chat_id, f"{header}{q['question']}", keyboard=kb)


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

    await sender.send_text(chat_id, "\n".join(lines))


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

            await sender.send_text(
                chat_id,
                f"<b>{session.wo_id}</b> updated to: {status_label}",
            )
            mgr.end_session(chat_id)
        return

    # Extract WO number
    wo_match = _WO_RE.search(text or "")
    if not wo_match:
        await sender.send_text(
            chat_id,
            "I couldn't find a work order number. Please include the WO reference (e.g. WO-2026-0045).",
        )
        return

    wo_code = wo_match.group(1).upper()
    wo_data = await _lookup_wo(wo_code)

    if not wo_data:
        await sender.send_text(chat_id, f"Work order <b>{wo_code}</b> not found.")
        return

    # Check if text contains "done"/"completed"
    text_lower = (text or "").lower()
    has_done = any(kw in text_lower for kw in ("done", "completed", "finished", "complete"))

    if has_done:
        # Quick complete
        await _update_wo_status(wo_code, "completed")
        await sender.send_text(chat_id, f"<b>{wo_code}</b> marked as completed.")
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
    await sender.send_text(chat_id, summary, keyboard=kb)


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
        await sender.send_text(chat_id, "Where is this? (floor, area, or desk number)")
        return

    # Step 1: Location received -> create WO
    if not text:
        await sender.send_text(chat_id, "Please type the location.")
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
        await sender.send_text(
            chat_id,
            f"Logged! Work order <b>{wo_code}</b> created.\nLocation: {text}\n\nSomeone will look into it.",
        )
    else:
        await sender.send_text(
            chat_id,
            f"Logged your report for: {text}\nA work order will be created shortly.",
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
            [InlineButton("Start inspection", "menu:start:inspection")],
            [InlineButton("Check work order", "menu:start:wo_check")],
        ]
    )
    await sender.send_text(
        chat_id,
        "Hi! How can I help?\n\nTap an option below or describe your issue.",
        keyboard=kb,
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
    handlers = {
        TelegramIntent.CLIENT_COMPLAINT: handle_client_complaint,
        TelegramIntent.TECHNICIAN_REPORT: handle_technician_report,
        TelegramIntent.WO_UPDATE: handle_wo_update,
        TelegramIntent.CHECKLIST_REPLY: _handle_checklist_reply,
        TelegramIntent.AD_HOC_FAULT: handle_adhoc_fault,
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
        await sender.send_text(
            chat_id,
            "Your previous session has expired. Let's start fresh.",
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
    """Create a work order from a client complaint session."""
    try:
        from app.database.repositories.work_order_repository import WorkOrderRepository

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
            "site_id": "site-002",
            "title": title,
            "description": description,
            "priority": "urgent" if priority == "critical" else priority,
            "status": "scheduled",
            "created_by": f"sentry:telegram:{session.chat_id}",
        }

        created = await wo_repo.create_work_order(wo_data)
        if created:
            return created.get("code")
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
        return True
    except Exception as e:
        logger.warning("WO status update failed for %s: %s", wo_code, e)
        return False
