---
title: "Security Assumptions — SENTINEL BMS"
type: "architecture"
status: "published"
version: "1.0.0"
created: "2026-04-26"
updated: "2026-04-26"
tags: ["sentinel", "security", "architecture"]
domain: "security"
audience: "all"
---

# Security Assumptions — SENTINEL BMS

**Date:** 2026-04-26 | **Classification:** Architectural Decision | **Review:** On any change to Supabase access pattern

---

## 1. The Trust Boundary: Service Role Key

SENTINEL's security architecture treats the **Supabase service role key** as the exclusive trust boundary for database access. All backend-to-Supabase communication uses the service role key — individual user JWTs never bypass this key.

This means:

- The service role key has **unrestricted access** to all tables and schemas in Supabase
- Row Level Security (RLS) policies are **bypassed** by the service role key
- App-layer filtering via `user_site_access` table is the **only** tenant isolation mechanism

**Implication:** If the service role key is compromised, RLS provides no protection. Key rotation is the primary mitigation.

---

## 2. Why RLS Doesn't Apply to This Architecture

RLS policies enforce access control at the database layer for queries made by **individual user tokens**. In SENTINEL's architecture:

1. All Supabase access is **server-side** — the backend holds the service role key
2. The frontend **never** receives or uses the service role key
3. All queries run under the service role, which bypasses RLS
4. Individual user tokens are used only for authentication, not database queries

Therefore, RLS adds no security value in this architecture. It would be ceremonial — a developer might believe the policy is enforced when it is not.

**If this assumption changes** — for example, if a future feature introduces client-side Supabase access (mobile app, third-party integration) using individual tokens — RLS **must** be implemented before that access is introduced.

---

## 3. App-Layer Filtering as Defense-in-Depth

SENTINEL enforces tenant isolation at the application layer via:

- `UserSiteAccessRepository` — filters all queries by `site_id`
- `SiteRepository.get_all_for_user()` — applies `user_site_access` joins
- Admin bypass via `SentinelRole.ADMIN` — intentional, for troubleshooting

This is **not** the primary isolation mechanism (the service role key is). It is defense-in-depth: if the service role key were somehow restricted, app-layer filtering provides a secondary enforcement layer.

---

## 4. Key Rotation as the Mitigation Strategy

Given that the service role key is the trust boundary:

- **Key rotation** is the primary mitigation for compromise
- Rotate immediately if the key is exposed in logs, commits, or third-party systems
- Supabase supports multiple active keys — rotate with zero downtime
- Monitor for unauthorized use via Supabase usage logs and `login_audit` table

**Rotation procedure:**
1. Generate new service role key in Supabase dashboard
2. Update `SUPABASE_SERVICE_ROLE_KEY` env var in all deployment targets
3. Deploy — zero downtime, key is read at startup
4. Revoke the old key in Supabase dashboard
5. Verify all services operational

---

## 5. Architectural Assumptions Summary

| Assumption | Rationale | If It Changes |
|-----------|----------|---------------|
| Service role key is backend-only | No client-side Supabase access | Implement RLS before any client-side access |
| RLS bypassed by service role | Service role has admin-equivalent access | Not applicable — bypass is by design |
| App-layer filtering is secondary | Defense-in-depth, not primary control | Would become primary if service role is scoped |
| Key rotation mitigates compromise | No additional secret storage layer | Consider Vault for key management |

---

## 6. Vault Status

**Obsidian vault:** `/home/bederf/sentinel-vault/` — knowledge management, not secret storage
**Hashicorp Vault:** Not deployed in current infrastructure

All secrets remain as env vars. Acceptable for current scale.

---

**Owner:** Architecture decision — review on any new Supabase access pattern or client integration.
