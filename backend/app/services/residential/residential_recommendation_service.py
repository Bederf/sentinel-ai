"""Residential recommendation service — dedup, gating, and Telegram delivery.

Routes AI-generated residential recommendations to homeowners via Telegram.
Never touches commercial RecommendationService or dashboard.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime

import redis

from app.config.settings import settings
from app.database.supabase_client import get_supabase_client
from app.services.residential.residential_ai_recommender import (
    ResidentialAIRecommender,
    ResidentialRecommendation,
)

logger = logging.getLogger(__name__)

# Redis key prefixes
_DEDUP_PREFIX = "recs:dedup:"
_AEGIS_P1_PREFIX = "aegis:p1:"
_DEDUP_TTL_SECONDS = 4 * 3600  # 4 hours
_AEGIS_P1_TTL_SECONDS = 3600  # P1 gate lasts 1 hour


class ResidentialRecommendationService:
    """
    Delivers AI recommendations to residential users via Telegram.

    Key behaviours:
    - 4h dedup window per (site_id, recommendation_hash)
    - AEGIS P1 gate: no recommendations during active P1 events
    - Loadshedding-aware: opportunity recommendations suppressed during outage
    - Message format: icon + title + message + estimated saving
    """

    def __init__(self):
        self._redis = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_timeout=2,
            socket_connect_timeout=2,
        )
        self._recommender = ResidentialAIRecommender()
        self._sender = self._load_sender()

    @staticmethod
    def _load_sender():
        from app.services.residential.residential_telegram_sender import (
            ResidentialTelegramSender,
        )

        return ResidentialTelegramSender()

    # ── Public API ─────────────────────────────────────────────────────────────

    async def process_site(self, site_id: str) -> int:
        """Run recommendation cycle for one site. Returns count delivered."""
        # 1. Check AEGIS P1 gate
        if self._is_aegis_p1_active(site_id):
            logger.debug("Skipping recommendations for %s — P1 AEGIS active", site_id)
            return 0

        # 2. Generate recommendations
        recs = await self._recommender.analyze(site_id)
        if not recs:
            return 0

        # 3. Get context for gating decisions
        ctx = self._build_light_context(site_id)

        # 4. Process each recommendation
        delivered = 0
        for rec in recs:
            if not self._should_deliver(site_id, rec, ctx):
                continue

            chat_id = self._get_chat_id(site_id)
            if not chat_id:
                logger.warning("No chat_id for site %s", site_id)
                continue

            msg = self._format_message(rec)
            severity = self._telegram_severity(rec.severity)

            try:
                sent = await self._sender.send_alert(
                    chat_id=chat_id,
                    message=msg,
                    severity=severity,
                    platform=ctx.get("platform", "solarman"),
                )
            except Exception as exc:
                logger.error("send_alert failed for %s: %s", site_id, exc)
                sent = False

            if sent:
                self._mark_delivered(site_id, rec)
                self._store_recommendation(site_id, rec, ctx)
                delivered += 1

        return delivered

    # ── Gating helpers ────────────────────────────────────────────────────────

    def _is_aegis_p1_active(self, site_id: str) -> bool:
        """Check if AEGIS P1 is active for this site (Redis check)."""
        try:
            return self._redis.exists(f"{_AEGIS_P1_PREFIX}{site_id}") == 1
        except Exception as exc:
            logger.warning("Redis P1 check failed for %s: %s", site_id, exc)
            return False  # fail open — don't block recommendations

    def set_aegis_p1_active(self, site_id: str) -> None:
        """Called by AEGIS dispatch when P1 fires. Sets Redis gate for 1h."""
        try:
            key = f"{_AEGIS_P1_PREFIX}{site_id}"
            self._redis.setex(key, _AEGIS_P1_TTL_SECONDS, "1")
        except Exception as exc:
            logger.warning("Could not set P1 gate for %s: %s", site_id, exc)

    def _should_deliver(
        self,
        site_id: str,
        rec: ResidentialRecommendation,
        ctx: dict,
    ) -> bool:
        """Apply all gating rules."""
        # Dedup check
        if self._is_duplicate(site_id, rec):
            return False

        # Loadshedding gate: no opportunity recs during grid outage
        ls_stage = ctx.get("loadshedding_stage", 0)
        grid_power = ctx.get("grid_power_w")
        is_outage = ls_stage > 0 and grid_power is not None and grid_power == 0

        if is_outage and rec.severity == "opportunity":
            return False

        # Near-shedding gate: only warning/advisory within 2h of slot
        minutes_to = ctx.get("minutes_to_next_slot")
        if ls_stage > 0 and minutes_to is not None and minutes_to < 120:
            if rec.severity not in ("warning", "advisory"):
                return False

        return True

    def _is_duplicate(self, site_id: str, rec: ResidentialRecommendation) -> bool:
        """Check dedup window — returns True if same rec delivered within 4h."""
        key = f"{_DEDUP_PREFIX}{site_id}:{_rec_hash(rec)}"
        try:
            return self._redis.exists(key) == 1
        except Exception:
            return False  # fail open

    def _mark_delivered(self, site_id: str, rec: ResidentialRecommendation) -> None:
        """Set dedup key with 4h TTL."""
        try:
            key = f"{_DEDUP_PREFIX}{site_id}:{_rec_hash(rec)}"
            self._redis.setex(key, _DEDUP_TTL_SECONDS, "1")
        except Exception as exc:
            logger.warning("Could not set dedup key for %s: %s", site_id, exc)

    # ── Context helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _build_light_context(site_id: str) -> dict:
        """Lightweight context for gating decisions (no MQTT call)."""
        from app.services.residential.eskomsepush_client import get_area_schedule

        try:
            supabase = get_supabase_client()
            row = (
                supabase.table("residential_sites")
                .select("platform,eskom_area_code")
                .eq("site_id", site_id)
                .maybe_execute()
            )
            platform = row.data[0].get("platform", "solarman") if row.data else "solarman"
            area_code = row.data[0].get("eskom_area_code") if row.data else None
        except Exception as exc:
            logger.warning("Could not fetch site ctx for %s: %s", site_id, exc)
            platform = "solarman"
            area_code = None

        ls_stage = 0
        minutes_to = None
        if area_code:
            sched = get_area_schedule(area_code)
            if sched and sched.stage:
                ls_stage = sched.stage
                if sched.next_slot_start:
                    delta = (sched.next_slot_start - datetime.now(UTC)).total_seconds()
                    minutes_to = max(0, int(delta / 60))

        # Grid power: try MQTT last known value (approximate via Redis cache)
        grid_power_key = f"sentinel:{site_id}:energy:grid_power_w"
        grid_power = None
        try:
            gp = redis.from_url(settings.redis_url, decode_responses=True).get(grid_power_key)
            if gp:
                grid_power = float(gp)
        except Exception:
            pass

        return {
            "platform": platform,
            "loadshedding_stage": ls_stage,
            "minutes_to_next_slot": minutes_to,
            "grid_power_w": grid_power,
            "eskom_area_code": area_code,
        }

    # ── Formatting ────────────────────────────────────────────────────────────

    SEVERITY_ICONS = {
        "warning": "⚠️",
        "advisory": "💡",
        "opportunity": "☀️",
    }

    def _format_message(self, rec: ResidentialRecommendation) -> str:
        icon = self.SEVERITY_ICONS.get(rec.severity, "💡")
        msg = f"{icon} {rec.title}\n\n{rec.message}"
        if rec.cost_impact_zar:
            msg += f"\n\nEstimated saving: ~R{rec.cost_impact_zar:.0f}/month"
        return msg

    @staticmethod
    def _telegram_severity(severity: str) -> str:
        return severity if severity in ("P1", "P2", "warning", "advisory", "opportunity") else "advisory"

    # ── Storage ─────────────────────────────────────────────────────────────

    def _store_recommendation(
        self,
        site_id: str,
        rec: ResidentialRecommendation,
        ctx: dict,
    ) -> None:
        """Store delivered recommendation in residential_recommendations table."""
        try:
            supabase = get_supabase_client()
            chat_id = self._get_chat_id(site_id)
            supabase.table("residential_recommendations").insert(
                {
                    "site_id": site_id,
                    "chat_id": chat_id,
                    "platform": ctx.get("platform", "solarman"),
                    "title": rec.title,
                    "message": rec.message,
                    "action_app": rec.action_app,
                    "severity": rec.severity,
                    "trigger": rec.trigger,
                    "expected_benefit": rec.expected_benefit,
                    "cost_impact_zar": rec.cost_impact_zar,
                    "confidence": rec.confidence,
                    "delivered_at": datetime.now(UTC).isoformat(),
                    "outcome_improved": None,  # filled by outcome tracker
                }
            ).execute()
        except Exception as exc:
            logger.warning("Could not store recommendation for %s: %s", site_id, exc)

    @staticmethod
    def _get_chat_id(site_id: str) -> int | None:
        try:
            supabase = get_supabase_client()
            result = supabase.table("residential_sites").select("chat_id").eq("site_id", site_id).maybe_execute()
            if result.data:
                return result.data[0].get("chat_id")
        except Exception as exc:
            logger.warning("Could not fetch chat_id for %s: %s", site_id, exc)
        return None


def _rec_hash(rec: ResidentialRecommendation) -> str:
    """Hash of site_id + title + severity — not just title."""
    data = f"{rec.title}:{rec.severity}"
    return hashlib.sha1(data.encode()).hexdigest()[:12]  # nosec - dedup hash, not security
