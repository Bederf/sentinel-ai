from __future__ import annotations

import logging
import os
import signal
import subprocess
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)

_ACL_FILE = Path("/etc/mosquitto/conf.d/sentinel.acl")
_CONF_FILE = Path("/etc/mosquitto/conf.d/sentinel.conf")
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
                    ["pkill", "-HUP", "mosquitto"],
                    capture_output=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    logger.info("Sent SIGHUP to mosquitto via pkill")
                else:
                    logger.warning("Mosquitto not running — ACL written but not reloaded")
        except Exception as exc:
            logger.warning("Could not reload mosquitto: %s", exc)


_provisioner = MQTTProvisioner()


def get_mqtt_provisioner() -> MQTTProvisioner:
    return _provisioner
