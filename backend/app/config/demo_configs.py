"""Backward-compatible demo config exports for older tests and auth helpers."""

from __future__ import annotations

from typing import TypedDict

from app.config.access_profiles import USER_ACCESS_PROFILES


class DemoConfig(TypedDict):
    companyName: str
    demoFocus: str
    allowedModules: list[str]
    allowedSites: list[str]
    defaultView: str
    viewMode: str
    description: str


USER_DEMO_CONFIGS: dict[str, DemoConfig] = {
    email: {
        "companyName": profile["companyName"],
        "demoFocus": profile["profileFocus"],
        "allowedModules": profile["allowedModules"],
        "allowedSites": profile["allowedSites"],
        "defaultView": profile["defaultView"],
        "viewMode": profile["viewMode"],
        "description": profile["description"],
    }
    for email, profile in USER_ACCESS_PROFILES.items()
}
