"""
Magic Link Service — generates and validates invite tokens, sends invite emails.

Used by the admin invite flow: POST /api/auth/invite creates a token and sends
an email to the invitee with a magic link. POST /api/auth/invite/accept validates
the token and creates the user account with site access.
"""

from __future__ import annotations

import logging
import os
import secrets
from datetime import UTC, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import aiosmtplib
import bcrypt

from app.config.settings import settings
from app.database.repositories.user_repository import get_user_repository
from app.database.repositories.user_site_access_repository import get_user_site_access_repository
from app.middleware.auth_middleware import create_jwt_token

logger = logging.getLogger(__name__)

# Default SMTP settings (same as visitor_email_service)
DEFAULT_SMTP_PORT = 587
DEFAULT_SMTP_USE_TLS = True
INVITE_TOKEN_EXPIRY_HOURS = 48


def _smtp_config() -> dict:
    return {
        "host": os.getenv("SMTP_HOST", "").strip(),
        "port": int(os.getenv("SMTP_PORT", str(DEFAULT_SMTP_PORT))),
        "username": os.getenv("SMTP_USER", "").strip(),
        "password": os.getenv("SMTP_PASSWORD", "").strip(),
        "from_addr": os.getenv("SMTP_FROM", os.getenv("NOTIFICATION_SMTP_USERNAME", "")).strip(),
        "from_name": os.getenv("SMTP_FROM_NAME", "SENTINEL BMS").strip(),
        "use_tls": os.getenv("SMTP_USE_TLS", "true").lower() in ("true", "1", "yes"),
        "dev_log": bool(os.getenv("DEV_EMAIL_LOG", "").strip()),
    }


