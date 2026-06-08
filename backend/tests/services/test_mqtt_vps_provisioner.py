from __future__ import annotations

from unittest.mock import MagicMock

from app.services.residential.mqtt_provisioner import get_mqtt_provisioner


class TestMQTTVPSProvisioner:
    def test_provision_vps_client_generates_credentials_and_yaml(self, monkeypatch):
        prov = get_mqtt_provisioner()

        # Patch out mosquitto interactions and DB
        monkeypatch.setattr(prov, "_upsert_password", lambda u, p: None)
        monkeypatch.setattr(prov, "provision_site", lambda site_id: None)
        monkeypatch.setattr(
            "app.services.residential.mqtt_provisioner.get_supabase_client",
            lambda: MagicMock(
                table=lambda *_: MagicMock(
                    select=lambda *_: MagicMock(eq=lambda *_: MagicMock(maybe_execute=lambda: MagicMock(data=[]))),
                    update=lambda *_: MagicMock(
                        eq=lambda *_: MagicMock(execute=lambda: MagicMock(data=[{"ok": True}]))
                    ),
                )
            ),
        )
        monkeypatch.setattr(
            "app.services.residential.mqtt_provisioner.get_encryption_service",
            lambda: MagicMock(encrypt=lambda s: s, decrypt=lambda s: s),
        )

        creds = prov.provision_vps_client(site_id="res-123", chat_id=123)
        assert creds.client_id == "ha-res-123"
        assert "mqtt:" in creds.config_yaml
        assert str(creds.port) in creds.config_yaml

    def test_verify_vps_connection_via_homeassistant_status(self, monkeypatch):
        prov = get_mqtt_provisioner()

        class _FakeClient:
            def __init__(self, *a, **kw):
                self.on_message = None

            def username_pw_set(self, *a, **kw):
                pass

            def connect(self, *a, **kw):
                # Immediately simulate receipt of retained online
                if self.on_message:

                    class Msg:
                        topic = "homeassistant/status"
                        payload = b"online"

                    self.on_message(self, None, Msg())

            def loop_start(self):
                pass

            def subscribe(self, *a, **kw):
                pass

            def loop_stop(self):
                pass

            def disconnect(self):
                pass

        fake_mqtt = MagicMock(Client=_FakeClient)
        monkeypatch.setitem(__import__("sys").modules, "paho.mqtt.client", fake_mqtt)

        ok = prov.verify_vps_connection("res-123", timeout_seconds=3)
        assert ok is True

    def test_revoke_vps_client_scrubs_credentials(self, monkeypatch):
        prov = get_mqtt_provisioner()

        # Patch subprocess and DB
        monkeypatch.setattr(
            "app.services.residential.mqtt_provisioner.subprocess.run",
            lambda *a, **k: MagicMock(returncode=0),
        )
        # site_config decrypt → dict with creds; ensure update called without keys after revoke
        updated = {}

        def _sb():
            tbl = MagicMock()
            tbl.select.return_value.eq.return_value.maybe_execute.return_value = MagicMock(
                data=[{"site_config": '{"mqtt_client_id":"ha-res-123","mqtt_password":"pw"}'}]
            )

            def _update(payload):
                nonlocal updated
                updated = payload
                return MagicMock(eq=lambda *_: MagicMock(execute=lambda: MagicMock(data=[{"ok": True}])))

            tbl.update.side_effect = _update
            return MagicMock(table=lambda *_: tbl)

        monkeypatch.setattr(
            "app.services.residential.mqtt_provisioner.get_supabase_client",
            _sb,
        )
        monkeypatch.setattr(
            "app.services.residential.mqtt_provisioner.get_encryption_service",
            lambda: MagicMock(encrypt=lambda s: s, decrypt=lambda s: s),
        )

        prov.revoke_vps_client("res-123")
        assert "mqtt_client_id" not in str(updated.get("site_config", "{}"))
