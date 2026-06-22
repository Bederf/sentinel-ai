# Supervised Control Readiness

SENTINEL must prove control readiness during advisory mode before a site can be promoted to supervised mode. A client or operator should not have to discover missing write permissions by pressing an approval button.

## Readiness Contract

A site may show AI recommendations in advisory mode, but it may not execute supervised control until all of these are true:

- The relevant control module is active and licensed, for example `hvac_control` for AHU, FCU, VAV, chiller, cooling tower, and pump control.
- The site has an enabled write-capable adapter.
- Bridge-backed sites expose `POST /api/sites/{site_id}/write`.
- The bridge policy stage is synced to the site onboarding phase.
- Verified writable control points exist in `point_asset_mappings`.
- Controllable equipment coverage meets the promotion threshold.
- The bridge writable-point whitelist includes every point SENTINEL may write.

## Required State Stores

SENTINEL uses more than one safety boundary. All must agree before supervised control is allowed.

| Boundary | Source | Purpose |
| --- | --- | --- |
| Site phase | `sites.onboarding_phase` | Determines trust-ladder mode: advisory, supervised, automatic |
| Control module | `site_modules` | Confirms the control add-on is licensed and active |
| Adapter config | `site_adapter_config.connection_config` | Stores bridge base URL, token, `supports_writes`, and `write_enabled` |
| Semantic mapping | `point_asset_mappings` | Maps equipment/action names to exact BMS object IDs |
| SENTINEL whitelist | `sentinel_write_whitelist.json` | Allows only known-safe equipment classes and point names |
| Bridge whitelist | `/opt/sites/{site_id}/config/bridge_writable_points.json` on the bridge host | Final bridge-side allowlist for actual writes |
| Bridge policy | `GET/PUT /api/sites/{site_id}/ipmvp/policy-state` | Ensures the bridge is in the same stage as SENTINEL |

## Advisory Promotion Gate

The advisory to supervised gate must fail if any readiness item is missing. The health page and phase update endpoints should show the failed gate rather than allowing promotion.

Current gate examples:

- `control_modules_active_for_controllable_equipment`
- `write_capable_adapter_configured`
- `bridge_write_endpoint_available`
- `verified_writable_control_points >= 10`
- `controllable_equipment_control_coverage >= 0.75`
- `no_safety_violations_30d`

## Telegram Behavior

Telegram approval buttons must only be shown when supervised readiness passes. If readiness fails:

- Do not show `Approve`.
- Show `Create work order` for manual BMS action.
- Show `Log issue` for support/developer follow-up.
- Do not attempt a device write from an old approval button.

## Bridge Whitelist Failure

If approval fails with:

```text
object_id '...' is not in the writable whitelist
```

then SENTINEL DB mappings are not enough. Add the exact object ID to the bridge host whitelist:

```text
/opt/sites/{site_id}/config/bridge_writable_points.json
```

Example object IDs for site-002 AHU B01:

```text
S002-AHU-B1-001.DAMPER_POSITION
S002-AHU-B1-001.sat_setpoint
```

After updating the bridge whitelist, verify:

- `GET /api/sites/{site_id}/ipmvp/policy-state` returns the intended stage.
- `POST /api/sites/{site_id}/write` no longer rejects the object ID with a whitelist error.
- SENTINEL approval audit records a successful write or a clear bridge-side rejection.

## Client Rule

Clients should only need to choose the desired mode. SENTINEL must do the readiness checks, explain failed gates, and block promotion until the previous phase has prepared the next phase safely.
