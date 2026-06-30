from __future__ import annotations

import logging
import re
from typing import Any

from app.database.supabase_client import get_supabase_client
from app.services.residential.residential_telegram_sender import ResidentialTelegramSender

logger = logging.getLogger(__name__)

_sender = ResidentialTelegramSender()

_TIME_RANGE_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)-([01]\d|2[0-3]):([0-5]\d)$")

KNOWN_ALERT_KEYS: dict[str, tuple[str, str]] = {
    "battery": ("battery_critical_enabled", "bool"),
    "pre_shed": ("pre_shed_enabled", "bool"),
    "grid_voltage": ("grid_voltage_enabled", "bool"),
    "inverter_alarm": ("inverter_alarm_enabled", "bool"),
    "pv_fault": ("pv_fault_enabled", "bool"),
    "battery_charge": ("battery_charge_fault_enabled", "bool"),
    "data_stale": ("data_stale_enabled", "bool"),
    "geyser": ("geyser_pre_shed_enabled", "bool"),
    "ev": ("ev_charger_drain_enabled", "bool"),
    "solar_surplus": ("solar_surplus_geyser_enabled", "bool"),
    "inverter_mismatch": ("inverter_mismatch_enabled", "bool"),
    "battery_temp": ("battery_overtemp_enabled", "bool"),
    "battery_soh": ("battery_soh_low_enabled", "bool"),
    "victron_battery": ("battery_degraded_enabled", "bool"),
    "victron_voltage": ("input_voltage_low_enabled", "bool"),
    "runaway": ("runaway_enabled", "bool"),
    "runaway_hours": ("runaway_hours", "float"),
    "overnight": ("overnight_enabled", "bool"),
    "overnight_window": ("overnight_window", "time_range"),
    "cost": ("cost_limit_enabled", "bool"),
    "cost_limit": ("cost_limit_zar", "float"),
    "kw_rating": ("appliance_kw_rating", "float"),
    "tariff": ("tariff_zar_per_kwh", "float"),
}

_FLOAT_RANGES = {
    "runaway_hours": (1.0, 24.0),
    "cost_limit_zar": (1.0, 10000.0),
    "appliance_kw_rating": (0.1, 20.0),
    "tariff_zar_per_kwh": (0.01, 20.0),
}


async def handle_alerts_command(chat_id: int, args: str) -> str:
    site = _load_site(chat_id)
    if site is None:
        message = "No active connection. Send /connect first."
        await _sender.send_text(chat_id, message)
        return message

    alert_config = site.get("alert_config") or {}
    if not args.strip():
        message = _format_status(alert_config)
        await _sender.send_text(chat_id, message)
        return message

    try:
        updates, message = _parse_updates(args.strip())
    except ValueError as exc:
        message = str(exc)
        await _sender.send_text(chat_id, message)
        return message

    merged = {**alert_config, **updates}
    _save_config(site["site_id"], merged)
    await _sender.send_text(chat_id, message)
    return message


def _load_site(chat_id: int) -> dict[str, Any] | None:
    result = (
        get_supabase_client()
        .table("residential_sites")
        .select("site_id,alert_config")
        .eq("chat_id", chat_id)
        .eq("is_active", True)
        .maybe_execute()
    )
    if not result.data:
        return None
    return result.data[0]


def _save_config(site_id: str, alert_config: dict[str, Any]) -> None:
    get_supabase_client().table("residential_sites").update({"alert_config": alert_config}).eq(
        "site_id", site_id
    ).execute()


