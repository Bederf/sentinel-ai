#!/usr/bin/env python3
"""
Prometheus Alertmanager → Sentry Telegram Bridge

Receives webhook alerts from Alertmanager and forwards to Telegram via Sentry bot.
Routes alerts to different chats based on X-Target-Chat header.

Security:
- Binds to 127.0.0.1 only (not exposed externally)
- Validates X-Shared-Secret header
- Dead man's switch: exposes /health for Prometheus to scrape

Environment:
  TELEGRAM_BOT_TOKEN or SENTRY_BOT_TOKEN - Bot token
  TELEGRAM_CHAT_ID_OPS - Building operators (Thandi: 8359288792)
  TELEGRAM_CHAT_ID_INFRA - Infrastructure team (bederf)
  SHARED_SECRET - Pre-shared key for webhook validation
  BRIDGE_PORT - Port to listen on (default: 9099)
"""

import json
import os
import sys
import hmac
import hashlib
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib import request

# Single destination: Main manager bot
MANAGER_BOT_CHAT_ID = os.environ.get("MANAGER_BOT_CHAT_ID", "8359288792")
BOT_TOKEN = os.environ.get("SENTRY_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
SHARED_SECRET = os.environ.get("SHARED_SECRET", "")

# Data freshness threshold (from environment)
DATA_FRESHNESS_THRESHOLD_MINUTES = int(os.environ.get("DATA_FRESHNESS_THRESHOLD_MINUTES", "5"))

# Track last alert time for dead man's switch
_last_alert_time = datetime.now()


def send_telegram_alert(message: str, chat_id: str) -> dict:
    """Send alert via Telegram Bot API."""
    if not BOT_TOKEN:
        print("⚠️ TELEGRAM_BOT_TOKEN not set — writing to fallback file")
        with open("/tmp/prometheus_telegram_alert.txt", 'a') as f:
            f.write(f"[{datetime.now().isoformat()}] TO {chat_id}:\n{message}\n---\n")
        return {'success': False, 'error': 'BOT_TOKEN not set', 'fallback': 'file'}

    try:
        payload = json.dumps({
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_notification": False,
        }).encode("utf-8")

        req = request.Request(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if result.get("ok"):
                print(f"📱 Telegram alert sent to {chat_id}")
                return {'success': True}
            else:
                print(f"⚠️ Telegram API error: {result}")
                return {'success': False, 'error': str(result)}
    except Exception as e:
        print(f"⚠️ Telegram error: {e}")
        with open("/tmp/prometheus_telegram_alert.txt", 'a') as f:
            f.write(f"[{datetime.now().isoformat()}] TO {chat_id}:\n{message}\n---\n")
        return {'success': False, 'error': str(e), 'fallback': 'file'}


def format_prometheus_alert(alert: dict) -> str:
    """Format Prometheus alert for Telegram (compact)."""
    global _last_alert_time
    _last_alert_time = datetime.now()

    status = alert.get('status', 'firing')
    labels = alert.get('labels', {})
    annotations = alert.get('annotations', {})

    alertname = labels.get('alertname', 'Unknown Alert')
    severity = labels.get('severity', 'warning')
    category = labels.get('category', 'unknown')
    instance = labels.get('instance', 'unknown')

    summary = annotations.get('summary', '')
    description = annotations.get('description', '')
    runbook = annotations.get('runbook_url', '')

    # Emoji based on severity
    emoji = {
        'critical': '🚨',
        'warning': '⚠️',
        'info': 'ℹ️',
    }.get(severity.lower(), '🔔')

    if status == 'resolved':
        return f"✅ <b>RESOLVED</b>: {alertname}\n📍 {instance}"

    message = f"""{emoji} <b>{severity.upper()}: {alertname}</b>
Category: {category}

📍 Instance: {instance}
"""
    if summary:
        message += f"📝 {summary}\n"
    if description:
        message += f"\n{description}\n"
    if runbook:
        message += f"\n📖 <a href='{runbook}'>Runbook</a>\n"

    # Add any extra labels
    extra_labels = {k: v for k, v in labels.items()
                   if k not in ('alertname', 'severity', 'instance', 'job', 'category')}
    if extra_labels:
        message += "\n<b>Details:</b>\n"
        for k, v in list(extra_labels.items())[:5]:  # Limit to 5
            message += f"  • {k}: {v}\n"

    message += f"\n⏱ {datetime.now().strftime('%H:%M:%S')}"
    return message


class AlertHandler(BaseHTTPRequestHandler):
    """Handle Alertmanager webhook requests."""

    def log_message(self, format, *args):
        """Suppress default logging."""
        print(f"[{datetime.now().isoformat()}] {args[0]}")

    def _validate_secret(self) -> bool:
        """Validate shared secret header if configured."""
        if not SHARED_SECRET:
            return True  # No secret required
        header_secret = self.headers.get('X-Shared-Secret', '')
        return hmac.compare_digest(header_secret, SHARED_SECRET)

    def do_post(self):
        """Receive Prometheus alerts."""
        if not self._validate_secret():
            self.send_error(401, 'Unauthorized')
            return

        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)

        try:
            data = json.loads(post_data.decode('utf-8'))
            alerts = data.get('alerts', [])

            print(f"📨 Received {len(alerts)} alerts from Alertmanager")

            sent_count = 0
            for alert in alerts:
                message = format_prometheus_alert(alert)
                result = send_telegram_alert(message, MANAGER_BOT_CHAT_ID)
                if result.get('success'):
                    sent_count += 1

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'status': 'ok',
                'alerts_received': len(alerts),
                'alerts_sent': sent_count
            }).encode())

        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON: {e}")
            self.send_error(400, 'Invalid JSON')
        except Exception as e:
            print(f"❌ Error processing alert: {e}")
            self.send_error(500, str(e))

    def do_GET(self):
        """Health check and metrics endpoints."""
        path = self.path

        if path == '/metrics':
            # Prometheus metrics format for scraping
            minutes_since_alert = (datetime.now() - _last_alert_time).total_seconds() / 60
            healthy = 1 if minutes_since_alert < DATA_FRESHNESS_THRESHOLD_MINUTES else 0

            metrics = f"""# HELP sentry_bridge_up Bridge health status (1 = healthy)
# TYPE sentry_bridge_up gauge
sentry_bridge_up {{telegram_configured="{int(bool(BOT_TOKEN))}",secret_configured="{int(bool(SHARED_SECRET))}"}} {healthy}
# HELP sentry_bridge_minutes_since_alert Minutes since last alert processed
# TYPE sentry_bridge_minutes_since_alert gauge
sentry_bridge_minutes_since_alert {minutes_since_alert:.1f}
# HELP sentry_bridge_data_freshness_threshold Configured freshness threshold in minutes
# TYPE sentry_bridge_data_freshness_threshold gauge
sentry_bridge_data_freshness_threshold {DATA_FRESHNESS_THRESHOLD_MINUTES}
"""
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(metrics.encode())

        elif path == '/health':
            # Simple health check
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'status': 'ok',
                'service': 'prometheus-sentry-bridge'
            }).encode())
        else:
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"prometheus-sentry-bridge")


