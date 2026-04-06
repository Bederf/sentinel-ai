---
title: "Auth API"
type: "reference"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-03-31"
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

- POST /login
- POST /login/mfa-complete
- POST /verify
- GET /me
- POST /logout
- POST /refresh
- GET /sessions
- DELETE /sessions/{session_id}
- DELETE /sessions
- POST /api-keys

... and 2 more endpoints


## Implementation

For full details, see: `backend/app/api/auth.py`
