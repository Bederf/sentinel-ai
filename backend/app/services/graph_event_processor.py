"""Graph Event Processor — processes Microsoft Graph webhook notifications.

Handles:
- Fetching full event details from Graph API after a webhook notification
- Extracting external attendees and creating/updating/cancelling visits
- Idempotency via external_event_id (Graph event ID stored on visit)

Env vars:
    OUTLOOK_CLIENT_ID       — Azure app client ID
    OUTLOOK_CLIENT_SECRET   — Azure app client secret
    OUTLOOK_TENANT_ID       — Azure tenant ID
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.database.repositories.visit_repository import BuildingMapRepository, VisitRepository
from app.models.visit import Visit, VisitStatus
from app.services.visit_token_service import VisitTokenService

logger = logging.getLogger(__name__)

# Shared internal email domains (mirrors OutlookCalendarService)
INTERNAL_DOMAINS = {"fnb.co.za", "sentinel.bms"}


def _is_external_email(email: str) -> bool:
    """Return True if email domain is not in the internal domain list."""
    if not email or "@" not in email:
        return True
    domain = email.split("@")[1].lower()
    return domain not in INTERNAL_DOMAINS


def _get_external_attendees(attendees: list[dict]) -> list[dict]:
    """Return all external attendee dicts from an attendee list."""
    return [a for a in attendees if _is_external_email(a.get("emailAddress", {}).get("address", ""))]


async def process_graph_event(change_type: str, event_id: str) -> None:
    """Process a Graph event notification.

    Args:
        change_type: "created", "updated", or "deleted"
        event_id: The Graph event ID extracted from the webhook resource path
    """
    repo = VisitRepository()
    building_map_repo = BuildingMapRepository()
    token_service = VisitTokenService(repo=repo)

    # Fetch full event from Graph API
    event = await _fetch_graph_event(event_id)
    if event is None:
        logger.warning("[GraphEvent] Could not fetch event %s", event_id)
        return

    attendees: list[dict] = event.get("attendees", [])
    external = _get_external_attendees(attendees)

    if not external:
        logger.debug("[GraphEvent] No external attendees in event %s — skipping", event_id)
        return

    # Extract fields
    host_email = event.get("organizer", {}).get("emailAddress", {}).get("address", "")
    location_text = event.get("location", {}).get("displayName", "") or ""
    subject = event.get("subject", "Visit")

    start_str = event.get("start", {}).get("dateTime", "")
    end_str = event.get("end", {}).get("dateTime", "")
    try:
        meeting_start = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        meeting_start = datetime.now(UTC)
    try:
        meeting_end = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        meeting_end = meeting_start

    building_id = _resolve_building(location_text, building_map_repo)

    if change_type == "created":
        _handle_event_created(
            repo=repo,
            token_service=token_service,
            event_id=event_id,
            host_email=host_email,
            subject=subject,
            external=external,
            building_id=building_id,
            meeting_start=meeting_start,
            meeting_end=meeting_end,
        )
    elif change_type == "updated":
        await _handle_event_updated(
            repo=repo,
            event_id=event_id,
            host_email=host_email,
            subject=subject,
            building_id=building_id,
            meeting_start=meeting_start,
            meeting_end=meeting_end,
        )
    elif change_type == "deleted":
        _handle_event_deleted(repo=repo, event_id=event_id)


# ---------------------------------------------------------------------------
# Graph API fetch
# ---------------------------------------------------------------------------


async def _fetch_graph_event(event_id: str) -> dict | None:
    """Fetch a single event from Microsoft Graph by ID.

    Raises:
        TokenAuthError: caller should not retry (credentials problem)
        TokenError: caller should retry later (rate-limit or transient)
    """
    try:
        token = _acquire_token()
    except TokenAuthError:
        # Credentials are invalid — don't retry, don't spam the log
        logger.error("[GraphEvent] Token auth error for event %s — credentials must be fixed", event_id)
        return None
    except TokenError:
        # Rate-limit or transient MSAL error — log at ERROR (unlike warning for 404)
        logger.error("[GraphEvent] Token acquisition failed for event %s — will retry on next webhook", event_id)
        return None

    if not token:
        # Missing config — no point retrying
        return None

    import httpx

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"https://graph.microsoft.com/v1.0/me/events/{event_id}",
                headers={"Authorization": f"Bearer {token}"},
                params={"$select": "id,subject,start,end,location,attendees,organizer"},
            )
            if response.status_code == 404:
                logger.warning("[GraphEvent] Event %s not found", event_id)
                return None
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 401:
            # Token may have expired between acquire and use — log ERROR
            logger.error("[GraphEvent] 401 fetching event %s — token may be expired", event_id)
        elif status == 429:
            # Rate-limited — log ERROR so it surfaces in monitoring
            logger.error("[GraphEvent] 429 rate-limited fetching event %s — will retry on next webhook", event_id)
        else:
            logger.error("[GraphEvent] HTTP error fetching event %s: %s", event_id, status)
        return None
    except Exception as exc:
        logger.error("[GraphEvent] Error fetching event %s: %s", event_id, exc)
        return None


class TokenError(Exception):
    """Raised when token acquisition fails in a way that should trigger retry."""

    pass


class TokenAuthError(TokenError):
    """Raised when token acquisition fails due to invalid credentials (401)."""

    pass


def _acquire_token() -> str | None:
    """Acquire a Microsoft Graph access token using client credentials flow.

    Returns:
        str: valid access token
        None: non-retryable failure (missing config, import error)
        Raises TokenAuthError: for 401 credential errors
        Raises TokenError: for 429 rate-limit or other retryable errors
    """
    import os

    client_id = os.getenv("OUTLOOK_CLIENT_ID", "").strip()
    client_secret = os.getenv("OUTLOOK_CLIENT_SECRET", "").strip()
    tenant_id = os.getenv("OUTLOOK_TENANT_ID", "").strip()

    if not all([client_id, client_secret, tenant_id]):
        return None

    try:
        from msal import ConfidentialClientApplication
    except ImportError:
        return None

    app = ConfidentialClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        client_credential=client_secret,
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])

    # Check for error response before assuming success
    if "access_token" not in result:
        error = result.get("error", "unknown")
        error_desc = result.get("error_description", "no description")
        if error == "invalid_client":
            # 401 — credentials are wrong or app is not authorized
            raise TokenAuthError(f"Graph API auth failed ({error}): {error_desc}")
        # 429 rate-limit or other MSAL error — log at ERROR and signal retry
        raise TokenError(f"Graph API token error ({error}): {error_desc}")

    return result["access_token"]


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------


def _handle_event_created(
    repo: VisitRepository,
    token_service: VisitTokenService,
    event_id: str,
    host_email: str,
    subject: str,
    external: list[dict],
    building_id: str,
    meeting_start: datetime,
    meeting_end: datetime,
) -> None:
    """Create a visit for a new external-attendee calendar event."""
    # Idempotency: skip if visit with this external_event_id already exists
    existing = repo.get_visit_by_external_event_id(event_id)
    if existing is not None:
        logger.info("[GraphEvent] Visit for event %s already exists (id=%s) — skipping", event_id, existing.id)
        return

    # Use the first external attendee as the visitor
    visitor = external[0]
    visitor_email = visitor.get("emailAddress", {}).get("address", "")
    if not visitor_email:
        logger.warning("[GraphEvent] External attendee has no email address in event %s", event_id)
        return

    token = token_service.generate_token()
    pin = token_service.generate_pin()
    qr_code = token_service.generate_qr_code(token)
    now = datetime.now(UTC)

    visit = Visit(
        id=token,
        token=token,
        pin=pin,
        visitor_email=visitor_email,
        host_email=host_email,
        host_name=host_email,  # Will be enriched by AD lookup in email service
        building_id=building_id,
        meeting_subject=subject,
        meeting_start=meeting_start,
        meeting_end=meeting_end,
        status=VisitStatus.PENDING,  # Accept-first: QR held until visitor accepts invite
        qr_code=qr_code,
        created_at=now,
        updated_at=now,
        external_event_id=event_id,
    )

    try:
        repo.create_visit(visit)
    except ValueError as exc:
        # Token/pin collision — log and skip
        logger.error("[GraphEvent] Could not create visit for event %s: %s", event_id, exc)
        return

    logger.info("[GraphEvent] Created PENDING Visit %s for event %s (visitor %s) — QR held until RSVP accepted", visit.id, event_id, visitor_email)
    # NOTE: QR email is NOT sent here. Visitor must accept the invite first.
    # When visitor accepts via their calendar client, Graph sends an "updated" notification
    # with the attendee PARTSTAT=ACCEPTED, which triggers RSVP processing.


async def _handle_event_updated(
    repo: VisitRepository,
    event_id: str,
    host_email: str,
    subject: str,
    building_id: str,
    meeting_start: datetime,
    meeting_end: datetime,
) -> None:
    """Update an existing visit when its calendar event is modified.

    Also detects visitor RSVP acceptance: when the visitor's partStat changes to "accepted",
    the visit transitions from PENDING -> CREATED and the QR confirmation email is sent.
    """
    existing = repo.get_visit_by_external_event_id(event_id)
    if existing is None:
        logger.debug("[GraphEvent] No existing visit for event %s — treating as created", event_id)
        return

    # Check if visitor has accepted — re-fetch event to get latest attendee status
    attendee_accepted = await _check_rsvp_accepted(event_id, existing.visitor_email)
    if attendee_accepted and existing.status == VisitStatus.PENDING.value:
        # Visitor accepted — transition to CREATED and send QR email
        updated = repo.update_visit(existing.id, {"status": VisitStatus.CREATED})
        logger.info("[GraphEvent] Visit %s ACCEPTED by visitor — QR email will be sent", existing.id)
        try:
            from app.services.visitor_email_service import VisitorEmailService
            email_svc = VisitorEmailService()
            email_svc.send_visitor_confirmation(updated or existing)
        except Exception as exc:
            logger.error("[GraphEvent] Failed to send QR email for %s: %s", existing.id, exc)
        return

    # Normal event update — just sync the fields
    updates: dict = {
        "host_email": host_email,
        "meeting_subject": subject,
        "building_id": building_id,
        "meeting_start": meeting_start.isoformat(),
        "meeting_end": meeting_end.isoformat(),
    }

    updated = repo.update_visit(existing.id, updates)
    if updated:
        logger.info("[GraphEvent] Updated Visit %s for event %s", updated.id, event_id)
    else:
        logger.warning("[GraphEvent] Failed to update Visit for event %s", event_id)


async def _check_rsvp_accepted(event_id: str, visitor_email: str) -> bool:
    """Re-fetch event from Graph and check if visitor's partStat is 'accepted'."""
    token = _acquire_token()  # Uses cached token, safe to call from async
    if not token:
        return False

    import httpx
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"https://graph.microsoft.com/v1.0/me/events/{event_id}",
                headers={"Authorization": f"Bearer {token}"},
                params={"$select": "attendees"},
            )
            if response.status_code == 404:
                return False
            response.raise_for_status()
            event = response.json()
    except Exception:
        return False

    attendees = event.get("attendees", [])
    for a in attendees:
        email = a.get("emailAddress", {}).get("address", "").lower()
        if email == visitor_email.lower():
            if _is_external_email(email):
                # External attendee — check responseStatus
                response_status = a.get("responseStatus", {})
                if response_status.get("response") == "accepted":
                    return True
    return False


