from __future__ import annotations

import signal
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.residential.mqtt_provisioner import MQTTProvisioner


def _provisioner_with_tmpfiles() -> tuple[MQTTProvisioner, Path, Path]:
    """Return a provisioner wired to temp ACL and conf files."""
    tmp = tempfile.mkdtemp()
    acl_path = Path(tmp) / "sentinel.acl"
    conf_path = Path(tmp) / "sentinel.conf"
    conf_path.write_text("listener 1883 0.0.0.0\nallow_anonymous false\npassword_file /etc/mosquitto/passwd\n")

    p = MQTTProvisioner()
    p._acl_file = acl_path   # type: ignore[attr-defined]
    p._conf_file = conf_path  # type: ignore[attr-defined]
    # Monkeypatch the module-level constants used inside the class methods
    import app.services.residential.mqtt_provisioner as mod
    mod._ACL_FILE = acl_path
    mod._CONF_FILE = conf_path
    mod._PID_FILE = Path(tmp) / "mosquitto.pid"
    return p, acl_path, conf_path


# ── provision_site ────────────────────────────────────────────────────────────

def test_provision_site_writes_acl_entry():
    p, acl_path, conf_path = _provisioner_with_tmpfiles()

    with patch.object(p, "_reload_mosquitto"):
        p.provision_site("site-005")

    content = acl_path.read_text()
    assert "# site:site-005" in content
    assert "topic readwrite sentinel/site-005/#" in content


def test_provision_site_adds_acl_file_directive_to_conf():
    p, acl_path, conf_path = _provisioner_with_tmpfiles()

    with patch.object(p, "_reload_mosquitto"):
        p.provision_site("site-005")

    conf = conf_path.read_text()
    assert "acl_file" in conf
    assert str(acl_path) in conf


def test_provision_site_is_idempotent():
    p, acl_path, _ = _provisioner_with_tmpfiles()

    with patch.object(p, "_reload_mosquitto"):
        p.provision_site("site-005")
        p.provision_site("site-005")  # second call must not duplicate

    content = acl_path.read_text()
    assert content.count("# site:site-005") == 1


def test_provision_site_never_writes_bare_wildcard():
    p, acl_path, _ = _provisioner_with_tmpfiles()

    with patch.object(p, "_reload_mosquitto"):
        p.provision_site("site-005")

    content = acl_path.read_text()
    assert "topic readwrite #" not in content
    assert "topic readwrite sentinel/site-005/#" in content


def test_provision_site_calls_reload():
    p, _, _ = _provisioner_with_tmpfiles()
    reload_mock = MagicMock()

    with patch.object(p, "_reload_mosquitto", reload_mock):
        p.provision_site("site-005")

    reload_mock.assert_called_once()


# ── revoke_site ───────────────────────────────────────────────────────────────

def test_revoke_site_removes_acl_entry():
    p, acl_path, _ = _provisioner_with_tmpfiles()

    with patch.object(p, "_reload_mosquitto"):
        p.provision_site("site-005")
        p.revoke_site("site-005")

    content = acl_path.read_text()
    assert "# site:site-005" not in content
    assert "topic readwrite sentinel/site-005/#" not in content


def test_revoke_site_is_idempotent():
    p, _, _ = _provisioner_with_tmpfiles()

    with patch.object(p, "_reload_mosquitto"):
        p.revoke_site("site-does-not-exist")  # must not raise


def test_revoke_site_preserves_other_sites():
    p, acl_path, _ = _provisioner_with_tmpfiles()

    with patch.object(p, "_reload_mosquitto"):
        p.provision_site("site-005")
        p.provision_site("site-006")
        p.revoke_site("site-005")

    content = acl_path.read_text()
    assert "site-005" not in content
    assert "sentinel/site-006/#" in content


# ── _reload_mosquitto ─────────────────────────────────────────────────────────

def test_reload_sends_sighup_via_pid_file():
    p, _, _ = _provisioner_with_tmpfiles()
    import app.services.residential.mqtt_provisioner as mod

    pid_path = mod._PID_FILE
    pid_path.write_text("99999\n")

    with patch("app.services.residential.mqtt_provisioner.os.kill") as mock_kill:
        mock_kill.side_effect = ProcessLookupError  # PID doesn't exist — still tests the path
        try:
            p._reload_mosquitto()
        except Exception:
            pass
        mock_kill.assert_called_once_with(99999, signal.SIGHUP)


def test_reload_falls_back_to_pkill_when_no_pid_file():
    p, _, _ = _provisioner_with_tmpfiles()
    import app.services.residential.mqtt_provisioner as mod

    # ensure PID file does NOT exist
    mod._PID_FILE.unlink(missing_ok=True)

    with patch("app.services.residential.mqtt_provisioner.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        p._reload_mosquitto()

    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert "pkill" in args
    assert "-HUP" in args
    assert "mosquitto" in args
