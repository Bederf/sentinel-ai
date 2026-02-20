---
title: "HTTPS/SSL Setup & Reverse Proxy Configuration"
type: "operational"
status: "approved"
version: "1.0.0"
created: "2026-02-09"
updated: "2026-02-09"
author: "Sentinel Development Team"
tags: ["deployment", "ssl", "https", "caddy", "reverse-proxy", "nginx"]
related: ["../docker-deployment.md"]
---

# HTTPS/SSL Setup for BMS Intelligence

## Problem Fixed

Frontend SSL error: `net::ERR_SSL_PROTOCOL_ERROR` when accessing from deployed HTTPS domain (`https://bms.aimthelaw.co.za`).

**Root Cause:** Frontend tried to connect to `https://localhost:9095` (upgrading HTTP localhost to HTTPS), but backend had no SSL certificate.

## Solution Architecture

Uses **Caddy** reverse proxy for:
- HTTPS termination (automatic Let's Encrypt SSL)
- Frontend routing (SPA served from nginx)
- API proxy (`/api/*` → backend)
- Security headers enforcement
- Automatic HTTP→HTTPS redirect

```
User Browser
    ↓ (HTTPS)
┌─────────────────────┐
│  Caddy :443         │ ← HTTPS termination, SSL certs
│  bms.aimthelaw.co.za│
└──────────┬──────────┘
     ↓ HTTP (internal)
  ┌─────────┴──────────┐
  ↓                    ↓
Frontend nginx:80   Backend :8000
```

## Changes Made

### 1. Frontend Nginx Configuration (`frontend/nginx.conf`)

Added `/api/` proxy rule:
```nginx
location /api/ {
    proxy_pass http://backend:8000/api/;
    proxy_http_version 1.1;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_read_timeout 60s;
}
```

This allows nginx to:
- Accept `/api/*` requests from browser
- Forward to backend via internal Docker network
- Preserve original client IP and protocol headers

### 2. Caddy Reverse Proxy (`infrastructure/caddy/Caddyfile`)

New configuration handles:
- HTTPS with automatic Let's Encrypt renewal
- Frontend SPA routing (`/` → nginx)
- API proxying (`/api/*` → backend)
- Security headers (HSTS, CSP, etc.)
- www → non-www redirect

```caddy
bms.aimthelaw.co.za {
  handle /api/* {
    reverse_proxy backend:8000
  }
  handle / {
    reverse_proxy frontend:80
  }
}
```

### 3. Docker Compose Updates

**Added Caddy service:**
```yaml
caddy:
  image: caddy:2-alpine
  ports:
    - "80:80"      # HTTP redirect
    - "443:443"    # HTTPS
  volumes:
    - ./infrastructure/caddy/Caddyfile:/etc/caddy/Caddyfile
    - caddy-data:/data          # SSL certificates
    - caddy-config:/config
```

**Updated frontend build:**
- Removed hardcoded `VITE_API_URL=http://localhost:8082` build arg
- Now uses empty `VITE_API_URL=""` from `.env.production`
- Requests use relative URLs `/api/*` (nginx proxies them)

**Added volumes:**
```yaml
volumes:
  caddy-data:     # Persistent SSL certificates
  caddy-config:   # Cached configurations
```

## How It Works

### Local Development
- Vite dev server proxy: `localhost:9096/api/*` → `http://localhost:9095/api/*`
- Browser connects to `http://localhost:9096` (no SSL)

### Deployed (Production)
- Caddy handles `https://bms.aimthelaw.co.za:443`
- Automatic Let's Encrypt certificate renewal
- Caddy proxies to:
  - Frontend nginx `:80` for SPA (`/` route)
  - Backend `:8000` for API (`/api/*` routes)
- All internal traffic is HTTP (internal Docker network)
- Client IP and protocol headers preserved via `X-Forwarded-*`

## DNS & SSL Requirements

For deployed environment to work:

1. **DNS Record** - Points to Caddy host:
   ```
   bms.aimthelaw.co.za  A  <server-ip>
   ```

2. **Firewall** - Opens ports to Caddy:
   ```
   Port 80/tcp   - HTTP (for Let's Encrypt ACME challenge)
   Port 443/tcp  - HTTPS (production traffic)
   ```

3. **Email** - For Let's Encrypt renewal notifications:
   - Configured in Caddyfile: `email bms@aimthelaw.co.za`

## Deployment Instructions

### First Time Deploy

```bash
# 1. Update DNS to point to server IP
# 2. Start services
docker-compose up -d

# 3. Verify SSL certificate (takes 30-60s)
docker-compose logs caddy | grep -i "certificate"

# 4. Test HTTPS access
curl -I https://bms.aimthelaw.co.za/api/health
# Should return 200 OK
```

### Monitor Certificate Renewal

```bash
# Check certificate expiry
docker exec bms-caddy caddy list-certs

# View Caddy logs
docker-compose logs -f caddy | grep -i cert

# Manual renewal (if needed)
docker exec bms-caddy caddy reload
```

## Troubleshooting

### SSL Certificate Not Issued

**Problem:** Caddy stuck waiting for certificate
```
docker-compose logs caddy | grep "error"
```

**Causes & Fixes:**

1. **DNS not resolving**
   ```bash
   nslookup bms.aimthelaw.co.za
   # Should resolve to server IP
   ```

2. **Port 80/443 blocked**
   ```bash
   sudo iptables -L -n | grep -i "^Chain\|80\|443"
   # Verify ports are ACCEPT
   ```

3. **Let's Encrypt rate limit**
   - Wait 1 hour between attempts
   - Caddy retries automatically

4. **Wrong email domain**
   - Update Caddyfile: `email your-email@domain.com`
   - Restart Caddy: `docker-compose restart caddy`

### API 429 Rate Limiting

**If frontend still shows rate limit errors:**

The SSL fix resolves the connectivity issue, but API rate limiting is managed separately:
- Frontend queues requests (MAX_CONCURRENT_API_REQUESTS = 4)
- Staggered with 250ms delays between requests
- See `docs/rate-limiting.md` for details

### Frontend Shows Blank/404

**Check nginx is serving SPA correctly:**
```bash
curl -I http://localhost:3002/
# Should return 200 (index.html)

curl -I http://localhost:3002/some/random/route
# Should also return 200 (SPA routing)
```

## Security Headers

Caddy automatically adds:
```
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
X-Frame-Options: SAMEORIGIN
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block
```

## Performance Notes

- **SSL overhead**: ~5-10ms per request (one-time TLS handshake)
- **Proxy latency**: ~1-2ms (internal Docker network)
- **Certificate caching**: Caddy caches in `caddy-data` volume

## Related

- [Docker Deployment](./docker-deployment.md)
- [Rate Limiting Guide](./rate-limiting.md)
- [Nginx Configuration](../nginx-optimization.md)
- [Caddy Documentation](https://caddyserver.com/docs)
