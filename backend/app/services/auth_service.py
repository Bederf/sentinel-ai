"""
Authentication Service - User authentication and authorization

Phase TODO: Implement proper authentication
Currently provides stub implementation for development.
"""

from typing import Optional
from fastapi import Header, HTTPException
from app.models.user import User


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
