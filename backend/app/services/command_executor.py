"""Command Executor Service for simulated building control commands."""

import re
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any
import json
from pathlib import Path

from app.services.device_abstraction import device_manager
from app.services.safety_interlocks import safety_engine

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
class CommandResult:
    """Result of a command execution."""
    success: bool
    command_type: str
    target: str
    action: str
    message: str
    simulated: bool = True
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "command_type": self.command_type,
            "target": self.target,
            "action": self.action,
            "message": self.message,
            "simulated": self.simulated,
            "timestamp": self.timestamp,
        }


class CommandExecutor:
    """Service for parsing and executing building control commands."""

    # Command patterns
    TEMPERATURE_PATTERNS = [
        r"set\s+(?:the\s+)?(?:temperature|temp)\s+(?:to\s+)?(\d+)\s*°?[cC]?\s+(?:at|for|in)\s+(.+)",
        r"set\s+(.+?)\s+(?:hvac|temperature|temp)\s+to\s+(\d+)\s*°?[cC]?",
        r"change\s+(?:the\s+)?(?:temperature|temp)\s+(?:to\s+)?(\d+)\s*°?[cC]?\s+(?:at|for|in)\s+(.+)",
    ]

    LIGHTING_PATTERNS = [
        r"turn\s+(on|off)\s+(?:the\s+)?lights?\s+(?:at|for|in)\s+(.+)",
        r"switch\s+(on|off)\s+(?:the\s+)?lights?\s+(?:at|for|in)\s+(.+)",
        r"(?:lights?\s+)(on|off)\s+(?:at|for|in)\s+(.+)",
    ]

    EMERGENCY_PATTERNS = [
        r"isolate\s+(?:equipment\s+)?(.+)",
        r"emergency\s+shutdown\s+(?:for\s+)?(.+)",
        r"shut\s+down\s+(.+)",
    ]

    def __init__(self):
        """Initialize command executor."""
        self._sites = None
        self._equipment = None

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
        """Find a site by name or ID (fuzzy match)."""
        query_lower = query.lower().strip()

        # Direct ID match
        for site in self.sites:
            if site["id"].lower() == query_lower:
                return site

        # Name contains match
        for site in self.sites:
            if query_lower in site["name"].lower():
                return site

        # Partial match on name words
        for site in self.sites:
            site_words = site["name"].lower().split()
            if any(query_lower in word for word in site_words):
                return site

        return None

    def _find_equipment(self, query: str) -> Optional[dict]:
        """Find equipment by name or ID (fuzzy match)."""
        query_lower = query.lower().strip()

        # Direct ID match
        for eq in self.equipment:
            if eq["id"].lower() == query_lower:
                return eq

        # Name match
        for eq in self.equipment:
            if query_lower in eq["name"].lower():
                return eq

        return None

    def parse_command(self, message: str) -> Optional[dict]:
        """
        Parse a message to detect if it's a control command.

        Args:
            message: User message to parse

        Returns:
            Command dict if detected, None otherwise
        """
        message_lower = message.lower().strip()

        # Check temperature commands
        for pattern in self.TEMPERATURE_PATTERNS:
            match = re.search(pattern, message_lower, re.IGNORECASE)
            if match:
                groups = match.groups()
                # Handle both orderings (temp, location) and (location, temp)
                if groups[0].isdigit():
                    temp, location = groups[0], groups[1]
                else:
                    location, temp = groups[0], groups[1]
                return {
                    "type": "temperature",
                    "temperature": int(temp),
                    "location": location.strip(),
                    "raw": message,
                }

        # Check lighting commands
        for pattern in self.LIGHTING_PATTERNS:
            match = re.search(pattern, message_lower, re.IGNORECASE)
            if match:
                action, location = match.groups()
                return {
                    "type": "lighting",
                    "action": action,
                    "location": location.strip(),
                    "raw": message,
                }

        # Check emergency commands
        for pattern in self.EMERGENCY_PATTERNS:
            match = re.search(pattern, message_lower, re.IGNORECASE)
            if match:
                target = match.group(1)
                return {
                    "type": "emergency",
                    "target": target.strip(),
                    "raw": message,
                }

        return None

    async def execute_command(self, command: dict) -> CommandResult:
        """
        Execute a parsed command (simulated).

        Args:
            command: Parsed command dict from parse_command()

        Returns:
            CommandResult with execution status and message
        """
        command_type = command.get("type")

        if command_type == "temperature":
            return await self._execute_temperature(command)
        elif command_type == "lighting":
            return self._execute_lighting(command)
        elif command_type == "emergency":
            return self._execute_emergency(command)
        else:
            return CommandResult(
                success=False,
                command_type="unknown",
                target="",
                action="",
                message=f"Unknown command type: {command_type}",
            )

    async def _execute_temperature(self, command: dict) -> CommandResult:
        """Execute temperature control command."""
        temp = command["temperature"]
        location = command["location"]

        # Find the site
        site = self._find_site(location)
        if not site:
            return CommandResult(
                success=False,
                command_type="temperature",
                target=location,
                action=f"set to {temp}°C",
                message=f"Could not find site matching '{location}'. Please specify a valid site name or ID.",
            )

        # Try to find HVAC devices at this site
        devices = await device_manager.list_devices_by_site(site["id"])
        hvac_devices = [d for d in devices if d.device_type.value == "hvac"]

        if not hvac_devices:
            # Fall back to simulated execution
            return self._execute_temperature_simulated(temp, site)

        # Use the first HVAC device for demo
        device = hvac_devices[0]

        # Find temperature setpoint point
        temp_points = [p for p in device.points.values()
                      if "temp" in p.name.lower() and p.writable]

        if not temp_points:
            # Fall back to simulated execution
            return self._execute_temperature_simulated(temp, site)

        point_name = temp_points[0].name

        try:
            # Check safety validation first
            if not safety_engine._initialized:
                await safety_engine.initialize()

            safety_result = await safety_engine.validate_control(device, point_name, temp)

            if not safety_result["allowed"]:
                reasons = safety_result.get("reasons", [])
                if reasons:
                    return CommandResult(
                        success=False,
                        command_type="temperature",
                        target=f"{device.name} at {site['name']}",
                        action=f"set to {temp}°C",
                        message=f"Safety violation: {', '.join(reasons)}",
                    )
                else:
                    return CommandResult(
                        success=False,
                        command_type="temperature",
                        target=f"{device.name} at {site['name']}",
                        action=f"set to {temp}°C",
                        message="Safety validation failed for temperature control.",
                    )

            # Execute the control command
            success = await device_manager.write_device_value(device.id, point_name, temp)

            if success:
                return CommandResult(
                    success=True,
                    command_type="temperature",
                    target=f"{device.name} at {site['name']}",
                    action=f"set to {temp}°C",
                    message=f"Temperature setpoint on {device.name} [{device.id}] at {site['name']} set to {temp}°C. "
                            f"Safety validation passed: {safety_result.get('message', 'OK')}",
                )
            else:
                return CommandResult(
                    success=False,
                    command_type="temperature",
                    target=f"{device.name} at {site['name']}",
                    action=f"set to {temp}°C",
                    message=f"Failed to write temperature setpoint to {device.name}.",
                )

        except Exception as e:
            logger.error(f"Error executing temperature command: {e}")
            # Fall back to simulated execution
            return self._execute_temperature_simulated(temp, site)

    def _execute_temperature_simulated(self, temp: float, site: dict) -> CommandResult:
        """Fallback simulated temperature execution."""
        # Validate temperature range (legacy validation)
        if temp < 16 or temp > 28:
            return CommandResult(
                success=False,
                command_type="temperature",
                target=site["name"],
                action=f"set to {temp}°C",
                message=f"Temperature {temp}°C is outside the safe range (16-28°C). Please specify a temperature within range.",
            )

        return CommandResult(
            success=True,
            command_type="temperature",
            target=site["name"],
            action=f"set to {temp}°C",
            message=f"[SIMULATED] HVAC temperature at {site['name']} [{site['id']}] set to {temp}°C. "
                    f"Estimated time to reach target: 15-20 minutes.",
        )

    def _execute_lighting(self, command: dict) -> CommandResult:
        """Execute lighting control command."""
        action = command["action"]
        location = command["location"]

        # Find the site
        site = self._find_site(location)
        if not site:
            return CommandResult(
                success=False,
                command_type="lighting",
                target=location,
                action=action,
                message=f"Could not find site matching '{location}'. Please specify a valid site name or ID.",
            )

        action_verb = "turned on" if action == "on" else "turned off"
        return CommandResult(
            success=True,
            command_type="lighting",
            target=site["name"],
            action=action,
            message=f"[SIMULATED] Lights at {site['name']} [{site['id']}] have been {action_verb}. "
                    f"Energy saving mode: {'disabled' if action == 'on' else 'enabled'}.",
        )

    def _execute_emergency(self, command: dict) -> CommandResult:
        """Execute emergency isolation command."""
        target = command["target"]

        # Try to find equipment first, then site
        eq = self._find_equipment(target)
        if eq:
            return CommandResult(
                success=True,
                command_type="emergency",
                target=eq["name"],
                action="isolated",
                message=f"[SIMULATED] EMERGENCY: {eq['name']} [{eq['id']}] at site {eq['site_id']} has been isolated. "
                        f"All connected systems have been notified. Manual inspection required before restart.",
            )

        site = self._find_site(target)
        if site:
            return CommandResult(
                success=True,
                command_type="emergency",
                target=site["name"],
                action="isolated",
                message=f"[SIMULATED] EMERGENCY: Site {site['name']} [{site['id']}] has been isolated. "
                        f"All building systems set to safe mode. On-site technician dispatch recommended.",
            )

        return CommandResult(
            success=False,
            command_type="emergency",
            target=target,
            action="isolate",
            message=f"Could not find equipment or site matching '{target}'. Please specify a valid equipment ID, equipment name, or site name.",
        )


# Module-level service instance
command_executor = CommandExecutor()
