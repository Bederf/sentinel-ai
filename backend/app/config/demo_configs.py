"""Demo user configurations - synced with frontend access-control.ts

Provides email-based and domain-based access restrictions for demo users.
Allows backend to grant module access based on demo configuration without
requiring explicit entries in the user_module_access table.

Priority: USER_DEMO_CONFIGS > COMPANY_DEMO_CONFIGS
"""

from typing import TypedDict


class DemoConfig(TypedDict):
    """Demo configuration for a user or company."""
    companyName: str
    demoFocus: str
    allowedModules: list[str]  # Module types visible to this user/company
    defaultView: str
    viewMode: str  # 'auditor', 'operator', or 'admin'
    description: str


# Per-user demo configurations (takes priority over company configs)
# Use this for generic email domains (gmail, protonmail, etc.)
USER_DEMO_CONFIGS: dict[str, DemoConfig] = {
    'bederf@protonmail.com': {
        'companyName': 'Bederf Solar Demo',
        'demoFocus': 'solar-bess',
        'allowedModules': [
            'dashboard',
            'digital-twin',
            'integrations',
            'solar',
            'control',
            'technician',
            'fleet',
            'settings',
        ],
        'defaultView': 'dashboard',
        'viewMode': 'operator',
        'description': 'Solar & BESS Demo for Bederf',
    },
}

# Company demo configurations (applies to domain-based email matching)
# Does NOT apply if user has a USER_DEMO_CONFIG entry
COMPANY_DEMO_CONFIGS: dict[str, DemoConfig] = {
    'wardew.co.za': {
        'companyName': 'Wardew',
        'demoFocus': 'dali-lighting',
        'allowedModules': [
            'dashboard',
            'digital-twin',
            'integrations',
            'occupancy',
            'lighting',
            'control',
            'technician',
            'fleet',
            'settings',
        ],
        'defaultView': 'occupancy',
        'viewMode': 'operator',
        'description': 'DALI Lighting & Occupancy Control Demo',
    },
}

# Mapping from frontend view names to backend module types
# (frontend nav items → backend ModuleType for permission checking)
VIEW_TO_MODULE_MAP: dict[str, str] = {
    'dashboard': 'hvac',  # Dashboard is always visible
    'digital-twin': 'digital_twin',
    'integrations': 'integrations',
    'occupancy': 'lighting',  # Occupancy monitoring is part of lighting module
    'lighting': 'lighting',
    'control': 'control',
    'technician': 'maintenance',  # Tech chat uses maintenance module
    'fleet': 'ml',  # Fleet ML uses ml module
    'solar': 'solar',
    'settings': 'kpi',  # Settings is internal, uses kpi module
}


def get_demo_config_for_email(email: str) -> DemoConfig | None:
    """Get demo config for a user - checks exact email first, then domain.
    
    Returns the config if user has a demo configuration, None otherwise.
    Priority: USER_DEMO_CONFIGS > COMPANY_DEMO_CONFIGS
    """
    normalized = email.lower().strip()

    # 1. Check exact email match first (takes priority)
    if normalized in USER_DEMO_CONFIGS:
        return USER_DEMO_CONFIGS[normalized]

    # 2. Fall back to domain-based match
    domain = normalized.split('@')[1] if '@' in normalized else None
    if domain and domain in COMPANY_DEMO_CONFIGS:
        return COMPANY_DEMO_CONFIGS[domain]

    return None


def has_demo_module_access(email: str, module_type: str) -> bool:
    """Check if user has access to a module via demo configuration.
    
    This allows frontend view-based access (e.g., 'solar' view)
    to map to backend module types (e.g., 'solar' module) without
    requiring explicit database grants.
    
    Args:
        email: User email address
        module_type: Backend ModuleType value (e.g., 'solar', 'lighting')
    
    Returns:
        True if user's demo config includes this module, False otherwise
    """
    config = get_demo_config_for_email(email)
    if not config:
        return False

    # Check if module is in allowed modules
    return module_type in config['allowedModules']
