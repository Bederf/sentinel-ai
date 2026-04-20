"""Google Calendar Service — Calendar API + Pub/Sub webhook for visitor intake.

Handles:
- Google Calendar API polling (with auto-refresh of OAuth2 tokens)
- Push notification webhooks via Google Cloud Pub/Sub
- Creating PENDING visits when external attendees are added to events
- Detecting RSVP acceptance and transitioning to CREATED

Env vars:
    GOOGLE_CLIENT_ID      — OAuth2 client ID
    GOOGLE_CLIENT_SECRET  — OAuth2 client secret
    GOOGLE_REFRESH_TOKEN  — OAuth2 refresh token (from gmail_token.json)
    GOOGLE_WEBHOOK_URL    — Public webhook URL for Pub/Sub push (https://bms.sentinel-ai.co.za/api/webhooks/google/calendar)
    GOOGLE_PUBSUB_TOPIC   — Google Cloud Pub/Sub topic for calendar notifications
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials

from app.database.repositories.visit_repository import BuildingMapRepository, VisitRepository
from app.models.visit import Visit, VisitStatus
from app.services.visit_token_service import VisitTokenService

logger = logging.getLogger(__name__)

CREDENTIALS_PATH = Path.home() / ".sentry" / "gateway" / "credentials" / "gmail_token.json"
DATA_DIR = Path(__file__).parent.parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
CHANNEL_STORE_PATH = DATA_DIR / "google_channel_store.json"

INTERNAL_DOMAINS = {"fnb.co.za", "sentinel.bms", "sentinel-ai.co.za"}

# ---------------------------------------------------------------------------
# Token management
# ---------------------------------------------------------------------------


def _load_credentials() -> Credentials | None:
    """Load Google OAuth2 credentials from the sentry gateway token file."""
    if not CREDENTIALS_PATH.exists():
        logger.warning("Google credentials not found at %s", CREDENTIALS_PATH)
        return None
    try:
        creds = Credentials.from_authorized_user_file(str(CREDENTIALS_PATH))
        return creds
    except Exception as exc:
        logger.warning("Failed to load Google credentials: %s", exc)
        return None


def _refresh_access_token() -> dict | None:
    """Refresh the access token using the stored refresh token."""
    creds = _load_credentials()
    if not creds:
        return None

    if creds.expired:
        try:
            creds.refresh(GoogleRequest())
            # Save refreshed credentials manually (creds.to_json() has write issues)
            token_data = {
                "token": creds.token,
                "refresh_token": creds.refresh_token,
                "client_id": creds.client_id,
                "client_secret": creds.client_secret,
                "scopes": list(creds.scopes) if creds.scopes else None,
                "expiry": creds.expiry.isoformat() if creds.expiry else None,
            }
            with open(CREDENTIALS_PATH, "w") as f:
                json.dump(token_data, f, indent=2)
            logger.info("Google access token refreshed and saved")
        except Exception as exc:
            logger.error("Failed to refresh Google access token: %s", exc)
            return None

    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    }


# ---------------------------------------------------------------------------
# Google Calendar API
# ---------------------------------------------------------------------------


def _calendar_get(endpoint: str, params: dict | None = None) -> dict | None:
    """Make an authenticated GET request to the Google Calendar API."""
    token_data = _refresh_access_token()
    if not token_data:
        return None

    headers = {"Authorization": f"Bearer {token_data['token']}"}
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(
                f"https://www.googleapis.com/calendar/v3{endpoint}",
                headers=headers,
                params=params,
            )
            if resp.status_code == 401:
                # Force refresh and retry once
                creds = _load_credentials()
                if creds:
                    creds.refresh(GoogleRequest())
                    token_data = {
                        "token": creds.token,
                        "refresh_token": creds.refresh_token,
                        "client_id": creds.client_id,
                        "client_secret": creds.client_secret,
                        "scopes": list(creds.scopes) if creds.scopes else None,
                        "expiry": creds.expiry.isoformat() if creds.expiry else None,
                    }
                    with open(CREDENTIALS_PATH, "w") as f:
                        json.dump(token_data, f, indent=2)
                    if token_data:
                        headers = {"Authorization": f"Bearer {token_data['token']}"}
                        resp = client.get(
                            f"https://www.googleapis.com/calendar/v3{endpoint}",
                            headers=headers,
                            params=params,
                        )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        logger.error("Google Calendar HTTP error %s: %s", exc.response.status_code, exc.response.text)
        return None
    except Exception as exc:
        logger.error("Google Calendar request error: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Channel/Pub/Sub lifecycle
# ---------------------------------------------------------------------------


def _load_channels() -> dict:
    """Load stored channels from disk."""
    if CHANNEL_STORE_PATH.exists():
        try:
            with open(CHANNEL_STORE_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_channels(channels: dict) -> None:
    """Save channels to disk atomically."""
    tmp_path = CHANNEL_STORE_PATH.with_suffix(".tmp")
    with open(tmp_path, "w") as f:
        json.dump(channels, f, indent=2)
    tmp_path.rename(CHANNEL_STORE_PATH)


def _is_external_email(email: str) -> bool:
    """Return True if email domain is not internal."""
    if not email or "@" not in email:
        return True
    domain = email.split("@")[1].lower()
    return domain not in INTERNAL_DOMAINS


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class GoogleCalendarService:
    """Watches Google Calendar for external-attendee events."""

    def __init__(self) -> None:
        self._repo = VisitRepository()
        self._building_map_repo = BuildingMapRepository()
        self._token_service = VisitTokenService(repo=self._repo)
        self._enabled = _load_credentials() is not None

    def is_enabled(self) -> bool:
        return self._enabled

    # ------------------------------------------------------------------
    # Polling (backup / initial sync)
    # ------------------------------------------------------------------

    def poll_recent_events(self) -> list[Visit]:
        """Poll for recent events with external attendees (backup mechanism)."""
        if not self._enabled:
            return []

        visits: list[Visit] = []
        now = datetime.now(UTC).isoformat()
        min_time = (datetime.now(UTC) - timedelta(hours=24)).isoformat()

        data = _calendar_get(
            "/calendars/primary/events",
            params={
                "timeMin": min_time,
                "timeMax": now,
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": 50,
                "fields": "items(id,summary,start,end,location,attendees,organizer)",
            },
        )
        if not data:
            return []

        for event in data.get("items", []):
            try:
                visit = self._process_event(event)
                if visit:
                    visits.append(visit)
            except Exception as exc:
                logger.error("Error processing Google Calendar event %s: %s", event.get("id"), exc)

        return visits

    # ------------------------------------------------------------------
    # Webhook notification (called by webhook endpoint)
    # ------------------------------------------------------------------

    def handle_webhook_notification(self, notification: dict) -> None:
        """Process a Google Calendar push notification.

        notification format:
          {
            "summary": "...",
            "start": {...},
            "end": {...},
            "attendees": [...],
            "organizer": {...},
            "iCalUID": "...",
          }
        """
        if not self._enabled:
            return

        event_id = notification.get("event_id") or notification.get("id")

        # Re-fetch full event to get current state
        data = _calendar_get(
            f"/calendars/primary/events/{event_id}",
            params={"fields": "id,summary,start,end,location,attendees,organizer,iCalUID"},
        )
        if not data:
            logger.warning("[GoogleCal] Could not fetch event %s from API", event_id)
            return

        try:
            self._process_event(data)
        except Exception as exc:
            logger.error("Error processing Google Calendar event %s: %s", event_id, exc)

    # ------------------------------------------------------------------
    # Event processing
    # ------------------------------------------------------------------

    def _process_event(self, event: dict) -> Visit | None:
        """Convert a Google Calendar event dict into a Visit record.

        Returns None if no external attendee found or event already processed.
        """
        event_id = event.get("id") or event.get("iCalUID")
        if not event_id:
            return None

        # Idempotency check
        existing = self._repo.get_visit_by_external_event_id(f"gcal-{event_id}")
        if existing is not None:
            logger.debug("[GoogleCal] Event %s already processed", event_id)
            return None

        attendees: list[dict] = event.get("attendees", [])
        ext_attendee = None
        for a in attendees:
            email = a.get("email", "")
            if _is_external_email(email):
                ext_attendee = a
                break

        if not ext_attendee:
            logger.debug("[GoogleCal] No external attendee in event %s", event_id)
            return None

        visitor_email = ext_attendee.get("email", "")
        if not visitor_email:
            return None

        # Check RSVP status
        attendee_response = ext_attendee.get("responseStatus", "needsAction")
        visitor_accepted = attendee_response == "accepted"

        # Resolve location -> building_id
        location_text = event.get("location", "") or ""
        building_id = self._resolve_building(location_text)

        # Parse times
        start_info = event.get("start", {})
        end_info = event.get("end", {})
        meeting_start = self._parse_datetime(start_info)
        meeting_end = self._parse_datetime(end_info)

        # Organizer (host)
        organizer = event.get("organizer", {})
        host_email = organizer.get("email", "")
        subject = event.get("summary", "Visit") or "Visit"

        # Generate token, PIN, QR
        token = self._token_service.generate_token()
        pin = self._token_service.generate_pin()
        qr_code = self._token_service.generate_qr_code(token)
        now = datetime.now(UTC)

        # Accept-first: status is PENDING unless visitor already accepted
        status = VisitStatus.CREATED if visitor_accepted else VisitStatus.PENDING

        visit = Visit(
            id=token,
            token=token,
            pin=pin,
            visitor_email=visitor_email,
            host_email=host_email,
            host_name=host_email,
            building_id=building_id,
            meeting_subject=subject,
            meeting_start=meeting_start,
            meeting_end=meeting_end,
            status=status,
            qr_code=qr_code,
            created_at=now,
            updated_at=now,
            external_event_id=f"gcal-{event_id}",
        )

        try:
            self._repo.create_visit(visit)
        except ValueError as exc:
            logger.error("[GoogleCal] Could not create visit for event %s: %s", event_id, exc)
            return None

        logger.info(
            "[GoogleCal] Created %s Visit %s for event %s (visitor %s)", status.value, visit.id, event_id, visitor_email
        )

        # If visitor already accepted, send QR email immediately
        if visitor_accepted:
            try:
                from app.services.visitor_email_service import VisitorEmailService

                email_svc = VisitorEmailService()
                email_svc.send_visitor_confirmation(visit)
            except Exception as exc:
                logger.error("[GoogleCal] Failed to send QR email for %s: %s", visit.id, exc)

        return visit

    def _parse_datetime(self, info: dict) -> datetime:
        """Parse a Google Calendar datetime dict."""
        dateTime = info.get("dateTime") or info.get("date", "")
        if not dateTime:
            return datetime.now(UTC)
        try:
            # Google returns "2026-04-08T11:00:00+02:00" or "2026-04-08" (all-day)
            if "T" in dateTime:
                return datetime.fromisoformat(dateTime)
            else:
                return datetime.fromisoformat(dateTime).replace(tzinfo=UTC)
        except ValueError:
            return datetime.now(UTC)

    def _resolve_building(self, location_text: str) -> str:
        """Resolve a Google Calendar location string to a building site_id."""
        if not location_text:
            return "site-001"
        mapping = self._building_map_repo.get_building_map_by_outlook_location(location_text)
        if mapping:
            return mapping.site_id
        # Case-insensitive fallback
        mapping = self._building_map_repo.get_building_map_by_outlook_location(location_text.strip().upper())
        if mapping:
            return mapping.site_id
        return "site-001"

    # ------------------------------------------------------------------
    # Channel registration (Pub/Sub push)
    # ------------------------------------------------------------------

    async def ensure_channel(self, webhook_url: str) -> bool:
        """Register a Pub/Sub push channel for the primary calendar.

        Creates a Google Cloud Pub/Sub topic (if needed) and sets up
        a watch on the user's primary calendar.
        """
        import uuid

        token_data = _refresh_access_token()
        if not token_data:
            return False

        topic_name = os.getenv("GOOGLE_PUBSUB_TOPIC", "sentinel-calendar-notifications")
        channel_id = str(uuid.uuid4())

        # Create/create Pub/Sub topic
        token = token_data["token"]
        headers = {"Authorization": f"Bearer {token}"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Ensure topic exists
                resp = await client.post(
                    f"https://pubsub.googleapis.com/v1/projects/{self._get_project_id()}/topics/{topic_name}",
                    headers=headers,
                    json={"name": f"projects/{self._get_project_id()}/topics/{topic_name}"},
                )
                # 409 = already exists, which is fine
                if resp.status_code not in (200, 409):
                    logger.error("[GoogleCal] Could not create Pub/Sub topic: %s", resp.status_code)
                    return False

                # Set up calendar watch
                expiration = int((datetime.now(UTC) + timedelta(days=7)).timestamp() * 1000)
                watch_resp = await client.post(
                    "https://www.googleapis.com/calendar/v3/calendars/primary/events/watch",
                    headers=headers,
                    json={
                        "id": channel_id,
                        "type": "web_hook",
                        "address": webhook_url,
                        "expiration": expiration,
                        "params": {
                            "ttl": str(expiration),
                        },
                    },
                )
                watch_data = watch_resp.json()
                if watch_resp.status_code not in (200, 204):
                    logger.error("[GoogleCal] Watch failed: %s", watch_data)
                    return False

                # Store channel
                channels = _load_channels()
                channels[channel_id] = {
                    "channel_id": channel_id,
                    "resource_id": watch_data.get("resourceId", ""),
                    "expiration": watch_data.get("expiration", ""),
                    "topic_name": topic_name,
                }
                _save_channels(channels)
                logger.info("[GoogleCal] Watch channel registered: %s", channel_id)
                return True

        except Exception as exc:
            logger.error("[GoogleCal] Failed to register watch channel: %s", exc)
            return False

    def _get_project_id(self) -> str:
        """Get GCP project ID from the client config."""
        creds = _load_credentials()
        if creds and hasattr(creds, "_project_id"):
            return creds._project_id
        # Fallback: extract from client_id
        # e.g. 255949941418-mdstubtrt9k4sc17ld1k4c9o8do17sa0.apps.googleusercontent.com
        return "aimthelaw-465707"