def _build_invite_email(email: str, full_name: str, invite_link: str, role: str, site_id: str) -> tuple[str, str]:
    """Build invite HTML email. Returns (subject, html_body)."""
    subject = f"You've been invited to SENTINEL — {role.title()} Access"
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
      <div style="background: #0f172a; padding: 24px; border-radius: 8px 8px 0 0;">
        <h1 style="color: #22c55e; margin: 0; font-size: 24px;">SENTINEL BMS</h1>
        <p style="color: #94a3b8; margin: 4px 0 0;">Building Intelligence Platform</p>
      </div>
      <div style="background: #1e293b; padding: 32px; border-radius: 0 0 8px 8px;">
        <p style="color: #f1f5f9; font-size: 16px;">Hi {full_name},</p>
        <p style="color: #cbd5e1; font-size: 14px;">
          You've been invited to join SENTINEL as a <strong style="color: #22c55e;">{role.title()}</strong>
          for site <strong>{site_id}</strong>.
        </p>
        <p style="color: #cbd5e1; font-size: 14px;">Click the button below to set your password and activate your account:</p>
        <div style="text-align: center; margin: 32px 0;">
          <a href="{invite_link}"
             style="display: inline-block; background: #22c55e; color: #fff; padding: 14px 28px;
                    text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 14px;">
            Activate Account
          </a>
        </div>
        <p style="color: #64748b; font-size: 12px;">
          This link expires in 48 hours. If you didn't expect this invitation, you can safely ignore this email.
        </p>
        <hr style="border: none; border-top: 1px solid #334155; margin: 24px 0;">
        <p style="color: #475569; font-size: 11px;">
          SENTINEL — Smart Environment & Telemetry Intelligence for Efficient Living
        </p>
      </div>
    </div>
    """
    return subject, html


def _send_email(to_addr: str, subject: str, html_body: str, config: dict) -> bool:
    """Send an HTML email via SMTP. Returns True on success."""
    if config["dev_log"]:
        logger.info("[DEV_EMAIL_LOG] Would send email to %s: %s", to_addr, subject)
        return True

    if not config["host"] or not config["username"] or not config["password"]:
        logger.warning("SMTP not configured — skipping email send to %s", to_addr)
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{config['from_name']} <{config['from_addr']}>"
    msg["To"] = to_addr

    part = MIMEText(html_body, "html")
    msg.attach(part)

    try:
        aiosmtplib.send(
            msg,
            hostname=config["host"],
            port=config["port"],
            username=config["username"],
            password=config["password"],
            use_tls=not config["use_tls"],
            start_tls=config["use_tls"],
        )
        logger.info("Invite email sent to %s", to_addr)
        return True
    except Exception as e:
        logger.error("Failed to send invite email to %s: %s", to_addr, e)
        return False


class MagicLinkService:
    """Service for magic link invite token lifecycle."""

    def __init__(self) -> None:
        self._user_repo = get_user_repository()
        self._access_repo = get_user_site_access_repository()
        from app.services.session_service import session_service as _sess_svc

        self._session_svc = _sess_svc
        self._smtp_config = _smtp_config()

    def _client(self):
        from app.database.supabase_client import get_supabase_client

        return get_supabase_client()

    def generate_invite_token(
        self,
        email: str,
        full_name: str,
        role: str,
        site_id: str,
        invited_by: str,
    ) -> dict[str, Any]:
        """Create a magic link token and send the invite email. Returns token record."""
        client = self._client()
        if not client:
            raise RuntimeError("Database unavailable")

        # Check for existing unaccepted token for this email
        existing = self._get_pending_token(client, email)
        if existing:
            # Return existing token for idempotency
            return existing

        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(hours=INVITE_TOKEN_EXPIRY_HOURS)

        result = (
            client.table("magic_link_tokens")
            .insert(
                {
                    "token": token,
                    "email": email.strip().lower(),
                    "full_name": full_name.strip(),
                    "role": role,
                    "site_id": site_id,
                    "invited_by": invited_by,
                    "expires_at": expires_at.isoformat(),
                }
            )
            .execute()
        )

        if not result.data:
            raise RuntimeError("Failed to create invite token")

        row = result.data[0]

        # Send invite email
        public_url = settings.sentinel_public_url or "https://bms.sentinel-ai.co.za"
        invite_link = f"{public_url.rstrip('/')}/invite?token={token}"
        subject, html_body = _build_invite_email(email, full_name, invite_link, role, site_id)
        _send_email(email, subject, html_body, self._smtp_config)

        return row

    def _get_pending_token(self, client, email: str) -> dict[str, Any] | None:
        """Return most recent pending (unaccepted) token for email, or None."""
        result = (
            client.table("magic_link_tokens")
            .select("*")
            .eq("email", email.strip().lower())
            .is_("accepted_at", None)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]
        return None

    def validate_token(self, token: str) -> dict[str, Any] | None:
        """Validate a magic link token. Returns token record if valid, None otherwise."""
        client = self._client()
        if not client:
            return None

        result = client.table("magic_link_tokens").select("*").eq("token", token).limit(1).execute()
        if not result.data:
            return None

        row = result.data[0]

        # Check expiry
        expires_at_str = row.get("expires_at")
        if expires_at_str:
            expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            if datetime.now(UTC) > expires_at:
                return None

        # Check already accepted
        if row.get("accepted_at"):
            return None

        return row

    def accept_invite(
        self,
        token: str,
        password: str,
        ip: str | None,
        user_agent: str | None,
    ) -> dict[str, Any]:
        """Accept a magic link invite: create/update user, grant site access, issue JWT.

        Returns dict with access_token, refresh_token, user, session_id on success.
        Raises ValueError on invalid/expired token, KeyError on missing fields.
        """
        token_record = self.validate_token(token)
        if not token_record:
            raise ValueError("Invalid or expired invite link")

        email = token_record["email"]
        full_name = token_record["full_name"]
        role = token_record["role"]
        site_id = token_record["site_id"]

        # Hash password and upsert user
        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        user = self._upsert_user_with_password(email, full_name, role, password_hash)
        if not user:
            raise RuntimeError("Failed to create user account")

        user_id = str(user["id"])

        # Grant site access
        self._access_repo.grant_access(email, site_id, granted_by=token_record["invited_by"])

        # Mark token accepted
        self._mark_token_accepted(token, ip, user_agent)

        # Issue JWT tokens and session
        access_token = create_jwt_token(
            user_id=user_id,
            email=email,
            role=role,
            full_name=full_name,
            token_type="access",
        )
        refresh_token = create_jwt_token(
            user_id=user_id,
            email=email,
            role=role,
            full_name=full_name,
            token_type="refresh",
        )

        # Create session record

        refresh_jti = secrets.token_urlsafe(16)
        session_id = self._session_svc.create_session(
            user_id=user_id,
            ip=ip or "unknown",
            user_agent=user_agent or "",
            token_jti=refresh_jti,
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {
                "user_id": user_id,
                "email": email,
                "full_name": full_name,
                "role": role,
            },
            "session_id": session_id,
        }

    def _upsert_user_with_password(
        self, email: str, full_name: str, role: str, password_hash: str
    ) -> dict[str, Any] | None:
        client = self._client()
        if not client:
            return None

        # Upsert: update if exists, create if not
        existing = client.table("sentinel_users").select("*").eq("email", email).limit(1).execute()

        if existing.data:
            # Update existing user with password
            result = (
                client.table("sentinel_users")
                .update(
                    {
                        "full_name": full_name,
                        "role": role,
                        "password_hash": password_hash,
                        "must_set_password": False,
                        "is_active": True,
                        "updated_at": datetime.now(UTC).isoformat(),
                    }
                )
                .eq("email", email)
                .execute()
            )
            if result.data:
                return result.data[0]
            return None
        else:
            # Create new user
            result = (
                client.table("sentinel_users")
                .insert(
                    {
                        "email": email,
                        "full_name": full_name,
                        "role": role,
                        "password_hash": password_hash,
                        "must_set_password": False,
                        "is_active": True,
                    }
                )
                .execute()
            )
            if result.data:
                return result.data[0]
            return None

    def _mark_token_accepted(self, token: str, ip: str | None, user_agent: str | None) -> None:
        client = self._client()
        if not client:
            return
        client.table("magic_link_tokens").update(
            {
                "accepted_at": datetime.now(UTC).isoformat(),
                "accepted_ip": ip,
                "accepted_user_agent": user_agent,
            }
        ).eq("token", token).execute()


def get_magic_link_service() -> MagicLinkService:
    return MagicLinkService()
