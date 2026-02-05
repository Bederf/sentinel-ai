"""
MFA Service - TOTP multi-factor authentication service.

Handles TOTP secret generation, verification, and enrollment workflow.
FSR Domain: 4.6 - Logical Access Control (MFA for privileged access)
"""

import pyotp
import logging
from typing import Optional, Tuple, Dict, Any
from datetime import datetime

from app.database.repositories.mfa_repository import get_mfa_repository
from app.models.auth import SentinelRole

logger = logging.getLogger(__name__)

# Roles that require MFA
MFA_REQUIRED_ROLES = {SentinelRole.ADMIN}

# TOTP configuration
TOTP_ISSUER = "SENTINEL BMS"
TOTP_INTERVAL = 30  # Standard 30-second interval
TOTP_DIGITS = 6  # Standard 6-digit codes

# Rate limiting
MAX_FAILED_ATTEMPTS = 5
RATE_LIMIT_WINDOW_MINUTES = 5


class MFAService:
    """Service for MFA/TOTP operations."""

    def __init__(self):
        self.repository = get_mfa_repository()

    def is_mfa_required(self, role: SentinelRole) -> bool:
        """
        Check if MFA is required for a given role.

        Args:
            role: User's role

        Returns:
            True if MFA is required for this role
        """
        return role in MFA_REQUIRED_ROLES

    def is_mfa_enabled(self, user_email: str) -> bool:
        """
        Check if MFA is enabled for a user.

        Args:
            user_email: User's email address

        Returns:
            True if user has MFA enabled
        """
        record = self.repository.get_mfa_secret(user_email)
        return record is not None and record.get("enabled", False)

    def is_mfa_enrolled(self, user_email: str) -> bool:
        """
        Check if user has started MFA enrollment (secret exists).

        Args:
            user_email: User's email address

        Returns:
            True if user has a TOTP secret (may not be enabled yet)
        """
        record = self.repository.get_mfa_secret(user_email)
        return record is not None

    def get_mfa_status(self, user_email: str, role: SentinelRole) -> Dict[str, Any]:
        """
        Get complete MFA status for a user.

        Args:
            user_email: User's email address
            role: User's role

        Returns:
            Status dict with required, enrolled, and enabled flags
        """
        record = self.repository.get_mfa_secret(user_email)
        mfa_required = self.is_mfa_required(role)

        if record is None:
            return {
                "mfa_required": mfa_required,
                "mfa_enrolled": False,
                "mfa_enabled": False,
                "last_used_at": None,
                "enrolled_at": None,
            }

        return {
            "mfa_required": mfa_required,
            "mfa_enrolled": True,
            "mfa_enabled": record.get("enabled", False),
            "last_used_at": record.get("last_used_at"),
            "enrolled_at": record.get("last_enrolled_at"),
        }

    def generate_secret(self) -> str:
        """
        Generate a new TOTP secret.

        Returns:
            Base32-encoded secret string
        """
        return pyotp.random_base32()

    def get_provisioning_uri(self, user_email: str, secret: str) -> str:
        """
        Generate a provisioning URI for QR code generation.

        Args:
            user_email: User's email address
            secret: TOTP secret

        Returns:
            otpauth:// URI for authenticator apps
        """
        totp = pyotp.TOTP(secret, interval=TOTP_INTERVAL, digits=TOTP_DIGITS)
        return totp.provisioning_uri(
            name=user_email,
            issuer_name=TOTP_ISSUER,
        )

    def enroll_user(
        self,
        user_email: str,
        source_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[bool, str, str]:
        """
        Start MFA enrollment for a user.

        Generates a new TOTP secret and stores it (disabled until verified).

        Args:
            user_email: User's email address
            source_ip: Client IP for audit logging
            user_agent: Client user agent for audit logging

        Returns:
            Tuple of (success, secret, provisioning_uri)
        """
        try:
            # Generate new secret
            secret = self.generate_secret()

            # Store in database (disabled until verified)
            result = self.repository.create_mfa_secret(user_email, secret)
            if not result:
                logger.error(f"Failed to store MFA secret for {user_email}")
                return False, "", ""

            # Generate provisioning URI
            uri = self.get_provisioning_uri(user_email, secret)

            logger.info(f"MFA enrollment started for {user_email}")
            return True, secret, uri

        except Exception as e:
            logger.error(f"Error enrolling MFA for {user_email}: {e}")
            return False, "", ""

    def verify_code(
        self,
        user_email: str,
        code: str,
        source_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Verify a TOTP code.

        Args:
            user_email: User's email address
            code: 6-digit TOTP code
            source_ip: Client IP for audit logging
            user_agent: Client user agent for audit logging

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Check rate limiting
            if self.repository.is_rate_limited(user_email, MAX_FAILED_ATTEMPTS):
                # Log rate limit event
                self.repository.log_mfa_event(
                    user_email=user_email,
                    event_type="mfa_rate_limited",
                    source_ip=source_ip,
                    user_agent=user_agent,
                )
                return False, f"Too many failed attempts. Try again in {RATE_LIMIT_WINDOW_MINUTES} minutes."

            # Get stored secret
            record = self.repository.get_mfa_secret(user_email)
            if not record:
                return False, "MFA not enrolled for this user"

            secret = record.get("totp_secret")
            if not secret:
                return False, "Invalid MFA configuration"

            # Verify code
            totp = pyotp.TOTP(secret, interval=TOTP_INTERVAL, digits=TOTP_DIGITS)

            # Allow 1 interval tolerance for clock skew
            if totp.verify(code, valid_window=1):
                # Success - update last used
                self.repository.update_last_used(user_email)

                # Log success event
                self.repository.log_mfa_event(
                    user_email=user_email,
                    event_type="mfa_verified",
                    source_ip=source_ip,
                    user_agent=user_agent,
                )

                logger.info(f"MFA verification successful for {user_email}")
                return True, ""

            # Failed verification
            failed_count = self.repository.record_failed_attempt(user_email)

            # Log failure event
            self.repository.log_mfa_event(
                user_email=user_email,
                event_type="mfa_failed",
                source_ip=source_ip,
                user_agent=user_agent,
                event_data={"attempts": failed_count},
            )

            remaining = MAX_FAILED_ATTEMPTS - failed_count
            if remaining > 0:
                return False, f"Invalid code. {remaining} attempts remaining."
            else:
                return False, f"Invalid code. Account locked for {RATE_LIMIT_WINDOW_MINUTES} minutes."

        except Exception as e:
            logger.error(f"Error verifying MFA code for {user_email}: {e}")
            return False, "Verification failed"

    def enable_mfa(
        self,
        user_email: str,
        code: str,
        source_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Enable MFA after verifying the initial code.

        Called during enrollment to confirm the user has set up their authenticator.

        Args:
            user_email: User's email address
            code: 6-digit TOTP code
            source_ip: Client IP for audit logging
            user_agent: Client user agent for audit logging

        Returns:
            Tuple of (success, error_message)
        """
        # First verify the code
        success, error = self.verify_code(user_email, code, source_ip, user_agent)
        if not success:
            return False, error

        # Enable MFA
        if self.repository.enable_mfa(user_email):
            # Log enrollment complete
            self.repository.log_mfa_event(
                user_email=user_email,
                event_type="mfa_enrolled",
                source_ip=source_ip,
                user_agent=user_agent,
            )

            logger.info(f"MFA enabled for {user_email}")
            return True, ""

        return False, "Failed to enable MFA"

    def disable_mfa(
        self,
        user_email: str,
        admin_email: str,
        source_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> bool:
        """
        Disable MFA for a user (admin action).

        Args:
            user_email: User whose MFA should be disabled
            admin_email: Admin performing the action
            source_ip: Client IP for audit logging
            user_agent: Client user agent for audit logging

        Returns:
            True if disabled successfully
        """
        if self.repository.disable_mfa(user_email):
            # Log disable event with admin info
            self.repository.log_mfa_event(
                user_email=user_email,
                event_type="mfa_disabled",
                source_ip=source_ip,
                user_agent=user_agent,
                event_data={"disabled_by": admin_email},
            )

            logger.info(f"MFA disabled for {user_email} by {admin_email}")
            return True

        return False


# Singleton instance
_service: Optional[MFAService] = None


def get_mfa_service() -> MFAService:
    """Get singleton MFA service."""
    global _service
    if _service is None:
        _service = MFAService()
    return _service
