"""Render technician-facing work-order detail briefs."""

from __future__ import annotations

from typing import Any


def _clean(value: Any, default: str = "N/A") -> str:
    text = str(value).strip() if value is not None else ""
    return text or default


def _format_assigned(work_order: dict[str, Any]) -> str:
    assigned_to = _clean(work_order.get("assigned_to"), "unassigned")
    assigned_team = str(work_order.get("assigned_team") or "").strip()
    return f"{assigned_to} ({assigned_team})" if assigned_team else assigned_to


def render_telegram_checklist(
    template: dict[str, Any] | None,
    oem_contexts: dict[str, str] | None = None,
) -> str:
    if not template:
        return ""

    name = _clean(template.get("template_name"), "Inspection checklist")
    duration = template.get("estimated_duration_minutes")
    lines = [f"📋 {name}", f"⏱ Estimated: {duration} min" if duration else "⏱ Estimated: N/A min", ""]
    current_category = None

    for item in template.get("checklist_items", []):
        category = _clean(item.get("category"), "General")
        if category != current_category:
            current_category = category
            lines.append(f"▸ {category}")

        item_id = _clean(item.get("item_id"), "")
        question = _clean(item.get("question") or item.get("description"), "")
        if not question:
            continue

        item_type = _clean(item.get("item_type"), "")
        options = item.get("options") or []
        oem_spec = (oem_contexts or {}).get(item_id, "")
        spec_hint = f" | OEM: {oem_spec[:150]}..." if oem_spec else ""
        q_with_spec = f"{question}{spec_hint}"

        if item_type == "measurement":
            unit = _clean(item.get("unit"), "")
            tmin = item.get("tolerance_min")
            tmax = item.get("tolerance_max")
            tolerance = f" ({tmin}-{tmax} {unit})" if tmin is not None and tmax is not None else ""
            lines.append(f"  ☐ {q_with_spec}{tolerance}")
        elif item_type == "visual_inspection":
            lines.append(f"  📷 {q_with_spec}")
        elif options:
            option_text = " / ".join(_clean(option.get("label"), "") for option in options if option.get("label"))
            suffix = f" ({option_text})" if option_text else ""
            lines.append(f"  ☐ {q_with_spec}{suffix}")
        else:
            lines.append(f"  ☐ {q_with_spec}")

    return "\n".join(lines)


def render_service_feedback_checklist(template: dict[str, Any] | None) -> str:
    """Render a technician closeout feedback template as plain text.

    Feedback templates define the evidence the technician needs to provide
    after the work order, such as a service sheet, audio recording, photo,
    or observation.
    """
    if not template:
        return ""

    name = _clean(template.get("template_name"), "Service closeout")
    required_items = list(template.get("required_items") or [])
    optional_items = list(template.get("optional_items") or [])
    prompts = template.get("prompts") or {}

    lines = [f"📋 {name}", ""]

    if required_items:
        lines.append("Required feedback:")
        for item in required_items:
            prompt = _clean(prompts.get(item), item.replace("_", " ").title())
            lines.append(f"  ☐ {prompt}")

    if optional_items:
        if required_items:
            lines.append("")
        lines.append("Optional feedback:")
        for item in optional_items:
            prompt = _clean(prompts.get(item), item.replace("_", " ").title())
            lines.append(f"  ◇ {prompt}")

    return "\n".join(lines)


def build_work_order_info_text(
    work_order: dict[str, Any],
    equipment: dict[str, Any] | None = None,
    service_record: dict[str, Any] | None = None,
    checklist_template: dict[str, Any] | None = None,
) -> str:
    """Build a technician-facing detail brief for a work order."""
    equipment = equipment or {}
    service_record = service_record or {}

    wo_code = _clean(work_order.get("code"), "work order")
    work_order_type = _clean(work_order.get("work_order_type") or work_order.get("type"), "unknown")
    closeout_tier = _clean(work_order.get("closeout_tier"), "unknown")
    status = _clean(work_order.get("status"), "unknown")
    priority = _clean(work_order.get("priority"), "medium").upper()
    title = _clean(work_order.get("title"), "")
    description = _clean(work_order.get("description"), "")
    work_type = _clean(work_order.get("work_type"), "")
    assigned = _format_assigned(work_order)

    equipment_code = _clean(equipment.get("code") or work_order.get("equipment_code") or work_order.get("equipment_id"))
    equipment_name = _clean(equipment.get("name") or equipment.get("description") or equipment_code)
    equipment_type = _clean(equipment.get("type") or work_order.get("equipment_type"), "unknown")

    lines = [
        f"Work Order Info: {wo_code}",
        f"Status: {status}",
        f"Type: {work_order_type}",
        f"Closeout tier: {closeout_tier}",
        f"Priority: {priority}",
        f"Assigned: {assigned}",
        f"Equipment: {equipment_name}",
        f"Equipment Code: {equipment_code}",
        f"Equipment Type: {equipment_type}",
    ]

    if work_type:
        lines.append(f"Work Type: {work_type}")
    if title:
        lines.append(f"Title: {title}")
    if description:
        lines.append(f"Description: {description}")

    sr_code = _clean(service_record.get("code"), "")
    if sr_code:
        lines.extend(
            [
                "",
                f"Service Record: {sr_code}",
                f"Service Record Status: {_clean(service_record.get('status'), 'unknown')}",
                f"Service Record Type: {_clean(service_record.get('service_type'), 'unknown')}",
            ]
        )

    checklist_text = ""
    if checklist_template:
        if checklist_template.get("required_items") or checklist_template.get("optional_items"):
            checklist_text = render_service_feedback_checklist(checklist_template)
        else:
            checklist_text = render_telegram_checklist(checklist_template)
    if checklist_text:
        lines.extend(["", "What to do:", checklist_text])
    else:
        lines.extend(
            [
                "",
                "What to do:",
                "1. Inspect the equipment and record the live readings.",
                "2. Capture photos or notes for anything abnormal.",
                "3. Complete the closeout checklist before marking the work order done.",
            ]
        )

    closeout_lines = [
        "",
        "Closeout expected:",
        "Record the readings, findings, and uploaded evidence before closing the WO.",
    ]
    if sr_code:
        closeout_lines.insert(2, f"Link the work against service record {sr_code} and keep the record current.")
    lines.extend(closeout_lines)

    lines.extend(
        [
            "",
            "Telegram commands:",
            f"/info-{equipment_code} - Equipment summary",
            f"/note-{equipment_code} - Add a note",
            f"/done-{wo_code} - Start closeout",
        ]
    )

    return "\n".join(lines)