def _handle_event_deleted(repo: VisitRepository, event_id: str) -> None:
    """Cancel a visit when its calendar event is deleted."""
    existing = repo.get_visit_by_external_event_id(event_id)
    if existing is None:
        logger.debug("[GraphEvent] No visit found for deleted event %s", event_id)
        return

    # Only cancel if not already completed
    if existing.status in (VisitStatus.EXPIRED.value, VisitStatus.CANCELLED.value):
        logger.debug("[GraphEvent] Visit %s already %s — no action", existing.id, existing.status)
        return

    updated = repo.update_visit(existing.id, {"status": VisitStatus.CANCELLED.value})
    if updated:
        logger.info("[GraphEvent] Cancelled Visit %s for deleted event %s", updated.id, event_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_building(location_text: str, building_map_repo: BuildingMapRepository) -> str:
    """Resolve an Outlook location string to a building site_id."""
    if not location_text:
        return "site-001"

    mapping = building_map_repo.get_building_map_by_outlook_location(location_text)
    if mapping is not None:
        return mapping.site_id

    # Case-insensitive fallback
    mapping = building_map_repo.get_building_map_by_outlook_location(location_text.strip().upper())
    if mapping is not None:
        return mapping.site_id

    logger.debug("No building map for location '%s', defaulting to site-001", location_text)
    return "site-001"
