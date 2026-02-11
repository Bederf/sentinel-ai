"""
Dashboard Preferences API

Provides REST API for user dashboard customization:
- GET /api/preferences/dashboard - Get user's dashboard preferences
- PUT /api/preferences/dashboard - Update dashboard preferences
- DELETE /api/preferences/dashboard - Reset to defaults
"""

import logging
from typing import List, Optional
from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException, Header

from app.database.repositories.preferences_repository import PreferencesRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/preferences", tags=["preferences"])

# Default card definitions
DEFAULT_KPI_CARDS = [
    "kpi-protected-sites",
    "kpi-monitored-assets",
    "kpi-active-risks",
    "kpi-potential-savings",
    "kpi-risk-predictions"
]

DEFAULT_SECTIONS = [
    "kpi-row",
    "site-protection",
    "energy-analytics",
    "risk-predictions"
]


class DashboardPreferences(BaseModel):
    """Dashboard preferences model."""
    visible_kpi_cards: List[str] = Field(default=DEFAULT_KPI_CARDS)
    visible_sections: List[str] = Field(default=DEFAULT_SECTIONS)
    kpi_card_order: List[str] = Field(default=DEFAULT_KPI_CARDS)
    section_order: List[str] = Field(default=DEFAULT_SECTIONS)
    default_energy_period: int = Field(default=30, ge=7, le=90)
    default_energy_site_id: Optional[str] = None


class DashboardPreferencesResponse(BaseModel):
    """Dashboard preferences response with metadata."""
    user_id: str
    preferences: DashboardPreferences
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


def get_user_id(x_user_id: Optional[str] = None) -> str:
    """Get user ID from header or generate default."""
    if x_user_id:
        return x_user_id
    # Default user for demo/development
    return "default-user"


@router.get("/dashboard", response_model=DashboardPreferencesResponse)
async def get_dashboard_preferences(
    x_user_id: Optional[str] = Header(None, alias="X-User-ID")
):
    """
    Get user's dashboard preferences.

    Returns the user's saved preferences or defaults if none exist.
    User ID is passed via X-User-ID header (optional, defaults to 'default-user').

    Example:
        GET /api/preferences/dashboard
        X-User-ID: user-123
    """
    user_id = get_user_id(x_user_id)

    try:
        prefs_repo = PreferencesRepository()

        # Try to get existing preferences
        row = await prefs_repo.get_by_user_id(user_id)

        if row:
            return DashboardPreferencesResponse(
                user_id=user_id,
                preferences=DashboardPreferences(
                    visible_kpi_cards=row.get("visible_kpi_cards", DEFAULT_KPI_CARDS),
                    visible_sections=row.get("visible_sections", DEFAULT_SECTIONS),
                    kpi_card_order=row.get("kpi_card_order", DEFAULT_KPI_CARDS),
                    section_order=row.get("section_order", DEFAULT_SECTIONS),
                    default_energy_period=row.get("default_energy_period", 30),
                    default_energy_site_id=row.get("default_energy_site_id")
                ),
                created_at=row.get("created_at"),
                updated_at=row.get("updated_at")
            )

        # Return defaults if no preferences exist
        return DashboardPreferencesResponse(
            user_id=user_id,
            preferences=DashboardPreferences()
        )

    except Exception as e:
        logger.error(f"Error loading dashboard preferences: {e}")
        # Return defaults on error (graceful degradation)
        return DashboardPreferencesResponse(
            user_id=user_id,
            preferences=DashboardPreferences()
        )


@router.put("/dashboard", response_model=DashboardPreferencesResponse)
async def update_dashboard_preferences(
    preferences: DashboardPreferences,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID")
):
    """
    Update user's dashboard preferences.

    Creates new preferences if none exist (upsert behavior).
    User ID is passed via X-User-ID header.

    Example:
        PUT /api/preferences/dashboard
        X-User-ID: user-123
        {
            "visible_kpi_cards": ["kpi-protected-sites", "kpi-active-risks"],
            "kpi_card_order": ["kpi-active-risks", "kpi-protected-sites"]
        }
    """
    user_id = get_user_id(x_user_id)

    try:
        prefs_repo = PreferencesRepository()

        # Upsert preferences
        row = await prefs_repo.upsert(user_id, preferences)

        return DashboardPreferencesResponse(
            user_id=user_id,
            preferences=preferences,
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at")
        )

    except Exception as e:
        logger.error(f"Error saving dashboard preferences: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save preferences: {str(e)}"
        )


@router.delete("/dashboard", response_model=dict)
async def reset_dashboard_preferences(
    x_user_id: Optional[str] = Header(None, alias="X-User-ID")
):
    """
    Reset user's dashboard preferences to defaults.

    Deletes the user's saved preferences, returning to default state.

    Example:
        DELETE /api/preferences/dashboard
        X-User-ID: user-123
    """
    user_id = get_user_id(x_user_id)

    try:
        prefs_repo = PreferencesRepository()

        # Delete existing preferences
        await prefs_repo.delete(user_id)

        return {
            "success": True,
            "message": "Dashboard preferences reset to defaults",
            "user_id": user_id
        }

    except Exception as e:
        logger.error(f"Error resetting dashboard preferences: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reset preferences: {str(e)}"
        )


@router.get("/dashboard/defaults", response_model=DashboardPreferences)
async def get_default_preferences():
    """
    Get default dashboard preferences.

    Returns the default card configuration without requiring user context.
    Useful for showing available cards in the card library UI.

    Example:
        GET /api/preferences/dashboard/defaults
    """
    return DashboardPreferences()