def _parse_updates(args: str) -> tuple[dict[str, Any], str]:
    parts = args.split()
    key = parts[0].lower()
    if key not in KNOWN_ALERT_KEYS:
        raise ValueError(f"Unknown setting: {key}")

    config_key, value_type = KNOWN_ALERT_KEYS[key]
    if key == "cost" and len(parts) >= 3 and _parse_bool(parts[1]) is True:
        limit = _parse_positive_float(parts[2], "cost limit", *_FLOAT_RANGES["cost_limit_zar"])
        return {"cost_limit_enabled": True, "cost_limit_zar": limit}, f"Daily cost limit alert enabled at R{limit:.0f}."

    if value_type == "bool":
        if len(parts) < 2:
            raise ValueError(f"Usage: /alerts {key} <on|off>")
        enabled = _parse_bool(parts[1])
        if enabled is None:
            raise ValueError(f"Invalid value for {key}: use on or off")
        label = key.replace("_", " ")
        return {config_key: enabled}, f"{label.title()} alert {'enabled' if enabled else 'disabled'}."

    if value_type == "float":
        if len(parts) < 2:
            raise ValueError(f"Usage: /alerts {key} <number>")
        minimum, maximum = _FLOAT_RANGES[config_key]
        value = _parse_positive_float(parts[1], key.replace("_", " "), minimum, maximum)
        return {config_key: value}, f"{key.replace('_', ' ').title()} set to {value:g}."

    if value_type == "time_range":
        if len(parts) < 2:
            raise ValueError(f"Usage: /alerts {key} HH:MM-HH:MM")
        match = _TIME_RANGE_RE.match(parts[1])
        if not match:
            raise ValueError("Invalid overnight window. Use HH:MM-HH:MM, for example 22:00-06:00.")
        start, end = parts[1].split("-", 1)
        return {config_key: [start, end]}, f"Overnight window set to {start}-{end}."

    raise ValueError(f"Unsupported setting type for {key}")


def _parse_bool(value: str) -> bool | None:
    normalised = value.lower()
    if normalised in {"on", "true", "yes", "1"}:
        return True
    if normalised in {"off", "false", "no", "0"}:
        return False
    return None


def _parse_positive_float(value: str, label: str, minimum: float, maximum: float) -> float:
    cleaned = value.strip().removeprefix("R").removeprefix("r")
    try:
        parsed = float(cleaned)
    except ValueError as exc:
        raise ValueError(f"Invalid {label}: enter a number.") from exc
    if parsed < minimum or parsed > maximum:
        raise ValueError(f"Invalid {label}: must be between {minimum:g} and {maximum:g}.")
    return parsed


def _enabled(config: dict[str, Any], key: str, default: bool = True) -> bool:
    return bool(config.get(key, default))


def _format_status(config: dict[str, Any]) -> str:
    runaway_hours = float(config.get("runaway_hours", 6))
    cost_limit = float(config.get("cost_limit_zar", 50))
    kw_rating = float(config.get("appliance_kw_rating", 1.5))
    overnight_window = config.get("overnight_window", ["22:00", "06:00"])
    start, end = overnight_window[0], overnight_window[1]

    return (
        "Your alert settings:\n\n"
        f"{_mark(_enabled(config, 'runaway_enabled', True))} Runs too long ({runaway_hours:g}h) - /alerts runaway off\n"
        f"{_mark(_enabled(config, 'overnight_enabled', False))} Overnight usage ({start}-{end}) - /alerts overnight on\n"
        f"{_mark(_enabled(config, 'cost_limit_enabled', False))} Daily cost limit (R{cost_limit:.0f}) - /alerts cost on {cost_limit:.0f}\n"
        f"Appliance rating: {kw_rating:g}kW - /alerts kw_rating 2.5\n\n"
        "Core safety alerts default on unless disabled:\n"
        f"{_mark(_enabled(config, 'battery_critical_enabled'))} Battery critical\n"
        f"{_mark(_enabled(config, 'grid_voltage_enabled'))} Grid voltage\n"
        f"{_mark(_enabled(config, 'inverter_alarm_enabled'))} Inverter alarms\n"
        f"{_mark(_enabled(config, 'data_stale_enabled'))} Data stale\n\n"
        "Type: /alerts <name> <on|off> [value]"
    )


def _mark(enabled: bool) -> str:
    return "✅" if enabled else "⬜"
