from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.sentry.residential_onboard_service import (
    ResidentialOnboardService,
    AWAITING_PLATFORM,
    AWAITING_HA_DEPLOYMENT,
    AWAITING_HA_READY,
)


class TestHAVPSOnboardingFlow:
    def service(self):
        return ResidentialOnboardService()

    def test_vps_path_credentials_message_and_warning(self, monkeypatch):
        svc = self.service()
        chat_id = 12345
        # Start flow
        msg = svc.handle_connect(chat_id)
        assert AWAITING_PLATFORM in str(svc._state.get(chat_id).step)

        # Select platform: HA
        svc.handle_platform_callback(chat_id, "cbid", "home_assistant")
        assert svc._state.get(chat_id).step == AWAITING_HA_DEPLOYMENT

        # Patch provisioner
        fake_creds = MagicMock(
            client_id="ha-res-12345",
            password="pw",
            broker="bms.sentinel-ai.co.za",
            port=1883,
            config_yaml="mqtt:\n  broker: bms.sentinel-ai.co.za\n  port: 1883\n  username: ha-res-12345\n  password: pw\n  client_id: ha-res-12345\n",
        )
        monkeypatch.setattr(
            "app.services.sentry.residential_onboard_service.get_mqtt_provisioner",
            lambda: MagicMock(provision_vps_client=lambda *_: fake_creds),
        )

        # Select VPS
        svc.handle_ha_deployment_callback(chat_id, "cb2", "vps")
        state = svc._state.get(chat_id)
        assert state.step == AWAITING_HA_READY

    @patch("app.services.sentry.residential_onboard_service.get_mqtt_provisioner")
    def test_ha_ready_transitions_to_mapping(self, mock_prov):
        svc = self.service()
        chat_id = 222
        svc.handle_connect(chat_id)
        svc.handle_platform_callback(chat_id, "cb1", "home_assistant")
        # Set state to awaiting HA ready
        st = svc._state.get(chat_id)
        st.step = AWAITING_HA_READY
        st.data["site_id"] = f"res-{chat_id}"
        svc._state.set(chat_id, st)

        mock_prov.return_value.verify_vps_connection.return_value = True
        msg = svc.handle_ha_ready(chat_id)
        assert "PV Power" in msg
