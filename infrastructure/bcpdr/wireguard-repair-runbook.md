# WireGuard Bridge Re-Pairing Procedure

**Purpose:** Re-establish the SENTINEL-to-BMS WireGuard tunnel after full VPS loss
or key rotation. The BMS bridge (on-site hardware at the building) connects to this
VPS over WireGuard to provide read/write access to Desigo CC and DALI networks.

**Owner for SENTINEL side:** [Platform team]
**Owner for Altron/BMS side:** [NAME — e.g. Evans or Brandon]
**Date this template was created:** $(date +%Y-%m-%d)
**Date Altron steps were confirmed:** [YYYY-MM-DD — blank means untested]
**Last tested:** [YYYY-MM-DD]

---

## Prerequisites

| Item | Where it lives | Restore from |
|------|----------------|--------------|
| SENTINEL WireGuard private key | Live VPS: `/etc/wireguard/` | Encrypted secrets bundle |
| Altron/BMS WireGuard public key | Live VPS: `/etc/wireguard/` | Encrypted secrets bundle |
| Bridge WireGuard config file | Live VPS: `/etc/wireguard/sentinel-bridge.conf` | Encrypted secrets bundle |

If the secrets bundle is intact, restore these files first (see DR runbook 3.6).
If the secrets bundle was also lost, both sides need new key generation.

---

## Step 1: SENTINEL Side (You)

1. Restore or regenerate WireGuard config:

   ```bash
   # If restoring from secrets bundle:
   age --decrypt -i /path/to/key.txt sentinel-secrets-*.tar.age | tar -xvf -

   # If regenerating (secrets bundle also lost):
   wg genkey | tee /etc/wireguard/private.key | wg pubkey > /etc/wireguard/public.key
   chmod 600 /etc/wireguard/private.key
   ```

2. Write the interface config to `/etc/wireguard/sentinel-bridge.conf`:

   ```ini
   [Interface]
   PrivateKey = <private key from step 1>
   Address = 10.99.0.2/24
   ListenPort = 51820

   [Peer]
   PublicKey = <BMS bridge public key — provided by Altron>
   AllowedIPs = 10.99.0.0/24
   PersistentKeepalive = 25
   ```

3. Bring up the interface:

   ```bash
   systemctl enable --now wg-quick@sentinel-bridge
   wg show
   ```

   Expected: handshake shows `latest handshake: [time]` — if blank, the BMS side
   has not yet accepted the new key.

4. Send the **new SENTINEL public key** to Altron/Brandon:

   ```
   cat /etc/wireguard/public.key
   ```

---

## Step 2: Altron/BMS Side (Brandon or Evans — **confirm these steps**)

> **⚠ This section MUST be validated by Brandon or Evans.**
> The exact steps on the BMS bridge (on-site hardware) depend on how their
> WireGuard peer config is managed and whether they use a management interface
> or SSH directly into the bridge.

**What Altron needs to do:**

1. Accept the new SENTINEL public key.
2. Update the bridge's WireGuard peer config with the new public key.
3. Verify the handshake establishes from their side.
4. Confirm the bridge can reach `10.99.0.2:51820`.

**Expected outcome after both sides are configured:**

```bash
wg show
# output: interface: sentinel-bridge
#   peer: <altron-public-key>
#     endpoint: <bridge-ip>:51820
#     allowed ips: 10.99.0.0/24
#     latest handshake: 30 seconds ago
#     transfer: 1.4 KiB received, 2.1 KiB sent
```

Then test the BMS API path:

```bash
curl -s http://10.99.0.1:8080/api/health
```

---

## Verification

| Check | Command | Expected |
|-------|---------|----------|
| WireGuard handshake | `wg show` | `latest handshake` < 5 min |
| Bridge API reachable | `curl -s http://10.99.0.1:8080/api/health` | 200 OK |
| Desigo CC telemetry flowing | Backend logs | `bridge_poll` shows sensor values |

---

## Key Rotation Notes

- If both sides rotate keys simultaneously, coordination is required ahead of time.
- Prefer a staggered rotation: rotate one side, confirm handshake, rotate the other.
- After rotation, regenerate the encrypted secrets bundle:
  ```
  ./infrastructure/secrets-bundle.sh encrypt
  ```

---

## Altron Contact

| Role | Name | Contact | Procedure confirmed? | Date |
|------|------|---------|---------------------|------|
| BMS bridge admin | [Brandon / Evans] | [phone/email] | [Yes/No] | [date] |

> **This procedure is incomplete until the Altron-side steps above are populated.**
> Contact Brandon or Evans to fill in Step 2 and record the date here.
> The DR runbook is not ready until both sides of the handshake are documented.
