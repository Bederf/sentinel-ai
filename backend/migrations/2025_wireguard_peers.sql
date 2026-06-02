-- Migration: wireguard_peers
-- Purpose: WireGuard peer lifecycle for Home Assistant residential gateways
-- Each HA gateway client gets their own VPN peer with an assigned IP

CREATE TABLE wireguard_peers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id              UUID        NOT NULL REFERENCES residential_sites(id),
    public_key VARCHAR(44) NOT NULL,
    assigned_ip VARCHAR NOT NULL,
    peer_config TEXT NOT NULL,  -- [Peer] block for wg0.conf — server-side only
    status VARCHAR DEFAULT 'pending'
        CHECK (status IN ('pending', 'active', 'revoked')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    activated_at TIMESTAMPTZ,
    CONSTRAINT valid_pubkey CHECK (public_key ~ '^[A-Za-z0-9+/]{43}=$')
);

-- Unique public key — no duplicate peers
CREATE UNIQUE INDEX idx_wireguard_peers_public_key
    ON wireguard_peers(public_key);

-- One active peer per site at a time
CREATE UNIQUE INDEX idx_wireguard_peers_site_id_active
    ON wireguard_peers(site_id)
    WHERE status = 'active';
