"""User access profiles - synced with frontend access-control.ts

Provides email-based and domain-based access restrictions for profiled users.
Allows backend to grant module access based on profile configuration without
requiring explicit entries in the user_module_access table.

Priority: USER_ACCESS_PROFILES > COMPANY_ACCESS_PROFILES
"""

from typing import TypedDict


class AccessProfile(TypedDict):
    """Access profile for a user or company."""

    companyName: str
    profileFocus: str
    allowedModules: list[str]  # Module types visible to this user/company
    allowedSites: list[str]  # Site codes user can access (empty = all sites)
    defaultView: str
    viewMode: str  # 'auditor', 'operator', or 'admin'
    description: str


# Per-user access profiles (takes priority over company profiles)
# Use this for generic email domains (gmail, protonmail, etc.)
USER_ACCESS_PROFILES: dict[str, AccessProfile] = {
    "bederf@protonmail.com": {
        "companyName": "Bederf Solar",
        "profileFocus": "solar-bess",
        "allowedModules": [
            "dashboard",
            "integrations",
            "solar",
            "control",
            "settings",
        ],
        "allowedSites": ["site-002"],  # Restrict to site-002 only
        "defaultView": "dashboard",
        "viewMode": "operator",
        "description": "Solar & BESS profile for Bederf",
    },
    "pietvrooyen@gmail.com": {
        "companyName": "Busamed Gateway",
        "profileFocus": "hospital",
        "allowedModules": [
            "dashboard",
            "integrations",
            "hvac",
            "energy",
            "lighting",
            "maintenance",
        ],
        "allowedSites": ["site-002"],
        "defaultView": "dashboard",
        "viewMode": "operator",
        "description": "Facilities operator for Busamed Gateway Hospital",
    },
}

# Company access profiles (applies to domain-based email matching)
# Does NOT apply if user has a USER_ACCESS_PROFILES entry
COMPANY_ACCESS_PROFILES: dict[str, AccessProfile] = {
    "grantdemo.co.za": {
        "companyName": "Grant Lighting",
        "profileFocus": "dali-lighting",
        "allowedModules": [
            "dashboard",
            "integrations",
            "occupancy",
            "lighting",
            "control",
            "settings",
        ],
        "allowedSites": ["site-002"],  # Restrict to site-002 only
        "defaultView": "occupancy",
        "viewMode": "operator",
        "description": "DALI Lighting & Occupancy Control profile",
    },
}

# Mapping from frontend view names to backend module types
# (frontend nav items → backend ModuleType for permission checking)
VIEW_TO_MODULE_MAP: dict[str, str] = {
    "dashboard": "hvac",  # Dashboard is always visible
    "digital-twin": "digital_twin",
    "integrations": "integrations",
    "occupancy": "lighting",  # Occupancy monitoring is part of lighting module
    "lighting": "lighting",
    "control": "control",
    "technician": "maintenance",  # Tech chat uses maintenance module
    "fleet": "ml",  # Fleet ML uses ml module
    "solar": "solar",
    "settings": "kpi",  # Settings is internal, uses kpi module
}


def get_access_profile_for_email(email: str) -> AccessProfile | None:
    """Get the access profile for a user - checks exact email first, then domain.

    Returns the profile if one exists for the user, None otherwise.
    Priority: USER_ACCESS_PROFILES > COMPANY_ACCESS_PROFILES
    """
    normalized = email.lower().strip()

    # 1. Check exact email match first (takes priority)
    if normalized in USER_ACCESS_PROFILES:
        return USER_ACCESS_PROFILES[normalized]

    # 2. Fall back to domain-based match
    domain = normalized.split("@")[1] if "@" in normalized else None
    if domain and domain in COMPANY_ACCESS_PROFILES:
        return COMPANY_ACCESS_PROFILES[domain]

    return None


def has_profile_module_access(email: str, module_type: str) -> bool:
    """Check if user has access to a module via profile configuration.

    This allows frontend view-based access (e.g., 'solar' view)
    to map to backend module types (e.g., 'solar' module) without
    requiring explicit database grants.

    Args:
        email: User email address
        module_type: Backend ModuleType value (e.g., 'solar', 'lighting')

    Returns:
        True if the user's access profile includes this module, False otherwise
    """
    profile = get_access_profile_for_email(email)
    if not profile:
        return False

    # Check if module is in allowed modules
    return module_type in profile["allowedModules"]


def has_profile_site_access(email: str, site_code: str) -> bool:
    """Check if user has access to a site via profile configuration.

    Restricts profiled users to specific sites (e.g., site-002 only).

    Args:
        email: User email address
        site_code: Site code (e.g., 'site-002')

    Returns:
        True if the user's access profile includes this site, or if no restriction is set
    """
    profile = get_access_profile_for_email(email)
    if not profile:
        return True  # No access profile = no site restriction

    allowed_sites = profile.get("allowedSites", [])
    if not allowed_sites:
        return True  # Empty list = no restriction

    return site_code in allowed_sites
