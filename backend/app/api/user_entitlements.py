"""
User Module Entitlements API

Manages user licensing and module access based on subscription/purchase.
Users can only access modules they have been granted.
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import List

from app.models.auth import AuthContext, AuthLevel
from app.middleware.auth_middleware import require_auth
from app.database.repositories.user_entitlements_repository import get_user_entitlements_repository
from app.models.user_entitlements import PRESET_ENTITLEMENTS
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user/entitlements", tags=["user-entitlements"])


# ==================== User Entitlements Endpoints ====================


@router.get("")
async def get_current_user_entitlements(auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED))) -> dict:
    """Get current user's module entitlements.

    Returns the modules the user has paid for or been granted access to.
    This is automatically loaded during login and stored in AuthContext.

    Returns:
        {
            "user_email": "operator@sentinel.local",
            "entitlements": ["control", "lighting", "energy", "hvac", "ml"],
            "preset": "grant"  // If user matches a preset
        }
    """
    # Check which preset (if any) matches user's entitlements
    matching_preset = None
    for preset_name, preset_data in PRESET_ENTITLEMENTS.items():
        if set(auth.entitlements) == set(preset_data["modules"]):
            matching_preset = preset_name
            break

    return {
        "user_email": auth.email or "unknown",
        "entitlements": auth.entitlements,
        "preset": matching_preset,
        "messaging": matching_preset and PRESET_ENTITLEMENTS[matching_preset].get("messaging", ""),
    }


@router.get("/{user_email}")
async def get_user_entitlements(user_email: str, auth: AuthContext = Depends(require_auth(AuthLevel.ADMIN))) -> dict:
    """Get entitlements for a specific user (admin only).

    Args:
        user_email: Email address of user to check

    Returns:
        {
            "user_email": "operator@sentinel.local",
            "entitlements": ["control", "lighting", "energy", "hvac", "ml"],
            "preset": "grant"
        }
    """
    repo = get_user_entitlements_repository()
    entitlements_profile = await repo.get_user_entitlements(user_email)

    if not entitlements_profile:
        raise HTTPException(status_code=404, detail=f"No entitlements found for {user_email}")

    # Check which preset matches
    matching_preset = None
    for preset_name, preset_data in PRESET_ENTITLEMENTS.items():
        if set(entitlements_profile.entitlements) == set(preset_data["modules"]):
            matching_preset = preset_name
            break

    return {
        "user_email": entitlements_profile.user_email,
        "entitlements": entitlements_profile.entitlements,
        "preset": matching_preset,
        "messaging": matching_preset and PRESET_ENTITLEMENTS[matching_preset].get("messaging", ""),
    }


@router.post("/{user_email}")
async def set_user_entitlements(
    user_email: str, modules: List[str], auth: AuthContext = Depends(require_auth(AuthLevel.ADMIN))
) -> dict:
    """Set modules for a user (admin only).

    Args:
        user_email: Email address of user
        modules: List of module type strings (e.g., ["control", "lighting", "energy"])

    Returns:
        Updated entitlements
    """
    repo = get_user_entitlements_repository()
    entitlements_profile = await repo.set_user_entitlements(user_email, modules)

    logger.info(f"Admin {auth.email} updated entitlements for {user_email}: {modules}")

    return {
        "user_email": entitlements_profile.user_email,
        "entitlements": entitlements_profile.entitlements,
        "status": "updated",
    }


@router.post("/{user_email}/preset/{preset_name}")
async def apply_preset_to_user(
    user_email: str, preset_name: str, auth: AuthContext = Depends(require_auth(AuthLevel.ADMIN))
) -> dict:
    """Apply a preset (grant, bederf, full) to a user (admin only).

    Presets are common module combinations:
    - 'grant': control + lighting + energy + hvac + ml
    - 'bederf': control + solar + energy + hvac + ml
    - 'full': all modules

    Args:
        user_email: Email address of user
        preset_name: Preset name (grant, bederf, full)

    Returns:
        Updated entitlements with preset messaging
    """
    if preset_name not in PRESET_ENTITLEMENTS:
        raise HTTPException(
            status_code=400, detail=f"Unknown preset: {preset_name}. Available: {list(PRESET_ENTITLEMENTS.keys())}"
        )

    repo = get_user_entitlements_repository()
    entitlements_profile = await repo.apply_preset_to_user(user_email, preset_name)

    preset_data = PRESET_ENTITLEMENTS[preset_name]
    logger.info(
        f"Admin {auth.email} applied preset '{preset_name}' to {user_email}: {entitlements_profile.entitlements}"
    )

    return {
        "user_email": entitlements_profile.user_email,
        "entitlements": entitlements_profile.entitlements,
        "preset": preset_name,
        "preset_name": preset_data["name"],
        "messaging": preset_data.get("messaging", ""),
        "status": "applied",
    }


@router.get("/presets/available")
async def get_available_presets() -> dict:
    """Get all available entitlement presets.

    Returns:
        {
            "presets": [
                {
                    "id": "grant",
                    "name": "Grant Demo",
                    "description": "...",
                    "modules": ["control", "lighting", ...],
                    "messaging": "11.5% base → 15.7%"
                },
                ...
            ]
        }
    """
    presets = []
    for preset_id, preset_data in PRESET_ENTITLEMENTS.items():
        presets.append(
            {
                "id": preset_id,
                "name": preset_data.get("name"),
                "description": preset_data.get("description"),
                "modules": preset_data.get("modules", []),
                "messaging": preset_data.get("messaging", ""),
            }
        )

    return {"presets": presets}
