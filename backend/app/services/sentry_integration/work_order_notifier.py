"""Work order notification service for Sentry Telegram bot.

Handles sending work order notifications to technicians via Sentry,
managing the conversation flow for data collection, and storing
responses in service records.
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any

from app.database.repositories.notification_repository import (
    SYSTEM_NOTIFIER_TECHNICIAN_ID,
    NotificationRepository,
)
from app.database.repositories.service_record_repository import ServiceRecordRepository
from app.database.repositories.work_order_repository import get_work_order_repository
from app.models.notification import ChannelType, NotificationDeliveryLog, NotificationStatus
from app.models.service_record import ServiceStatus
from app.services.ml_template_service import MLTemplateService
from app.services.popia_consent_guard import evaluate_ingress_processing_consent

logger = logging.getLogger(__name__)

# Placeholder equipment for call-log entries that don't reference real equipment.
_CALL_LOG_PLACEHOLDER_EQUIPMENT_ID = "00000000-0000-0000-0000-000000000001"


class WorkOrderNotifier:
    """Service for notifying technicians about work orders via Sentry."""

    def __init__(self):
        self.sentry_api_url = "http://localhost:18789"  # Sentry bot API
        self.bms_api_url = "http://localhost:9095"  # SENTINEL API
        self.repository = ServiceRecordRepository()
        self.template_service = MLTemplateService()
        self._notification_repo = NotificationRepository()

    @staticmethod
    def _normalize_text(value: Any) -> str:
        """Normalize text fields and convert escaped newlines for email readability."""
        if value is None:
            return ""
        text = str(value).strip()
        return text.replace("\\n", "\n")

    @staticmethod
    def _resolve_equipment(equipment_id: str, _equipment_name: str = "") -> dict[str, Any] | None:
        """Look up equipment by UUID or code for email body enrichment."""
        if not equipment_id:
            return None
        try:
            import re

            from app.database.supabase_client import get_supabase_client

            sb = get_supabase_client()
            is_uuid = bool(
                re.match(
                    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                    equipment_id,
                    re.IGNORECASE,
                )
            )
            field = "id" if is_uuid else "code"
            resp = sb.table("equipment").select("id,code,name,type").eq(field, equipment_id).execute()
            if resp.data:
                return resp.data[0]
        except Exception:
            pass
        return None

    @staticmethod
    def _resolve_site(site_id: str) -> dict[str, Any] | None:
        """Look up site by UUID or code for email body enrichment."""
        if not site_id:
            return None
        try:
            import re

            from app.database.supabase_client import get_supabase_client

            sb = get_supabase_client()
            is_uuid = bool(
                re.match(
                    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                    site_id,
                    re.IGNORECASE,
                )
            )
            field = "id" if is_uuid else "code"
            resp = sb.table("sites").select("id,code,name").eq(field, site_id).execute()
            if resp.data:
                return resp.data[0]
        except Exception:
            pass
        return None

    @staticmethod
    def _get_inspection_checklist(equipment_type: str) -> str:
        """Get the inspection checklist for an equipment type as plain text for email.

        Returns formatted checklist string, or empty string if no checklist exists.
        """
        if not equipment_type or equipment_type == "n/a":
            return ""
        try:
            from app.services.checklist_service import get_checklist_service

            svc = get_checklist_service()
            template = svc.get_template_for_inspection(equipment_type.lower(), "routine")
            if not template:
                return ""

            items = template.get("checklist_items", [])
            name = template.get("template_name", f"{equipment_type.upper()} Inspection")
            duration = template.get("estimated_duration_minutes", 30)

            lines = [f"{name} (est. {duration} min)", ""]
            current_category = None

            for item in items:
                cat = item.get("category", "General")
                if cat != current_category:
                    current_category = cat
                    lines.append(f"  {cat}:")

                q = item.get("question") or item.get("description") or ""
                if not q:
                    continue
                item_type = item.get("item_type", "")
                options = item.get("options", [])
                method = item.get("method", "")
                acceptance = item.get("acceptance_criteria", "")

                if item_type == "measurement":
                    unit = item.get("unit", "")
                    tmin = item.get("tolerance_min")
                    tmax = item.get("tolerance_max")
                    tol = f" (acceptable: {tmin}-{tmax} {unit})" if tmin is not None else ""
                    lines.append(f"    [ ] {q}{tol}")
                elif options:
                    opts_str = " / ".join(o.get("label", "") for o in options)
                    lines.append(f"    [ ] {q} ({opts_str})")
                elif acceptance:
                    lines.append(f"    [ ] {q}")
                    lines.append(f"         Criteria: {acceptance}")
                else:
                    lines.append(f"    [ ] {q}")

                if method and method != "visual_inspection":
                    lines.append(f"         Method: {method.replace('_', ' ')}")

                photos = item.get("photos_required") or ("photo" in (item.get("recording_required") or []))
                if photos:
                    lines.append("         ^ Photo required")

            return "\n".join(lines)
        except Exception as e:
            logger.warning(f"Could not load checklist for {equipment_type}: {e}")
            return ""

    async def _load_work_order_context(self, work_order_id: str) -> dict[str, Any]:
        """Load work order context from repository using ID or code."""
        if not work_order_id:
            return {}

        try:
            work_order_repo = get_work_order_repository()
            # Most flows send UUID id here.
            work_order = await work_order_repo.get_work_order(work_order_id)
            if work_order:
                return work_order

            # Fallback: some flows may pass code e.g. WO-2026-0042.
            work_order = await work_order_repo.get_work_order_by_code(work_order_id)
            return work_order or {}
        except Exception as e:
            logger.warning(f"Failed to load work order context for {work_order_id}: {e}")
            return {}

    def _build_email_subject(self, work_order_data: dict[str, Any], work_order: dict[str, Any]) -> str:
        """Build a descriptive subject line with WO reference and priority."""
        equipment_name = work_order_data.get("equipment_name") or work_order.get("title") or "Equipment"
        criticality = str(work_order_data.get("criticality") or work_order.get("priority") or "MEDIUM").upper()
        wo_ref = (
            work_order.get("code")
            or work_order_data.get("code")
            or work_order_data.get("work_order_code")
            or work_order_data.get("work_order_id")
            or "N/A"
        )
        return f"[{criticality}] Work Order {wo_ref} - {equipment_name}"

    def _build_email_body(
        self,
        work_order_data: dict[str, Any],
        service_record: dict[str, Any],
        work_order: dict[str, Any],
    ) -> str:
        """Build full-detail email body for technician execution."""
        equipment_obj = work_order.get("equipment") or {}
        site_obj = work_order.get("sites") or {}
        diagnostic_context = work_order_data.get("diagnostic_context") or service_record.get("diagnostic_context") or {}

        # Resolve equipment/site from Supabase if not joined in work_order
        if not equipment_obj.get("code"):
            equipment_obj = (
                self._resolve_equipment(
                    work_order_data.get("equipment_id", ""),
                    work_order_data.get("equipment_name", ""),
                )
                or equipment_obj
            )
        if not site_obj.get("name"):
            site_obj = (
                self._resolve_site(
                    work_order_data.get("site_id", ""),
                )
                or site_obj
            )

        wo_ref = (
            work_order.get("code")
            or work_order_data.get("code")
            or work_order_data.get("work_order_code")
            or work_order_data.get("work_order_id")
            or "N/A"
        )
        equipment_name = work_order_data.get("equipment_name") or equipment_obj.get("name") or "Unknown Equipment"
        equipment_code = equipment_obj.get("code") or work_order_data.get("equipment_code") or "N/A"
        equipment_type = (equipment_obj.get("type") or work_order_data.get("equipment_type") or "N/A").upper()
        site_name = site_obj.get("name") or work_order_data.get("site_name") or "N/A"
        site_code = site_obj.get("code") or work_order_data.get("site_code") or "N/A"
        priority = str(work_order_data.get("criticality") or work_order.get("priority") or "MEDIUM").upper()
        service_type = str(work_order_data.get("service_type") or "callout").lower()
        technician_name = work_order_data.get("technician_name", "Technician")
        service_record_code = service_record.get("code", "")

        _title = self._normalize_text(work_order.get("title") or work_order_data.get("title"))
        description = self._normalize_text(
            work_order.get("description")
            or work_order_data.get("problem_description")
            or work_order_data.get("description")
            or "No description provided."
        )

        diagnostics_text = ""
        if isinstance(diagnostic_context, dict) and diagnostic_context:
            diagnostics_text = json.dumps(diagnostic_context, indent=2, ensure_ascii=True)
        elif diagnostic_context:
            diagnostics_text = self._normalize_text(diagnostic_context)

        instructions = self._normalize_text(
            work_order_data.get("instructions") or work_order_data.get("inspection_instructions")
        )

        lines = [
            f"Hi {technician_name},",
            "",
            "A new work order has been assigned.",
            "",
            "WORK ORDER REFERENCES",
            f"- Work Order: {wo_ref}",
            f"- Service Record: {service_record_code}",
            f"- Priority: {priority}",
            f"- Service Type: {service_type}",
            "",
            "LOCATION",
            f"- Zone: {work_order_data.get('zone_id', 'N/A')}",
            f"- Desk: {work_order_data.get('desk_id', 'N/A')}",
            "",
            "EQUIPMENT & SITE",
            f"- Site: {site_name} ({site_code})",
            f"- Equipment: {equipment_name}",
            f"- Equipment Code: {equipment_code}",
            f"- Equipment Type: {equipment_type}",
        ]

        original_msg = self._normalize_text(work_order.get("notes") or work_order_data.get("original_message") or "")

        if _title:
            lines.extend(["", "ISSUE TITLE", _title])

        lines.extend(["", "ISSUE DESCRIPTION", description])

        if original_msg:
            lines.extend(["", "REPORTER'S DESCRIPTION", original_msg])

        if diagnostics_text:
            lines.extend(
                [
                    "",
                    "DIAGNOSTIC CONTEXT",
                    diagnostics_text,
                ]
            )

        # Load equipment-specific inspection checklist
        checklist_text = self._get_inspection_checklist(equipment_type.lower())

        if checklist_text:
            lines.extend(["", "INSPECTION CHECKLIST", checklist_text])
        elif instructions:
            lines.extend(["", "FIELD INSTRUCTIONS", instructions])
        else:
            lines.extend(
                [
                    "",
                    "FIELD INSTRUCTIONS",
                    "1. Verify site safety controls before touching equipment.",
                    "2. Inspect the faulted subsystem and capture photos/readings.",
                    "3. Run diagnostics and record measured values.",
                    "4. Identify likely root cause and required corrective action.",
                ]
            )

        # Telegram equipment code for commands (dashes → underscores)
        tg_code = equipment_code.replace("-", "_") if equipment_code != "N/A" else ""
        tg_commands = ""
        if tg_code:
            tg_commands = (
                f"\nTELEGRAM COMMANDS\n"
                f"  /info-{tg_code} — Equipment status & readings\n"
                f"  /note-{tg_code} — Add a note during inspection\n"
                f"  done #{wo_ref} — Submit inspection findings"
            )

        lines.extend(
            [
                "",
                "HOW TO REPORT",
                "When you have completed the inspection, open Telegram and type:",
                f"  done #{wo_ref}",
                "",
                "Sentry will guide you through each checklist item one at a time.",
                "Your answers are saved to the service record automatically.",
                tg_commands,
                "",
                "---",
                f"{site_name} · Facilities Management",
            ]
        )

        return "\n".join(lines)

    def _build_email_body_html(
        self,
        work_order_data: dict[str, Any],
        service_record: dict[str, Any],
        work_order: dict[str, Any],
    ) -> str:
        """Build Sentinel-branded HTML email body for technician execution."""
        equipment_obj = work_order.get("equipment") or {}
        site_obj = work_order.get("sites") or {}
        diagnostic_context = work_order_data.get("diagnostic_context") or service_record.get("diagnostic_context") or {}

        if not equipment_obj.get("code"):
            equipment_obj = (
                self._resolve_equipment(
                    work_order_data.get("equipment_id", ""),
                    work_order_data.get("equipment_name", ""),
                )
                or equipment_obj
            )
        if not site_obj.get("name"):
            site_obj = (
                self._resolve_site(
                    work_order_data.get("site_id", ""),
                )
                or site_obj
            )

        wo_ref = (
            work_order.get("code")
            or work_order_data.get("code")
            or work_order_data.get("work_order_code")
            or work_order_data.get("work_order_id")
            or "N/A"
        )
        equipment_name = work_order_data.get("equipment_name") or equipment_obj.get("name") or "Unknown Equipment"
        equipment_code = equipment_obj.get("code") or work_order_data.get("equipment_code") or "N/A"
        equipment_type = (equipment_obj.get("type") or work_order_data.get("equipment_type") or "N/A").upper()
        site_name = site_obj.get("name") or work_order_data.get("site_name") or "N/A"
        site_code = site_obj.get("code") or work_order_data.get("site_code") or "N/A"
        priority = str(work_order_data.get("criticality") or work_order.get("priority") or "MEDIUM").upper()
        service_type = str(work_order_data.get("service_type") or "callout").lower()
        technician_name = work_order_data.get("technician_name", "Technician")
        service_record_code = service_record.get("code", "")

        _title = self._normalize_text(work_order.get("title") or work_order_data.get("title"))
        description = self._normalize_text(
            work_order.get("description")
            or work_order_data.get("problem_description")
            or work_order_data.get("description")
            or "No description provided."
        )

        diagnostics_text = ""
        if isinstance(diagnostic_context, dict) and diagnostic_context:
            diagnostics_text = json.dumps(diagnostic_context, indent=2, ensure_ascii=True)
        elif diagnostic_context:
            diagnostics_text = self._normalize_text(diagnostic_context)

        instructions = self._normalize_text(
            work_order_data.get("instructions") or work_order_data.get("inspection_instructions")
        )

        # Priority color mapping
        priority_colors = {
            "CRITICAL": "#ea4335",
            "HIGH": "#f57c00",
            "MEDIUM": "#1a73e8",
            "LOW": "#188038",
        }
        priority_color = priority_colors.get(priority, "#1a73e8")

        # Inspection checklist - build HTML list
        checklist_raw = self._get_inspection_checklist(equipment_type.lower())
        if checklist_raw:
            checklist_items = [f"<li>{line.strip()}</li>" for line in checklist_raw.split("\n") if line.strip()]
            checklist_html = f"<ul>{''.join(checklist_items)}</ul>"
        elif instructions:
            instruction_items = [f"<li>{line.strip()}</li>" for line in instructions.split("\n") if line.strip()]
            checklist_html = f"<ul>{''.join(instruction_items)}</ul>"
        else:
            checklist_html = (
                "<ul>"
                "<li>Verify site safety controls before touching equipment.</li>"
                "<li>Inspect the faulted subsystem and capture photos/readings.</li>"
                "<li>Run diagnostics and record measured values.</li>"
                "<li>Identify likely root cause and required corrective action.</li>"
                "</ul>"
            )

        tg_code = equipment_code.replace("-", "_") if equipment_code != "N/A" else ""

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Work Order {wo_ref}</title>
<style>
  body {{ font-family: Arial, sans-serif; background-color: #f8f9fa; margin: 0; padding: 20px; }}
  .container {{ max-width: 600px; margin: 0 auto; background: #ffffff;
    border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.12); }}
  .header {{ background: linear-gradient(135deg, #1a73e8 0%, #0d47a1 100%);
    color: white; padding: 24px 32px; }}
  .header h1 {{ margin: 0 0 4px 0; font-size: 20px; font-weight: 600;
    letter-spacing: 0.5px; }}
  .header p {{ margin: 0; opacity: 0.85; font-size: 13px; }}
  .badge-row {{ padding: 20px 32px 0 32px; display: flex; gap: 12px;
    align-items: center; flex-wrap: wrap; }}
  .priority-badge {{ display: inline-block; padding: 4px 12px; border-radius: 16px;
    color: white; font-size: 12px; font-weight: 600;
    background-color: {priority_color}; }}
  .wo-ref {{ background: #e8f0fe; color: #1a73e8; padding: 4px 12px;
    border-radius: 16px; font-size: 12px; font-weight: 600; }}
  .content {{ padding: 24px 32px; }}
  .info-table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
  .info-table td {{ padding: 8px 0; vertical-align: top; font-size: 14px; }}
  .info-table td:first-child {{ color: #5f6368; width: 40%; }}
  .info-table td:last-child {{ color: #202124; font-weight: 500; }}
  h2 {{ color: #1a73e8; font-size: 14px; font-weight: 600; margin: 0 0 12px 0;
    text-transform: uppercase; letter-spacing: 0.5px; }}
  .description {{ background: #f8f9fa; border-left: 4px solid #1a73e8;
    padding: 12px 16px; border-radius: 0 4px 4px 0; font-size: 14px;
    line-height: 1.6; color: #202124; margin-bottom: 20px;
    white-space: pre-wrap; }}
  .checklist {{ background: #f8f9fa; border-radius: 8px; padding: 16px 20px; margin-bottom: 20px; }}
  .checklist ul {{ margin: 0; padding-left: 20px; }}
  .checklist li {{ font-size: 14px; line-height: 1.8; color: #202124; }}
  .telegram-section {{ background: #e8f0fe; border-radius: 8px; padding: 16px 20px; margin-bottom: 20px; }}
  .telegram-section p {{ margin: 0 0 8px 0; font-size: 14px; color: #202124; }}
  .telegram-section code {{ background: #1a73e8; color: white; padding: 2px 8px; border-radius: 4px; font-size: 13px; }}
  .footer {{ background: #f8f9fa; border-top: 1px solid #e0e0e0; padding: 16px 32px; text-align: center; }}
  .footer p {{ margin: 0; font-size: 12px; color: #5f6368; }}
  .footer .brand {{ color: #1a73e8; font-weight: 600; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>SENTINEL BMS Intelligence</h1>
    <p>New Work Order Assigned</p>
  </div>
  <div class="badge-row">
    <span class="priority-badge">{priority}</span>
    <span class="wo-ref">{wo_ref}</span>
    <span class="wo-ref">{service_record_code}</span>
  </div>
  <div class="content">
    <p>Hi {technician_name},</p>
    <p>A new work order has been assigned to you. Please review the details below and take action.</p>

    <table class="info-table">
      <tr><td>Zone</td><td>{work_order_data.get("zone_id", "N/A")}</td></tr>
      <tr><td>Desk</td><td>{work_order_data.get("desk_id", "N/A")}</td></tr>
      <tr><td>Site</td><td>{site_name} ({site_code})</td></tr>
      <tr><td>Equipment</td><td>{equipment_name}</td></tr>
      <tr><td>Equipment Code</td><td>{equipment_code}</td></tr>
      <tr><td>Equipment Type</td><td>{equipment_type}</td></tr>
      <tr><td>Service Type</td><td>{service_type.capitalize()}</td></tr>
    </table>

    <h2>Issue Description</h2>
    <div class="description">{description}</div>"""

        if diagnostics_text:
            html += f"""
    <h2>Diagnostic Context</h2>
    <div class="description" style="font-family: monospace; font-size: 12px; white-space: pre-wrap;">{diagnostics_text}</div>"""

        html += f"""
    <h2>Inspection Checklist</h2>
    <div class="checklist">{checklist_html}</div>

    <div class="telegram-section">
      <p><strong>How to Report Completion</strong></p>"""

        if tg_code:
            html += f"""      <p>Open Telegram and use these commands:</p>
      <p><code>/info-{tg_code}</code> — Equipment status &amp; readings</p>
      <p><code>/note-{tg_code}</code> — Add a note during inspection</p>
      <p><code>done #{wo_ref}</code> — Submit inspection findings</p>"""
        else:
            html += f"""      <p>When you have completed the inspection, type: <code>done #{wo_ref}</code></p>"""

        html += f"""    </div>
  </div>
    <div class="footer">
    <p><span class="brand">{site_name}</span> · Facilities Management</p>
    <p>This is an automated message from SENTINEL.</p>
  </div>
</div>
</body>
</html>"""
        return html

    async def _send_email_via_local_gmail_helper(self, to_email: str, subject: str, body: str) -> bool:
        """Fallback delivery via local gmail helper, still triggered from API flow."""
        if not to_email or "@" not in to_email:
            return False

        sentry_home = os.environ.get("SENTRY_HOME", "")
        if not sentry_home:
            logger.info("SENTRY_HOME not set — skipping gmail helper fallback")
            return False

        helper_path = os.path.join(sentry_home, "tools", "gmail_helper.py")
        if not os.path.exists(helper_path):
            logger.info("Gmail helper not found at %s — skipping fallback", helper_path)
            return False

        try:
            process = await asyncio.create_subprocess_exec(
                "/usr/bin/python3",
                helper_path,
                "send",
                subject,
                body,
                to_email,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            out = (stdout or b"").decode("utf-8", errors="ignore")
            err = (stderr or b"").decode("utf-8", errors="ignore")

            if process.returncode == 0 and "Email sent successfully" in out:
                logger.info("Email sent via local gmail helper fallback to %s", to_email)
                return True

            logger.warning(
                "gmail_helper fallback failed rc=%s stdout=%s stderr=%s",
                process.returncode,
                out.strip(),
                err.strip(),
            )
            return False
        except Exception as e:
            logger.warning("Exception in gmail_helper fallback: %s", e)
            return False

    async def _send_email_via_native_smtp(
        self, to_email: str, subject: str, body: str, body_html: str | None = None, technician_name: str = "Technician"
    ) -> bool:
        """Send email via native SMTP (aiosmtplib) using configured SMTP settings.

        Uses workorder@sentinel-ai.co.za (or whatever is in notification_smtp_* settings).
        This is the preferred fallback when the Sentry /send-email endpoint is unavailable.
        """
        if not to_email or "@" not in to_email:
            return False

        try:
            from app.services.email_reply_service import get_email_reply_service

            service = get_email_reply_service()
            if not service.is_configured():
                logger.info("Native SMTP not configured — skipping")
                return False

            result = await service.send_reply(
                to_email=to_email,
                to_name=technician_name,
                subject=subject,
                body_plain=body,
                body_html=body_html,
            )

            if result.sent:
                logger.warning("[WO-NOTIFY] Email sent via SMTP to %s", to_email)
                return True
            else:
                logger.warning("[WO-NOTIFY] SMTP failed: %s", result.error)
                return False
        except Exception as e:
            logger.warning("Exception in native SMTP email: %s", e)
            return False

    async def notify_technician_with_code(self, work_order_data: dict[str, Any]) -> dict[str, Any]:
        """Notify technician via BOTH email and Telegram.

        Creates a service record for the work order and sends notifications via:
        1. Telegram via Sentry bot (instant messaging)
        2. Email via native SMTP (workorder@sentinel-ai.co.za)

        Returns:
            Dict with success status and service_record_code
        """
        try:
            # For call-log entries, site_id and equipment_id may be TEXT codes (e.g., "site-002", "ZONE-207")
            # that don't map to UUID FKs. Attempt to resolve them; if resolution fails, set to None
            # so the service record can still be created (these fields may be nullable).
            site_id_val = work_order_data.get("site_id")
            if site_id_val:
                try:
                    uuid.UUID(str(site_id_val))
                except ValueError:
                    # Try to resolve via sites table
                    try:
                        from app.database.repositories.site_repository import SiteRepository

                        site_repo = SiteRepository()
                        site = site_repo.get_by_id(site_id_val)
                        site_id_val = site.get("id") if site else None
                    except Exception:
                        site_id_val = None

            equipment_id_val = work_order_data.get("equipment_id")
            if equipment_id_val:
                try:
                    uuid.UUID(str(equipment_id_val))
                except ValueError:
                    # Try to resolve via equipment table
                    try:
                        from app.database.repositories.equipment_repository import get_equipment_repository

                        eq_repo = get_equipment_repository()
                        # equipment.code is text like "S002-LIGHTING-L2-001" or "ZONE-207"
                        eqs = await eq_repo.get_equipment_by_code(equipment_id_val)
                        equipment_id_val = eqs.get("id") if eqs else None
                    except Exception:
                        equipment_id_val = None

            # Create service record only if real equipment is involved
            create_sr = work_order_data.get("create_service_record", True)
            service_record = None
            if create_sr:
                service_record = await self.create_service_record(work_order_data, site_id_val, equipment_id_val)
                if not service_record:
                    return {"success": False, "error": "Failed to create service record"}
                logger.info(f"Service record {service_record['code']} created for {work_order_data['equipment_name']}")
            else:
                logger.info("Skipping service record — general complaint, no equipment involved")

            # Ensure technician email is available (look up if not passed)
            if not work_order_data.get("technician_email"):
                try:
                    from app.database.repositories.technician_repository import get_technician_repository

                    tech_repo = get_technician_repository()
                    tech_name = work_order_data.get("technician_name", "")
                    all_techs = await tech_repo.get_all_technicians(active_only=True)
                    needle = tech_name.strip().lower()
                    matched = next(
                        (t for t in all_techs if t.get("name", "").lower() == needle),
                        None,
                    )
                    if matched and matched.get("email"):
                        work_order_data["technician_email"] = matched["email"]
                except Exception as e:
                    logger.warning(f"Could not look up technician email: {e}")

            # Resolve technician Telegram ID from DB (match by name, then by email)
            if not work_order_data.get("technician_id") or "@" in str(work_order_data.get("technician_id", "")):
                try:
                    from app.database.repositories.technician_repository import get_technician_repository

                    tech_repo = get_technician_repository()
                    tech_name = work_order_data.get("technician_name", "")
                    tech_email = work_order_data.get("technician_email", "")
                    all_techs = await tech_repo.get_all_technicians(active_only=True)

                    matched = None
                    # Try name match first
                    if tech_name:
                        needle = tech_name.strip().lower()
                        matched = next(
                            (t for t in all_techs if t.get("name", "").lower() == needle),
                            None,
                        )
                    # Fall back to email match
                    if not matched and tech_email:
                        needle = tech_email.strip().lower()
                        matched = next(
                            (t for t in all_techs if t.get("email", "").lower() == needle),
                            None,
                        )

                    if matched and matched.get("telegram_id"):
                        work_order_data["technician_id"] = matched["telegram_id"]
                        logger.warning(
                            f"[WO-NOTIFY] Resolved Telegram ID for {matched.get('name')}: {matched['telegram_id']}"
                        )
                    elif matched:
                        logger.warning(
                            f"[WO-NOTIFY] No Telegram ID for {matched.get('name')} (email: {matched.get('email')})"
                        )
                except Exception as e:
                    logger.warning(f"Could not look up Telegram ID: {e}")

            # Send Telegram notification directly via Sentry CLI
            sr = service_record or {}
            telegram_sent = await self._send_telegram_notification(work_order_data, sr)

            # Send Email notification via native SMTP
            email_sent = await self._send_email_notification(work_order_data, sr)

            logger.warning(f"[WO-NOTIFY] Notifications sent — Telegram: {telegram_sent}, Email: {email_sent}")

            return {
                "success": True,
                "service_record_code": service_record["code"] if service_record else "",
                "telegram_sent": telegram_sent,
                "email_sent": email_sent,
            }

        except Exception as e:
            logger.error(f"Error creating service record: {e}")
            return {"success": False, "error": str(e)}

    async def _log_delivery(
        self,
        *,
        work_order_data: dict[str, Any],
        service_record: dict[str, Any],
        channel_type: ChannelType,
        status: NotificationStatus,
        recipient_identifier: str,
        title: str,
        body: str,
        provider: str = "sentry",
        external_message_id: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        provider_response: dict[str, Any] | None = None,
    ) -> None:
        """Persist work order send attempt into notification delivery log."""
        # Resolve technician_id — prefer UUID from repo lookup, fall back to system notifier
        technician_uuid = SYSTEM_NOTIFIER_TECHNICIAN_ID
        try:
            from uuid import UUID

            from app.database.repositories.technician_repository import get_technician_repository

            tech_repo = get_technician_repository()
            tech_telegram_id = str(work_order_data.get("technician_id") or "").strip()
            if tech_telegram_id and not tech_telegram_id.startswith("@"):
                tech = await tech_repo.get_technician_by_telegram_id(tech_telegram_id)
                if tech and tech.get("id"):
                    technician_uuid = UUID(tech["id"])
        except Exception:
            pass

        delivery_log = NotificationDeliveryLog(
            id=uuid.uuid4(),
            work_order_id=work_order_data.get("work_order_id"),
            technician_id=technician_uuid,
            notification_type="work_order_assigned",
            title=title,
            body=body,
            channel_type=channel_type,
            recipient_identifier=recipient_identifier,
            status=status,
            error_code=error_code,
            error_message=error_message,
            provider=provider,
            provider_response=provider_response or {},
            external_message_id=external_message_id,
            sent_at=datetime.utcnow() if status == NotificationStatus.SENT else None,
        )

        await self._notification_repo.create_delivery_log(delivery_log)

    async def _send_telegram_notification(
        self, work_order_data: dict[str, Any], service_record: dict[str, Any]
    ) -> bool:
        """Send Telegram notification to technician via Telegram Bot API directly."""
        import httpx

        try:
            technician_id = str(work_order_data.get("technician_id") or "").strip()
            if not technician_id or "@" in technician_id:
                logger.info(
                    "No Telegram ID for %s (technician_id=%r) — skipping Telegram send",
                    work_order_data.get("technician_name"),
                    technician_id,
                )
                return False

            from app.config.settings import settings

            # Call-log notifications route through the tech bot so the technician
            # receives the WO alert in their tech-bot chat, not the staff bot.
            is_callout = work_order_data.get("service_type") == "callout"
            bot_token = settings.sentry_tech_bot_token if is_callout else settings.sentry_client_bot_token
            if not bot_token:
                fallback = settings.sentry_client_bot_token
                bot_token = fallback
            if not bot_token:
                logger.warning("No bot token configured for Telegram notifications")
                return False

            wo_ref = (
                work_order_data.get("code")
                or work_order_data.get("work_order_code")
                or work_order_data.get("work_order_id", "WO-???")
            )
            pri = work_order_data.get("criticality", "MEDIUM").upper()
            equipment_code = work_order_data.get("equipment_code", "")
            eq_line = f"\nEquipment: {equipment_code}" if equipment_code else ""

            reported_by = work_order_data.get("reported_by", "")
            reporter_phone = work_order_data.get("reporter_phone", "")
            location = work_order_data.get("location", "")
            if not location:
                zone_id = work_order_data.get("zone_id", "")
                desk_id = work_order_data.get("desk_id", "")
                if desk_id and zone_id:
                    location = f"Desk {desk_id}, {zone_id}"
                elif desk_id:
                    location = f"Desk {desk_id}"
                elif zone_id:
                    location = zone_id
            problem = work_order_data.get("original_message", "") or work_order_data.get("problem_description", "")
            problem = problem.strip()

            lines = [f"Work Order Created #{wo_ref}", f"Priority: {pri}"]
            if reported_by:
                lines.append(f"From: {reported_by}")
            if location:
                lines.append(f"Location: {location}")
            if reporter_phone:
                lines.append(f"Contact: {reporter_phone}")
            if eq_line:
                lines.append(eq_line.strip())
            if problem:
                lines.append("")
                lines.append(problem)
            msg = "\n".join(lines)

            code_dashed = equipment_code.replace("_", "-") if equipment_code else ""
            desk_number = work_order_data.get("desk_number", "")
            info_ref = code_dashed or (desk_number if desk_number.isdigit() else "")
            note_ref = code_dashed or ""
            info_value = f"/info-{info_ref}" if info_ref else ""
            note_value = f"/note-{note_ref}" if note_ref else ""
            done_value = f"done #{wo_ref}"
            inline_keyboard = []
            row = []
            if info_value:
                row.append({"text": "📋 Info", "callback_data": info_value})
            if note_value:
                row.append({"text": "📝 Notes", "callback_data": note_value})
            if row:
                inline_keyboard.append(row)
            inline_keyboard.append([{"text": "✅ Done", "callback_data": done_value}])

            payload = {
                "chat_id": technician_id,
                "text": msg,
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": inline_keyboard},
            }

            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json=payload,
                )
                result = resp.json()

            if result.get("ok"):
                logger.info("Telegram sent to %s for %s", technician_id, wo_ref)
                await self._log_delivery(
                    work_order_data=work_order_data,
                    service_record=service_record,
                    channel_type=ChannelType.TELEGRAM,
                    status=NotificationStatus.SENT,
                    recipient_identifier=technician_id,
                    title=f"Work Order {wo_ref}",
                    body=msg,
                    provider="telegram_direct",
                    external_message_id=str(result.get("result", {}).get("message_id", "")),
                )
                return True
            else:
                err = result.get("description", "unknown error")
                logger.warning("Telegram send failed for %s: %s", wo_ref, err)
                await self._log_delivery(
                    work_order_data=work_order_data,
                    service_record=service_record,
                    channel_type=ChannelType.TELEGRAM,
                    status=NotificationStatus.FAILED,
                    recipient_identifier=technician_id,
                    title=f"Work Order {wo_ref}",
                    body=msg,
                    provider="telegram_direct",
                    error_code=result.get("error_code", "unknown"),
                    error_message=err,
                )
                return False
        except Exception as e:
            logger.warning("Failed to send Telegram notification: %s", e)
            await self._log_delivery(
                work_order_data=work_order_data,
                service_record=service_record,
                channel_type=ChannelType.TELEGRAM,
                status=NotificationStatus.FAILED,
                recipient_identifier=str(work_order_data.get("technician_id") or ""),
                title=f"Work Order {work_order_data.get('code', '?')}",
                body="",
                provider="telegram_direct",
                error_code="exception",
                error_message=str(e),
            )
            return False

    async def _send_email_notification(self, work_order_data: dict[str, Any], service_record: dict[str, Any]) -> bool:
        """Send email notification to technician via native SMTP (workorder@sentinel-ai.co.za)."""
        try:
            work_order = await self._load_work_order_context(work_order_data.get("work_order_id", ""))

            technician_id = work_order_data.get("technician_id", "")
            technician_email = work_order_data.get("technician_email")

            recipient = technician_email or technician_id
            if "@" not in str(recipient):
                logger.warning("No valid recipient email for work order %s", work_order_data.get("work_order_id"))
                return False

            email_subject = self._build_email_subject(work_order_data, work_order)
            email_body_plain = self._build_email_body(work_order_data, service_record, work_order)
            email_body_html = self._build_email_body_html(work_order_data, service_record, work_order)
            technician_name = work_order_data.get("technician_name", "Technician")

            sent = await self._send_email_via_native_smtp(
                to_email=recipient,
                subject=email_subject,
                body=email_body_plain,
                body_html=email_body_html,
                technician_name=technician_name,
            )

            await self._log_delivery(
                work_order_data=work_order_data,
                service_record=service_record,
                channel_type=ChannelType.EMAIL,
                status=NotificationStatus.SENT if sent else NotificationStatus.FAILED,
                recipient_identifier=str(recipient),
                title=email_subject,
                body=email_body_plain[:500] if email_body_plain else "",
                provider="smtp",
                error_code=None if sent else "smtp_failed",
                error_message=None if sent else "Email send returned False",
            )
            return sent

        except Exception as e:
            logger.warning("Failed to send WO email notification: %s", e)
            await self._log_delivery(
                work_order_data=work_order_data,
                service_record=service_record,
                channel_type=ChannelType.EMAIL,
                status=NotificationStatus.FAILED,
                recipient_identifier=str(work_order_data.get("technician_email") or ""),
                title=f"Work Order {work_order_data.get('code', '?')}",
                body="",
                provider="smtp",
                error_code="exception",
                error_message=str(e),
            )
            return False

    async def notify_technician(self, work_order_data: dict[str, Any]) -> bool:
        """Notify technician about new work order via Sentry.

        Sends notification only - data collection does NOT start yet.
        Technician must reply "done" AFTER completing service work.

        Args:
            work_order_data: Work order information including:
                - work_order_id: UUID
                - equipment_id: Equipment UUID
                - site_id: Building UUID
                - equipment_name: Display name
                - criticality: HIGH/MEDIUM/LOW
                - service_type: minor/major/breakdown/callout
                - technician_id: Telegram ID/email
                - technician_name: Display name
                - description: Problem description

        Workflow:
            1. Create service record in database
            2. Send notification via Sentry (Telegram)
            3. Technician completes service work
            4. Technician replies "done" → triggers data collection
            5. See handle_technician_reply() for collection flow

        Returns:
            True if notification sent successfully
        """
        result = await self.notify_technician_with_code(work_order_data)
        return result.get("success", False)

    async def create_service_record(
        self,
        work_order_data: dict[str, Any],
        site_id_val: str | None = None,
        equipment_id_val: str | None = None,
    ) -> dict[str, Any] | None:
        """Create a service record from work order data.

        Args:
            work_order_data: Work order information including diagnostic_context
            site_id_val: Pre-resolved site UUID (optional — skips resolution if None)
            equipment_id_val: Pre-resolved equipment UUID (optional — falls back to work_order_id if None)

        Returns:
            Created service record, or None if failed
        """
        import uuid

        # Idempotency guard: if a service record already exists for this work order,
        # reuse it instead of creating duplicates (DB trigger + notifier can both run).
        existing = await self.repository.list(filters={"work_order_id": work_order_data["work_order_id"]})
        if existing:
            logger.info(
                "Reusing existing service record %s for work order %s",
                existing[0].get("code"),
                work_order_data["work_order_id"],
            )
            return existing[0]

        # Generate service record code
        code = f"SR-{datetime.now().year}-{str(uuid.uuid4())[:6].upper()}"

        # Extract diagnostic context from work order (passed from alert)
        diagnostic_context = work_order_data.get("diagnostic_context")

        # Use pre-resolved UUIDs where available; equipment_id falls back to placeholder
        # (service_records.equipment_id is NOT NULL and must reference real equipment)
        resolved_equipment_id = equipment_id_val or _CALL_LOG_PLACEHOLDER_EQUIPMENT_ID
        resolved_site_id = site_id_val or work_order_data.get("site_id")

        record_data = {
            "code": code,
            "work_order_id": work_order_data["work_order_id"],
            "equipment_id": resolved_equipment_id,
            "site_id": resolved_site_id,
            "service_type": work_order_data["service_type"],
            "technician_id": work_order_data["technician_id"],
            "technician_name": work_order_data["technician_name"],
            "status": ServiceStatus.NOTIFIED.value,
            "items_collected": [],
            "diagnostic_context": diagnostic_context,  # Store alert context for data collection
        }

        created = await self.repository.create(record_data)

        # Set equipment to maintenance while service is pending
        if created and resolved_equipment_id and resolved_equipment_id != _CALL_LOG_PLACEHOLDER_EQUIPMENT_ID:
            await self._update_equipment_status(resolved_equipment_id, "maintenance")
            logger.info("Equipment %s set to maintenance (SR %s)", resolved_equipment_id, code)

        return created

    async def handle_technician_reply(self, service_record_code: str, reply_data: dict[str, Any]) -> dict[str, Any]:
        """Handle technician's reply to work order notification.

        Args:
            service_record_code: Service record code (e.g., SR-2026-ABC123)
            reply_data: Reply information including:
                - message_type: text/photo/audio/file
                - content: Message content or file info
                - telegram_user_id: User ID for context

        Returns:
            Response with next action
        """
        try:
            # Find service record
            filters = {"code": service_record_code}
            records = await self.repository.list(filters)

            if not records:
                return {"error": "Service record not found", "service_record_code": service_record_code}

            service_record = records[0]

            # Get equipment type
            equipment = await self.repository.get_equipment_by_id(service_record["equipment_id"])
            if not equipment:
                return {"error": "Equipment not found", "equipment_id": service_record["equipment_id"]}

            equipment_type = equipment.get("type", "unknown")

            # Process the reply based on type
            if reply_data["message_type"] == "text":
                result = await self._handle_text_reply(service_record, equipment_type, reply_data)
            elif reply_data["message_type"] in ["photo", "file"]:
                result = await self._handle_file_reply(service_record, equipment_type, reply_data)
            elif reply_data["message_type"] == "audio":
                result = await self._handle_audio_reply(service_record, equipment_type, reply_data)
            else:
                result = {"error": "Unsupported message type"}

            # Check if data collection is complete
            if result.get("success"):
                completion_status = self._check_completion(service_record, equipment_type)
                result.update(completion_status)

            return result

        except Exception as e:
            logger.error(f"Error handling technician reply: {e}")
            return {"error": str(e)}

    async def _handle_text_reply(
        self, service_record: dict[str, Any], equipment_type: str, reply_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle text reply from technician."""
        content = reply_data.get("content", "")
        diagnostic_context = service_record.get("diagnostic_context")
        service_type = service_record.get("service_type", "minor")

        # Check if it's the initial "done" response to start data collection
        if content.lower() in ["done", "ok", "completed", "finished"]:
            # "Done" response - move to data collection
            await self.repository.update(service_record["id"], {"status": ServiceStatus.DATA_COLLECTION.value})

            # Get context-aware flow for breakdowns with diagnostic context
            if service_type == "breakdown" and diagnostic_context:
                flow = self.template_service.get_breakdown_flow(equipment_type, diagnostic_context)
                current_step = flow[0] if flow else "fault_description"

                # Get context-aware prompt
                prompt_data = self.template_service.get_context_aware_prompt(
                    equipment_type,
                    service_type,
                    diagnostic_context,
                    service_record.get("items_collected", []),
                    current_step,
                )

                # Store current step
                await self.repository.update(service_record["id"], {"current_prompt": current_step})

                return {
                    "success": True,
                    "type": "ready_for_collection",
                    "next_prompt": prompt_data["prompt"],
                    "prompt_type": prompt_data["type"],
                    "options": prompt_data.get("options"),
                    "current_step": current_step,
                    "collected_items": service_record.get("items_collected", []),
                }

            # Standard flow for minor/major services
            next_item = self.template_service.get_next_prompt(
                equipment_type, service_type, service_record.get("items_collected", [])
            )

            return {
                "success": True,
                "type": "ready_for_collection",
                "next_prompt": next_item,
                "collected_items": service_record.get("items_collected", []),
            }

        # Handle responses during data collection (not "done")
        current_step = service_record.get("current_prompt")

        # For breakdown with context, try to extract all info from response
        if service_type == "breakdown" and diagnostic_context:
            # First, try to extract structured info from free-form response
            extraction = self.template_service.extract_info_from_response(equipment_type, diagnostic_context, content)

            # If technician provided comprehensive info, process it all
            if extraction["completed_steps"]:
                return await self._handle_comprehensive_response(
                    service_record, equipment_type, diagnostic_context, extraction, content
                )

            # Otherwise, process as single step response
            if current_step:
                return await self._handle_breakdown_step_response(
                    service_record, equipment_type, diagnostic_context, current_step, content
                )

        # Otherwise store as observation
        observation = await self.repository.add_observation(
            service_record["id"], {"observation_type": "text", "content": content}
        )
        return {"success": True, "type": "observation", "observation_id": observation["id"]}

    async def _handle_comprehensive_response(
        self,
        service_record: dict[str, Any],
        equipment_type: str,
        diagnostic_context: dict[str, Any],
        extraction: dict[str, Any],
        original_content: str,
    ) -> dict[str, Any]:
        """Handle a comprehensive response that contains multiple pieces of info.

        When technician says something like:
        "Yes actuator failed, replaced Belimo LMV-D3, zone now 21.5C"

        Extract all info and skip to what's still needed (usually just the photo).

        Args:
            service_record: Service record
            equipment_type: Equipment type
            diagnostic_context: Diagnostic context
            extraction: Extracted info from template service
            original_content: Original technician message

        Returns:
            Response with acknowledgment and next needed item
        """
        extracted = extraction["extracted"]
        completed_steps = extraction["completed_steps"]
        remaining_steps = extraction["remaining_steps"]

        # Store extracted data
        if "fault_confirmation" in extracted:
            await self.repository.add_observation(
                service_record["id"],
                {"observation_type": "fault_confirmation", "content": extracted["fault_confirmation"]},
            )

        if "root_cause" in extracted:
            await self.repository.update(service_record["id"], {"confirmed_fault": extracted["root_cause"]})

        if "repair_action" in extracted:
            await self.repository.update(service_record["id"], {"actual_repair": extracted["repair_action"]})

        if "verification_reading" in extracted:
            await self.repository.add_observation(
                service_record["id"],
                {"observation_type": "verification_reading", "content": str(extracted["verification_reading"])},
            )

        # Update collected items
        current_collected = service_record.get("items_collected", [])
        for step in completed_steps:
            if step not in current_collected:
                current_collected.append(step)
                await self.repository.update_items_collected(service_record["id"], step)

        # Build acknowledgment message
        ack_parts = []
        if "fault_confirmation" in extracted:
            ack_parts.append("fault confirmed")
        if "root_cause" in extracted:
            ack_parts.append(f"root cause: {extracted['root_cause']}")
        if "parts_mentioned" in extracted:
            ack_parts.append(f"part: {extracted['parts_mentioned']}")
        if "verification_reading" in extracted:
            ack_parts.append(f"temp: {extracted['verification_reading']}°C")

        acknowledgment = f"Got it! ({', '.join(ack_parts)})"

        # If only photo needed
        if extraction["all_text_complete"] and extraction["needs_photo"]:
            return {
                "success": True,
                "type": "comprehensive_response",
                "acknowledgment": acknowledgment,
                "next_prompt": "Just need a photo of the replacement part label",
                "prompt_type": "photo",
                "completed_steps": completed_steps,
                "remaining_steps": remaining_steps,
                "extracted_data": extracted,
            }

        # If there are still text steps needed
        if remaining_steps:
            next_step = remaining_steps[0]
            prompt_data = self.template_service.get_context_aware_prompt(
                equipment_type, "breakdown", diagnostic_context, current_collected, next_step
            )

            await self.repository.update(service_record["id"], {"current_prompt": next_step})

            return {
                "success": True,
                "type": "comprehensive_response",
                "acknowledgment": acknowledgment,
                "next_prompt": prompt_data["prompt"],
                "prompt_type": prompt_data["type"],
                "options": prompt_data.get("options"),
                "current_step": next_step,
                "completed_steps": completed_steps,
                "remaining_steps": remaining_steps,
            }

        # All complete
        return {
            "success": True,
            "type": "collection_complete",
            "acknowledgment": acknowledgment,
            "is_complete": True,
            "extracted_data": extracted,
        }

    async def _handle_breakdown_step_response(
        self,
        service_record: dict[str, Any],
        equipment_type: str,
        diagnostic_context: dict[str, Any],
        current_step: str,
        content: str,
    ) -> dict[str, Any]:
        """Handle response to a breakdown data collection step.

        Args:
            service_record: Service record
            equipment_type: Equipment type
            diagnostic_context: Original diagnostic context
            current_step: Current step in flow
            content: Technician's response

        Returns:
            Response with next prompt
        """
        # Store the response based on step
        if current_step == "fault_confirmation":
            # Store confirmation
            await self.repository.add_observation(
                service_record["id"], {"observation_type": "fault_confirmation", "content": content}
            )
        elif current_step == "root_cause":
            # Store confirmed root cause
            await self.repository.update(service_record["id"], {"confirmed_fault": content})
        elif current_step == "repair_action":
            # Store actual repair
            await self.repository.update(service_record["id"], {"actual_repair": content})

        # Mark step as collected
        collected = service_record.get("items_collected", [])
        if current_step not in collected:
            collected.append(current_step)
            await self.repository.update_items_collected(service_record["id"], current_step)

        # Get next step in flow
        flow = self.template_service.get_breakdown_flow(equipment_type, diagnostic_context)
        current_index = flow.index(current_step) if current_step in flow else -1
        next_index = current_index + 1

        if next_index < len(flow):
            next_step = flow[next_index]

            # Get next context-aware prompt
            prompt_data = self.template_service.get_context_aware_prompt(
                equipment_type, "breakdown", diagnostic_context, collected, next_step
            )

            # Update current step
            await self.repository.update(service_record["id"], {"current_prompt": next_step})

            return {
                "success": True,
                "type": "next_step",
                "next_prompt": prompt_data["prompt"],
                "prompt_type": prompt_data["type"],
                "options": prompt_data.get("options"),
                "current_step": next_step,
                "collected_items": collected,
            }

        # All steps complete
        return {"success": True, "type": "collection_complete", "collected_items": collected, "is_complete": True}

    async def _handle_file_reply(
        self, service_record: dict[str, Any], equipment_type: str, reply_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle file/photo reply from technician."""
        file_info = reply_data.get("content", {})

        # Determine attachment type
        attachment_type = self._classify_attachment(file_info, service_record)

        # Add attachment to service record
        attachment = await self.repository.add_attachment(
            {
                "service_record_id": service_record["id"],
                "attachment_type": attachment_type,
                "file_path": file_info.get("file_path", ""),
                "file_name": file_info.get("file_name", ""),
                "file_size_bytes": file_info.get("file_size", 0),
                "mime_type": file_info.get("mime_type", "application/octet-stream"),
                "analysis_status": "pending",
            }
        )

        # Update collected items
        new_collected = [*service_record.get("items_collected", []), attachment_type]
        await self.repository.update_items_collected(service_record["id"], attachment_type)

        # For breakdown service with diagnostic context, use context-aware flow
        service_type = service_record.get("service_type", "minor")
        diagnostic_context = service_record.get("diagnostic_context")

        if service_type == "breakdown" and diagnostic_context:
            # Get next step in breakdown flow
            flow = self.template_service.get_breakdown_flow(equipment_type, diagnostic_context)
            current_step = service_record.get("current_prompt", "")

            # Find next step after current
            try:
                current_index = flow.index(current_step) if current_step in flow else -1
                next_index = current_index + 1

                if next_index < len(flow):
                    next_step = flow[next_index]

                    # Update current step
                    await self.repository.update(service_record["id"], {"current_prompt": next_step})

                    # Get context-aware prompt for next step
                    prompt_data = self.template_service.get_context_aware_prompt(
                        equipment_type, service_type, diagnostic_context, new_collected, next_step
                    )

                    return {
                        "success": True,
                        "type": "attachment_added",
                        "attachment_type": attachment_type,
                        "attachment_id": attachment["id"],
                        "next_prompt": prompt_data["prompt"],
                        "prompt_type": prompt_data["type"],
                        "options": prompt_data.get("options"),
                        "current_step": next_step,
                    }
                else:
                    # All steps complete
                    return {
                        "success": True,
                        "type": "collection_complete",
                        "attachment_type": attachment_type,
                        "attachment_id": attachment["id"],
                        "is_complete": True,
                    }
            except ValueError:
                pass  # Fall through to standard handling

        # Standard flow - get next prompt
        next_prompt = self.template_service.get_next_prompt(equipment_type, service_type, new_collected)

        return {
            "success": True,
            "type": "attachment_added",
            "attachment_type": attachment_type,
            "attachment_id": attachment["id"],
            "next_prompt": next_prompt,
        }

    async def _handle_audio_reply(
        self, service_record: dict[str, Any], equipment_type: str, reply_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle audio reply from technician."""
        return await self._handle_file_reply(service_record, equipment_type, reply_data)

    def _classify_attachment(self, file_info: dict[str, Any], service_record: dict[str, Any]) -> str:
        """Classify attachment type based on file characteristics and current step.

        For photos, uses the current collection step to determine if it's a
        before photo, after photo, or parts photo.
        """
        file_name = file_info.get("file_name", "").lower()
        mime_type = file_info.get("mime_type", "")
        current_step = service_record.get("current_prompt", "")
        collected_items = service_record.get("items_collected", [])

        # Check by MIME type
        if mime_type.startswith("image/"):
            # First check filename hints for specific types
            if "oil" in file_name:
                return "oil_sample"
            elif "diesel" in file_name or "fuel" in file_name:
                return "diesel_sample"
            elif "service" in file_name or "sheet" in file_name:
                return "service_sheet"
            elif "thermal" in file_name or "flir" in file_name:
                return "thermal_image"

            # Use current step to determine photo type
            _step_map = {
                "photo_before": "photo_before",
                "photo_after": "photo_after",
                "parts_replaced": "parts_replaced",
            }
            if current_step in _step_map:
                return _step_map[current_step]

            # Fallback: determine based on what's already collected
            if "photo_before" not in collected_items:
                return "photo_before"
            elif "photo_after" not in collected_items:
                return "photo_after"
            elif "parts_replaced" not in collected_items:
                return "parts_replaced"
            else:
                return "issue_photo"

        elif mime_type.startswith("audio/"):
            return "audio_recording"

        elif mime_type.startswith("video/"):
            return "load_test_video"

        # Default based on what we expect
        return "service_sheet"

    def _check_completion(self, service_record: dict[str, Any], equipment_type: str) -> dict[str, Any]:
        """Check if all required items have been collected.

        Args:
            service_record: Service record with collected items
            equipment_type: Equipment type

        Returns:
            Status of completion
        """
        validation = self.template_service.validate_collected_items(
            equipment_type, service_record["service_type"], service_record.get("items_collected", [])
        )

        if validation["is_complete"]:
            # Mark as complete and trigger equipment health restoration
            # fire-and-forget: result discarded intentionally
            asyncio.create_task(self._complete_service_record_and_restore_equipment(service_record))  # noqa: RUF006

        return {
            "is_complete": validation["is_complete"],
            "missing_items": validation["missing_items"],
            "progress": validation["progress"],
            "completion_percentage": validation["completion_percentage"],
        }

    async def _complete_service_record_and_restore_equipment(self, service_record: dict[str, Any]):
        """Complete service record and restore equipment to healthy state.

        This method:
        1. Marks the service record as complete
        2. Restores equipment health_score (85-95%)
        3. Resolves any active alerts for the equipment
        4. Resolves any active predictions for the equipment

        Args:
            service_record: The completed service record
        """
        try:
            # 1. Mark service record as complete
            await self.repository.update(service_record["id"], {"status": ServiceStatus.COMPLETE.value})
            logger.info(f"Service record {service_record.get('code')} marked as complete")

            equipment_id = service_record.get("equipment_id")

            # 2. Resolve active alerts for this equipment
            await self._resolve_equipment_alerts(equipment_id)

            # 3. Resolve active predictions for this equipment
            await self._resolve_equipment_predictions(equipment_id)

            # 4. Update equipment status to 'normal' in Supabase
            await self._update_equipment_status(equipment_id, "normal")

            # 5. Restore health score based on service type + configured healthy threshold
            await self._restore_equipment_health(equipment_id, service_record.get("service_type"))

        except Exception as e:
            logger.error(f"Error completing service record: {e}")

    async def _resolve_equipment_alerts(self, equipment_id: str):
        """Resolve all active alerts for equipment."""
        try:
            from app.database.repositories.alert_repository import AlertRepository

            alert_repo = AlertRepository()
            result = await alert_repo.resolve_by_equipment(equipment_id)
            if result:
                logger.info(f"Resolved alerts for equipment {equipment_id}")
        except Exception as e:
            logger.warning(f"Could not resolve alerts: {e}")

    async def _resolve_equipment_predictions(self, equipment_id: str):
        """Resolve all active predictions for equipment."""
        try:
            from app.database.repositories.prediction_repository import PredictionRepository

            pred_repo = PredictionRepository()
            result = await pred_repo.resolve_by_equipment(equipment_id)
            if result:
                logger.info(f"Resolved predictions for equipment {equipment_id}")
        except Exception as e:
            logger.warning(f"Could not resolve predictions: {e}")

    async def _update_equipment_status(self, equipment_id: str, status: str):
        """Update equipment status in Supabase."""
        try:
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            client.table("equipment").update({"status": status, "updated_at": datetime.now().isoformat()}).eq(
                "id", equipment_id
            ).execute()
            logger.info(f"Equipment {equipment_id} status updated to '{status}'")
        except Exception as e:
            logger.warning(f"Could not update equipment status: {e}")

    async def _restore_equipment_health(self, equipment_id: str | None, service_type: str | None):
        """Restore equipment health score after service, anchored to the configured healthy threshold.

        Recovery scale by service type:
          breakdown / major  → healthy threshold (full overhaul, full reset)
          minor              → warning + 70% of (healthy - warning)
          callout            → warning + 30% of (healthy - warning)  (investigation, partial)
        """
        if not equipment_id or equipment_id == _CALL_LOG_PLACEHOLDER_EQUIPMENT_ID:
            return
        try:
            from app.database.repositories.equipment_repository import get_equipment_repository
            from app.services.health_threshold_service import get_health_thresholds

            thresholds = get_health_thresholds()
            healthy = thresholds["healthy"]
            warning = thresholds["warning"]
            gap = healthy - warning

            recovery_map = {
                "breakdown": healthy,
                "major": healthy,
                "minor": int(warning + gap * 0.7),
                "callout": int(warning + gap * 0.3),
            }
            recovery_score = recovery_map.get(service_type or "", int(warning + gap * 0.5))

            repo = get_equipment_repository()
            repo.update_health_score(equipment_id, recovery_score)
            logger.info(
                "Equipment %s health restored to %d (service_type=%s, healthy_threshold=%d)",
                equipment_id,
                recovery_score,
                service_type,
                healthy,
            )
        except Exception as e:
            logger.warning(f"Could not restore equipment health score: {e}", exc_info=True)

    async def get_collection_status(self, service_record_code: str) -> dict[str, Any]:
        """Get data collection status for a service record.

        Args:
            service_record_code: Service record code

        Returns:
            Collection status with progress and next steps
        """
        # Find service record
        filters = {"code": service_record_code}
        records = await self.repository.list(filters)

        if not records:
            return {"error": "Service record not found", "service_record_code": service_record_code}

        service_record = records[0]

        # Get equipment type
        equipment = await self.repository.get_equipment_by_id(service_record["equipment_id"])
        if not equipment:
            return {"error": "Equipment not found", "equipment_id": service_record["equipment_id"]}

        equipment_type = equipment.get("type", "unknown")

        # Get status
        validation = self.template_service.validate_collected_items(
            equipment_type, service_record["service_type"], service_record.get("items_collected", [])
        )

        next_prompt = self.template_service.get_next_prompt(
            equipment_type, service_record["service_type"], service_record.get("items_collected", [])
        )

        return {
            "service_record_code": service_record_code,
            "status": service_record["status"],
            "collected_items": service_record.get("items_collected", []),
            "missing_items": validation["missing_items"],
            "progress": validation["progress"],
            "completion_percentage": validation["completion_percentage"],
            "next_prompt": next_prompt,
        }

    async def complete_service_record(self, service_record_code: str, force: bool = True) -> dict[str, Any]:
        """Complete a service record and trigger health restoration/closure flow."""
        filters = {"code": service_record_code}
        records = await self.repository.list(filters)
        if not records:
            return {"error": "Service record not found", "service_record_code": service_record_code}

        service_record = records[0]
        if service_record.get("status") == ServiceStatus.COMPLETE.value:
            return {
                "success": True,
                "service_record_code": service_record_code,
                "status": ServiceStatus.COMPLETE.value,
                "already_complete": True,
            }

        equipment = await self.repository.get_equipment_by_id(service_record["equipment_id"])
        if not equipment:
            return {"error": "Equipment not found", "equipment_id": service_record["equipment_id"]}

        equipment_type = equipment.get("type", "unknown")
        validation = self.template_service.validate_collected_items(
            equipment_type,
            service_record["service_type"],
            service_record.get("items_collected", []),
        )

        if not validation["is_complete"] and not force:
            return {
                "error": "incomplete_data_collection",
                "service_record_code": service_record_code,
                "missing_items": validation["missing_items"],
                "completion_percentage": validation["completion_percentage"],
            }

        await self._complete_service_record_and_restore_equipment(service_record)
        return {
            "success": True,
            "service_record_code": service_record_code,
            "status": ServiceStatus.COMPLETE.value,
            "forced": (not validation["is_complete"]) and force,
            "completion_percentage": validation["completion_percentage"],
            "missing_items": validation["missing_items"],
        }


# Global instance
work_order_notifier = WorkOrderNotifier()


async def handle_telegram_comfort_complaint(
    telegram_user_id: str,
    message_text: str,
) -> str | None:
    """
    Route a comfort complaint from Telegram to the LangGraph agent.

    Returns the response text, or None if the message isn't a comfort complaint
    and there's no active complaint session.
    """
    consent_decision = evaluate_ingress_processing_consent(
        data_subject_id=telegram_user_id,
        platform="telegram",
        message_text=message_text,
    )
    if not consent_decision.allow_processing:
        return consent_decision.response_message

    try:
        from langchain_core.messages import HumanMessage

        from app.agents import get_desk_complaint_graph
        from app.agents.complaint_nlp import detect_comfort_complaint

        agent = get_desk_complaint_graph()
        thread_id = f"tg_{telegram_user_id}"
        config = {"configurable": {"thread_id": thread_id}}

        # 1. Check for active multi-turn session
        state = agent.get_state(config)
        if state.values and state.values.get("needs_input"):
            result = agent.invoke(
                {"messages": [HumanMessage(content=message_text)]},
                config=config,
            )
            return result.get("response", "")

        # 2. Detect new comfort complaint
        if detect_comfort_complaint(message_text):
            result = agent.invoke(
                {
                    "messages": [HumanMessage(content=message_text)],
                    "user_id": telegram_user_id,
                    "channel": "telegram",
                },
                config=config,
            )
            return result.get("response", "")

        return None
    except ImportError:
        logger.debug("LangGraph not available for Telegram comfort complaints")
        return None
    except Exception as e:
        logger.warning(f"Telegram comfort complaint agent error: {e}")
        return None


async def handle_telegram_recommendation_approval(telegram_user_id: str, message_text: str) -> str | None:
    """Handle Telegram-based Tier 2 recommendation approval/rejection.

    Detects APPROVE/REJECT commands and resumes the checkpointed
    recommendation agent graph if an active approval session exists.

    Args:
        telegram_user_id: Telegram user ID
        message_text: Message text (e.g., "/approve abc123", "/reject abc123 too risky")

    Returns:
        Response string if handled, None if not a recommendation approval
    """
    consent_decision = evaluate_ingress_processing_consent(
        data_subject_id=telegram_user_id,
        platform="telegram",
        message_text=message_text,
    )
    if not consent_decision.allow_processing:
        return consent_decision.response_message

    try:
        text_upper = message_text.strip().upper()

        # Check for approval command patterns
        is_approve = text_upper.startswith("/APPROVE") or text_upper.startswith("APPROVE")
        is_reject = text_upper.startswith("/REJECT") or text_upper.startswith("REJECT")

        if not is_approve and not is_reject:
            return None

        from langchain_core.messages import HumanMessage

        from app.agents import get_recommendation_graph
        from app.agents.recommendation_tools import (
            execute_approved_recommendation,
            reject_recommendation,
        )

        agent = get_recommendation_graph()
        thread_id = f"rec_tg_{telegram_user_id}"
        config = {"configurable": {"thread_id": thread_id}}

        state = await agent.aget_state(config)
        # Normalize: strip leading "/" for parsing and agent resume.
        normalized = message_text.strip()
        if normalized.startswith("/"):
            normalized = normalized[1:]

        if state.values and state.values.get("needs_input"):
            result = await agent.ainvoke(
                {"messages": [HumanMessage(content=normalized)]},
                config=config,
            )
            return result.get("response", "")

        # Fallback: no active checkpoint session, execute directly by rec-id.
        parts = normalized.split(maxsplit=2)
        if not parts:
            return "Please include APPROVE/REJECT and a recommendation ID."

        action = parts[0].upper()
        token = parts[1].strip() if len(parts) > 1 else ""
        reason = parts[2].strip() if len(parts) > 2 else "Rejected via Telegram"
        if not token:
            return "Include recommendation ID, e.g. /approve rec-... or /reject rec-... <reason>."

        async def _resolve_recommendation_id(value: str) -> str:
            try:
                from app.database.repositories import get_recommendation_repository

                repo = get_recommendation_repository()
                return await repo.resolve_id_prefix(value)
            except Exception:
                return ""
            return ""

        rec_id = await _resolve_recommendation_id(token)
        if not rec_id:
            return f"Recommendation '{token}' not found. Use the full recommendation ID."

        if action == "APPROVE":
            result = await execute_approved_recommendation(
                recommendation_id=rec_id,
                approved_by=f"telegram:{telegram_user_id}",
                notes="Approved via Telegram fallback",
            )
            if result.get("success"):
                return f"Recommendation {rec_id[:8]} executed successfully."
            return f"Could not execute {rec_id[:8]}: {result.get('error_message') or 'unknown error'}"

        result = await reject_recommendation(
            recommendation_id=rec_id,
            rejected_by=f"telegram:{telegram_user_id}",
            reason=reason,
        )
        if result.get("success"):
            return f"Recommendation {rec_id[:8]} rejected: {reason}"
        return f"Could not reject {rec_id[:8]}: {result.get('error_message') or 'unknown error'}"

    except ImportError:
        logger.debug("LangGraph not available for Telegram recommendation approvals")
        return None
    except Exception as e:
        logger.warning(f"Telegram recommendation approval error: {e}")
        return None
