"""
User Models - Authentication and authorization

Phase TODO: Implement proper user management
Currently provides stub implementation for development.
"""

from pydantic import BaseModel


class User(BaseModel):
    """User model for authentication."""

    id: str
    username: str
    email: str | None = None
    role: str = "technician"
    full_name: str | None = None
    is_active: bool = True


class UserCreate(BaseModel):
    """Model for creating a new user."""

    username: str
    email: str | None = None
    password: str
    full_name: str | None = None
    role: str = "technician"


class UserUpdate(BaseModel):
    """Model for updating a user."""

    email: str | None = None
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None


class UserInDB(User):
    """User model as stored in database."""

    hashed_password: str
