Residential Setup Checklist (Production)
=======================================

Purpose: Validate and finalize the residential stack for Phase 217+.

Required environment variables (backend/.env or systemd):

- SENTINEL_HOME_BOT_TOKEN= <from @BotFather for @Sentinelaihomebot>
- HOME_BOT_WEBHOOK_SECRET= <generated via secrets.token_hex(32), set via setWebhook>
- MQTT_BROKER_PUBLIC_HOST= bms.sentinel-ai.co.za (or your broker hostname)
- MQTT_BROKER_PORT= 1883 (or your broker port)
- RESIDENTIAL_MQTT_USERNAME= <backend account for broker>
- RESIDENTIAL_MQTT_PASSWORD= <backend account password>
- SOLARMAN_APP_ID= <from SOLARMAN developer portal>
- SOLARMAN_APP_SECRET= <from SOLARMAN developer portal>

Webhook secret setup (run once after generating HOME_BOT_WEBHOOK_SECRET):

    curl -X POST "https://api.telegram.org/bot<SENTINEL_HOME_BOT_TOKEN>/setWebhook" \
      -d "url=https://your-domain.com/api/residential/telegram/webhook" \
      -d "secret_token=<HOME_BOT_WEBHOOK_SECRET>" \
      -d 'allowed_updates=["message","callback_query"]'

The webhook endpoint validates X-Telegram-Bot-Api-Secret-Token on every request.
Backend rejects with 401 if the header is missing or wrong.

Mosquitto configuration (/etc/mosquitto/conf.d/sentinel.conf):

    listener 1883 0.0.0.0
    allow_anonymous false
    password_file /etc/mosquitto/passwd
    acl_file /etc/mosquitto/conf.d/sentinel.acl

Files must be owned by the user running the backend (chown bederf:bederf).

Verification:

1. Run the environment checker using the backend interpreter:
   backend/venv/bin/python -m app.scripts.check_residential_env

   Expected: all items show OK. If any are MISSING, populate backend/.env and restart the backend.

2. Restart backend:
   sudo systemctl restart sentinel-backend

3. Home Assistant VPS onboarding (operator flow):
   - From Telegram @Sentinelaihomebot, use /connect → Home Assistant Manual → VPS/Cloud
   - Paste the generated YAML into Home Assistant configuration.yaml and restart HA
   - Run /ha_ready to verify connection (checks retained homeassistant/status)

4. SOLARMAN onboarding (preferred immediate path):
   - From @Sentinelaihomebot, run /connect → SOLARMAN Smart and enter credentials
   - Confirm energy telemetry starts and AEGIS rules evaluate

5. Home Assistant Add-on onboarding:
   - From @Sentinelaihomebot, run /connect → Home Assistant Add-on
   - Follow the on-screen guide to install the SENTINEL add-on in HA
   - The add-on auto-registers via POST /api/residential/addon-register

Platform flows:

- SOLARMAN / Victron: email → password → discover → DB write → MQTT ACL → polling
- Home Assistant Manual: deployment choice → WireGuard (local) or MQTT creds (VPS)
- Home Assistant Add-on: API-based, add-on calls addon-register endpoint

State machine steps in residential_onboard_service.py:

    AWAITING_PLATFORM  → user must tap a button; text triggers guidance reply
    AWAITING_EMAIL     → validates email format
    AWAITING_PASSWORD  → deletes password msg immediately, runs auth in background
    DISCOVERING        → idempotency guard, writes site + devices to DB

Async safety:

All _send / _delete / _answer_callback helpers detect running event loop
and use create_task() instead of asyncio.run() to avoid RuntimeError
when called from FastAPI async webhook context.

MQTTProvisioner singleton:

The _provisioner instance is created after the VPS-extended class definition
so that provision_vps_client, revoke_vps_client, and verify_vps_connection
are available on the singleton.

Morning Summary:

- Scheduled at 07:00 SAST per site. Job id format: morning:{site_id}
- Uses residential MQTT retained values and optional loadshedding area code (/setarea)

Teardown (deactivation):

1) Cancel morning job → 2) Revoke VPS Mosquitto creds → 3) Remove ACL → 4) Clear retained topics (best-effort).

Notes:

- Do not paste secrets into chat. Store in backend/.env or systemd drop-in only.
- ACL scope is sentinel/{site_id}/#.
- Overtemp rule uses hysteresis (fire >45°C, clear <42°C).
- Webhook secret must match between setWebhook call and HOME_BOT_WEBHOOK_SECRET env var.
