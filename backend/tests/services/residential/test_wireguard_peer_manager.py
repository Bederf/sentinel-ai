"""Tests for WireGuardPeerManager."""

from __future__ import annotations

from unittest.mock import patch
import pytest
from app.services.residential.wireguard_peer_manager import (
    PUBLIC_KEY_RE,
    WireGuardPeerManager,
)


class TestPublicKeyValidation:
    def manager(self):
        return WireGuardPeerManager()

    def test_valid_format(self):
        # 44 base64 chars ending with = — real-looking example
        key = "aGkh77+2+QhN7V8YZq2R1xFnJ8M6P4K3L9A0B5C7D9E="
        assert len(key) == 44
        assert bool(PUBLIC_KEY_RE.match(key))

    def test_rejects_short(self):
        assert self.manager().validate_public_key("short") is False

    def test_rejects_empty(self):
        assert self.manager().validate_public_key("") is False

    def test_rejects_wrong_length(self):
        key_43 = "aGkh77+2+QhN7V8YZq2R1xFnJ8M6P4K3L9A0B5C7D9E"
        assert len(key_43) == 43
        assert self.manager().validate_public_key(key_43) is False

    def test_rejects_invalid_chars(self):
        key_bad = "aGkh77+2!QhN7V8YZq2R1xFnJ8M6P4K3L9A0B5C7D9E="
        assert self.manager().validate_public_key(key_bad) is False

    def test_rejects_missing_equals(self):
        key_no_eq = "aGkh77+2+QhN7V8YZq2R1xFnJ8M6P4K3L9A0B5C7D9E"
        assert len(key_no_eq) == 43
        assert self.manager().validate_public_key(key_no_eq) is False

    @patch("app.services.residential.wireguard_peer_manager.settings")
    def test_generate_peer_config_format(self, mock_settings):
        mock_settings.wireguard_vpn_subnet = "10.99.0.0/24"
        mock_settings.wireguard_vps_public_key = "serverpubkey1234="
        mock_settings.wireguard_vps_endpoint = "158.220.87.183:51820"
        wg = WireGuardPeerManager()
        cfg = wg.generate_peer_config("clientpubkey1234=", "10.99.0.5")
        assert "[Peer]" in cfg
        assert "PublicKey = clientpubkey1234=" in cfg
        assert "AllowedIPs = 10.99.0.5/32" in cfg
        # server key should NOT appear in client-side peer config
        assert "serverpubkey" not in cfg

    @patch("app.services.residential.wireguard_peer_manager.settings")
    def test_generate_client_config_has_interface_and_peer(self, mock_settings):
        mock_settings.wireguard_vpn_subnet = "10.99.0.0/24"
        mock_settings.wireguard_vps_public_key = "serverpubkey1234="
        mock_settings.wireguard_vps_endpoint = "158.220.87.183:51820"
        wg = WireGuardPeerManager()
        cfg = wg.generate_client_config("10.99.0.5")
        assert "[Interface]" in cfg
        assert "[Peer]" in cfg
        assert "PrivateKey = <YOUR_PRIVATE_KEY>" in cfg
        assert "Address = 10.99.0.5/32" in cfg
        assert "PublicKey = serverpubkey1234=" in cfg
        assert "Endpoint = 158.220.87.183:51820" in cfg
        assert "PersistentKeepalive = 25" in cfg


class TestIPAllocation:
    @patch("app.services.residential.wireguard_peer_manager.settings")
    def test_allocate_ip_raises_on_exhaustion(self, mock_settings):
        mock_settings.wireguard_vpn_subnet = "10.99.0.0/30"
        mock_settings.wireguard_vps_public_key = "srvpubkey1234="
        mock_settings.wireguard_vps_endpoint = "1.2.3.4:51820"
        wg = WireGuardPeerManager()
        # /30 usable hosts: .1 and .2
        with patch.object(wg, "_get_taken_ips") as mock_taken:
            mock_taken.return_value = {"10.99.0.1", "10.99.0.2"}
            with pytest.raises(RuntimeError, match="exhausted"):
                wg.allocate_ip()

    @patch("app.services.residential.wireguard_peer_manager.settings")
    def test_allocate_ip_returns_first_free(self, mock_settings):
        mock_settings.wireguard_vpn_subnet = "10.99.0.0/30"
        mock_settings.wireguard_vps_public_key = "srvpubkey1234="
        mock_settings.wireguard_vps_endpoint = "1.2.3.4:51820"
        wg = WireGuardPeerManager()
        with patch.object(wg, "_get_taken_ips") as mock_taken:
            mock_taken.return_value = set()
            ip = wg.allocate_ip()
            assert ip == "10.99.0.1"  # first usable host in /30

    @patch("app.services.residential.wireguard_peer_manager.settings")
    def test_allocate_ip_skips_taken(self, mock_settings):
        mock_settings.wireguard_vpn_subnet = "10.99.0.0/30"
        mock_settings.wireguard_vps_public_key = "srvpubkey1234="
        mock_settings.wireguard_vps_endpoint = "1.2.3.4:51820"
        wg = WireGuardPeerManager()
        with patch.object(wg, "_get_taken_ips") as mock_taken:
            mock_taken.return_value = {"10.99.0.1"}
            ip = wg.allocate_ip()
            assert ip == "10.99.0.2"
