---
title: "Telegram Voice And Mail Credentials"
type: "runbook"
status: "active"
version: "1.0.0"
created: "2026-06-16"
updated: "2026-06-16"
tags: ["sentinel", "telegram", "voice", "smtp", "credentials", "operations"]
related:
  - "/opt/bms-intelligence/docs/09-security/secrets-management.md"
  - "/opt/bms-intelligence/docs/09-security/secret-rotation-log.md"
domain: "bms"
audience: "operators"
complexity: "intermediate"
estimated_read_time: 8
---

# Telegram Voice And Mail Credentials

This note documents the runtime credential locations and checks for the SENTRY Telegram gateway voice response path and SENTINEL backend mail credentials.

Do not store raw credential values in this document. Keep secrets in the runtime files listed below and redact command output when sharing diagnostics.

## Runtime Services

| Service | Purpose | Restart after credential change |
|---------|---------|----------------------------------|
| `sentry.service` | SENTRY/OpenClaw Telegram gateway | Yes, for gateway config or extension changes |
| `sentinel-backend` | FastAPI backend, scheduled jobs, mail polling and notification paths | Yes, for `/etc/sentinel/*.env` changes |

## Telegram Voice Response

Telegram voice response is handled by a local SENTRY gateway extension:

- extension: `/home/bederf/.sentry/gateway/extensions/telegram-voice-response`
- plugin config: `/home/bederf/.sentry/gateway/sentry.json`
- TTS helper: `/home/bederf/.sentry/tools/voice_tts.py`
- ElevenLabs gateway credential: `/home/bederf/.sentry/gateway/credentials/elevenlabs.json`

The extension detects text requests such as:

- `reply in voice`
- `respond in voice`
- `voice response`
- `voice note`
- `say it`

When triggered, it leaves the normal text reply intact and adds a Telegram voice note. This keeps Telegram text replies working if TTS or Telegram voice upload fails.

### Voice Credential Check

Check that the gateway credential exists without printing the value:

```bash
python3 - <<'PY'
import json
from pathlib import Path
p = Path("/home/bederf/.sentry/gateway/credentials/elevenlabs.json")
data = json.loads(p.read_text()) if p.exists() else {}
print("exists:", p.exists())
print("api_key present:", bool(data.get("api_key")))
PY
```

Generate a short Telegram-compatible OGG/Opus file:

```bash
python3 /home/bederf/.sentry/tools/voice_tts.py --ogg "Sentry voice test."
```

Expected result: a path under `/tmp/sentry_voice_responses/` ending in `.ogg`.

### Voice Gateway Verification

Restart the gateway after extension or gateway credential changes:

```bash
sudo systemctl restart sentry.service
```

Verify service state:

```bash
systemctl show sentry.service --property=ActiveState,SubState,ExecMainPID --no-pager
```

Verify plugin load:

```bash
journalctl -u sentry.service --since "10 minutes ago" --no-pager | \
  grep -E "telegram-voice-response|http server listening|ERROR|failed"
```

Expected log indicators:

- `[telegram-voice-response] registering {}`
- `plugin=telegram-voice-response`
- `http server listening`

Operational warnings about local plugin provenance are expected until the gateway has an explicit `plugins.allow` policy. They are not voice failures.

## Mail Credentials

The production backend reads mail secrets from:

- `/etc/sentinel/secrets.env`

The non-secret mail host/user/from configuration is expected in:

- `/etc/sentinel/backend.env`

The helper scripts under `/home/bederf/.sentry/tools/` may also read:

- `/home/bederf/.sentry/.env`

### Backend Mail Secret Variables

The live backend mail password variables are:

| Variable | Use |
|----------|-----|
| `SMTP_PASSWORD` | Main visitor/reception mail path |
| `NOTIFICATION_SMTP_PASSWORD` | Notification SMTP fallback path |
| `ROOMS_IMAP_PASSWORD` | Rooms email intake polling |
| `ROOMS_SMTP_PASSWORD` | Rooms outbound alert mail |

Keep all four in sync when the provider password is changed, unless the mail accounts are intentionally split.

### Redacted Secret Check

```bash
sudo grep -nE 'SMTP_PASSWORD|ROOMS_IMAP_PASSWORD|ROOMS_SMTP_PASSWORD|NOTIFICATION_SMTP_PASSWORD' \
  /etc/sentinel/secrets.env | sed 's/=.*/=***REDACTED***/'
```

### SMTP Login Check

Use a direct login probe without printing credentials:

```bash
sudo python3 - <<'PY'
import smtplib
from pathlib import Path

env = {}
for p in ["/etc/sentinel/backend.env", "/etc/sentinel/secrets.env"]:
    for line in Path(p).read_text().splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k] = v.strip().strip('"').strip("'")

host = env.get("SMTP_HOST")
port = int(env.get("SMTP_PORT", "587"))
user = env.get("SMTP_USER")
password = env.get("SMTP_PASSWORD")

with smtplib.SMTP(host, port, timeout=15) as smtp:
    smtp.ehlo()
    smtp.starttls()
    smtp.ehlo()
    smtp.login(user, password)

print("smtp ok")
PY
```

### Backend Restart And Verification

Restart the backend after changing `/etc/sentinel/secrets.env`:

```bash
sudo systemctl restart sentinel-backend
```

Verify the backend is running and bound to port `9095`:

```bash
systemctl show sentinel-backend --property=ActiveState,SubState,ExecMainPID --no-pager
ss -ltnp | grep ':9095'
```

Check for recent mail login errors:

```bash
tail -250 /var/log/sentinel/backend.log | \
  grep -Ei 'RoomsEmail|SMTP|IMAP|LOGIN command|auth|mail' | tail -60
```

No output from the grep is acceptable when there have been no recent mail events.

## Current Known State On 2026-06-16

- Telegram voice response extension is enabled in the SENTRY gateway.
- ElevenLabs TTS generation produced a valid `.ogg` test file.
- `sentry.service` loaded `telegram-voice-response`.
- Main SMTP login tested successfully after password update.
- `sentinel-backend` restarted and was listening on `0.0.0.0:9095`.
