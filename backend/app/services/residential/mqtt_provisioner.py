from __future__ import annotations

import contextlib
import logging
import os
import signal
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)

_ACL_FILE = Path("/etc/mosquitto/conf.d/sentinel.acl")
_CONF_FILE = Path("/etc/mosquitto/conf.d/sentinel.conf")
_PASSWD_FILE = Path("/etc/mosquitto/passwd")
_PID_FILE = Path("/run/mosquitto/mosquitto.pid")
_FILE_LOCK = Lock()


class MQTTProvisioner:
    """Manages per-site Mosquitto ACL entries for residential MQTT isolation."""

    def provision_site(self, site_id: str) -> None:
        """Add ACL entry for site_id. Idempotent."""
        self._ensure_acl_file_directive()
        with _FILE_LOCK:
            existing = self._read_acl()
            marker = f"# site:{site_id}"
            if marker in existing:
                return
            entry = f"\n{marker}\ntopic readwrite sentinel/{site_id}/#\n"
            with _ACL_FILE.open("a") as f:
                f.write(entry)
        self._reload_mosquitto()
        logger.info("Provisioned MQTT ACL for site %s", site_id)

    def revoke_site(self, site_id: str) -> None:
        """Remove ACL entry for site_id. Idempotent."""
        with _FILE_LOCK:
            existing = self._read_acl()
            marker = f"# site:{site_id}"
            if marker not in existing:
                return
            lines = existing.splitlines(keepends=True)
            cleaned: list[str] = []
            skip_next = False
            for line in lines:
                if skip_next:
                    skip_next = False
                    continue
                if line.strip() == marker:
                    skip_next = True
                    continue
                cleaned.append(line)
            _ACL_FILE.write_text("".join(cleaned))
        self._reload_mosquitto()
        logger.info("Revoked MQTT ACL for site %s", site_id)

    def _read_acl(self) -> str:
        if not _ACL_FILE.exists():
            return ""
        return _ACL_FILE.read_text()

    def _ensure_acl_file_directive(self) -> None:
        if not _CONF_FILE.exists():
            return
        conf = _CONF_FILE.read_text()
        if "acl_file" in conf:
            return
        with _CONF_FILE.open("a") as f:
            f.write(f"\nacl_file {_ACL_FILE}\n")
        logger.info("Added acl_file directive to %s", _CONF_FILE)

    def _reload_mosquitto(self) -> None:
        try:
            if _PID_FILE.exists():
                pid = int(_PID_FILE.read_text().strip())
                os.kill(pid, signal.SIGHUP)
                logger.info("Sent SIGHUP to mosquitto PID %d", pid)
            else:
                result = subprocess.run(
                    ["sudo", "pkill", "-HUP", "mosquitto"],
                    capture_output=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    logger.info("Sent SIGHUP to mosquitto via pkill")
                else:
                    logger.warning("Mosquitto not running — ACL written but not reloaded")
        except Exception as exc:
            logger.warning("Could not reload mosquitto: %s", exc)


# ── VPS MQTT Provisioning (HA on VPS, no WireGuard) ───────────────────────────


@dataclass
class VPSMQTTCredentials:
    client_id: str
    password: str
    broker: str
    port: int
    config_yaml: str


class MQTTProvisioner(MQTTProvisioner):  # type: ignore[misc]
    def _generate_ha_config_yaml(self, client_id: str, password: str, site_id: str) -> str:
        from app.config.settings import settings

        return (
            f"""
mqtt:
  broker: {settings.mqtt_broker_public_host}
  port: {settings.mqtt_broker_port}
  username: {client_id}
  password: {password}
  client_id: {client_id}
  discovery: true
  discovery_prefix: homeassistant
"""
        ).strip()

    def _upsert_password(self, username: str, password: str) -> None:
        """Create or update a mosquitto password using mosquitto_passwd.

        Falls back silently if mosquitto_passwd is unavailable.
        """
        try:
            subprocess.run(
                ["sudo", "mosquitto_passwd", "-b", str(_PASSWD_FILE), username, password],
                capture_output=True,
                timeout=5,
                check=False,
            )
        except Exception as exc:
            logger.warning("mosquitto_passwd not available: %s", exc)

    def provision_vps_client(self, site_id: str, chat_id: int) -> VPSMQTTCredentials:
        """
        Provisions Mosquitto credentials for VPS-hosted Home Assistant.
        Idempotent: rewrites password and ensures ACL entry exists.
        Stores encrypted credentials in residential_sites.site_config.
        """
        import json as _json
        import secrets

        from app.config.settings import settings
        from app.database.supabase_client import get_supabase_client
        from app.services.encryption_service import get_encryption_service

        client_id = f"ha-{site_id}"
        password = secrets.token_urlsafe(32)

        # Update mosquitto password file and ACL entry
        self._ensure_acl_file_directive()
        self._upsert_password(client_id, password)
        # Ensure site ACL exists (topic readwrite sentinel/{site_id}/#)
        self.provision_site(site_id)

        # Update encrypted site_config with MQTT creds
        sb = get_supabase_client()
        row = sb.table("residential_sites").select("site_config").eq("site_id", site_id).maybe_single().execute()
        current_cfg = {}
        try:
            if row:
                enc_blob = row.get("site_config") or "{}"
                # site_config may be encrypted via Fernet
                try:
                    raw = get_encryption_service().decrypt(enc_blob)
                    current_cfg = _json.loads(raw)
                except Exception:
                    # Not encrypted JSON — best-effort parse
                    current_cfg = _json.loads(enc_blob) if isinstance(enc_blob, str) else dict(enc_blob or {})
        except Exception:
            current_cfg = {}

        current_cfg.update(
            {
                "mqtt_client_id": client_id,
                "mqtt_password": password,
                "ha_deployment_type": "vps",
            }
        )
        enc = get_encryption_service().encrypt(_json.dumps(current_cfg))
        sb.table("residential_sites").update({"site_config": enc, "ha_deployment_type": "vps"}).eq(
            "site_id", site_id
        ).execute()

        return VPSMQTTCredentials(
            client_id=client_id,
            password=password,
            broker=settings.mqtt_broker_public_host,
            port=settings.mqtt_broker_port,
            config_yaml=self._generate_ha_config_yaml(client_id, password, site_id),
        )

    def verify_vps_connection(self, site_id: str, timeout_seconds: int = 30) -> bool:
        """Verify HA connected by checking retained homeassistant/status='online'.

        Attempts up to 3 times, 10s apart. Falls back to a TCP probe on the
        broker port if retained status is unavailable.
        """
        from app.config.settings import settings

        try:
            import paho.mqtt.client as mqtt
        except Exception:
            mqtt = None  # type: ignore[assignment]

        status_online = False

        if mqtt is not None and settings.mqtt_broker_public_host:

            def _on_message(_client, _userdata, msg):
                nonlocal status_online
                try:
                    payload = msg.payload.decode("utf-8", errors="ignore").strip().lower()
                    if msg.topic == "homeassistant/status" and payload == "online":
                        status_online = True
                except Exception:
                    pass

            for _attempt in range(3):
                try:
                    client = mqtt.Client(client_id=f"sentinel-verify-{site_id}")
                    # Use backend credentials (broker requires allow_anonymous false)
                    try:
                        if getattr(settings, "residential_mqtt_username", ""):
                            client.username_pw_set(
                                settings.residential_mqtt_username, settings.residential_mqtt_password
                            )
                    except Exception:
                        pass
                    client.on_message = _on_message
                    # Anonymous connect attempt — if broker requires auth, this will fail
                    client.connect(settings.mqtt_broker_public_host, settings.mqtt_broker_port, keepalive=10)
                    client.loop_start()
                    client.subscribe("homeassistant/status", qos=0)
                    # Wait up to ~10s per attempt
                    import time as _t

                    deadline = _t.time() + min(timeout_seconds, 10)
                    while _t.time() < deadline and not status_online:
                        _t.sleep(0.2)
                    client.loop_stop()
                    client.disconnect()
                    if status_online:
                        return True
                except Exception:
                    # Connection failed — try again after delay
                    pass
                # Inter-attempt delay
                import time as _t2

                _t2.sleep(10)

        # Fallback: TCP probe public broker port
        try:
            with socket.create_connection((settings.mqtt_broker_public_host, settings.mqtt_broker_port), timeout=3):
                return True
        except Exception:
            return False

    def revoke_vps_client(self, site_id: str) -> None:
        """Revoke VPS client credentials and ACL entry for a site.

        Removes password from mosquitto passwd (best-effort) and clears
        mqtt credentials from encrypted site_config.
        """
        import json as _json

        from app.database.supabase_client import get_supabase_client
        from app.services.encryption_service import get_encryption_service

        username = f"ha-{site_id}"
        # Remove user from passwd file
        try:
            subprocess.run(
                ["sudo", "mosquitto_passwd", "-D", str(_PASSWD_FILE), username],
                capture_output=True,
                timeout=5,
                check=False,
            )
        except Exception as exc:
            logger.warning("mosquitto_passwd -D failed: %s", exc)

        # Remove ACL entry and reload
        with contextlib.suppress(Exception):
            self.revoke_site(site_id)

        # Scrub credentials from site_config
        sb = get_supabase_client()
        row = sb.table("residential_sites").select("site_config").eq("site_id", site_id).maybe_single().execute()
        try:
            if row:
                enc_blob = row.get("site_config") or "{}"
                raw = get_encryption_service().decrypt(enc_blob)
                cfg = _json.loads(raw)
        except Exception:
            cfg = {}
        try:
            for k in ("mqtt_client_id", "mqtt_password"):
                cfg.pop(k, None)
            enc = get_encryption_service().encrypt(_json.dumps(cfg))
            sb.table("residential_sites").update({"site_config": enc}).eq("site_id", site_id).execute()
        except Exception as exc:
            logger.warning("Failed to scrub MQTT credentials from site_config: %s", exc)


_provisioner = MQTTProvisioner()


def get_mqtt_provisioner() -> MQTTProvisioner:
    return _provisioner
