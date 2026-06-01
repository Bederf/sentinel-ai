"""FM Context Service for building data injection into Claude context."""

import logging
from datetime import UTC

from app.core.site_resolver import get_primary_site_code
from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class FMContextService:
    """Service for providing building management context to Claude."""

    def _get_site_uuid(self, site_code: str) -> str | None:
        """Resolve a site code (e.g. 'site-002') to its UUID."""
        client = get_supabase_client()
        resp = client.table("sites").select("id").eq("code", site_code).execute()
        return resp.data[0]["id"] if resp.data else None

    def _get_site_name(self, site_uuid: str) -> str:
        """Resolve a site UUID to its name."""
        client = get_supabase_client()
        resp = client.table("sites").select("name").eq("id", site_uuid).execute()
        return resp.data[0]["name"] if resp.data else "Unknown"

    def get_sites_context(self) -> str:
        """
        Get formatted site context for Claude.

        Returns:
            Markdown-formatted site information.
        """
        client = get_supabase_client()

        sites_resp = client.table("sites").select("id, code, name, region, type, sqm").execute()
        sites = sites_resp.data or []
        if not sites:
            return "No sites available."

        lines = ["| Site ID | Name | Region | Type | Size (sqm) | Equipment | Active Alerts |"]
        lines.append("|---------|------|--------|------|------------|-----------|---------------|")

        for site in sites:
            site_uuid = site["id"]
            eq_resp = client.table("equipment").select("id", count="exact").eq("site_id", site_uuid).execute()
            alert_resp = (
                client.table("alerts")
                .select("id", count="exact")
                .eq("site_id", site_uuid)
                .eq("status", "active")
                .execute()
            )
            lines.append(
                f"| {site.get('code', '')} | {site.get('name', '')} | {site.get('region', '')} | "
                f"{site.get('type', '')} | {site.get('sqm', '')} | {eq_resp.count or 0} | {alert_resp.count or 0} |"
            )

        return "\n".join(lines)

    def get_equipment_context(self, site_id: str | None = None) -> str:
        """
        Get formatted equipment context for Claude.

        Args:
            site_id: Optional site ID (code like 'site-002') to filter equipment.

        Returns:
            Markdown-formatted equipment information.
        """
        client = get_supabase_client()

        query = client.table("equipment").select("id, code, name, type, status, health_score, last_service, site_id")
        if site_id:
            site_uuid = self._get_site_uuid(site_id)
            if site_uuid:
                query = query.eq("site_id", site_uuid)
        resp = query.execute()
        equipment = resp.data or []

        if not equipment:
            return "No equipment found."

        # Build site name lookup
        site_uuids = list({e["site_id"] for e in equipment})
        if site_uuids:
            sites_resp = client.table("sites").select("id, name").in_("id", site_uuids).execute()
            site_lookup = {s["id"]: s["name"] for s in sites_resp.data}
        else:
            site_lookup = {}

        lines = ["| Equipment ID | Name | Site | Type | Status | Health | Last Service |"]
        lines.append("|--------------|------|------|------|--------|--------|--------------|")

        # Focus on equipment with issues first
        equipment_sorted = sorted(
            equipment,
            key=lambda e: (
                0 if e.get("status") == "critical" else (1 if e.get("status") == "warning" else 2),
                e.get("health_score") or 100,
            ),
        )

        # Limit to top 20 for context size
        for eq in equipment_sorted[:20]:
            site_name = site_lookup.get(eq.get("site_id"), "Unknown")
            lines.append(
                f"| {eq['id']} | {eq['name']} | {site_name[:20]} | "
                f"{eq['type']} | {eq['status']} | {eq['health_score']}% | {eq.get('last_service') or 'N/A'} |"
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
        client = get_supabase_client()

        alerts_resp = (
            client.table("alerts")
            .select("id, severity, site_id, equipment_id, title")
            .eq("status", "active")
            .order("severity")
            .execute()
        )
        active_alerts = alerts_resp.data or []

        if not active_alerts:
            return "No active alerts."

        # Build lookups
        eq_lookup = {}
        site_lookup = {}
        eq_ids = list({a["equipment_id"] for a in active_alerts if a.get("equipment_id")})
        site_uuids = list({a["site_id"] for a in active_alerts if a.get("site_id")})

        if eq_ids:
            eq_resp = client.table("equipment").select("id, name").in_("id", eq_ids).execute()
            eq_lookup = {e["id"]: e["name"] for e in eq_resp.data}
        if site_uuids:
            sites_resp = client.table("sites").select("id, name").in_("id", site_uuids).execute()
            site_lookup = {s["id"]: s["name"] for s in sites_resp.data}

        lines = ["| Alert ID | Severity | Site | Equipment | Title |"]
        lines.append("|----------|----------|------|-----------|-------|")

        for alert in active_alerts:
            site_name = site_lookup.get(alert.get("site_id"), "Unknown")
            eq_name = eq_lookup.get(alert.get("equipment_id"), "Unknown")
            title = (alert.get("title") or "")[:40]
            lines.append(
                f"| {alert['id']} | **{alert['severity'].upper()}** | {site_name[:15]} | {eq_name} | {title} |"
            )

        return "\n".join(lines)

    def get_anomalies_context(self, site_id: str | None = None) -> str:
        """
        Get formatted open anomalies/predictions context for Claude.

        Args:
            site_id: Optional site code (e.g. 'site-002') to filter anomalies.

        Returns:
            Markdown-formatted anomaly information.
        """
        client = get_supabase_client()

        try:
            query = (
                client.table("anomalies")
                .select("id, severity, type, confidence, status, site_id, equipment_id")
                .eq("status", "open")
            )

            if site_id:
                site_uuid = self._get_site_uuid(site_id)
                if site_uuid:
                    query = query.eq("site_id", site_uuid)

            resp = query.execute()
            anomalies = resp.data or []
        except Exception:
            return "No open anomalies."

        if not anomalies:
            return "No open anomalies."

        # Build lookups
        eq_lookup = {}
        site_lookup = {}
        eq_ids = list({a["equipment_id"] for a in anomalies if a.get("equipment_id")})
        site_uuids = list({a["site_id"] for a in anomalies if a.get("site_id")})

        if eq_ids:
            eq_resp = client.table("equipment").select("id, name").in_("id", eq_ids).execute()
            eq_lookup = {e["id"]: e["name"] for e in eq_resp.data}
        if site_uuids:
            sites_resp = client.table("sites").select("id, name").in_("id", site_uuids).execute()
            site_lookup = {s["id"]: s["name"] for s in sites_resp.data}

        # Sort by severity (critical first)
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        anomalies.sort(key=lambda a: (severity_order.get(a.get("severity", "low"), 4), -(a.get("confidence", 0))))

        lines = ["| Anomaly ID | Severity | Site | Equipment | Type | Confidence |"]
        lines.append("|------------|----------|------|-----------|------|------------|")

        for anomaly in anomalies:
            site_name = site_lookup.get(anomaly.get("site_id"), "Unknown")
            eq_name = eq_lookup.get(anomaly.get("equipment_id"), "Unknown")
            confidence_pct = int(anomaly.get("confidence", 0) * 100)
            lines.append(
                f"| {anomaly['id']} | **{anomaly.get('severity', 'unknown').upper()}** | {site_name[:15]} | {eq_name} | "
                f"{anomaly.get('type') or 'N/A'} | {confidence_pct}% |"
            )

        lines.append("")
        lines.append(f"**Total open anomalies:** {len(anomalies)}")

        return "\n".join(lines)

    def get_predictions_context(self, site_id: str | None = None) -> str:
        """
        Get formatted AI failure predictions context for Claude.

        Args:
            site_id: Optional site code (e.g. 'site-002') to filter predictions.

        Returns:
            Markdown-formatted prediction information with explainability.
        """
        client = get_supabase_client()

        try:
            query = (
                client.table("predictions")
                .select(
                    "id, equipment_id, site_id, prediction_type, probability_percent, confidence, "
                    "predicted_failure_date, horizon_hours, severity, evidence, contributing_factors"
                )
                .eq("status", "active")
            )

            if site_id:
                site_uuid = self._get_site_uuid(site_id)
                if site_uuid:
                    query = query.eq("site_id", site_uuid)

            resp = query.execute()
            predictions = resp.data or []
        except Exception:
            return "No AI failure predictions available."

        if not predictions:
            return "No AI failure predictions available."

        # Build lookups
        eq_ids = list({p["equipment_id"] for p in predictions if p.get("equipment_id")})
        site_uuids = list({p["site_id"] for p in predictions if p.get("site_id")})
        eq_lookup, site_lookup = {}, {}

        if eq_ids:
            eq_resp = client.table("equipment").select("id, name").in_("id", eq_ids).execute()
            eq_lookup = {e["id"]: e["name"] for e in eq_resp.data}
        if site_uuids:
            sites_resp = client.table("sites").select("id, name").in_("id", site_uuids).execute()
            site_lookup = {s["id"]: s["name"] for s in sites_resp.data}

        # Sort by probability (highest first)
        predictions.sort(key=lambda p: p.get("probability_percent", 0), reverse=True)

        lines = ["| Prediction ID | Site | Equipment | Type | Probability | Timeframe | Severity |"]
        lines.append("|---------------|------|-----------|------|-------------|----------|----------|")

        for pred in predictions:
            site_name = site_lookup.get(pred.get("site_id"), "Unknown")
            eq_name = eq_lookup.get(pred.get("equipment_id"), "Unknown")
            prob = pred.get("probability_percent", 0)
            timeframe = f"{pred.get('horizon_hours', 0) or 0:.0f}h"
            severity = pred.get("severity", "unknown").upper()
            lines.append(
                f"| {pred['id'][:8]}... | {site_name[:15]} | {eq_name} | "
                f"{pred['prediction_type']} | **{prob}%** | {timeframe} | **{severity}** |"
            )

        # Detailed breakdown for high-probability predictions
        lines.append("\n### Prediction Details (High Probability Only)")
        lines.append("")

        for pred in predictions:
            if pred.get("probability_percent", 0) < 70:
                continue

            site_name = site_lookup.get(pred.get("site_id"), "Unknown")
            eq_name = eq_lookup.get(pred.get("equipment_id"), "Unknown")
            lines.append(f"#### {eq_name} at {site_name}")
            lines.append(f"**Prediction:** {pred['prediction_type'].replace('_', ' ').title()}")
            lines.append(
                f"**Probability:** {pred['probability_percent']}% ({pred.get('confidence', 0):.0%} confidence)"
            )
            lines.append(f"**Predicted Failure:** {pred.get('predicted_failure_date') or 'N/A'}")
            lines.append(f"**Timeframe:** {pred.get('horizon_hours', 0) or 0:.0f}h")

            # Evidence
            evidence = pred.get("evidence") or {}
            if evidence:
                lines.append("**Evidence:**")
                for key, val in evidence.items():
                    if val:
                        lines.append(f"- {key.replace('_', ' ').title()}: {val}")

            # Contributing factors
            factors = pred.get("contributing_factors") or []
            if factors:
                lines.append("**Top Contributing Factors:**")
                for factor in factors[:3]:
                    w = int(factor.get("weight", 0) * 100)
                    lines.append(f"- {factor.get('factor', 'unknown')} ({w}%): {factor.get('description', '')}")

            # Financial impact
            repair = pred.get("repair_cost_zar") or 0
            loss = pred.get("potential_loss_zar") or 0
            if repair or loss:
                lines.append("**Financial Impact:**")
                lines.append(f"- Repair cost: R{repair:,.0f}")
                lines.append(f"- Potential loss: R{loss:,.0f}")
                if repair:
                    lines.append(f"- Potential savings: R{max(0, loss - repair):,.0f}")

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

    def get_full_context(self, site_id: str | None = None) -> str:
        """
        Get complete building context for Claude system prompt.

        Args:
            site_id: Optional site code (e.g. 'site-002') to scope all data to a specific site.

        Returns:
            Full markdown-formatted context with all building data.
        """
        sections = [
            "## Available Building Data\n",
            "### Sites Overview\n",
            self.get_sites_context(),
            "\n### Equipment Status (Priority Issues)\n",
            self.get_equipment_context(site_id),
            "\n### Active Alerts\n",
            self.get_alerts_context(),
            "\n### Predicted Issues (Anomalies)\n",
            self.get_anomalies_context(site_id),
            "\n### AI Failure Predictions\n",
            self.get_predictions_context(site_id),
        ]

        return "\n".join(sections)


# Module-level service instance
fm_context_service = FMContextService()
