"""Work Order Service for creating maintenance work orders from chat."""

import re
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import json
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

# Data directory for lookups
DATA_DIR = Path(__file__).parent.parent / "data"


def load_json(filename: str) -> list[dict]:
    """Load JSON data file."""
    filepath = DATA_DIR / filename
    if filepath.exists():
        with open(filepath) as f:
            return json.load(f)
    return []


@dataclass
class WorkOrder:
    """Work order data class."""

    id: str
    site_id: str
    site_name: str
    equipment_id: Optional[str]
    equipment_name: Optional[str]
    description: str
    priority: str  # critical, high, medium, low
    category: str  # hvac, electrical, maintenance, plumbing, other
    reported_by: str
    created_at: str = ""
    status: str = "open"

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "site_id": self.site_id,
            "site_name": self.site_name,
            "equipment_id": self.equipment_id,
            "equipment_name": self.equipment_name,
            "description": self.description,
            "priority": self.priority,
            "category": self.category,
            "reported_by": self.reported_by,
            "created_at": self.created_at,
            "status": self.status,
        }

    def format_confirmation(self) -> str:
        """Format work order as confirmation message."""
        eq_info = f"**Equipment:** {self.equipment_name} [{self.equipment_id}]\n" if self.equipment_id else ""
        return f"""
**Work Order Created Successfully**

**Work Order ID:** {self.id}
**Site:** {self.site_name} [{self.site_id}]
{eq_info}**Description:** {self.description}
**Priority:** {self.priority.upper()}
**Category:** {self.category}
**Reported By:** {self.reported_by}
**Created:** {self.created_at[:16].replace("T", " ")}
**Status:** {self.status.upper()}

This work order has been logged for action by the maintenance team.
"""


# Keywords that suggest a maintenance issue / work order need
MAINTENANCE_KEYWORDS = [
    "broken",
    "not working",
    "malfunction",
    "fault",
    "error",
    "noise",
    "noisy",
    "grinding",
    "squeaking",
    "rattling",
    "leak",
    "leaking",
    "dripping",
    "water",
    "hot",
    "cold",
    "warm",
    "freezing",
    "temperature issue",
    "smell",
    "odor",
    "burning",
    "repair",
    "fix",
    "service",
    "maintenance needed",
    "is down",
    "went down",
    "shut down",
    "offline",
    "stopped",
    "won't start",
    "flickering",
    "dim",
    "buzzing",
    "damaged",
    "cracked",
    "bent",
]

# Equipment patterns
EQUIPMENT_PATTERNS = [
    r"(ahu[-\s]?\d+)",  # AHU-1, AHU 1
    r"(ch[-\s]?\d+)",  # CH-1, Chiller 1
    r"(ups[-\s]?\d+)",  # UPS-1
    r"(gen[-\s]?\d+)",  # GEN-1, Generator 1
    r"(fcu[-\s]?\d+)",  # FCU-001
    r"(ac[-\s]?\d+)",  # AC-1
    r"(crac[-\s]?\d+)",  # CRAC-1
    r"(eqp[-\s]?\d+)",  # Equipment ID
    r"(hvac|air\s*con|chiller|generator|ups|boiler)",  # Generic equipment types
]

# Category keywords
CATEGORY_KEYWORDS = {
    "hvac": ["hvac", "air", "cooling", "heating", "ahu", "chiller", "fcu", "ac", "temperature", "hot", "cold", "crac"],
    "electrical": ["ups", "generator", "power", "electrical", "flickering", "buzzing", "lights", "transformer"],
    "plumbing": ["water", "leak", "pipe", "drain", "toilet", "tap", "plumbing"],
    "maintenance": ["service", "maintenance", "repair", "inspection"],
}

# Priority keywords
PRIORITY_KEYWORDS = {
    "critical": ["critical", "urgent", "emergency", "immediately", "asap", "safety hazard", "dangerous"],
    "high": ["high priority", "important", "soon", "quickly", "serious"],
    "medium": ["medium", "moderate", "when possible"],
    "low": ["low priority", "minor", "cosmetic", "when convenient"],
}


