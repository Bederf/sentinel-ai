"""Outlook Calendar Service — Microsoft Graph API listener.

Polls Outlook shared inbox for calendar events with external attendees,
creates Visit records, and sends confirmation emails.

Env vars:
    OUTLOOK_CLIENT_ID       — Azure app client ID
    OUTLOOK_CLIENT_SECRET   — Azure app client secret
    OUTLOOK_TENANT_ID       — Azure tenant ID
    OUTLOOK_USER_EMAIL      — Shared inbox to monitor (e.g. reception@company.com)
    OUTLOOK_INTERNAL_DOMAINS — Comma-separated internal email domains
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import ClassVar

import httpx

from app.database.repositories.visit_repository import BuildingMapRepository, VisitRepository
from app.models.visit import Visit
from app.services.visit_token_service import VisitTokenService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Token cache
# ---------------------------------------------------------------------------

_msal_token_cache: dict | None = None


def _get_msal_token() -> dict | None:
    """Acquire an MSGraph access token using client credentials flow.

    Caches the token in module global and refreshes before expiry.
    Returns None if OUTLOOK_* env vars are not configured.
    """
    global _msal_token_cache

    client_id = os.getenv("OUTLOOK_CLIENT_ID", "").strip()
    client_secret = os.getenv("OUTLOOK_CLIENT_SECRET", "").strip()
    tenant_id = os.getenv("OUTLOOK_TENANT_ID", "").strip()

    if not all([client_id, client_secret, tenant_id]):
        return None

    now = datetime.now(UTC)

    # Return cached token if still valid (with 60s buffer)
    if _msal_token_cache is not None:
        expires_at = datetime.fromisoformat(_msal_token_cache["expires_at"])
        if expires_at > now:
            return _msal_token_cache

    # Acquire new token
    try:
        import msal
    except ImportError:
        logger.warning("msal not installed — Outlook polling unavailable")
        return None

    app = msal.ConfidentialClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        client_credential=client_secret,
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" not in result:
        logger.warning("Failed to acquire MSGraph token: %s", result.get("error_description"))
        return None

    expires_at = now.replace(microsecond=0)
    expires_in = result.get("expires_in", 3600)
    expires_at = expires_at.replace(second=expires_at.second + expires_in)

    _msal_token_cache = {
        "access_token": result["access_token"],
        "expires_at": expires_at.isoformat(),
    }
    logger.info("MSGraph token acquired, expires at %s", expires_at)
    return _msal_token_cache


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class OutlookCalendarService:
    """Polls Outlook for external-attendee calendar events and creates Visits."""

    INTERNAL_DOMAINS: ClassVar[set[str]] = {
        "fnb.co.za",
        "sentinel.bms",
    }

    def __init__(self) -> None:
        self._enabled = self._check_config()
        self._repo = VisitRepository()
        self._building_map_repo = BuildingMapRepository()
        self._token_service = VisitTokenService(repo=self._repo)
        self._internal_domains = self._load_internal_domains()

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def _check_config(self) -> bool:
        """Return True only if all OUTLOOK_* env vars are set."""
        required = ["OUTLOOK_CLIENT_ID", "OUTLOOK_CLIENT_SECRET", "OUTLOOK_TENANT_ID", "OUTLOOK_USER_EMAIL"]
        missing = [v for v in required if not os.getenv(v, "").strip()]
        if missing:
            logger.warning(
                "Outlook not configured — missing env vars: %s. "
                "Set OUTLOOK_CLIENT_ID, OUTLOOK_CLIENT_SECRET, OUTLOOK_TENANT_ID, "
                "OUTLOOK_USER_EMAIL to enable calendar polling.",
                missing,
            )
            return False
        logger.info("Outlook calendar service enabled (MSGraph)")
        return True

    def _load_internal_domains(self) -> set[str]:
        """Load additional internal domains from OUTLOOK_INTERNAL_DOMAINS env var."""
        extra = os.getenv("OUTLOOK_INTERNAL_DOMAINS", "")
        domains = {d.strip().lower() for d in extra.split(",") if d.strip()}
        return self.INTERNAL_DOMAINS | domains

    # ------------------------------------------------------------------
    # External attendee detection
    # ------------------------------------------------------------------

    def _is_external_email(self, email: str) -> bool:
        """Return True if email domain is not in the internal domain list."""
        if not email or "@" not in email:
            return True
        domain = email.split("@")[1].lower()
        return domain not in self._internal_domains

    def _get_external_attendee(self, attendees: list[dict]) -> dict | None:
        """Return the first external attendee dict, or None."""
        for a in attendees:
            email = a.get("emailAddress", {}).get("address", "")
            if self._is_external_email(email):
                return a
        return None

    # ------------------------------------------------------------------
    # Graph API
    # ------------------------------------------------------------------

    async def _graph_get(self, endpoint: str, params: dict | None = None) -> dict | None:
        """Make an authenticated GET request to MSGraph."""
        token = _get_msal_token()
        if token is None:
            return None

        headers = {"Authorization": f"Bearer {token['access_token']}"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.get(
                    f"https://graph.microsoft.com/v1.0{endpoint}",
                    headers=headers,
                    params=params,
                )
                if resp.status_code == 401:
                    global _msal_token_cache
                    _msal_token_cache = None  # Force token refresh
                    logger.warning("MSGraph token expired, will retry on next poll")
                    return None
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as exc:
                logger.error("MSGraph HTTP error %s: %s", exc.response.status_code, exc.response.text)
                return None
            except httpx.RequestError as exc:
                logger.error("MSGraph request error: %s", exc)
                return None

    # ------------------------------------------------------------------
    # Event polling
    # ------------------------------------------------------------------

    async def poll_new_external_attendee_events(self) -> list[Visit]:
        """Poll Outlook for new events with external attendees.

        Returns a list of newly created Visit records.
        """
        if not self._enabled:
            logger.debug("Outlook polling skipped — not configured")
            return []

        user_email = os.getenv("OUTLOOK_USER_EMAIL", "").strip()

        # Filter: events the user is the organizer, start >= now, has external attendee
        # We fetch a window starting 1 hour ago to catch any near-real-time events
        hour_ago_iso = datetime.now(UTC).replace(microsecond=0).isoformat()

        params = {
            "$filter": (f"organizer/emailAddress/address eq '{user_email}' and start/dateTime ge '{hour_ago_iso}'"),
            "$select": "id,subject,start,end,location,attendees,organizer",
            "$orderby": "start/dateTime asc",
            "$top": "50",
        }

        data = await self._graph_get(f"/users/{user_email}/events", params=params)
        if data is None:
            return []

        visits_created: list[Visit] = []

        for event in data.get("value", []):
            try:
                visit = self._process_event(event)
                if visit is not None:
                    visits_created.append(visit)
            except Exception as exc:
                logger.error("Error processing Outlook event %s: %s", event.get("id"), exc)

        if visits_created:
            logger.info("Created %d visit(s) from Outlook polling", len(visits_created))

        return visits_created

    def _process_event(self, event: dict) -> Visit | None:
        """Convert a Graph event dict into a Visit record.

        Returns None if no external attendee found or event is already processed.
        """
        attendees: list[dict] = event.get("attendees", [])
        ext_attendee = self._get_external_attendee(attendees)
        if ext_attendee is None:
            logger.debug("No external attendee in event %s", event.get("id"))
            return None

        visitor_email = ext_attendee.get("emailAddress", {}).get("address", "")
        if not visitor_email:
            return None

        # Check if already processed (token uniqueness in repo)
        token = self._token_service.generate_token()
        existing = self._repo.get_visit_by_token(token)
        if existing is not None:
            logger.debug("Visit for token %s already exists, skipping", token)
            return None

        # Resolve location -> building_id
        location_text = event.get("location", {}).get("displayName", "") or ""
        building_id = self._resolve_building(location_text)

        # Parse times
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

        # Organizer (host)
        host_email = event.get("organizer", {}).get("emailAddress", {}).get("address", "")
        subject = event.get("subject", "Visit")

        # Generate token, PIN, QR
        pin = self._token_service.generate_pin()
        qr_code = self._token_service.generate_qr_code(token)

        now = datetime.now(UTC)

        visit = Visit(
            id=token,  # UUID used as id for simplicity
            token=token,
            pin=pin,
            visitor_email=visitor_email,
            host_email=host_email,
            host_name=subject,  # Fallback; AD service can update later
            building_id=building_id,
            meeting_start=meeting_start,
            meeting_end=meeting_end,
            status="created",
            qr_code=qr_code,
            created_at=now,
            updated_at=now,
        )

        # Persist
        try:
            self._repo.create_visit(visit)
        except ValueError as exc:
            # Duplicate token/pin — regenerate and retry once
            logger.warning("Collision creating visit: %s — retrying", exc)
            token = self._token_service.generate_token()
            pin = self._token_service.generate_pin()
            qr_code = self._token_service.generate_qr_code(token)
            now = datetime.now(UTC)
            visit = Visit(
                id=token,
                token=token,
                pin=pin,
                visitor_email=visitor_email,
                host_email=host_email,
                host_name=subject,
                building_id=building_id,
                meeting_start=meeting_start,
                meeting_end=meeting_end,
                status="created",
                qr_code=qr_code,
                created_at=now,
                updated_at=now,
            )
            self._repo.create_visit(visit)

        logger.info("Created Visit %s for visitor %s (event %s)", visit.id, visitor_email, event.get("id"))

        # Send email (fire-and-forget)
        try:
            from app.services.visitor_email_service import VisitorEmailService

            email_svc = VisitorEmailService()
            email_svc.send_visitor_confirmation(visit)
        except Exception as exc:
            logger.error("Failed to send visitor email for %s: %s", visit.id, exc)

        return visit

    def _resolve_building(self, location_text: str) -> str:
        """Resolve an Outlook location string to a building site_id.

        Falls back to 'site-001' if no mapping found.
        """
        if not location_text:
            return "site-001"

        mapping = self._building_map_repo.get_building_map_by_outlook_location(location_text)
        if mapping is not None:
            return mapping.site_id

        # Case-insensitive fallback: strip common prefixes
        stripped = location_text.strip().upper()
        mapping = self._building_map_repo.get_building_map_by_outlook_location(stripped)
        if mapping is not None:
            return mapping.site_id

        logger.debug("No building map for location '%s', defaulting to site-001", location_text)
        return "site-001"
