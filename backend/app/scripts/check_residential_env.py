"""Operator check: verify residential production env configuration.

Run with the backend interpreter, e.g.:

    backend/venv/bin/python -m app.scripts.check_residential_env

Exits with non-zero status if critical items are missing.
"""

from __future__ import annotations


from app.config.settings import settings


def _bool_str(val: bool) -> str:
    return "OK" if val else "MISSING"


def main() -> int:
    print("Residential Production Environment Check")
    print("--------------------------------------")

    # Critical: public MQTT broker details for VPS HA onboarding
    has_public_broker = bool(settings.mqtt_broker_public_host)
    print(f"MQTT_BROKER_PUBLIC_HOST: {_bool_str(has_public_broker)} ({settings.mqtt_broker_public_host or '-'} )")
    print(f"MQTT_BROKER_PORT: {settings.mqtt_broker_port}")

    # Backend internal MQTT creds (used for verify and publishing)
    has_backend_mqtt_user = bool(getattr(settings, "residential_mqtt_username", ""))
    has_backend_mqtt_pass = bool(getattr(settings, "residential_mqtt_password", ""))
    print(f"RESIDENTIAL_MQTT_USERNAME: {_bool_str(has_backend_mqtt_user)}")
    print(f"RESIDENTIAL_MQTT_PASSWORD: {_bool_str(has_backend_mqtt_pass)}")

    # SOLARMAN adapter credentials
    has_solarman_id = bool(settings.solarman_app_id)
    has_solarman_secret = bool(settings.solarman_app_secret)
    print(f"SOLARMAN_APP_ID: {_bool_str(has_solarman_id)}")
    print(f"SOLARMAN_APP_SECRET: {_bool_str(has_solarman_secret)}")

    # Aggregate status
    ok = (
        has_public_broker
        and has_backend_mqtt_user
        and has_backend_mqtt_pass
        and has_solarman_id
        and has_solarman_secret
    )

    print("--------------------------------------")
    if ok:
        print("All required residential vars are set.")
        return 0
    else:
        print("One or more required vars are missing. See docs/05-troubleshooting/residential-setup.md")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
