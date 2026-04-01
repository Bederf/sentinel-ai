"""WhatsApp Visit Reply Webhook — receives YES/NO from hosts via Twilio.

POST /whatsapp/visit/reply
  Input (from Twilio): Body=single word "YES" or "NO", From=host mobile number
  Logic:
  1. Parse Body.strip().upper()
  2. Look up host by mobile number in host_directory.json (reverse lookup)
  3. Find most recent ACTIVE visit for this host (status == REGISTERED or ARRIVED)
  4. If YES:
     - Update visit status to APPROVED
     - Log audit event
  5. If NO:
     - Update visit status to DENIED
     - Log audit event
  6. Reply to host: TwiML "Approved" or "Denied"
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Form, Response
from twilio.twiml import TwiML

from app.database.repositories.visit_repository import VisitRepository
from app.models.visit import VisitStatus
from app.services.active_directory_service import get_active_directory_service
from app.services.visit_audit_logger import VisitAuditLogger, VisitEventType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp/visit", tags=["visitor_management"])

# In-memory repo instance for this request scope
_audit_logger: VisitAuditLogger | None = None


def _get_audit_logger() -> VisitAuditLogger:
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = VisitAuditLogger()
    return _audit_logger


@router.post("/reply")
async def handle_visit_reply(
    Body: str = Form(...),
    From: str = Form(...),
) -> Response:
    """Handle YES/NO WhatsApp reply from host.

    Twilio sends Form data:
    - Body: message text ("YES" or "NO")
    - From: sender mobile number
    """
    # Step 1: parse
    decision = Body.strip().upper()
    if decision not in ("YES", "NO"):
        logger.warning(f"[WhatsApp Visit] Non-decision body: {Body!r}")
        return _twiml_response("Sorry, please reply YES or NO to approve your visitor.")

    from_number = _normalise_mobile(From)
    logger.info(f"[WhatsApp Visit] {decision} from {from_number}")

    # Step 2: look up host by mobile
    ad = get_active_directory_service()
    host = ad.get_host_by_mobile(from_number)
    if not host:
        logger.warning(f"[WhatsApp Visit] Unknown mobile {from_number}, cannot route reply")
        return _twiml_response("Your number is not registered in the visitor system.")

    host_email = host.get("email", "")
    logger.info(f"[WhatsApp Visit] Reply routed to host: {host.get('name')} <{host_email}>")

    # Step 3: find most recent active visit for this host
    repo = VisitRepository()
    visits = repo.list_active_visits()

    # Find visits where host_email matches and status is REGISTERED or ARRIVED
    host_visits = [
        v
        for v in visits
        if v.host_email.lower() == host_email.lower()
        and v.status in (VisitStatus.REGISTERED, VisitStatus.ARRIVED, VisitStatus.CREATED)
    ]
    # Sort by created_at descending, take most recent
    host_visits.sort(key=lambda v: v.created_at, reverse=True)
    visit = host_visits[0] if host_visits else None

    if not visit:
        logger.warning(f"[WhatsApp Visit] No active visit found for host {host_email}")
        return _twiml_response("No pending visitor found for your name. Contact reception.")

    # Steps 4/5: update status
    audit = _get_audit_logger()
    if decision == "YES":
        repo.update_visit(visit.id, {"status": VisitStatus.APPROVED.value})
        audit.log_event(
            VisitEventType.APPROVE,
            visit_id=str(visit.id),
            details={"host": host_email, "host_name": host.get("name"), "from": from_number},
        )
        logger.info(f"[WhatsApp Visit] Visit {visit.id} APPROVED by {host_email}")
        return _twiml_response(f"\u2705 Approved. Your visitor ({visit.visitor_name or 'guest'}) has been cleared.")
    else:  # NO
        repo.update_visit(visit.id, {"status": VisitStatus.DENIED.value})
        audit.log_event(
            VisitEventType.DENY,
            visit_id=str(visit.id),
            details={"host": host_email, "host_name": host.get("name"), "from": from_number},
        )
        logger.info(f"[WhatsApp Visit] Visit {visit.id} DENIED by {host_email}")
        return _twiml_response(
            f"\u274c Access denied. Your visitor ({visit.visitor_name or 'guest'}) will not be admitted."
        )


def _normalise_mobile(mobile: str) -> str:
    """Strip whatsapp: prefix and whitespace from a Twilio From field."""
    return mobile.replace("whatsapp:", "").replace(" ", "").strip()


def _twiml_response(message: str) -> Response:
    """Build a TwiML messaging response with the given text."""
    response = TwiML()
    response.message(body=message)
    return Response(
        content=str(response),
        media_type="application/xml",
    )
