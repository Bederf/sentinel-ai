---
title: "Auth API"
type: "reference"
status: "draft"
version: "1.1.0"
created: "2026-03-31"
updated: "2026-05-23"
tags: ["sentinel", "documentation"]
related: []
domain: "security"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# Auth API

## Overview

Authentication API endpoints for SENTINEL BMS Platform.

## Endpoints

### POST /api/auth/login
Magic-link login — sends a code to the user's email.

**Request:**
```json
{ "email": "user@example.com" }
```

**Response:**
```json
{ "message": "Login code sent", "email": "user@example.com" }
```

---

### POST /api/auth/login/verify
Complete login with the code from email.

**Request:**
```json
{ "email": "user@example.com", "code": "123456" }
```

**Response:** Sets HttpOnly `access_token` + `refresh_token` cookies.
```json
{
  "access_token": "<jwt>",
  "refresh_token": "<jwt>",
  "user": { "user_id": "...", "email": "...", "full_name": "...", "role": "..." }
}
```

---

### POST /api/auth/invite
Send a magic-link invite to a new user. **Admin only.**

**Request:**
```json
{
  "email": "newuser@example.com",
  "full_name": "Jane Manager",
  "role": "operator",
  "site_id": "site-002"
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `email` | string | required | Invitee email address |
| `full_name` | string | required | Invitee display name |
| `role` | string | `"operator"` | One of: `admin`, `operator`, `developer`, `auditor` |
| `site_id` | string | `"site-002"` | Site the user will have access to |

**Response:** `201 Created`
```json
{
  "message": "Invite sent",
  "email": "newuser@example.com",
  "expires_at": "2026-05-25T12:00:00+00:00"
}
```

**Rate limit:** 10 invites/hour per admin.

---

### POST /api/auth/invite/accept
Accept a magic-link invite and activate the account. **Public — no auth required.**

**Request:**
```json
{
  "token": "<magic-link-token>",
  "password": "securepassword123"
}
```

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `token` | string | required | Token from the invite email link |
| `password` | string | 8–128 chars | Account password |

**Response:** Sets HttpOnly `access_token` + `refresh_token` cookies.
```json
{
  "access_token": "<jwt>",
  "refresh_token": "<jwt>",
  "user": { "user_id": "...", "email": "...", "full_name": "...", "role": "..." },
  "session_id": "..."
}
```

**Error cases:**
- `400` — Token expired, already accepted, or invalid
- `404` — Token not found

---

### GET /api/auth/me
Get current authenticated user.

**Response:**
```json
{ "user_id": "...", "email": "...", "full_name": "...", "role": "..." }
```

---

### POST /api/auth/logout
Revoke the current session and clear cookies.

---

### GET /api/auth/sessions
List active sessions for the current user. **Auth required.**

---

### DELETE /api/auth/sessions/{session_id}
Revoke a specific session. **Auth required.**

---

### POST /api/auth/refresh
Refresh access token using the refresh_token cookie.

---

## Magic Link Flow

```
Admin                          Platform                         Invitee
  |                                  |                               |
  |-- POST /api/auth/invite -------->|                               |
  |   (role, site_id, email)         |                               |
  |                                  |-- SMTP email ------------------>|
  |                                  |   /invite?token=xxx            |
  |                                  |                               |
  |                                  |                 User clicks   |
  |                                  |                 Sets password |
  |                                  |<-- POST /invite/accept -------|
  |                                  |   (token, password)           |
  |                                  |-- JWT cookies set             |
  |                                  |                               |
```

## Database

| Table | Purpose |
|-------|---------|
| `magic_link_tokens` | Invite token lifecycle — expiry, acceptance, metadata |
| `sentinel_users` | Users with `password_hash` + `must_set_password` columns |
| `user_site_access` | Site access granted on invite acceptance |

## Implementation

For full details, see: `backend/app/api/auth.py` and `backend/app/services/magic_link_service.py`
