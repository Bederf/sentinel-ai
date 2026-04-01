"""Graph Subscription Service — Microsoft Graph webhook subscription lifecycle.

Handles:
- Creating Graph webhook subscriptions for Outlook calendar events
- Renewing subscriptions before expiry (72h max, renew at 24h remaining)
- Loading/storing subscriptions in a local JSON file

Env vars:
    GRAPH_WEBHOOK_URL         — Public webhook URL for Graph to call
    OUTLOOK_CLIENT_ID         — Azure app client ID
    OUTLOOK_CLIENT_SECRET     — Azure app client secret
    OUTLOOK_TENANT_ID         — Azure tenant ID
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# Subscription store path
DATA_DIR = Path(__file__).parent.parent.parent / "data"
SUBSCRIPTION_STORE_PATH = DATA_DIR / "graph_subscription_store.json"

RENEWAL_WINDOW_HOURS = 24  # Renew if < 24 hours remaining
MAX_SUBSCRIPTION_DAYS = 3  # Graph max is 3 days


@dataclass
class GraphSubscription:
    subscription_id: str
    expiration_datetime: datetime
    client_state: str
    resource: str

    def is_valid(self) -> bool:
        """Return True if subscription has not yet expired."""
        return self.expiration_datetime > datetime.now(UTC)


class GraphSubscriptionService:
    """Manages Microsoft Graph webhook subscriptions for Outlook calendar events."""

    def __init__(self) -> None:
        self._subscription: GraphSubscription | None = None
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Token acquisition                                                  #
    # ------------------------------------------------------------------ #

    def _acquire_token(self) -> str | None:
        """Acquire a Microsoft Graph access token using client credentials flow."""
        client_id = os.getenv("OUTLOOK_CLIENT_ID", "").strip()
        client_secret = os.getenv("OUTLOOK_CLIENT_SECRET", "").strip()
        tenant_id = os.getenv("OUTLOOK_TENANT_ID", "").strip()

        if not all([client_id, client_secret, tenant_id]):
            logger.warning(
                "Graph subscription service: OUTLOOK_CLIENT_ID, OUTLOOK_CLIENT_SECRET, "
                "or OUTLOOK_TENANT_ID not set — cannot acquire token"
            )
            return None

        try:
            from msal import ConfidentialClientApplication
        except ImportError:
            logger.warning("msal not installed — Graph subscription unavailable")
            return None

        app = ConfidentialClientApplication(
            client_id,
            client_authority=f"https://login.microsoftonline.com/{tenant_id}",
            client_credential=client_secret,
        )
        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        if "access_token" not in result:
            logger.warning("Failed to acquire MSGraph token: %s", result.get("error_description"))
            return None

        return result["access_token"]

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #

    async def get_or_create_subscription(self) -> GraphSubscription | None:
        """Return existing valid subscription, or create a new one."""
        existing = self._load_subscription()
        if existing and existing.expiration_datetime > datetime.now(UTC) + timedelta(hours=RENEWAL_WINDOW_HOURS):
            logger.debug(
                "Graph subscription %s still valid until %s", existing.subscription_id, existing.expiration_datetime
            )
            return existing

        logger.info("No valid Graph subscription found — creating new one")
        return await self._create_subscription()

    async def renew_subscription_if_needed(self) -> bool:
        """Renew the stored subscription if within the renewal window.

        Returns True if renewal was attempted (success or not).
        Returns False if no stored subscription exists.
        """
        stored = self._load_subscription()
        if not stored:
            logger.debug("No stored Graph subscription to renew")
            return False

        if stored.expiration_datetime > datetime.now(UTC) + timedelta(hours=RENEWAL_WINDOW_HOURS):
            logger.debug("Graph subscription not yet due for renewal (expires %s)", stored.expiration_datetime)
            return True  # Not an error — just nothing to do

        return await self._renew_subscription(stored)

    def get_subscription(self) -> GraphSubscription | None:
        """Return the stored subscription if one exists."""
        return self._load_subscription()

    # ------------------------------------------------------------------ #
    # Internal — subscription lifecycle                                  #
    # ------------------------------------------------------------------ #

    async def _create_subscription(self) -> GraphSubscription | None:
        """POST to Microsoft Graph /subscriptions endpoint to create a new subscription."""
        token = self._acquire_token()
        if not token:
            logger.error("Cannot create Graph subscription — no access token")
            return None

        client_state = secrets.token_urlsafe(32)
        expiration = datetime.now(UTC) + timedelta(days=MAX_SUBSCRIPTION_DAYS)
        notification_url = os.getenv("GRAPH_WEBHOOK_URL", "").strip()

        if not notification_url:
            logger.error("GRAPH_WEBHOOK_URL not set — cannot create subscription")
            return None

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://graph.microsoft.com/v1.0/subscriptions",
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "changeType": "created,updated,deleted",
                        "notificationUrl": notification_url,
                        "resource": "me/events",
                        "expirationDateTime": expiration.isoformat(),
                        "clientState": client_state,
                    },
                )
                response.raise_for_status()
                data = response.json()

        except httpx.HTTPStatusError as exc:
            logger.error("Graph subscription create failed (HTTP %s): %s", exc.response.status_code, exc.response.text)
            return None
        except Exception as exc:
            logger.error("Graph subscription create failed: %s", exc)
            return None

        sub = GraphSubscription(
            subscription_id=data["subscriptionId"],
            expiration_datetime=datetime.fromisoformat(data["expirationDateTime"].replace("Z", "+00:00")),
            client_state=client_state,
            resource="me/events",
        )
        self._save_subscription(sub)
        self._subscription = sub
        logger.info("Graph subscription created: id=%s expires=%s", sub.subscription_id, sub.expiration_datetime)
        return sub

    async def _renew_subscription(self, stored: GraphSubscription) -> bool:
        """PATCH to Microsoft Graph to renew an existing subscription."""
        token = self._acquire_token()
        if not token:
            logger.error("Cannot renew Graph subscription — no access token")
            return False

        notification_url = os.getenv("GRAPH_WEBHOOK_URL", "").strip()
        new_expiration = datetime.now(UTC) + timedelta(days=MAX_SUBSCRIPTION_DAYS)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.patch(
                    f"https://graph.microsoft.com/v1.0/subscriptions/{stored.subscription_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "expirationDateTime": new_expiration.isoformat(),
                        "notificationUrl": notification_url,
                        "clientState": stored.client_state,
                    },
                )
                response.raise_for_status()
                data = response.json()

        except httpx.HTTPStatusError as exc:
            logger.error("Graph subscription renew failed (HTTP %s): %s", exc.response.status_code, exc.response.text)
            return False
        except Exception as exc:
            logger.error("Graph subscription renew failed: %s", exc)
            return False

        renewed = GraphSubscription(
            subscription_id=data["subscriptionId"],
            expiration_datetime=datetime.fromisoformat(data["expirationDateTime"].replace("Z", "+00:00")),
            client_state=data.get("clientState", stored.client_state),
            resource=data.get("resource", stored.resource),
        )
        self._save_subscription(renewed)
        logger.info("Graph subscription renewed until %s", renewed.expiration_datetime)
        return True

    # ------------------------------------------------------------------ #
    # Persistence                                                        #
    # ------------------------------------------------------------------ #

    def _load_subscription(self) -> GraphSubscription | None:
        """Load subscription from JSON store."""
        if not SUBSCRIPTION_STORE_PATH.exists():
            return None
        try:
            with open(SUBSCRIPTION_STORE_PATH) as f:
                data = json.load(f)
            return GraphSubscription(
                subscription_id=data["subscription_id"],
                expiration_datetime=datetime.fromisoformat(data["expiration_datetime"]),
                client_state=data["client_state"],
                resource=data["resource"],
            )
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.warning("Failed to load Graph subscription store: %s", exc)
            return None

    def _save_subscription(self, sub: GraphSubscription) -> None:
        """Atomically write subscription to JSON store."""
        data = {
            "subscription_id": sub.subscription_id,
            "expiration_datetime": sub.expiration_datetime.isoformat(),
            "client_state": sub.client_state,
            "resource": sub.resource,
        }
        dirname = SUBSCRIPTION_STORE_PATH.parent
        with tempfile.NamedTemporaryFile(mode="w", dir=dirname, delete=False) as tmp:
            json.dump(data, tmp, indent=2)
            tmp_path = Path(tmp.name)
        shutil.move(str(tmp_path), str(SUBSCRIPTION_STORE_PATH))
        self._subscription = sub


# Singleton instance
graph_subscription_service = GraphSubscriptionService()
