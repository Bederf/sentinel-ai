"""FM Context Service for building data injection into Claude context."""

import json
import logging
from datetime import UTC
from pathlib import Path

from app.core.site_resolver import get_primary_site_code

logger = logging.getLogger(__name__)

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
        sites = load_json("sites.json") or load_json("sites.json")
        equipment = load_json("equipment.json")
        alerts = load_json("alerts.json")

        if not sites:
            return "No sites available."

        lines = ["| Site ID | Name | Region | Type | Size (sqm) | Equipment | Active Alerts |"]
        lines.append("|---------|------|--------|------|------------|-----------|---------------|")

        for site in sites:
            site_id = site.get("id", "")
            site_code = site.get("code", site_id)
            site_equipment = [e for e in equipment if e.get("site_id") == site_id or e.get("site_id") == site_id]
            site_alerts = [
                a
                for a in alerts
                if (a.get("site_id") == site_id or a.get("site_id") == site_code) and a.get("status") == "active"
            ]
            lines.append(
                f"| {site_code} | {site.get('name', '')} | {site.get('region', '')} | "
                f"{site.get('type', '')} | {site.get('sqm', '')} | {len(site_equipment)} | {len(site_alerts)} |"
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

        if site_id:
            equipment = [e for e in equipment if e.get("site_id") == site_id]

        if not equipment:
            return "No equipment found."

        # Create site lookup
        site_lookup = {s["id"]: s["name"] for s in sites}

        lines = ["| Equipment ID | Name | Site | Type | Status | Health | Last Service |"]
        lines.append("|--------------|------|------|------|--------|--------|--------------|")

        # Focus on equipment with issues first
        equipment_sorted = sorted(
            equipment,
            key=lambda e: (
                0 if e.get("status") == "critical" else (1 if e.get("status") == "warning" else 2),
                e.get("health_score", 100),
            ),
        )

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

    def get_predictions_context(self) -> str:
        """
        Get formatted AI failure predictions context for Claude.

        Returns:
            Markdown-formatted prediction information with explainability.
        """
        predictions = load_json("predictions.json")

        if not predictions:
            return "No AI failure predictions available."

        # Sort by probability (highest first)
        predictions.sort(key=lambda p: p.get("probability_percent", 0), reverse=True)

        lines = ["| Prediction ID | Site | Equipment | Type | Probability | Timeframe | Severity |"]
        lines.append("|---------------|------|-----------|------|-------------|----------|----------|")

        for pred in predictions:
            site_name = pred.get("site_name", "Unknown")
            eq_name = pred.get("equipment_name", "Unknown")
            prob = pred.get("probability_percent", 0)
            timeframe = f"{pred.get('timeframe_days', 0)} days"
            severity = pred.get("severity", "unknown").upper()
            lines.append(
                f"| {pred['id']} | {site_name[:15]} | {eq_name} | "
                f"{pred['prediction_type']} | **{prob}%** | {timeframe} | **{severity}** |"
            )

        # Add detailed explainability for each prediction
        lines.append("\n### Prediction Details (High Probability Only)")
        lines.append("")

        for pred in predictions:
            if pred.get("probability_percent", 0) < 70:
                continue

            lines.append(f"#### {pred['id']}: {pred['equipment_name']} at {pred['site_name']}")
            lines.append(f"**Prediction:** {pred['prediction_type'].replace('_', ' ').title()}")
            lines.append(f"**Probability:** {pred['probability_percent']}% ({pred['confidence']} confidence)")
            lines.append(f"**Predicted Failure:** {pred['predicted_failure_date']}")

            # Evidence summary
            evidence = pred.get("evidence", {})
            lines.append("**Evidence:**")
            repeat_wo = evidence.get("repeat_work_orders", 0)
            repeat_months = evidence.get("repeat_period_months", 0)
            lines.append(f"- Repeat work orders: {repeat_wo} in {repeat_months} months")
            asset_age = evidence.get("asset_age_years", 0)
            exp_life = evidence.get("expected_life_years", 0)
            lines.append(f"- Asset age: {asset_age} years (expected life: {exp_life} years)")

            # Top contributing factors
            lines.append("**Top Contributing Factors:**")
            factors = pred.get("contributing_factors", [])[:3]
            for factor in factors:
                weight_pct = int(factor.get("weight", 0) * 100)
                lines.append(f"- {factor['factor']} ({weight_pct}%): {factor['description']}")

            # Financial impact
            financial = pred.get("financial_impact", {})
            lines.append("**Financial Impact:**")
            lines.append(f"- Repair cost: R{financial.get('repair_cost_zar', 0):,.0f}")
            lines.append(f"- Potential loss: R{financial.get('potential_loss_zar', 0):,.0f}")
            potential_savings = financial.get("potential_loss_zar", 0) - financial.get("repair_cost_zar", 0)
            lines.append(f"- Potential savings: R{potential_savings:,.0f}")

            # Cost impact breakdown
            cost_impact = pred.get("costImpact")
            if cost_impact:
                lines.append("**Cost Impact Analysis:**")
                lines.append(f"- Failure cost: R{cost_impact.get('estimatedFailureCost', 0):,.0f}")
                lines.append(f"- Preventive cost: R{cost_impact.get('estimatedPreventiveCost', 0):,.0f}")
                lines.append(f"- **Potential savings: R{cost_impact.get('potentialSavings', 0):,.0f}**")

                failure_breakdown = cost_impact.get("failureBreakdown", {})
                if failure_breakdown:
                    lines.append("  - Failure breakdown:")
                    lines.append(f"    - Parts: R{failure_breakdown.get('parts', 0):,.0f}")
                    lines.append(f"    - Labor: R{failure_breakdown.get('labor', 0):,.0f}")
                    lines.append(f"    - Downtime: R{failure_breakdown.get('downtime', 0):,.0f}")
                    lines.append(f"    - Secondary damage: R{failure_breakdown.get('secondaryDamage', 0):,.0f}")

                preventive_breakdown = cost_impact.get("preventiveBreakdown", {})
                if preventive_breakdown:
                    lines.append("  - Preventive breakdown:")
                    lines.append(f"    - Parts: R{preventive_breakdown.get('parts', 0):,.0f}")
                    lines.append(f"    - Labor: R{preventive_breakdown.get('labor', 0):,.0f}")
                    lines.append(f"    - Downtime: R{preventive_breakdown.get('downtime', 0):,.0f}")

                story = cost_impact.get("story")
                if story:
                    lines.append(f"  - Context: {story}")

            # Similar failures
            similar = pred.get("similar_failures", [])
            if similar:
                lines.append("**Similar Historical Failures:**")
                for fail in similar[:2]:
                    lines.append(f"- {fail['site']} {fail['equipment']} (failed {fail['failure_date']})")

            lines.append("")

        return "\n".join(lines)

    def get_agent_memory_context(self, site_id: str | None = None) -> str:
        """Get agent memory context for injection into Claude system prompt.

        Returns a concise markdown block with up to 20 memories grouped by
        context_type. Keeps output under ~2-3K chars.

        Args:
            site_id: Site to load memories for.

        Returns:
            Markdown-formatted agent memory section, or empty string if none.
        """
        site_id = site_id or get_primary_site_code() or "unknown"
        try:
            from app.database.repositories.agent_memory_repository import (
                get_agent_memory_repository,
            )

            repo = get_agent_memory_repository()
            memories = repo.get_by_site(site_id, limit=20)

            if not memories:
                return ""

            # Filter out expired memories
            from datetime import datetime

            now = datetime.now(UTC)
            active = []
            for m in memories:
                expires = m.get("expires_at")
                if expires:
                    try:
                        exp_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
                        if exp_dt < now:
                            continue
                    except (ValueError, TypeError):
                        pass
                active.append(m)

            if not active:
                return ""

            # Group by context_type
            grouped: dict[str, list] = {}
            for m in active:
                ct = m.get("context_type", "other")
                grouped.setdefault(ct, []).append(m)

            TYPE_LABELS = {
                "building_quirk": "Building Quirks",
                "equipment_note": "Equipment Notes",
                "operator_preference": "Operator Preferences",
                "seasonal": "Seasonal Patterns",
                "safety_note": "Safety Notes",
            }

            lines = ["## Institutional Knowledge (Agent Memory)"]
            lines.append(
                "The following are verified observations from previous sessions. "
                "Use them to inform your responses without re-discovering."
            )
            lines.append("")

            for ctx_type, items in grouped.items():
                label = TYPE_LABELS.get(ctx_type, ctx_type.replace("_", " ").title())
                lines.append(f"### {label}")
                for item in items:
                    equip = item.get("equipment_code")
                    prefix = f"[{equip}] " if equip else ""
                    conf = item.get("confidence", 1.0)
                    conf_note = f" (confidence: {conf:.0%})" if conf < 1.0 else ""
                    lines.append(f"- {prefix}**{item['key']}**: {item['value']}{conf_note}")
                lines.append("")

            return "\n".join(lines)

        except Exception as e:
            logger.warning("Could not load agent memory context: %s", e)
            return ""

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
            "\n### AI Failure Predictions\n",
            self.get_predictions_context(),
        ]

        return "\n".join(sections)


# Module-level service instance
fm_context_service = FMContextService()
