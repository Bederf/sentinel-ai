"""
AI Usage Tracker Service
=========================
Tracks token consumption and costs across all AI providers:
- Anthropic (Claude Sonnet, Haiku, Opus)
- OpenAI (GPT-4.1-nano, GPT-4.1-mini)
- Sentry Gateway (Claude Sonnet via openclaw)
- Ollama (local, free but tracked for audit)
- ElevenLabs TTS (character-based pricing)

Persists to JSON with daily rollup. No external dependencies.
"""

import json
import logging
from datetime import date
from pathlib import Path
from threading import Lock
from typing import Optional

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
USAGE_FILE = DATA_DIR / "ai_usage_log.json"

# ---- Pricing (per 1M tokens, USD) — updated 2026-03 ----
# Convert to ZAR at checkout using configurable rate.

PRICING_USD_PER_1M = {
    # Anthropic
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-opus-4-20250514": {"input": 15.00, "output": 75.00},
    # OpenAI
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    # ZhipuAI
    "glm-4.7-flash": {"input": 0.10, "output": 0.10},
    # Local (free)
    "ollama": {"input": 0.00, "output": 0.00},
}

# Default USD→ZAR rate (configurable via settings)
DEFAULT_USD_ZAR = 18.50


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

    def _load_today(self):
        """Load today's usage from disk."""
        today = date.today().isoformat()
        self._today_key = today
        data = self._read_file()
        self._today_cache = data.get("daily", {}).get(today, {})

    def _read_file(self) -> dict:
        if not USAGE_FILE.exists():
            return {"daily": {}, "usd_zar_rate": self._usd_zar}
        try:
            with open(USAGE_FILE) as f:
                return json.load(f)
        except Exception:
            return {"daily": {}, "usd_zar_rate": self._usd_zar}

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
        cache_read_tokens: int = 0,
        cache_creation_tokens: int = 0,
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
        """
        today = date.today().isoformat()

        with self._write_lock:
            # Roll over day if needed
            if today != self._today_key:
                self._flush()
                self._today_key = today
                self._today_cache = {}

            # Build key: provider/model
            key = f"{provider}/{model}"
            if key not in self._today_cache:
                self._today_cache[key] = {
                    "provider": provider,
                    "model": model,
                    "calls": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cache_read_tokens": 0,
                    "cache_creation_tokens": 0,
                    "cost_usd": 0.0,
                    "sources": {},
                }

            entry = self._today_cache[key]
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

            # Flush periodically (every 10 calls)
            if entry["calls"] % 10 == 0:
                self._flush()

    def _flush(self):
        """Persist today's cache to disk."""
        try:
            data = self._read_file()
            if "daily" not in data:
                data["daily"] = {}
            data["daily"][self._today_key] = self._today_cache
            data["usd_zar_rate"] = self._usd_zar
            self._write_file(data)
        except Exception as e:
            logger.error(f"Failed to flush AI usage data: {e}")

    def flush(self):
        """Public flush — call on shutdown."""
        with self._write_lock:
            self._flush()

    def set_exchange_rate(self, usd_zar: float):
        """Update the USD/ZAR exchange rate."""
        self._usd_zar = usd_zar
        with self._write_lock:
            self._flush()

    def get_summary(self, days: int = 30) -> dict:
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
            "daily": daily_costs,
        }

    def get_today(self) -> dict:
        """Get today's usage only."""
        with self._write_lock:
            today = date.today().isoformat()
            if today != self._today_key:
                self._flush()
                self._today_key = today
                self._today_cache = {}

            rate = self._usd_zar
            total_usd = sum(e.get("cost_usd", 0) for e in self._today_cache.values())
            total_tokens = sum(e.get("input_tokens", 0) + e.get("output_tokens", 0) for e in self._today_cache.values())
            total_calls = sum(e.get("calls", 0) for e in self._today_cache.values())

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
                },
            }

    def send_daily_report_email(self, to_email: str = "info@sentinel-ai.co.za") -> bool:
        """Send a daily AI cost summary email via SMTP.

        Called by background scheduler at end of day (23:55).
        Returns True if email sent successfully.
        """
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

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

        for key, model_data in today_data.get("models", {}).items():
            lines.append(
                f"  {key}: {model_data['calls']} calls, "
                f"{model_data['input_tokens']:,}+{model_data['output_tokens']:,} tokens, "
                f"R {model_data['cost_zar']:.2f}"
            )

        if not today_data.get("models"):
            lines.append("  (no API calls today)")

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
        msg["Subject"] = f"SENTINEL AI Costs: R {total_zar:.2f} — {day_str}"
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