class WorkOrderService:
    """Service for detecting and creating work orders from chat messages."""

    def __init__(self):
        """Initialize work order service."""
        self._sites = None
        self._equipment = None
        self._work_orders: list[WorkOrder] = []

    @property
    def sites(self) -> list[dict]:
        """Lazy load sites data."""
        if self._sites is None:
            self._sites = load_json("sites.json")
        return self._sites

    @property
    def equipment(self) -> list[dict]:
        """Lazy load equipment data."""
        if self._equipment is None:
            self._equipment = load_json("equipment.json")
        return self._equipment

    def _find_site(self, query: str) -> Optional[dict]:
        """Find a site by name or ID."""
        query_lower = query.lower().strip()
        for site in self.sites:
            if site["id"].lower() == query_lower or query_lower in site["name"].lower():
                return site
        return None

    def _find_equipment(self, query: str) -> Optional[dict]:
        """Find equipment by name or ID."""
        query_lower = query.lower().strip().replace(" ", "").replace("-", "")
        for eq in self.equipment:
            eq_id_normalized = eq["id"].lower().replace("-", "")
            eq_name_normalized = eq["name"].lower().replace(" ", "").replace("-", "")
            if eq_id_normalized == query_lower or eq_name_normalized == query_lower:
                return eq
            # Partial match
            if query_lower in eq_name_normalized or query_lower in eq_id_normalized:
                return eq
        return None

    def _extract_equipment_reference(self, message: str) -> Optional[str]:
        """Extract equipment reference from message."""
        message_lower = message.lower()
        for pattern in EQUIPMENT_PATTERNS:
            match = re.search(pattern, message_lower, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def _determine_category(self, message: str) -> str:
        """Determine work order category from message."""
        message_lower = message.lower()
        for category, keywords in CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                if keyword in message_lower:
                    return category
        return "other"

    def _determine_priority(self, message: str) -> str:
        """Determine work order priority from message."""
        message_lower = message.lower()
        for priority, keywords in PRIORITY_KEYWORDS.items():
            for keyword in keywords:
                if keyword in message_lower:
                    return priority
        return "medium"  # Default priority

    def detect_work_order_request(self, message: str) -> Optional[dict]:
        """
        Detect if a message is a work order request.

        Args:
            message: User message to analyze

        Returns:
            Dict with work order details if detected, None otherwise
        """
        message_lower = message.lower()

        # Check for maintenance keywords
        has_maintenance_keyword = any(kw in message_lower for kw in MAINTENANCE_KEYWORDS)

        # Check for equipment reference
        equipment_ref = self._extract_equipment_reference(message)

        # If has equipment reference and maintenance keyword, likely a work order
        if equipment_ref and has_maintenance_keyword:
            return {
                "detected": True,
                "equipment_ref": equipment_ref,
                "category": self._determine_category(message),
                "priority": self._determine_priority(message),
                "description": message,
            }

        # Without equipment reference, require explicit work order intent
        wo_intent_phrases = [
            "create work order",
            "create wo",
            "raise work order",
            "raise wo",
            "log a job",
            "maintenance needed",
            "needs repair",
            "needs fixing",
            "schedule maintenance",
            "report fault",
            "report issue",
        ]
        has_wo_intent = any(phrase in message_lower for phrase in wo_intent_phrases)
        if has_maintenance_keyword and has_wo_intent and len(message) > 20:
            return {
                "detected": True,
                "equipment_ref": equipment_ref,
                "category": self._determine_category(message),
                "priority": self._determine_priority(message),
                "description": message,
            }

        return None

    def create_work_order(
        self,
        description: str,
        site_id: Optional[str] = None,
        equipment_ref: Optional[str] = None,
        category: str = "other",
        priority: str = "medium",
        reported_by: str = "AI Chat System",
    ) -> WorkOrder:
        """
        Create a new work order.

        Args:
            description: Issue description
            site_id: Optional site ID (will try to infer from equipment)
            equipment_ref: Equipment reference string
            category: Work order category
            priority: Priority level
            reported_by: Who reported the issue

        Returns:
            Created WorkOrder object
        """
        # Generate work order ID
        wo_id = f"WO-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

        # Find equipment if reference provided
        equipment = None
        if equipment_ref:
            equipment = self._find_equipment(equipment_ref)

        # Determine site
        site = None
        if site_id:
            site = self._find_site(site_id)
        elif equipment:
            site = self._find_site(equipment.get("site_id", ""))

        # Use default site if none found
        if not site and self.sites:
            site = self.sites[0]  # Default to first site
            logger.warning(f"No site specified, defaulting to {site['name']}")

        work_order = WorkOrder(
            id=wo_id,
            site_id=site["id"] if site else "unknown",
            site_name=site["name"] if site else "Unknown Site",
            equipment_id=equipment["id"] if equipment else None,
            equipment_name=equipment["name"] if equipment else None,
            description=description,
            priority=priority,
            category=category,
            reported_by=reported_by,
        )

        # Store work order (in-memory for demo)
        self._work_orders.append(work_order)

        logger.info(f"Created work order: {wo_id}")
        return work_order

    def get_work_orders(self, site_id: Optional[str] = None) -> list[WorkOrder]:
        """Get all work orders, optionally filtered by site."""
        if site_id:
            return [wo for wo in self._work_orders if wo.site_id == site_id]
        return self._work_orders


# Module-level service instance
work_order_service = WorkOrderService()
