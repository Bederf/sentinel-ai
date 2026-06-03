"""Residential AI Recommender — HAIKU-powered energy advice for homeowners.

Standalone service for residential sites. Generates plain-language recommendations
delivered via Telegram. Does NOT touch commercial ai_optimizer.py.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

# System prompt for residential AI advisor
RESIDENTIAL_SYSTEM_PROMPT = """
You are SENTINEL, an AI energy advisor for a South African home
with solar power, battery backup, and regular load shedding.

YOUR ROLE:
- Monitor the home's energy system
- Give specific, timely, actionable advice
- Help the homeowner get the most from their solar investment
- Protect their battery during load shedding

YOUR RULES:
- Plain language only — no technical jargon
- Every recommendation must say exactly what to do and in which app
- Only recommend actions the homeowner can actually do right now
- Never recommend the same thing twice within 4 hours
- Recommendations must be grounded in the actual sensor values provided
- If data is missing or stale, say so — do not guess

SOUTH AFRICAN CONTEXT:
- Load shedding is frequent and scheduled via EskomSePush
- Battery backup is critical — protect it before each shed slot
- Solar surplus is an opportunity — use it for geysers, EV charging
- Grid voltage below 210V or above 250V is abnormal

OUTPUT FORMAT:
Return a JSON array of recommendations:
[
  {
    "title": "Short action title (max 8 words)",
    "message": "Plain language explanation and exact action (max 3 sentences)",
    "action_app": "SOLARMAN app|Victron VRM portal|Home Assistant",
    "severity": "advisory|opportunity|warning",
    "trigger": "what condition triggered this",
    "expected_benefit": "what the homeowner gains",
    "cost_impact_zar": null or estimated ZAR saving,
    "confidence": 0.0-1.0
  }
]

Return empty array [] if no actionable recommendations exist.
Do not invent recommendations. Only recommend when conditions warrant it.
""".strip()


@dataclass
class ResidentialRecommendation:
    title: str
    message: str
    action_app: str
    severity: str
    trigger: str
    expected_benefit: str
    cost_impact_zar: float | None
    confidence: float


class ResidentialAIRecommender:
    """
    Generates plain-language AI recommendations for residential sites.

    Uses HAIKU model for background generation (fast, cheap).
    Reads MQTT retained values, EskomSePush cache, and historical patterns.
    Delivers via Telegram — never touches commercial pipeline.
    """

    def __init__(self):
        from app.services.model_gateway import model_gateway

        self._model = model_gateway

    async def analyze(self, site_id: str) -> list[ResidentialRecommendation]:
        """Main entry point — builds context and calls AI."""
        import paho.mqtt.client as mqtt

        # Build MQTT client for retained value reading
        from app.config.settings import settings as _settings
        from app.services.residential.residential_recommendation_context import (
            ResidentialRecommendationContext,
        )

        broker = getattr(_settings, "residential_mqtt_broker", "localhost")
        port = getattr(_settings, "residential_mqtt_port", 1883)

        mqtt_client = mqtt.Client(client_id=f"sentinel-res-recs-{site_id}")
        try:
            mqtt_client.connect(broker, port, keepalive=10)
            mqtt_client.loop_start()
        except Exception as exc:
            logger.warning("MQTT connect failed for rec context %s: %s", site_id, exc)
            mqtt_client = None

        # Build context
        try:
            if mqtt_client:
                ctx = await ResidentialRecommendationContext.build(site_id, mqtt_client)
            else:
                ctx = await ResidentialRecommendationContext.build(site_id, None)
        except Exception as exc:
            logger.error("Context build failed for %s: %s", site_id, exc)
            return []

        # Check for stale data
        if ctx.last_updated:
            age = (datetime.now(UTC) - ctx.last_updated).total_seconds()
            if age > 900:  # 15 minutes
                logger.info("Skipping recommendation for %s — data stale (%.0f min)", site_id, age / 60)
                return []

        prompt = self._build_prompt(ctx)

        try:
            response = await self._call_haiku(prompt)
        except Exception as exc:
            logger.error("HAIKU call failed for %s: %s", site_id, exc)
            return []

        return self._parse_response(response, ctx)

    def _build_prompt(self, ctx) -> str:
        """Assemble the full prompt from context."""
        battery_power_str = (
            f"{ctx.battery_power_w}W charging"
            if ctx.battery_power_w and ctx.battery_power_w > 0
            else f"{abs(ctx.battery_power_w)}W discharging"
            if ctx.battery_power_w is not None
            else "unknown"
        )
        grid_status = "AVAILABLE" if ctx.grid_power_w and ctx.grid_power_w != 0 else "DOWN"
        grid_dir = (
            "importing"
            if ctx.grid_power_w and ctx.grid_power_w > 0
            else "exporting"
            if ctx.grid_power_w is not None
            else ""
        )

        if ctx.minutes_to_next_slot is not None:
            ls_context = f"Stage {ctx.loadshedding_stage} — next slot in {ctx.minutes_to_next_slot}min"
        else:
            ls_context = f"Stage {ctx.loadshedding_stage} — no slot scheduled"

        history_lines: list[str] = []
        if ctx.avg_daily_pv_kwh:
            history_lines.append(f"Average daily generation: {ctx.avg_daily_pv_kwh} kWh")
        if ctx.avg_daily_consumption_kwh:
            history_lines.append(f"Average daily consumption: {ctx.avg_daily_consumption_kwh} kWh")
        if ctx.typical_full_charge_time:
            history_lines.append(f"Typical full charge time: {ctx.typical_full_charge_time}")
        if ctx.eskom_area_code is None:
            history_lines.append("Loadshedding status unknown — area code not set")
        history_block = "\n".join(history_lines) if history_lines else "No historical data available."

        geyser_line = f"\nGeyser: {ctx.geyser_state} ({ctx.geyser_power_w}W)" if ctx.geyser_state else ""
        ev_line = f"\nEV Charger: {ctx.ev_charger_power_w}W" if ctx.ev_charger_power_w is not None else ""

        return f"""CURRENT SYSTEM STATE:
