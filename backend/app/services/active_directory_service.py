"""Active Directory Service — mock implementation with JSON lookup.

Provides host details (name, mobile, department) for visitor confirmation emails.

In production this would call LDAP/AD.  For now it reads from a local JSON
file seeded with FNB example hosts.

Env vars:
    INTERNAL_EMAIL_DOMAINS — comma-separated domains considered internal
                             (also used by outlook_calendar_service)
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import ClassVar

logger = logging.getLogger(__name__)

# Path to host directory JSON
DATA_DIR = Path(__file__).parent.parent / "data"
HOST_DIRECTORY_PATH = DATA_DIR / "host_directory.json"


class ActiveDirectoryService:
    """Mock AD service — returns host details from a JSON lookup table.

    Follows the same pattern as technicians_whatsapp.json for consistency.
    """

    DEFAULT_INTERNAL_DOMAINS: ClassVar[set[str]] = {
        "fnb.co.za",
        "sentinel.bms",
    }

    def __init__(self) -> None:
        self._hosts: list[dict] = self._load_hosts()
        self._email_index: dict[str, dict] = {h["email"].lower(): h for h in self._hosts if "email" in h}
        self._name_index: dict[str, dict] = {h["name"].lower(): h for h in self._hosts if "name" in h}
        self._mobile_index: dict[str, dict] = self._build_mobile_index()
        self._internal_domains = self._load_internal_domains()

    # ------------------------------------------------------------------
    # Load / parse
    # ------------------------------------------------------------------

    def _load_hosts(self) -> list[dict]:
        """Load hosts from JSON file."""
        if not HOST_DIRECTORY_PATH.exists():
            logger.warning(
                "Host directory not found at %s — AD service returns None for all lookups", HOST_DIRECTORY_PATH
            )
            return []
        try:
            with open(HOST_DIRECTORY_PATH) as f:
                data = json.load(f)
            return data.get("hosts", [])
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Failed to load host directory: %s", exc)
            return []

    def _load_internal_domains(self) -> set[str]:
        extra = os.getenv("INTERNAL_EMAIL_DOMAINS", "")
        domains = {d.strip().lower() for d in extra.split(",") if d.strip()}
        return self.DEFAULT_INTERNAL_DOMAINS | domains

    def _build_mobile_index(self) -> dict[str, dict]:
        """Build a normalised mobile -> host index for O(1) reverse lookup."""
        index: dict[str, dict] = {}
        for host in self._hosts:
            mobile = host.get("mobile_number") or host.get("mobile")
            if not mobile:
                continue
            # Store under all normalised forms for flexible matching
            normalised = mobile.replace("whatsapp:", "").replace(" ", "").strip()
            index[normalised] = host
            # +27... form
            if normalised.startswith("0") and len(normalised) == 10:
                index["+" + normalised[1:]] = host
            # 07... form
            elif normalised.startswith("+") and len(normalised) == 12:
                index["0" + normalised[3:]] = host
        # Also index from technicians_whatsapp.json as fallback
        self._index_technicians_mobile(index)
        return index

    def _index_technicians_mobile(self, index: dict[str, dict]) -> None:
        """Supplement mobile index with technicians_whatsapp.json data."""
        try:
            tech_path = DATA_DIR / "technicians_whatsapp.json"
            if not tech_path.exists():
                return
            with open(tech_path) as f:
                data = json.load(f)
            for tech in data.get("technicians", []):
                mobile = tech.get("whatsapp_number", "").replace("whatsapp:", "").replace(" ", "").strip()
                if not mobile:
                    continue
                if mobile not in index:
                    index[mobile] = {
                        "name": tech.get("name"),
                        "email": tech.get("email"),
                        "mobile_number": tech.get("whatsapp_number"),
                        "department": tech.get("specialty"),
                    }
                normalised = mobile.replace("whatsapp:", "").replace(" ", "").strip()
                index[normalised] = index[mobile]
                if normalised.startswith("0") and len(normalised) == 10:
                    index["+" + normalised[1:]] = index[mobile]
                elif normalised.startswith("+") and len(normalised) == 12:
                    index["0" + normalised[3:]] = index[mobile]
        except Exception as e:
            logger.warning(f"Failed to index technicians_whatsapp.json for mobile lookup: {e}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_host_details(self, email: str) -> dict | None:
        """Return host details dict for the given email address.

        Returns:
            {
                "name": "Thandi Dineka",
                "mobile_number": "+27821234567",
                "department": "Facilities Management",
                "email": "tdineka@fnb.co.za"
            }
            or None if the host is not found.
        """
        if not email:
            return None
        key = email.lower()
        host = self._email_index.get(key)
        if host is None:
            logger.debug("AD lookup miss for email: %s", email)
            return None
        return {
            "name": host.get("name"),
            "mobile_number": host.get("mobile_number"),
            "department": host.get("department"),
            "email": host.get("email"),
        }

    def get_host_by_name(self, name: str) -> dict | None:
        """Return the first host matching the given name (case-insensitive)."""
        if not name:
            return None
        key = name.lower()
        host = self._name_index.get(key)
        if host is None:
            logger.debug("AD lookup miss for name: %s", name)
            return None
        return {
            "name": host.get("name"),
            "mobile_number": host.get("mobile_number"),
            "department": host.get("department"),
            "email": host.get("email"),
        }

    def is_internal_email(self, email: str) -> bool:
        """Return True if the email domain is in the internal domain list."""
        if not email or "@" not in email:
            return False
        domain = email.split("@")[1].lower()
        return domain in self._internal_domains

    def get_host_by_mobile(self, mobile: str) -> dict | None:
        """Reverse look up a host record by mobile number.

        Handles SA formats: +27XXXXXXXXX, 0XXXXXXXXX, whatsapp:+27XXXXXXXXX.

        Args:
            mobile: Mobile number in any common SA format.

        Returns:
            Host dict with keys: name, email, mobile_number, department,
            or None if not found.
        """
        if not mobile:
            return None
        normalised = mobile.replace("whatsapp:", "").replace(" ", "").strip()
        host = self._mobile_index.get(normalised)
        if host is None:
            logger.debug("AD mobile lookup miss for: %s", mobile)
            return None
        return {
            "name": host.get("name"),
            "email": host.get("email"),
            "mobile_number": host.get("mobile_number") or host.get("mobile"),
            "department": host.get("department"),
        }

    def get_host_by_email(self, email: str) -> dict | None:
        """Alias for get_host_details — look up host by email address."""
        return self.get_host_details(email)
