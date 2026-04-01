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

import base64
import hashlib
import hmac
import logging
import os

from fastapi import APIRouter, Form, Header, HTTPException, Request, Response
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


def _verify_twilio_signature(request_url: str, params: dict[str, str], signature: str | None) -> bool:
    """Verify Twilio HMAC-SHA1 signature on incoming webhook requests."""
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
    if not auth_token:
        # No token configured — skip verification (dev/demo mode)
        return True
    if not signature:
        return False
    payload = request_url + "".join(f"{key}{params[key]}" for key in sorted(params))
    digest = hmac.new(auth_token.encode("utf-8"), payload.encode("utf-8"), hashlib.sha1).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)


@router.post("/reply")
async def handle_visit_reply(
    request: Request,
    Body: str = Form(...),
    From: str = Form(...),
    X_Twilio_Signature: str | None = Header(default=None, alias="X-Twilio-Signature"),
) -> Response:
    """Handle YES/NO WhatsApp reply from host.

    Twilio sends Form data:
    - Body: message text ("YES" or "NO")
    - From: sender mobile number

    Protected by Twilio HMAC-SHA1 signature verification.
    """
    # Step 0: verify Twilio signature
    form_data = await request.form()
    params = {k: v for k, v in form_data.items() if isinstance(v, str)}
    public_base = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    request_url = f"{public_base}/api/whatsapp/whatsapp/visit/reply" if public_base else str(request.url)
    if not _verify_twilio_signature(request_url, params, X_Twilio_Signature):
        logger.warning("[WhatsApp Visit] Invalid Twilio signature — rejecting request")
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

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

    # Step 3: find most recent active visit for this host — ATOMIC UPDATE
    # Use a conditional update: only succeeds if visit is in expected status range.
    # This eliminates the read-then-write race condition.
    repo = VisitRepository()
    eligible_statuses = [VisitStatus.REGISTERED.value, VisitStatus.ARRIVED.value, VisitStatus.CREATED.value]

    # Try to atomically claim this visit by updating with a status filter
    visit = None
    for _attempt in range(3):  # up to 3 attempts to find an eligible visit
        visits = repo.list_active_visits()
        host_visits = [
            v for v in visits if v.host_email.lower() == host_email.lower() and v.status in eligible_statuses
        ]
        if not host_visits:
            break
        # Pick the most recent by created_at
        host_visits.sort(key=lambda v: v.created_at, reverse=True)
        candidate = host_visits[0]

        # Atomic conditional update — only succeeds if status hasn't changed
        new_status = VisitStatus.APPROVED.value if decision == "YES" else VisitStatus.DENIED.value
        updated = repo.update_visit_with_status_check(
            candidate.id,
            new_status,
            candidate.status,
        )
        if updated is not None:
            visit = updated
            break
        # Status changed concurrently — retry with remaining visits (remove the one we just tried)
        eligible_statuses = [s for s in eligible_statuses if s != candidate.status.value]
    else:
        # Exhausted all attempts
        pass

    if not visit:
        logger.warning(f"[WhatsApp Visit] No eligible visit found for host {host_email}")
        return _twiml_response("No pending visitor found for your name. Contact reception.")

    # Step 4/5: log audit
    audit = _get_audit_logger()
    audit.log_event(
        VisitEventType.APPROVE if decision == "YES" else VisitEventType.DENY,
        visit_id=str(visit.id),
        details={"host": host_email, "host_name": host.get("name"), "from": from_number},
    )
    logger.info(f"[WhatsApp Visit] Visit {visit.id} {decision} by {host_email}")

    msg = (
        f"\u2705 Approved. Your visitor ({visit.visitor_name or 'guest'}) has been cleared."
        if decision == "YES"
        else f"\u274c Access denied. Your visitor ({visit.visitor_name or 'guest'}) will not be admitted."
    )
    return _twiml_response(msg)


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
