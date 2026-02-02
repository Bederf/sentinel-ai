"""
User Models - Authentication and authorization

Phase TODO: Implement proper user management
Currently provides stub implementation for development.
"""

from typing import Optional
from pydantic import BaseModel


class User(BaseModel):
    """User model for authentication."""
    id: str
    username: str
    email: Optional[str] = None
    role: str = "technician"
    full_name: Optional[str] = None
    is_active: bool = True


class UserCreate(BaseModel):
    """Model for creating a new user."""
    username: str
    email: Optional[str] = None
    password: str
    full_name: Optional[str] = None
    role: str = "technician"


class UserUpdate(BaseModel):
    """Model for updating a user."""
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


class UserInDB(User):
    """User model as stored in database."""
    hashed_password: str
