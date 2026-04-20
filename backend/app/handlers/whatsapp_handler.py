"""
WhatsApp event handlers for SENTRY notifications.
Maps BMS events to WhatsApp messages for technicians and facility managers.
"""

import json
import logging
import os
from datetime import datetime
from typing import Any

from app.integrations.whatsapp_service import get_whatsapp_service

logger = logging.getLogger(__name__)


class WhatsAppHandler:
    """Handle WhatsApp messaging for SENTRY bot."""

    def __init__(self):
        self.service = get_whatsapp_service()
        self.technician_mapping = self._load_technician_mapping()
        self.enabled = self.service.enabled

    def _load_technician_mapping(self) -> dict[str, dict[str, Any]]:
        """Load technician WhatsApp phone numbers and details."""
        try:
            # Try to load from config file
            config_paths = [
                "backend/app/data/technicians_whatsapp.json",
                "/opt/bms-intelligence/backend/app/data/technicians_whatsapp.json",
                "app/data/technicians_whatsapp.json",
            ]

            for config_path in config_paths:
                if os.path.exists(config_path):
                    with open(config_path) as f:
                        data = json.load(f)
                        mapping = {}
                        for tech in data.get("technicians", []):
                            mapping[tech["id"]] = {
                                "phone": tech.get("whatsapp_number"),
                                "name": tech.get("name", "Unknown"),
                                "specialty": tech.get("specialty", "general"),
                            }
                        logger.info(f"Loaded {len(mapping)} technicians from {config_path}")
                        return mapping

            logger.warning("technicians_whatsapp.json not found, using local fallback data")
            return {}

        except Exception as e:
            logger.error(f"Error loading technician mapping: {e}")
            return {}

    async def send_work_order_assignment(self, work_order: dict[str, Any], technician_id: str) -> bool:
        """
        Notify technician of work order assignment via WhatsApp.

        Args:
            work_order: Work order object from BMS
            technician_id: Technician ID to notify

        Returns:
            Success status
        """
        if not self.enabled:
            logger.debug("WhatsApp disabled, skipping work order notification")
            return False

        tech_info = self.technician_mapping.get(technician_id)
        if not tech_info:
            logger.warning(f"No WhatsApp number for technician {technician_id}")
            return False

        phone = tech_info.get("phone")
        if not phone:
            return False

        priority = work_order.get("priority", "NORMAL")
        priority_emoji = "🔴" if priority == "CRITICAL" else "🟡" if priority == "HIGH" else "🟢"

        message = f"""{priority_emoji} *Work Order Assigned*

*ID*: {work_order.get("id", "N/A")}
*Priority*: {priority}
*Equipment*: {work_order.get("equipment_code", "N/A")}
*Location*: {work_order.get("location", "N/A")}
*Description*: {work_order.get("description", "No description")}"""

        try:
            result = await self.service.send_text_message(phone, message)
            if result.get("success"):
                logger.info(f"Work order {work_order.get('id')} sent to {tech_info.get('name')} via WhatsApp")
            return result.get("success", False)
        except Exception as e:
            logger.error(f"Error sending work order via WhatsApp: {e}")
            return False

    async def send_critical_alert(self, alert: dict[str, Any], recipient_ids: list[str]) -> int:
        """
        Send critical alert to multiple technicians/managers.

        Args:
            alert: Alert object from BMS
            recipient_ids: List of technician/manager IDs

        Returns:
            Count of successfully sent messages
        """
        if not self.enabled:
            logger.debug("WhatsApp disabled, skipping alert notification")
            return 0

        count = 0
        message = f"""🚨 *CRITICAL ALERT*

*Type*: {alert.get("type", "System")}
*Equipment*: {alert.get("equipment_code", "Unknown")}
*Severity*: {alert.get("severity", "High")}
*Details*: {alert.get("description", "No details")}

⚠️ Immediate action required!"""

        for recipient_id in recipient_ids:
            tech_info = self.technician_mapping.get(recipient_id)
            if tech_info:
                phone = tech_info.get("phone")
                if phone:
                    try:
                        result = await self.service.send_text_message(phone, message)
                        if result.get("success"):
                            count += 1
                            logger.info(f"Alert sent to {tech_info.get('name')} via WhatsApp")
                    except Exception as e:
                        logger.error(f"Error sending alert to {phone}: {e}")

        logger.info(f"Critical alert sent to {count}/{len(recipient_ids)} recipients via WhatsApp")
        return count

    async def send_daily_summary(
        self, facility_id: str, facility_name: str, summary: dict[str, Any], manager_id: str | None = None
    ) -> bool:
        """Send daily operations summary to facility manager."""
        if not self.enabled:
            logger.debug("WhatsApp disabled, skipping daily summary")
            return False

        if not manager_id:
            logger.warning("No manager ID provided for daily summary")
            return False

        manager_info = self.technician_mapping.get(manager_id)
        if not manager_info:
            logger.warning(f"No WhatsApp for manager {manager_id}")
            return False

        phone = manager_info.get("phone")
        if not phone:
            return False

        date_str = datetime.now().strftime("%Y-%m-%d")
        message = f"""📊 *Daily Facilities Summary* - {date_str}

*Facility*: {facility_name}

*Occupancy*: {summary.get("avg_occupancy", 0)}% average
*Energy*: {summary.get("energy_kwh", 0)} kWh used
*Equipment Status*: {summary.get("healthy_count", 0)}/{summary.get("total_count", 0)} healthy
*Alerts*: {summary.get("critical_count", 0)} critical, {summary.get("warning_count", 0)} warnings

*Recommendation*: {summary.get("recommendation", "All systems nominal")}"""

        try:
            result = await self.service.send_text_message(phone, message)
            if result.get("success"):
                logger.info(f"Daily summary sent to {manager_info.get('name')} via WhatsApp")
            return result.get("success", False)
        except Exception as e:
            logger.error(f"Error sending daily summary: {e}")
            return False

    async def send_status_update(self, to_id: str, status_text: str) -> bool:
        """Send general status update message."""
        if not self.enabled:
            return False

        tech_info = self.technician_mapping.get(to_id)
        if not tech_info:
            return False

        phone = tech_info.get("phone")
        if not phone:
            return False

        try:
            result = await self.service.send_text_message(phone, status_text)
            return result.get("success", False)
        except Exception as e:
            logger.error(f"Error sending status update: {e}")
            return False

    def get_technician_phone(self, technician_id: str) -> str | None:
        """Get WhatsApp phone number for a technician."""
        tech_info = self.technician_mapping.get(technician_id)
        return tech_info.get("phone") if tech_info else None

    def get_status(self) -> dict[str, Any]:
        """Get WhatsApp handler status."""
        return {
            "enabled": self.enabled,
            "technicians_configured": len(self.technician_mapping),
            "service_status": self.service.get_status(),
        }


# Singleton
_handler: WhatsAppHandler | None = None


def get_whatsapp_handler() -> WhatsAppHandler:
    """Get WhatsApp handler singleton."""
    global _handler
    if _handler is None:
        _handler = WhatsAppHandler()
    return _handler
