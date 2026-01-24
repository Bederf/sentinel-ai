"""FM Context Service for building data injection into Claude context."""

import json
from pathlib import Path

# Data directory
DATA_DIR = Path(__file__).parent.parent / "data"


def load_json(filename: str) -> list[dict]:
    """Load JSON data file."""
    filepath = DATA_DIR / filename
    if filepath.exists():
        with open(filepath) as f:
            return json.load(f)
    return []


class FMContextService:
    """Service for providing building management context to Claude."""

    def get_sites_context(self) -> str:
        """
        Get formatted site context for Claude.

        Returns:
            Markdown-formatted site information.
        """
        sites = load_json("sites.json")
        equipment = load_json("equipment.json")
        alerts = load_json("alerts.json")

        if not sites:
            return "No sites available."

        lines = ["| Site ID | Name | Region | Type | Size (sqm) | Equipment | Active Alerts |"]
        lines.append("|---------|------|--------|------|------------|-----------|---------------|")

        for site in sites:
            site_equipment = [e for e in equipment if e.get("site_id") == site["id"]]
            site_alerts = [
                a for a in alerts
                if a.get("site_id") == site["id"] and a.get("status") == "active"
            ]
            lines.append(
                f"| {site['id']} | {site['name']} | {site['region']} | "
                f"{site['type']} | {site['sqm']} | {len(site_equipment)} | {len(site_alerts)} |"
            )

        return "\n".join(lines)

    def get_equipment_context(self, site_id: str | None = None) -> str:
        """
        Get formatted equipment context for Claude.

        Args:
            site_id: Optional site ID to filter equipment.

        Returns:
            Markdown-formatted equipment information.
        """
        equipment = load_json("equipment.json")
        sites = load_json("sites.json")
        alerts = load_json("alerts.json")

        if site_id:
            equipment = [e for e in equipment if e.get("site_id") == site_id]

        if not equipment:
            return "No equipment found."

        # Create site lookup
        site_lookup = {s["id"]: s["name"] for s in sites}

        lines = ["| Equipment ID | Name | Site | Type | Status | Health | Last Service |"]
        lines.append("|--------------|------|------|------|--------|--------|--------------|")

        # Focus on equipment with issues first
        equipment_sorted = sorted(equipment, key=lambda e: (
            0 if e.get("status") == "critical" else (1 if e.get("status") == "warning" else 2),
            e.get("health_score", 100)
        ))

        # Limit to top 20 for context size
        for eq in equipment_sorted[:20]:
            site_name = site_lookup.get(eq.get("site_id"), "Unknown")
            lines.append(
                f"| {eq['id']} | {eq['name']} | {site_name[:20]} | "
                f"{eq['type']} | {eq['status']} | {eq['health_score']}% | {eq['last_service']} |"
            )

        if len(equipment) > 20:
            lines.append(f"\n*Showing top 20 of {len(equipment)} equipment items (sorted by status/health)*")

        return "\n".join(lines)

    def get_alerts_context(self) -> str:
        """
        Get formatted active alerts context for Claude.

        Returns:
            Markdown-formatted alert information.
        """
        alerts = load_json("alerts.json")
        equipment = load_json("equipment.json")
        sites = load_json("sites.json")

        # Filter to active alerts only
        active_alerts = [a for a in alerts if a.get("status") == "active"]

        if not active_alerts:
            return "No active alerts."

        # Create lookups
        eq_lookup = {eq["id"]: eq["name"] for eq in equipment}
        site_lookup = {s["id"]: s["name"] for s in sites}

        # Sort by priority (1 = highest)
        active_alerts.sort(key=lambda a: a.get("priority", 99))

        lines = ["| Alert ID | Severity | Site | Equipment | Title | Est. Cost (ZAR) |"]
        lines.append("|----------|----------|------|-----------|-------|-----------------|")

        for alert in active_alerts:
            site_name = site_lookup.get(alert.get("site_id"), "Unknown")
            eq_name = eq_lookup.get(alert.get("equipment_id"), "Unknown")
            cost = alert.get("estimated_cost_zar", 0)
            lines.append(
                f"| {alert['id']} | **{alert['severity'].upper()}** | {site_name[:15]} | "
                f"{eq_name} | {alert['title'][:40]}... | R{cost:,.0f} |"
            )

        return "\n".join(lines)

    def get_anomalies_context(self) -> str:
        """
        Get formatted anomalies/predictions context for Claude.

        Returns:
            Markdown-formatted anomaly information.
        """
        anomalies = load_json("anomalies.json")
        equipment = load_json("equipment.json")
        sites = load_json("sites.json")

        if not anomalies:
            return "No anomalies detected."

        # Create lookups
        eq_lookup = {eq["id"]: eq["name"] for eq in equipment}
        site_lookup = {s["id"]: s["name"] for s in sites}

        # Sort by urgency
        urgency_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        anomalies.sort(key=lambda a: urgency_order.get(a.get("urgency", "low"), 4))

        lines = ["| Anomaly ID | Site | Equipment | Type | Urgency | Predicted Failure | Confidence |"]
        lines.append("|------------|------|-----------|------|---------|-------------------|------------|")

        for anomaly in anomalies:
            site_name = site_lookup.get(anomaly.get("site_id"), "Unknown")
            eq_name = eq_lookup.get(anomaly.get("equipment_id"), "Unknown")
            confidence_pct = int(anomaly.get("confidence", 0) * 100)
            lines.append(
                f"| {anomaly['id']} | {site_name[:15]} | {eq_name} | "
                f"{anomaly['type']} | **{anomaly['urgency'].upper()}** | "
                f"{anomaly['predicted_failure']} | {confidence_pct}% |"
            )

        # Add summary
        total_repair = sum(a.get("repair_cost_zar", 0) for a in anomalies)
        total_damage = sum(a.get("damage_cost_zar", 0) for a in anomalies)
        lines.append("")
        lines.append(f"**Total Repair Cost:** R{total_repair:,.0f}")
        lines.append(f"**Potential Damage if Unaddressed:** R{total_damage:,.0f}")

        return "\n".join(lines)

    def get_full_context(self) -> str:
        """
        Get complete building context for Claude system prompt.

        Returns:
            Full markdown-formatted context with all building data.
        """
        sections = [
            "## Available Building Data\n",
            "### Sites Overview\n",
            self.get_sites_context(),
            "\n### Equipment Status (Priority Issues)\n",
            self.get_equipment_context(),
            "\n### Active Alerts\n",
            self.get_alerts_context(),
            "\n### Predicted Issues (Anomalies)\n",
            self.get_anomalies_context(),
        ]

        return "\n".join(sections)


# Module-level service instance
fm_context_service = FMContextService()
