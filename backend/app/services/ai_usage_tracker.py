"""
AI Usage Tracker Service
=========================
Tracks token consumption and costs across all paid services:
- Anthropic (Claude Sonnet, Haiku, Opus)
- OpenAI (GPT-4.1-nano, GPT-4.1-mini)
- ZhipuAI / Z.ai (GLM-4.7-flash)
- Sentry Gateway (Claude Sonnet via openclaw)
- Ollama (local, free but tracked for audit)
- ElevenLabs TTS (character-based pricing)
- WhatsApp (Meta Cloud API / Twilio)
- BulkSMS (per-message pricing)
- Telegram (free but tracked for audit)
- EskomSePush (free tier, tracked for quota)

Persists to JSON with daily rollup. No external dependencies.
"""

import asyncio
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Optional
from zoneinfo import ZoneInfo

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
USAGE_FILE = DATA_DIR / "ai_usage_log.json"

# ---- Pricing (per 1M tokens, USD) — updated 2026-04 ----
# Convert to ZAR at checkout using configurable rate.
# Models must match model_gateway routing + routing_profiles.py entries exactly.

PRICING_USD_PER_1M = {
    # Anthropic
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-opus-4-6": {"input": 15.00, "output": 75.00},
    # OpenAI
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    # MiniMax
    "MiniMax-M2.5": {"input": 0.15, "output": 0.95, "cached_input": 0.06},
    "MiniMax-M2.7": {"input": 0.30, "output": 1.20, "cached_input": None},
    # Azure OpenAI (uses OpenAI pricing tiers)
    "azure_openai/gpt-4o": {"input": 2.50, "output": 10.00},
    "azure_openai/gpt-4o-mini": {"input": 0.15, "output": 0.60},
    # ZhipuAI
    "glm-4.7-flash": {"input": 0.10, "output": 0.10},
    # Moonshot / Kimi
    "kimi-k2.6": {"input": 0.95, "output": 4.00},
    "kimi-k2.5": {"input": 0.80, "output": 3.20},
    "kimi-k2-thinking-turbo": {"input": 1.00, "output": 4.50},
    "kimi-k2-turbo-preview": {"input": 0.90, "output": 3.80},
    # DeepSeek
    "deepseek-chat": {"input": 0.27, "output": 1.10},
}

# ---- Per-message pricing (USD) ----
MESSAGE_PRICING_USD = {
    "whatsapp_meta": 0.005,  # Meta Cloud API conversation fee
    "whatsapp_twilio": 0.005,  # Twilio WhatsApp per-message
    "bulksms": 0.006,  # BulkSMS per-SMS (ZA rate)
    "telegram": 0.0,  # Free — tracked for audit
}

# ---- Per-unit service pricing (USD) ----
SERVICE_PRICING_USD = {
    "elevenlabs_chars": 0.00003,  # ~$0.03 per 1K characters
    "eskomsepush_call": 0.0,  # Free tier (50 req/day)
}

# Default USD→ZAR rate (configurable via settings)
DEFAULT_USD_ZAR = 18.50

# Interactive task classes — excluded from token budget enforcement
INTERACTIVE_TASK_CLASSES = frozenset({"chat_ai", "chat_tech"})


class TokenBudgetExceeded(Exception):
    """Raised when a site's daily token budget is exceeded."""

    def __init__(self, site_id: str, current: int, budget: int):
        self.site_id = site_id
        self.current = current
        self.budget = budget
        super().__init__(f"Daily token budget exceeded for {site_id}: {current}/{budget}")