Platform: {ctx.platform_app_name}
Battery: {ctx.battery_soc_pct}% SOC, {battery_power_str}
Solar: {ctx.pv_power_w}W generation
Grid: {grid_status} ({ctx.grid_power_w}W {grid_dir})
Load: {ctx.load_power_w}W total consumption{geyser_line}{ev_line}

LOADSHEDDING:
{ls_context}
Area: {ctx.eskom_area_code or "not configured"}

HISTORICAL PATTERNS (last 7 days):
{history_block}

Generate recommendations for current conditions only."""

    async def _call_haiku(self, prompt: str) -> str:
        """Call LLM via model_gateway using 'light' task_class → MiniMax-M2.5 (no Anthropic cost)."""
        from app.services.model_gateway import model_gateway

        response = await model_gateway.call(
            task_class="light",
            messages=[{"role": "user", "content": prompt}],
            system=RESIDENTIAL_SYSTEM_PROMPT,
            max_tokens=1536,
        )
        return response

    def _parse_response(
        self,
        response: str,
        ctx,
    ) -> list[ResidentialRecommendation]:
        """Parse JSON array from model output."""
        recs = []
        try:
            # Try extracting JSON from response
            text = response.strip()
            # Handle markdown code blocks
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            text = text.strip()

            data = json.loads(text)
            if not isinstance(data, list):
                logger.warning("Residential AI response is not a list: %s", type(data))
                return []

            for item in data:
                if not isinstance(item, dict):
                    continue
                try:
                    recs.append(
                        ResidentialRecommendation(
                            title=item.get("title", "")[:80],
                            message=item.get("message", ""),
                            action_app=item.get("action_app", ctx.platform_app_name),
                            severity=item.get("severity", "advisory"),
                            trigger=item.get("trigger", ""),
                            expected_benefit=item.get("expected_benefit", ""),
                            cost_impact_zar=item.get("cost_impact_zar"),
                            confidence=float(item.get("confidence", 0.5)),
                        )
                    )
                except Exception as exc:
                    logger.debug("Skipping invalid rec item: %s", exc)
                    continue

        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse residential AI response: %s", exc)
        return recs
