Residential Setup Checklist (Production)
=======================================

Purpose: Validate and finalize the residential stack for Phase 217.

Required environment variables (backend/.env):

- MQTT_BROKER_PUBLIC_HOST= bms.sentinel-ai.co.za (or your broker hostname)
- MQTT_BROKER_PORT= 1883 (or your broker port)
- RESIDENTIAL_MQTT_USERNAME= <backend account for broker>
- RESIDENTIAL_MQTT_PASSWORD= <backend account password>
- SOLARMAN_APP_ID= <from SOLARMAN developer portal>
- SOLARMAN_APP_SECRET= <from SOLARMAN developer portal>

Verification:

1. Run the environment checker using the backend interpreter:
   backend/venv/bin/python -m app.scripts.check_residential_env

   Expected: all items show OK. If any are MISSING, populate backend/.env and restart the backend.

2. Restart backend:
   sudo systemctl restart sentinel-backend

3. Home Assistant VPS onboarding (operator flow):
   - From Telegram @Sentinelaihomebot, use /connect → Home Assistant → VPS/Cloud
   - Paste the generated YAML into Home Assistant configuration.yaml and restart HA
   - Run /ha_ready to verify connection (checks retained homeassistant/status)

4. SOLARMAN onboarding (preferred immediate path):
   - From @Sentinelaihomebot, run /connect → SOLARMAN Smart and enter credentials
   - Confirm energy telemetry starts and AEGIS rules evaluate

Morning Summary:

- Scheduled at 07:00 SAST per site. Job id format: morning:{site_id}
- Uses residential MQTT retained values and optional loadshedding area code (/setarea)

Teardown (deactivation):

1) Cancel morning job → 2) Revoke VPS Mosquitto creds → 3) Remove ACL → 4) Clear retained topics (best-effort).

Notes:

- Do not paste secrets into chat. Store in backend/.env only.
- ACL scope is sentinel/{site_id}/#.
- Overtemp rule uses hysteresis (fire >45°C, clear <42°C).
