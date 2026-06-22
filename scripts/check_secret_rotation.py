#!/usr/bin/env python3
"""
Secret Rotation Reminder — checks rotation log for overdue secrets.

Exit codes:
  0 — all secrets within rotation window
  1 — one or more secrets overdue
"""

import re
import sys
from datetime import datetime, timedelta

ROTATION_LOG = "/opt/bms-intelligence/docs/09-security/secret-rotation-log.md"

ROTATION_INTERVALS = {
    "AI Provider Keys": 90,
    "Telegram Bot Tokens": 90,
    "SMTP / IMAP Passwords": 180,
    "Database Credentials": 180,
    "JWT Signing Key": 365,
    "Encryption Keys": 365,
    "Bridge / Internal Service Tokens": 180,
    "Third-party API Keys": 365,
}

SECRET_CLASS_KEYWORDS = {
    "AI Provider Keys": ["ANTHROPIC", "OPENAI", "DEEPSEEK", "MINIMAX", "ELEVENLABS", "FIRECRAWL"],
    "Telegram Bot Tokens": ["SENTRY_BOT", "SENTRY_CLIENT", "SENTRY_TECH", "SENTRY_MANAGER", "HOME_BOT", "TELEGRAM_BOT"],
    "SMTP / IMAP Passwords": ["SMTP_PASSWORD", "NOTIFICATION_SMTP", "ROOMS_SMTP", "ROOMS_IMAP"],
    "Database Credentials": ["DATABASE_URL", "SUPABASE_SERVICE_ROLE"],
    "JWT Signing Key": ["JWT_SECRET"],
    "Encryption Keys": ["ENCRYPTION_KEY", "SOPS"],
    "Bridge / Internal Service Tokens": ["BRIDGE_API_TOKEN", "INTERNAL_SERVICE_KEY"],
    "Third-party API Keys": ["ESKOMSEPUSH", "OPENWEATHER", "SOLARMAN", "N8N_API_KEY", "MCP_API_KEY"],
}


def parse_rotation_log(path):
    entries = []
    try:
        with open(path) as f:
            content = f.read()
    except FileNotFoundError:
        print(f"ERROR: rotation log not found at {path}")
        return entries
    in_table = False
    for line in content.split("\n"):
        if line.startswith("| Secret | Date |"):
            in_table = True
            continue
        if in_table and line.startswith("|"):
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) >= 3:
                secret = parts[0]
                date_str = parts[1]
                try:
                    date = datetime.strptime(date_str, "%Y-%m-%d")
                    entries.append({"secret": secret, "date": date})
                except ValueError:
                    pass
        elif in_table and not line.startswith("|"):
            in_table = False
    return entries


def classify_secret(secret_name):
    for secret_class, keywords in SECRET_CLASS_KEYWORDS.items():
        for kw in keywords:
            if kw in secret_name.upper():
                return secret_class
    return None


def check_rotations(entries):
    overdue = []
    for entry in entries:
        secret_class = classify_secret(entry["secret"])
        if secret_class is None:
            continue
        interval_days = ROTATION_INTERVALS.get(secret_class, 90)
        deadline = entry["date"] + timedelta(days=interval_days)
        if datetime.now() > deadline:
            overdue.append(
                f"  OVERDUE: {entry['secret']} ({secret_class}) — "
                f"rotated {entry['date'].strftime('%Y-%m-%d')}, "
                f"due {deadline.strftime('%Y-%m-%d')} "
                f"(over by {(datetime.now() - deadline).days}d)"
            )
        else:
            remaining = (deadline - datetime.now()).days
            if remaining <= 14:
                print(f"  WARNING: {entry['secret']} ({secret_class}) — due in {remaining}d")
    return overdue


def check_unrotated(entries):
    rotated_secrets = {e["secret"] for e in entries}
    unrotated = []
    known = [
        "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "MINIMAX_API_KEY", "ZAI_API_KEY",
        "FIRECRAWL_API_KEY", "TWILIO_AUTH_TOKEN", "WHATSAPP_API_TOKEN",
        "SMTP_PASSWORD", "JWT_SECRET_KEY", "ENCRYPTION_KEY",
        "INTERNAL_SERVICE_KEY", "ESKOMSEPUSH_API_TOKEN", "MCP_API_KEY",
        "SOLARMAN_APP_SECRET", "OPENWEATHER_API_KEY", "N8N_API_KEY",
        "SENTRY_WEBHOOK_SECRET", "CONSENT_HASH_SALT",
    ]
    for secret in known:
        if secret not in rotated_secrets:
            unrotated.append(f"  UNTRACKED: {secret} — never logged as rotated")
    return unrotated


def main():
    print("=== Secret Rotation Check ===")
    print(f"Run: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    entries = parse_rotation_log(ROTATION_LOG)
    if not entries:
        print("No rotation entries found.")
        sys.exit(1)
    print(f"Entries: {len(entries)}\n")
    overdue = check_rotations(entries)
    unrotated = check_unrotated(entries)
    all_issues = overdue + unrotated
    if all_issues:
        print("Issues:")
        for i in all_issues:
            print(i)
        print(f"\nTotal: {len(overdue)} overdue, {len(unrotated)} untracked")
        sys.exit(1)
    else:
        print("All secrets within rotation window.")
        sys.exit(0)


if __name__ == "__main__":
    main()
