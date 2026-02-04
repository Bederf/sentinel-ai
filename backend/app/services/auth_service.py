"""
Authentication Service - User authentication and authorization

Provides stub authentication for development/demo and an AuthorizationService
for role-based access control in remote operations (Phase 59).
"""

import logging
from typing import Optional, List, Dict

from fastapi import Header, HTTPException

from app.models.user import User
from app.models.remote_ops import AuthorizationLevel, COMMAND_AUTHORIZATION

logger = logging.getLogger(__name__)


async def get_current_user(
    authorization: Optional[str] = Header(None)
) -> User:
    """
    Get the current authenticated user from request headers.

    TODO: Implement proper JWT validation or API key authentication

    Args:
        authorization: Authorization header from request

    Returns:
        User object

    Raises:
        HTTPException: If no valid authorization provided
    """
    # For development, return a default user
    # In production, this would validate JWT tokens or API keys
    if not authorization:
        # Allow unauthenticated access for demo mode
        return User(
            id="demo-user",
            username="demo_technician",
            email="demo@sentinel.bms",
            role="technician"
        )

    # Parse token (stub implementation)
    if authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
        # TODO: Validate JWT token
        return User(
            id="authenticated-user",
            username="technician",
            role="technician"
        )

    # API key authentication (stub)
    return User(
        id="api-key-user",
        username="api_user",
        role="technician"
    )


def verify_admin_user(current_user: User) -> User:
    """
    Verify that the current user has admin privileges.

    Args:
        current_user: Current authenticated user

    Returns:
        User if admin

    Raises:
        HTTPException: If user is not admin
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin privileges required"
        )
    return current_user


class AuthorizationService:
    """Singleton authorization service for remote operations.

    Maps user roles to authorization levels and determines
    which remote commands a user can execute.

    Authorization levels (cumulative):
      - VIEW_ONLY (1): View building status and readings
      - OPERATOR (2): Run diagnostics, assess dispatch need, unlock doors
      - TECHNICIAN (3): Adjust setpoints, override schedules
      - ENGINEER (4): Start/stop equipment, reset faults, fire panel reset
    """

    _instance: Optional["AuthorizationService"] = None

    # Default role-to-level mapping
    _authorization_levels: Dict[str, AuthorizationLevel] = {
        "viewer": AuthorizationLevel.VIEW_ONLY,
        "operator": AuthorizationLevel.OPERATOR,
        "technician": AuthorizationLevel.TECHNICIAN,
        "engineer": AuthorizationLevel.ENGINEER,
        "admin": AuthorizationLevel.ENGINEER,
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def check_authorization(
        self, user_role: str, required_level: AuthorizationLevel
    ) -> bool:
        """Check if a user role meets or exceeds the required authorization level.

        Args:
            user_role: The user's role string (viewer, operator, technician, engineer, admin).
            required_level: The minimum AuthorizationLevel required.

        Returns:
            True if the user's level >= required_level.
        """
        user_level = self.get_user_authorization_level(user_role)
        return user_level >= required_level

    def get_allowed_commands(self, user_role: str) -> List[str]:
        """Return the list of remote command types the user is allowed to execute.

        Args:
            user_role: The user's role string.

        Returns:
            List of command type strings the user can execute.
        """
        user_level = self.get_user_authorization_level(user_role)
        return [
            cmd_type
            for cmd_type, required_level in COMMAND_AUTHORIZATION.items()
            if user_level >= required_level
        ]

    def get_user_authorization_level(self, user_role: str) -> AuthorizationLevel:
        """Get the authorization level for a given user role.

        Args:
            user_role: The user's role string.

        Returns:
            AuthorizationLevel for the role. Defaults to VIEW_ONLY for unknown roles.
        """
        return self._authorization_levels.get(
            user_role.lower(), AuthorizationLevel.VIEW_ONLY
        )


def get_authorization_service() -> AuthorizationService:
    """Factory function returning the singleton AuthorizationService."""
    return AuthorizationService()
