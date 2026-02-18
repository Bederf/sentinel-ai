"""
User Module Entitlements Model

Maps users to the modules they have access to based on subscription/licensing.
When a user logs in, their entitlements determine which modules are active in their session.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class UserModuleEntitlement:
    """A user's entitlement to a specific module.

    Represents what modules a user has paid for or been granted access to.
    """
    user_id: str
    user_email: str
    module_type: str
    activated_at: str  # ISO format datetime
    expires_at: Optional[str] = None  # ISO format, None = no expiry
    is_active: bool = True
    notes: Optional[str] = None


@dataclass
class UserEntitlementProfile:
    """Complete module entitlements for a user.

    Contains all modules the user has access to.
    Loaded on login and used to configure their dashboard.
    """
    user_id: str
    user_email: str
    entitlements: List[str] = field(default_factory=list)  # List of module type strings
    last_updated: str = ""  # ISO format

    def has_module(self, module_type: str) -> bool:
        """Check if user is entitled to a specific module."""
        return module_type in self.entitlements

    def has_all_modules(self, module_types: List[str]) -> bool:
        """Check if user is entitled to all specified modules."""
        return all(m in self.entitlements for m in module_types)

    def has_any_module(self, module_types: List[str]) -> bool:
        """Check if user is entitled to any of the specified modules."""
        return any(m in self.entitlements for m in module_types)


# Preset definitions based on common module combinations
# (For reference - actual entitlements come from database per user)

PRESET_ENTITLEMENTS = {
    "grant": {
        "name": "Grant Demo",
        "description": "Lighting/Occupancy optimization story",
        "modules": ["control", "lighting", "energy", "hvac", "ml"],
        "messaging": "11.5% base → 15.7% with occupancy + lighting"
    },
    "bederf": {
        "name": "Bederf Demo",
        "description": "Solar/BESS optimization story",
        "modules": ["control", "solar", "energy", "hvac", "ml"],
        "messaging": "11.5% base → 21.3% with solar + BESS"
    },
    "full": {
        "name": "Full Platform",
        "description": "All modules for investor/internal presentations",
        "modules": ["control", "solar", "lighting", "security", "sustainability",
                   "water", "contracts", "maintenance", "energy", "hvac", "ml",
                   "assets", "simbiot", "integrations", "notifications", "fire", "access"],
        "messaging": "Complete SENTINEL platform with all optimizations"
    }
}
