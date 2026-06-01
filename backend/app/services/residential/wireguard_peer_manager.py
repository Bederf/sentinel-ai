"""WireGuard peer lifecycle manager for Home Assistant residential gateways.

Each HA gateway client gets their own WireGuard peer with an assigned VPN IP.
Peer configs are generated server-side and operator adds them to wg0.conf.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app.config.settings import settings
from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

# WireGuard public key format: 44 base64 characters ending with '='
PUBLIC_KEY_RE = re.compile(r"^[A-Za-z0-9+/]{43}=$")


@dataclass
class WireGuardPeer:
    """Represents a WireGuard peer registered for a residential HA gateway."""

    id: uuid.UUID
    site_id: str
    public_key: str
    assigned_ip: str
    peer_config: str  # [Peer] block for wg0.conf — server-side only
    status: str  # "pending" | "active" | "revoked"
    created_at: datetime
    activated_at: datetime | None


class WireGuardPeerManager:
    """
    Manages WireGuard peer lifecycle for Home Assistant residential gateways.

    WireGuard config values come from settings — never hardcoded:
    - settings.wireguard_vpn_subnet   (e.g. "10.99.0.0/24")
    - settings.wireguard_vps_public_key
    - settings.wireguard_vps_endpoint (e.g. "158.220.87.183:51820")
    """

    def validate_public_key(self, key: str) -> bool:
        """Validate WireGuard public key format: 44 base64 chars ending with '='."""
        if not key or len(key) != 44:
            return False
        return bool(PUBLIC_KEY_RE.match(key))

    def _parse_subnet(self) -> ipaddress.IPv4Network:
        """Parse VPN subnet from settings."""
        return ipaddress.ip_network(settings.wireguard_vpn_subnet, strict=False)

    def _get_taken_ips(self) -> set[str]:
        """Get IPs already assigned to active/pending peers."""
        client = get_supabase_client()
        resp = client.table("wireguard_peers").select("assigned_ip").in_("status", ["pending", "active"]).execute()
        return {row["assigned_ip"] for row in resp.data}

    def allocate_ip(self) -> str:
        """Allocate next available IP in VPN subnet.

        Raises RuntimeError if subnet is exhausted — never silently assigns
        a duplicate IP.
        """
        subnet = self._parse_subnet()
        taken = self._get_taken_ips()

        # Hosts() skips network and broadcast addresses; start from .2
        for host in subnet.hosts():
            ip_str = str(host)
            if ip_str not in taken:
                return ip_str

        raise RuntimeError(f"WireGuard VPN subnet {subnet} is exhausted — no available IPs")

    def generate_peer_config(self, public_key: str, assigned_ip: str) -> str:
        """Generate [Peer] block for wg0.conf (server-side, operator copies)."""
        return f"[Peer]\nPublicKey = {public_key}\nAllowedIPs = {assigned_ip}/32\n"

    def generate_client_config(self, assigned_ip: str) -> str:
        """Generate full WireGuard config for HA WireGuard Add-on.

        PrivateKey is filled in by the user on the HA side.
        Returns [Interface]+[Peer] block.
        """
        return (
            f"[Interface]\n"
            f"PrivateKey = <YOUR_PRIVATE_KEY>\n"
            f"Address = {assigned_ip}/32\n"
            f"[Peer]\n"
            f"PublicKey = {settings.wireguard_vps_public_key}\n"
            f"Endpoint = {settings.wireguard_vps_endpoint}\n"
            f"AllowedIPs = {settings.wireguard_vpn_subnet}\n"
            f"PersistentKeepalive = 25\n"
        )

    def register_peer(self, site_id: str, public_key: str) -> WireGuardPeer:
        """Validate key → allocate IP → generate peer config → save to DB.

        Status is 'pending' until operator adds the peer to wg0.conf
        and calls activate_peer().
        """
        if not self.validate_public_key(public_key):
            raise ValueError(
                f"Invalid WireGuard public key format: expected 44 base64 "
                f"chars ending with '=', got {len(public_key)} chars"
            )

        client = get_supabase_client()

        # Check not already registered
        existing = client.table("wireguard_peers").select("id").eq("public_key", public_key).execute()
        if existing.data:
            raise ValueError(f"Public key already registered: {public_key[:8]}...")

        assigned_ip = self.allocate_ip()
        peer_block = self.generate_peer_config(public_key, assigned_ip)

        resp = (
            client.table("wireguard_peers")
            .insert(
                {
                    "site_id": site_id,
                    "public_key": public_key,
                    "assigned_ip": assigned_ip,
                    "peer_config": peer_block,
                    "status": "pending",
                }
            )
            .execute()
        )

        row = resp.data[0]
        return WireGuardPeer(
            id=uuid.UUID(row["id"]),
            site_id=row["site_id"],
            public_key=row["public_key"],
            assigned_ip=row["assigned_ip"],
            peer_config=peer_block,
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")),
            activated_at=None,
        )

    def activate_peer(self, site_id: str) -> None:
        """Mark peer as active. Called by operator after adding to wg0.conf."""
        client = get_supabase_client()
        client.table("wireguard_peers").update(
            {
                "status": "active",
                "activated_at": datetime.now(UTC).isoformat(),
            }
        ).eq("site_id", site_id).eq("status", "pending").execute()

    def get_peer(self, site_id: str) -> WireGuardPeer | None:
        """Get peer by site_id, regardless of status."""
        client = get_supabase_client()
        resp = client.table("wireguard_peers").select("*").eq("site_id", site_id).execute()
        if not resp.data:
            return None
        row = resp.data[0]
        return WireGuardPeer(
            id=uuid.UUID(row["id"]),
            site_id=row["site_id"],
            public_key=row["public_key"],
            assigned_ip=row["assigned_ip"],
            peer_config=row["peer_config"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")),
            activated_at=(
                datetime.fromisoformat(row["activated_at"].replace("Z", "+00:00")) if row.get("activated_at") else None
            ),
        )

    def check_reachability(self, site_id: str) -> bool:
        """Check if peer's assigned IP is reachable.

        Tries ICMP ping first (3 attempts, 2s apart).
        Falls back to TCP probe on port 8123 (Home Assistant default).
        Returns False if neither succeeds or peer is not active.
        """
        import socket
        import subprocess

        peer = self.get_peer(site_id)
        if not peer or peer.status != "active":
            return False
        assigned_ip = peer.assigned_ip

        # Try ICMP ping
        for attempt in range(3):
            try:
                result = subprocess.run(
                    ["ping", "-c", "1", "-W", "2", assigned_ip],
                    capture_output=True,
                    timeout=3,
                )
                if result.returncode == 0:
                    return True
            except (subprocess.TimeoutExpired, FileNotFoundError):
                break  # ping not available on this system
            import time

            time.sleep(2)

        # Fallback: TCP probe port 8123 (HA default)
        for attempt in range(3):
            try:
                sock = socket.create_connection((assigned_ip, 8123), timeout=3)
                sock.close()
                return True
            except (TimeoutError, ConnectionRefusedError, OSError):
                import time

                time.sleep(2)
        return False

    def revoke_peer(self, site_id: str) -> None:
        """Mark peer as revoked. Operator must manually remove from wg0.conf."""
        client = get_supabase_client()
        client.table("wireguard_peers").update({"status": "revoked"}).eq("site_id", site_id).execute()

    def list_pending(self) -> list[WireGuardPeer]:
        """List all pending peers awaiting wg0.conf activation."""
        client = get_supabase_client()
        resp = (
            client.table("wireguard_peers")
            .select("*")
            .eq("status", "pending")
            .order("created_at", desc=False)
            .execute()
        )
        peers = []
        for row in resp.data:
            peers.append(
                WireGuardPeer(
                    id=uuid.UUID(row["id"]),
                    site_id=row["site_id"],
                    public_key=row["public_key"],
                    assigned_ip=row["assigned_ip"],
                    peer_config=row["peer_config"],
                    status=row["status"],
                    created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")),
                    activated_at=None,
                )
            )
        return peers