class AiUsageTracker:
    """Thread-safe singleton that logs every AI API call with token counts."""

    _instance: Optional["AiUsageTracker"] = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._write_lock = Lock()
        self._today_cache: dict = {}
        self._today_key: str = ""
        self._usd_zar = DEFAULT_USD_ZAR
        self._load_today()
        # Token budget infrastructure
        self._redis = None
        self._redis_checked = False
        self._memory_daily_totals: dict[str, int] = {}  # site_id -> total tokens today
        self._memory_alert_sent: dict[str, bool] = {}  # site_id -> alert sent today
        # Supabase primary store (Phase 193+)
        self._client = None
        self._pending_rows: list[dict] = []  # daily usage rows waiting to flush

    @property
    def _supabase(self):
        if self._client is None:
            self._client = get_supabase_client()
        return self._client

    def _load_today(self):
        """Load today's usage from DB (Supabase primary, JSON fallback retired)."""
        today = date.today().isoformat()
        self._today_key = today
        self._today_cache = {}
        try:
            result = self._supabase.table("ai_usage_daily").select("*").eq("date", today).execute()
            for row in result.data:
                key = f"{row['provider']}/{row['model']}|{row.get('site_id', 'unknown')}"
                self._today_cache[key] = {
                    "provider": row["provider"],
                    "model": row["model"],
                    "site_id": row.get("site_id", "unknown"),
                    "calls": row.get("calls", 0),
                    "input_tokens": row.get("input_tokens", 0),
                    "output_tokens": row.get("output_tokens", 0),
                    "cache_read_tokens": row.get("cache_read_tokens", 0),
                    "cache_creation_tokens": row.get("cache_creation_tokens", 0),
                    "cost_usd": float(row.get("cost_usd", 0)),
                    "sources": row.get("sources", {}),
                }
        except Exception:
            pass

    def _sast_date(self) -> str:
        """Return today's date in SAST (UTC+2)."""
        return datetime.now(ZoneInfo("Africa/Johannesburg")).strftime("%Y-%m-%d")

    def _get_redis(self):
        """Lazy Redis connection for budget counters."""
        if self._redis is not None:
            return self._redis
        if self._redis_checked:
            return None
        try:
            from app.config.settings import settings

            if not settings.redis_enabled:
                self._redis_checked = True
                return None
            import redis

            self._redis = redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            self._redis.ping()
            self._redis_checked = True
            return self._redis
        except Exception as e:
            logger.warning("Token budget Redis unavailable, using memory fallback: %s", e)
            self._redis_checked = True
            self._redis = None
            return None

    async def _get_daily_total(self, site_id: str) -> int:
        """Get today's token total for a site from Redis, or 0 if unavailable."""
        today = self._sast_date()
        key = f"token_budget:{site_id}:{today}"
        redis_client = self._get_redis()
        if redis_client:
            try:
                val = await asyncio.to_thread(redis_client.get, key)
                return int(val) if val else 0
            except Exception:
                return 0
        return self._memory_daily_totals.get(key, 0)

    def _increment_daily_total(self, site_id: str, tokens: int) -> int:
        """Atomically increment daily total. Returns new total. Uses Redis INCRBY or memory fallback."""
        today = self._sast_date()
        key = f"token_budget:{site_id}:{today}"
        redis_client = self._get_redis()
        if redis_client:
            try:
                new_total = redis_client.incrby(key, tokens)
                redis_client.expire(key, 86400)
                return int(new_total)
            except Exception:
                pass
        # Memory fallback
        current = self._memory_daily_totals.get(key, 0)
        new_total = current + tokens
        self._memory_daily_totals[key] = new_total
        return new_total

    async def _check_alert_sent(self, site_id: str) -> bool:
        """Check if budget alert has already been sent today for this site."""
        today = self._sast_date()
        key = f"token_budget_alert:{site_id}:{today}"
        redis_client = self._get_redis()
        if redis_client:
            try:
                val = await asyncio.to_thread(redis_client.get, key)
                return bool(val)
            except Exception:
                return self._memory_alert_sent.get(key, False)
        return self._memory_alert_sent.get(key, False)

    async def _mark_alert_sent(self, site_id: str) -> None:
        """Mark that a budget alert has been sent today for this site."""
        today = self._sast_date()
        key = f"token_budget_alert:{site_id}:{today}"
        redis_client = self._get_redis()
        if redis_client:
            try:
                await asyncio.to_thread(redis_client.setex, key, 86400, "1")
                return
            except Exception:
                pass
        self._memory_alert_sent[key] = True

    async def _send_budget_alert(self, site_id: str, current: int, budget: int) -> None:
        """Send Telegram budget alert via ThreadPoolExecutor (fire-and-forget)."""
        pct = (current / budget * 100) if budget > 0 else 0
        try:
            from concurrent.futures import ThreadPoolExecutor

            from app.services.notification_providers.telegram_provider import TelegramProvider

            tp = TelegramProvider()
            if not tp.is_enabled():
                logger.warning("Telegram not configured, cannot send budget alert for %s", site_id)
                return

            def _send():
                try:
                    tp.send_budget_alert(site_id, current, budget, pct)
                except Exception as e:
                    logger.warning("Budget alert failed for %s: %s", site_id, e)

            ThreadPoolExecutor(max_workers=1).submit(_send)
        except Exception as e:
            logger.warning("Failed to send token budget alert: %s", e)

    async def _check_and_enforce_budget(self, site_id: str, tokens: int, task_class: str) -> None:
        """Check budget and raise TokenBudgetExceeded or send alert as needed."""
        from app.config.settings import settings

        if settings.token_budget_exclude_interactive:
            if task_class in INTERACTIVE_TASK_CLASSES:
                return

        new_total = self._increment_daily_total(site_id, tokens)
        budget = settings.daily_token_budget_per_site

        if new_total >= budget * settings.token_budget_alert_threshold:
            if not await self._check_alert_sent(site_id):
                await self._send_budget_alert(site_id, new_total, budget)
                await self._mark_alert_sent(site_id)

        if new_total >= budget and settings.token_budget_hard_limit:
            raise TokenBudgetExceeded(site_id, new_total, budget)

    def _read_file(self) -> dict:
        """Legacy fallback — reads from JSON (not used for new writes)."""
        if not USAGE_FILE.exists():
            return {"daily": {}, "usd_zar_rate": self._usd_zar}
        try:
            with open(USAGE_FILE) as f:
                return json.load(f)
        except Exception:
            return {"daily": {}, "usd_zar_rate": self._usd_zar}

    def _flush_daily_to_db(self, key: str, entry: dict):
        """Write a daily usage row to Supabase."""
        parts = key.split("|")
        provider = parts[0].split("/")[0] if "/" in parts[0] else parts[0]
        model = parts[0].split("/")[1] if "/" in parts[0] else parts[0]
        site_id = parts[1] if len(parts) > 1 else "unknown"
        today = date.today().isoformat()
        try:
            self._supabase.table("ai_usage_daily").upsert(
                {
                    "date": today,
                    "provider": provider,
                    "model": model,
                    "site_id": site_id,
                    "calls": entry.get("calls", 0),
                    "input_tokens": entry.get("input_tokens", 0),
                    "output_tokens": entry.get("output_tokens", 0),
                    "cache_read_tokens": entry.get("cache_read_tokens", 0),
                    "cache_creation_tokens": entry.get("cache_creation_tokens", 0),
                    "cost_usd": entry.get("cost_usd", 0),
                    "sources": entry.get("sources", {}),
                },
                on_conflict="date,provider,model,site_id",
            ).execute()
        except Exception as exc:
            logger.warning("Failed to flush usage to DB: %s", exc)

    def _write_file(self, data: dict):
        USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(USAGE_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def record(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        source: str = "chat",
        site_id: str = "unknown",
        cache_read_tokens: int = 0,
        cache_creation_tokens: int = 0,
        task_class: str = "",
        feature: str | None = None,
        session_id: str | None = None,
    ):
        """Record a single AI API call.

        Args:
            provider: "anthropic", "openai", "ollama", "elevenlabs", "sentry"
            model: Model ID string
            input_tokens: Input/prompt tokens
            output_tokens: Output/completion tokens
            source: "chat", "tools", "sentry", "background", "vision", "tts"
            cache_read_tokens: Anthropic prompt cache read tokens (75% discount)
            cache_creation_tokens: Anthropic prompt cache write tokens (25% surcharge)
            task_class: Optional task class for budget enforcement ("heavy", "medium",
                "light", "chat_ai", "chat_tech"). Defaults to "" (checked but not enforced).
            feature: Optional feature tag for cost attribution (e.g. "rag_query",
                "email_ocr", "recommendation", "gsd_phase_193"). Defaults to source.
            session_id: Optional session identifier for per-session tracking.
        """
        today = date.today().isoformat()

        with self._write_lock:
            # Roll over day if needed
            if today != self._today_key:
                self._flush()
                self._today_key = today
                self._today_cache = {}

            # Build key: provider/model/site to preserve site-scoped accounting.
            site_key = (site_id or "unknown").strip() or "unknown"
            key = f"{provider}/{model}|{site_key}"
            if key not in self._today_cache:
                self._today_cache[key] = {
                    "provider": provider,
                    "model": model,
                    "site_id": site_key,
                    "calls": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cache_read_tokens": 0,
                    "cache_creation_tokens": 0,
                    "cost_usd": 0.0,
                    "sources": {},
                    "feature": feature or source,
                    "session_id": session_id,
                }

            entry = self._today_cache[key]
            if feature:
                entry["feature"] = feature
            if session_id:
                entry["session_id"] = session_id
            entry["calls"] += 1
            entry["input_tokens"] += input_tokens
            entry["output_tokens"] += output_tokens
            entry["cache_read_tokens"] += cache_read_tokens
            entry["cache_creation_tokens"] += cache_creation_tokens

            # Track by source
            entry["sources"][source] = entry["sources"].get(source, 0) + 1

            # Calculate cost
            pricing = PRICING_USD_PER_1M.get(model, {"input": 0, "output": 0})
            # Standard tokens
            cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
            # Cache read tokens are 90% cheaper (only 10% of input price)
            cost += (cache_read_tokens * pricing["input"] * 0.1) / 1_000_000
            # Cache creation tokens are 25% more expensive
            cost += (cache_creation_tokens * pricing["input"] * 1.25) / 1_000_000
            entry["cost_usd"] += cost

            # Phase 160: Governance metrics — token/cost by route
            try:
                from app.services.governance_metrics_collector import governance_metrics

                governance_metrics.record_ai_usage(
                    route=source,
                    site_id=site_key,
                    provider=provider,
                    model=model,
                    task_class=task_class,
                    tokens=input_tokens + output_tokens,
                    cost=cost,
                )
            except Exception:
                pass

            # Flush periodically (every 10 calls)
            if entry["calls"] % 10 == 0:
                self._flush()

            # Budget enforcement (Phase 185 Wave 2)
            total_tokens = input_tokens + output_tokens
            if total_tokens > 0 and site_key != "unknown":
                try:
                    # Run synchronously to ensure budget check completes before record() returns
                    # (avoid async task race condition in tests and scheduler call sites)
                    asyncio.get_event_loop().run_until_complete(
                        self._check_and_enforce_budget(site_key, total_tokens, task_class)
                    )
                except RuntimeError:
                    # No event loop — create one for this call
                    asyncio.run(self._check_and_enforce_budget(site_key, total_tokens, task_class))
                except Exception:
                    # Budget check failures must never block usage recording
                    pass

    def record_message(
        self,
        provider: str,
        recipient_count: int = 1,
        source: str = "alert",
        site_id: str = "unknown",
    ):
        """Record a messaging API call (WhatsApp, BulkSMS, Telegram).

        Uses fixed per-message pricing from MESSAGE_PRICING_USD.
        Stores as provider/message key with zero tokens.
        """
        unit_cost = MESSAGE_PRICING_USD.get(provider, 0.0) * recipient_count
        self.record(
            provider=provider,
            model="message",
            input_tokens=0,
            output_tokens=0,
            source=source,
            site_id=site_id,
        )
        # Override cost (record() would compute 0 from tokens)
        with self._write_lock:
            site_key = (site_id or "unknown").strip() or "unknown"
            key = f"{provider}/message|{site_key}"
            if key in self._today_cache:
                self._today_cache[key]["cost_usd"] += unit_cost
        self._check_cost_alert()

    def record_service(
        self,
        provider: str,
        units: int,
        unit_type: str = "chars",
        source: str = "tts",
        site_id: str = "unknown",
    ):
        """Record a unit-based service call (ElevenLabs chars, EskomSePush calls).

        Uses per-unit pricing from SERVICE_PRICING_USD.
        """
        pricing_key = f"{provider}_{unit_type}"
        unit_cost = SERVICE_PRICING_USD.get(pricing_key, 0.0) * units
        self.record(
            provider=provider,
            model=unit_type,
            input_tokens=0,
            output_tokens=0,
            source=source,
            site_id=site_id,
        )
        # Override cost and store unit count
        with self._write_lock:
            site_key = (site_id or "unknown").strip() or "unknown"
            key = f"{provider}/{unit_type}|{site_key}"
            if key in self._today_cache:
                self._today_cache[key]["cost_usd"] += unit_cost
        self._check_cost_alert()

    def record_escalation(
        self,
        from_class: str,
        to_class: str,
        reason: str,
        mode: str,
        resolved_model: str,
        session_id: str = "",
        provider: str = "",
    ) -> None:
        """
        Log an escalation event to ai_usage_log.json.

        Escalation schema (extends existing log format):
        {
            "event": "escalation_triggered",
            "timestamp": "<ISO8601>",
            "from_class": "<from_class>",
            "to_class": "<to_class>",
            "reason": "<reason>",
            "mode": "<mode>",
            "resolved_model": "<resolved_model>",
            "session_id": "<session_id>",
            "provider": "<provider>"
        }

        Written to the same ai_usage_log.json file via the existing write mechanism.
        No cost fields — escalation events are metadata, not billable calls.
        The actual escalated call is recorded separately via record() when it executes.
        """
        from datetime import datetime

        event = {
            "event": "escalation_triggered",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "from_class": from_class,
            "to_class": to_class,
            "reason": reason,
            "mode": mode,
            "resolved_model": resolved_model,
            "session_id": session_id,
            "provider": provider,
        }

        with self._write_lock:
            try:
                self._supabase.table("ai_usage_escalations").insert(
                    {
                        "timestamp": event["timestamp"],
                        "provider": event.get("provider", ""),
                        "escalation_type": "escalation_triggered",
                        "site_id": event.get("mode", ""),
                        "details": json.dumps(
                            {
                                "from_class": event.get("from_class"),
                                "to_class": event.get("to_class"),
                                "reason": event.get("reason"),
                                "resolved_model": event.get("resolved_model"),
                                "session_id": event.get("session_id"),
                            }
                        ),
                    }
                ).execute()
            except Exception as exc:
                logger.warning("Failed to write escalation to DB: %s", exc)

    def _check_cost_alert(self):
        """Send Telegram alert if daily spend exceeds threshold."""
        try:
            from app.config.settings import settings

            threshold = getattr(settings, "cost_alert_daily_threshold_zar", 100.0)
            if threshold <= 0:
                return

            total_usd = sum(e.get("cost_usd", 0) for e in self._today_cache.values())
            total_zar = total_usd * self._usd_zar

            if total_zar < threshold:
                return

            # Only alert once per day — use a flag in cache
            if self._today_cache.get("_cost_alert_sent"):
                return
            self._today_cache["_cost_alert_sent"] = True

            chat_id = getattr(settings, "cost_alert_telegram_chat_id", "") or getattr(
                settings, "telegram_alert_chat_id", ""
            )
            bot_token = getattr(settings, "telegram_bot_token", "")
            if not (chat_id and bot_token):
                logger.warning("Cost alert threshold exceeded (R %.2f) but no Telegram config", total_zar)
                return

            import httpx

            msg = (
                f"⚠️ *SENTINEL Cost Alert*\n"
                f"Daily spend: R {total_zar:.2f} (threshold: R {threshold:.2f})\n"
                f"USD: ${total_usd:.4f}"
            )
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            # Fire-and-forget sync call (we're already in a lock context)
            try:
                httpx.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}, timeout=5.0)
                logger.info("Cost alert sent: R %.2f exceeds threshold R %.2f", total_zar, threshold)
            except Exception as exc:
                logger.error("Failed to send cost alert: %s", exc)
        except Exception:
            pass  # Never let alert logic break tracking

    def _flush(self):
        """Persist today's cache to Supabase (DB primary, JSON retired in Phase 193+)."""
        for key, entry in self._today_cache.items():
            self._flush_daily_to_db(key, entry)

    def _get_cache_stats(self, days: int = 30) -> dict:
        """Calculate cache efficiency metrics from Supabase (primary store)."""
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        try:
            result = (
                self._supabase.table("ai_usage_daily")
                .select("input_tokens,cache_read_tokens,output_tokens")
                .gte("date", cutoff)
                .execute()
            )
            total_input = 0
            total_cache_read = 0
            total_output = 0
            for row in result.data:
                total_input += row.get("input_tokens", 0) or 0
                total_cache_read += row.get("cache_read_tokens", 0) or 0
                total_output += row.get("output_tokens", 0) or 0
            cache_hit_rate = (total_cache_read / total_input) if total_input > 0 else 0
            return {
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "cache_read_tokens": total_cache_read,
                "cache_hit_rate": round(cache_hit_rate, 4),
                "cache_hit_pct": round(cache_hit_rate * 100, 2),
            }
        except Exception as exc:
            logger.warning("Failed to get cache stats from DB, falling back to JSON: %s", exc)
            # Fallback to JSON for backwards compatibility
            data = self._read_file()
            daily = data.get("daily", {})
            today_dt = date.today()
            cutoff_dt = today_dt - timedelta(days=days)
            total_input = 0
            total_cache_read = 0
            total_output = 0
            for day_str, entries in daily.items():
                try:
                    day_date = date.fromisoformat(day_str)
                except ValueError:
                    continue
                if day_date < cutoff_dt:
                    continue
                for key, entry in entries.items():
                    if str(key).startswith("_"):
                        continue
                    total_input += entry.get("input_tokens", 0)
                    total_cache_read += entry.get("cache_read_tokens", 0)
                    total_output += entry.get("output_tokens", 0)
            cache_hit_rate = (total_cache_read / total_input) if total_input > 0 else 0
            return {
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "cache_read_tokens": total_cache_read,
                "cache_hit_rate": round(cache_hit_rate, 4),
                "cache_hit_pct": round(cache_hit_rate * 100, 2),
            }

    def _group_by_feature(self, days: int = 30) -> dict:
        """Group usage by feature from Supabase (primary store)."""
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        try:
            result = (
                self._supabase.table("ai_usage_daily")
                .select("sources,calls,input_tokens,output_tokens,cost_usd")
                .gte("date", cutoff)
                .execute()
            )
            by_feature: dict = {}
            for row in result.data:
                sources = row.get("sources", {}) or {}
                call_count = row.get("calls", 0) or 0
                in_tok = row.get("input_tokens", 0) or 0
                out_tok = row.get("output_tokens", 0) or 0
                cost = row.get("cost_usd", 0.0) or 0.0
                tokens = in_tok + out_tok

                if isinstance(sources, dict) and sources:
                    for feature in sources:
                        if feature not in by_feature:
                            by_feature[feature] = {"calls": 0, "tokens": 0, "cost_usd": 0.0}
                        by_feature[feature]["calls"] += call_count
                        by_feature[feature]["tokens"] += tokens
                        by_feature[feature]["cost_usd"] += cost
                else:
                    feature = "unknown"
                    if feature not in by_feature:
                        by_feature[feature] = {"calls": 0, "tokens": 0, "cost_usd": 0.0}
                    by_feature[feature]["calls"] += call_count
                    by_feature[feature]["tokens"] += tokens
                    by_feature[feature]["cost_usd"] += cost
            return by_feature
        except Exception as exc:
            logger.warning("Failed to get feature stats from DB, falling back to JSON: %s", exc)
            # Fallback to JSON for backwards compatibility
            data = self._read_file()
            daily = data.get("daily", {})
            today_dt = date.today()
            cutoff_dt = today_dt - timedelta(days=days)
            by_feature: dict = {}
            for day_str, entries in daily.items():
                try:
                    day_date = date.fromisoformat(day_str)
                except ValueError:
                    continue
                if day_date < cutoff_dt:
                    continue
                for key, entry in entries.items():
                    if str(key).startswith("_"):
                        continue
                    src_map = entry.get("sources", {}) or {}
                    feature = (
                        entry.get("feature")
                        or entry.get("source")
                        or (list(src_map.keys())[0] if src_map else "unknown")
                    )
                    if feature not in by_feature:
                        by_feature[feature] = {"calls": 0, "tokens": 0, "cost_usd": 0.0}
                    by_feature[feature]["calls"] += entry.get("calls", 0)
                    by_feature[feature]["tokens"] += entry.get("input_tokens", 0) + entry.get("output_tokens", 0)
                    by_feature[feature]["cost_usd"] += entry.get("cost_usd", 0.0)
            return by_feature

    def flush(self):
        """Public flush — call on shutdown."""
        with self._write_lock:
            self._flush()

    def set_exchange_rate(self, usd_zar: float):
        """Update the USD/ZAR exchange rate."""
        self._usd_zar = usd_zar
        with self._write_lock:
            self._flush()

    def get_summary(self, days: int = 30, site_id: str | None = None) -> dict:
        """Get usage summary for the last N days."""
        with self._write_lock:
            self._flush()

        data = self._read_file()
        daily = data.get("daily", {})
        rate = data.get("usd_zar_rate", DEFAULT_USD_ZAR)

        # Filter to last N days
        today = date.today()
        cutoff = date(today.year, today.month, today.day)
        from datetime import timedelta

        cutoff = cutoff - timedelta(days=days)

        totals_by_provider: dict = {}
        totals_by_model: dict = {}
        totals_by_source: dict = {}
        daily_costs: list = []
        grand_total_usd = 0.0
        grand_total_tokens = 0

        for day_str, models in sorted(daily.items()):
            try:
                day_date = date.fromisoformat(day_str)
            except ValueError:
                continue
            if day_date < cutoff:
                continue

            day_cost = 0.0
            day_tokens = 0
            for key, entry in models.items():
                if str(key).startswith("_"):
                    continue
                entry_site = str(entry.get("site_id", "unknown")).strip() or "unknown"
                if site_id and entry_site != site_id:
                    continue
                provider = entry.get("provider", "unknown")
                model = entry.get("model", "unknown")
                cost = entry.get("cost_usd", 0)
                tokens = entry.get("input_tokens", 0) + entry.get("output_tokens", 0)

                # By provider
                if provider not in totals_by_provider:
                    totals_by_provider[provider] = {"calls": 0, "tokens": 0, "cost_usd": 0.0}
                totals_by_provider[provider]["calls"] += entry.get("calls", 0)
                totals_by_provider[provider]["tokens"] += tokens
                totals_by_provider[provider]["cost_usd"] += cost

                # By model
                if model not in totals_by_model:
                    totals_by_model[model] = {"calls": 0, "tokens": 0, "cost_usd": 0.0}
                totals_by_model[model]["calls"] += entry.get("calls", 0)
                totals_by_model[model]["tokens"] += tokens
                totals_by_model[model]["cost_usd"] += cost

                # By source/route (apportion cost across sources by call share)
                source_counts = entry.get("sources", {}) or {}
                total_source_calls = sum(source_counts.values()) or entry.get("calls", 0) or 1
                for source_name, source_call_count in source_counts.items():
                    if source_name not in totals_by_source:
                        totals_by_source[source_name] = {"calls": 0, "tokens": 0, "cost_usd": 0.0}
                    share = float(source_call_count) / float(total_source_calls)
                    totals_by_source[source_name]["calls"] += source_call_count
                    totals_by_source[source_name]["tokens"] += int(tokens * share)
                    totals_by_source[source_name]["cost_usd"] += cost * share

                day_cost += cost
                day_tokens += tokens
                grand_total_usd += cost
                grand_total_tokens += tokens

            daily_costs.append(
                {
                    "date": day_str,
                    "cost_usd": round(day_cost, 4),
                    "cost_zar": round(day_cost * rate, 2),
                    "tokens": day_tokens,
                }
            )

        return {
            "period_days": days,
            "usd_zar_rate": rate,
            "total_cost_usd": round(grand_total_usd, 4),
            "total_cost_zar": round(grand_total_usd * rate, 2),
            "total_tokens": grand_total_tokens,
            "by_provider": {
                k: {**v, "cost_usd": round(v["cost_usd"], 4), "cost_zar": round(v["cost_usd"] * rate, 2)}
                for k, v in sorted(totals_by_provider.items(), key=lambda x: -x[1]["cost_usd"])
            },
            "by_model": {
                k: {**v, "cost_usd": round(v["cost_usd"], 4), "cost_zar": round(v["cost_usd"] * rate, 2)}
                for k, v in sorted(totals_by_model.items(), key=lambda x: -x[1]["cost_usd"])
            },
            "by_source": {
                k: {**v, "cost_usd": round(v["cost_usd"], 4), "cost_zar": round(v["cost_usd"] * rate, 2)}
                for k, v in sorted(totals_by_source.items(), key=lambda x: -x[1]["cost_usd"])
            },
            "by_feature": self._group_by_feature(),
            "cache_stats": self._get_cache_stats(days=days),
            "daily": daily_costs,
        }

    def get_today(self, site_id: str | None = None) -> dict:
        """Get today's usage only."""
        with self._write_lock:
            today = date.today().isoformat()
            if today != self._today_key:
                self._flush()
                self._today_key = today
                self._today_cache = {}

            rate = self._usd_zar

            def _included(entry: dict) -> bool:
                if site_id is None:
                    return True
                return str(entry.get("site_id", "unknown")).strip() == site_id

            filtered_entries = [e for k, e in self._today_cache.items() if not str(k).startswith("_") and _included(e)]
            total_usd = sum(e.get("cost_usd", 0) for e in filtered_entries)
            total_tokens = sum(e.get("input_tokens", 0) + e.get("output_tokens", 0) for e in filtered_entries)
            total_calls = sum(e.get("calls", 0) for e in filtered_entries)
            totals_by_source: dict[str, dict] = {}
            for entry in filtered_entries:
                tokens = entry.get("input_tokens", 0) + entry.get("output_tokens", 0)
                cost = entry.get("cost_usd", 0.0)
                source_counts = entry.get("sources", {}) or {}
                total_source_calls = sum(source_counts.values()) or entry.get("calls", 0) or 1
                for source_name, source_call_count in source_counts.items():
                    bucket = totals_by_source.setdefault(source_name, {"calls": 0, "tokens": 0, "cost_usd": 0.0})
                    share = float(source_call_count) / float(total_source_calls)
                    bucket["calls"] += source_call_count
                    bucket["tokens"] += int(tokens * share)
                    bucket["cost_usd"] += cost * share

            return {
                "date": today,
                "total_calls": total_calls,
                "total_tokens": total_tokens,
                "total_cost_usd": round(total_usd, 4),
                "total_cost_zar": round(total_usd * rate, 2),
                "models": {
                    k: {
                        "calls": v.get("calls", 0),
                        "input_tokens": v.get("input_tokens", 0),
                        "output_tokens": v.get("output_tokens", 0),
                        "cost_usd": round(v.get("cost_usd", 0), 4),
                        "cost_zar": round(v.get("cost_usd", 0) * rate, 2),
                    }
                    for k, v in self._today_cache.items()
                    if not str(k).startswith("_") and _included(v)
                },
                "by_source": {
                    k: {**v, "cost_usd": round(v["cost_usd"], 4), "cost_zar": round(v["cost_usd"] * rate, 2)}
                    for k, v in sorted(totals_by_source.items(), key=lambda x: -x[1]["cost_usd"])
                },
            }

    def send_daily_report_email(self, to_email: str = "info@sentinel-ai.co.za") -> bool:
        """Send a daily AI cost summary email via SMTP.

        Called by background scheduler at end of day (23:55).
        Returns True if email sent successfully.
        """
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        from app.config.settings import settings

        # Get today's data (or yesterday if called manually)
        today_data = self.get_today()

        total_zar = today_data["total_cost_zar"]
        total_usd = today_data["total_cost_usd"]
        total_calls = today_data["total_calls"]
        total_tokens = today_data["total_tokens"]

        # Also get 30-day running total
        monthly = self.get_summary(days=30)
        monthly_zar = monthly["total_cost_zar"]

        # Build email body
        day_str = today_data["date"]

        lines = [
            f"SENTINEL AI Cost Report — {day_str}",
            "=" * 50,
            "",
            f"Today's Spend:   R {total_zar:.2f}  (${total_usd:.4f} USD)",
            f"API Calls:       {total_calls}",
            f"Tokens Used:     {total_tokens:,}",
            "",
            "--- By Model ---",
        ]

        ai_models = {}
        messaging_models = {}
        service_models = {}
        for key, model_data in today_data.get("models", {}).items():
            if key.endswith("/message"):
                messaging_models[key] = model_data
            elif key.endswith("/chars") or key.endswith("/calls"):
                service_models[key] = model_data
            else:
                ai_models[key] = model_data

        for key, model_data in ai_models.items():
            lines.append(
                f"  {key}: {model_data['calls']} calls, "
                f"{model_data['input_tokens']:,}+{model_data['output_tokens']:,} tokens, "
                f"R {model_data['cost_zar']:.2f}"
            )

        if not ai_models:
            lines.append("  (no AI calls today)")

        if messaging_models:
            lines.extend(["", "--- Messaging ---"])
            for key, model_data in messaging_models.items():
                provider = key.split("/")[0]
                lines.append(f"  {provider}: {model_data['calls']} messages, R {model_data['cost_zar']:.2f}")

        if service_models:
            lines.extend(["", "--- Services ---"])
            for key, model_data in service_models.items():
                lines.append(f"  {key}: {model_data['calls']} calls, R {model_data['cost_zar']:.2f}")

        # Token budget section (Phase 185 Wave 2)
        import asyncio


        budget = settings.daily_token_budget_per_site
        budget_lines = ["", "--- Token Budget ---"]
        site_budget_found = False
        for site_id in sorted(set(e.get("site_id", "unknown") for e in self._today_cache.values())):
            if site_id == "unknown":
                continue
            site_budget_found = True
            try:
                site_total = asyncio.run(self._get_daily_total(site_id))
            except Exception:
                site_total = 0
            if site_total == 0:
                continue
            pct = site_total / budget * 100 if budget > 0 else 0
            status = "✅ within budget" if site_total < budget else "🚨 EXCEEDED"
            budget_lines.append(f"  {site_id}: {site_total:,} / {budget:,} ({pct:.0f}%) — {status}")
        if not site_budget_found:
            budget_lines.append("  (no site-scoped data)")

        lines.extend(budget_lines)
        lines.extend(
            [
                "",
                "--- 30-Day Running Total ---",
                f"  Total Spend:   R {monthly_zar:.2f}",
                f"  Total Tokens:  {monthly['total_tokens']:,}",
            ]
        )

        for provider, pdata in monthly.get("by_provider", {}).items():
            lines.append(f"  {provider}: R {pdata['cost_zar']:.2f} ({pdata['calls']} calls)")

        # Cache efficiency (30-day)
        cache_stats = monthly.get("cache_stats")
        if cache_stats and cache_stats.get("total_input_tokens", 0) > 0:
            lines.extend(
                [
                    "",
                    "--- Cache Efficiency (30d) ---",
                    f"  Input Tokens:     {cache_stats['total_input_tokens']:,}",
                    f"  Cache Read:      {cache_stats['cache_read_tokens']:,}",
                    f"  Hit Rate:        {cache_stats['cache_hit_pct']:.1f}%",
                ]
            )
        else:
            lines.extend(
                [
                    "",
                    "--- Cache Efficiency (30d) ---",
                    "  (no cache data available)",
                ]
            )

        # By feature (30-day)
        by_feature = monthly.get("by_feature")
        if by_feature:
            lines.extend(
                [
                    "",
                    "--- By Feature (30d) ---",
                ]
            )
            for feature, fdata in sorted(by_feature.items(), key=lambda x: -x[1]["tokens"]):
                lines.append(
                    f"  {feature}: {fdata['calls']} calls, "
                    f"{fdata['tokens']:,} tokens, "
                    f"R {fdata['cost_usd'] * self._usd_zar:.2f}"
                )

        lines.extend(
            [
                "",
                f"Exchange Rate:   1 USD = R {self._usd_zar:.2f}",
                "",
                "— SENTINEL AI Operations",
            ]
        )

        body = "\n".join(lines)

        # Use notification SMTP config
        host = settings.notification_smtp_host
        port = settings.notification_smtp_port
        username = settings.notification_smtp_username
        password = settings.notification_smtp_password

        if not (host and username and password):
            logger.warning("No SMTP configured — cannot send AI cost report email")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"SENTINEL Service Costs: R {total_zar:.2f} — {day_str}"
        msg["From"] = f"SENTINEL AI Ops <{username}>"
        msg["To"] = to_email
        msg.attach(MIMEText(body, "plain"))

        try:
            server = smtplib.SMTP(host, port, timeout=15)
            server.starttls()
            server.login(username, password)
            server.sendmail(username, to_email, msg.as_string())
            server.quit()
            logger.info("AI cost report email sent to %s (R %.2f)", to_email, total_zar)
            return True
        except Exception as exc:
            logger.error("Failed to send AI cost report email: %s", exc)
            return False


# Singleton
usage_tracker = AiUsageTracker()