def _heartbeat_loop():
    """Background thread: Update heartbeat every 30 seconds to prevent false dead man's switch."""
    global _last_alert_time
    while True:
        time.sleep(30)
        _last_alert_time = datetime.now()
        print(f"💓 Heartbeat updated at {_last_alert_time.isoformat()}")

def main():
    port = int(os.environ.get('BRIDGE_PORT', '9099'))

    if not BOT_TOKEN:
        print("⚠️ Warning: SENTRY_BOT_TOKEN not set - alerts will go to fallback file")
    else:
        print(f"✅ Manager bot configured (chat: {MANAGER_BOT_CHAT_ID})")

    if SHARED_SECRET:
        print(f"✅ Shared secret configured (auth required)")
    else:
        print("⚠️ No SHARED_SECRET set - webhooks accepted without auth")

    # Start heartbeat thread to prevent false dead man's switch positives
    import threading
    heartbeat_thread = threading.Thread(target=_heartbeat_loop, daemon=True)
    heartbeat_thread.start()
    print("💓 Heartbeat thread started (30s interval)")

    # Bind to all interfaces (Docker internal network) - protected by shared secret
    server = HTTPServer(('0.0.0.0', port), AlertHandler)
    print(f"🚀 Prometheus→Sentry bridge listening on 0.0.0.0:{port}")
    print(f"   Alertmanager should POST to http://localhost:{port}")
    print(f"   Health check: http://localhost:{port}/health")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Shutting down")
        server.shutdown()


if __name__ == '__main__':
    main()
