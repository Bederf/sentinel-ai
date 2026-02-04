# Cloudflare WAF Rules for SENTINEL BMS Intelligence

## Overview

This directory contains WAF (Web Application Firewall) rule definitions for SENTINEL web endpoints. Rules are applied via the Cloudflare Dashboard or API -- they are not automated in Docker.

**FSR Domains Addressed:**
- 4.9 Application Security (HIGH gap) -- WAF protection for internet-facing endpoints
- 4.13 Incident Detection (HIGH gap) -- Network-based IPS via Cloudflare managed services

## Architecture

```
Internet --> Cloudflare Edge (WAF + DDoS) --> Cloudflare Tunnel --> SENTINEL Backend
                     |
              9 WAF Rules Applied
              - OWASP CRS
              - SQL Injection Block
              - XSS Block
              - Path Traversal Block
              - Rate Limiting (4 tiers)
              - Bot Protection
              - Geo Restrictions
              - Size Limits
              - Header Validation
```

## Rule Summary

| ID | Rule Name | Action | Protects Against |
|----|-----------|--------|-----------------|
| 001 | OWASP Core Rule Set | Challenge | Top 10 web vulnerabilities |
| 002 | SQL Injection | Block | Database manipulation |
| 003 | XSS Protection | Block | Script injection |
| 004 | Path Traversal | Block | File system access |
| 005 | API Rate Limiting | Block/Challenge | Cost abuse, safety |
| 006 | Bot Protection | Challenge | Automated scanners |
| 007 | Geographic Access | Challenge | High-risk regions |
| 008 | Request Size | Block | DoS via large payloads |
| 009 | Header Validation | Block | Content-type confusion |

## Rate Limiting Tiers

| Endpoint | Limit | Rationale |
|----------|-------|-----------|
| `/api/chat`, `/api/hybrid-chat` | 30 req/min/IP | Claude API costs ~$0.01/query |
| `/api/mcp/simbiot/call` | 60 req/min/IP | BMS tool interaction safety |
| `/api/devices/*/control` | 20 req/min/IP | Safety-critical setpoint changes |
| `/api/*` (general) | 120 req/min/IP | Normal dashboard usage |

## Applying Rules via Cloudflare Dashboard

### Step 1: Enable Managed Rulesets
1. Log in to Cloudflare Dashboard
2. Navigate to **Security > WAF > Managed Rules**
3. Enable **Cloudflare OWASP Core Ruleset**
4. Set sensitivity to **Medium** (Paranoia Level 2)
5. Set anomaly score threshold to **60**

### Step 2: Create Custom Rules
1. Navigate to **Security > WAF > Custom Rules**
2. For each rule in `waf-rules.json`:
   - Click **Create Rule**
   - Enter the rule name and description
   - Copy the expression from the JSON file
   - Set the action (Block, Challenge, etc.)
   - Enable logging
   - Save and deploy

### Step 3: Configure Rate Limiting
1. Navigate to **Security > WAF > Rate Limiting Rules**
2. For each rate limit in rule `sentinel-waf-005`:
   - Click **Create Rule**
   - Set the expression (endpoint match)
   - Set requests per period
   - Set mitigation action and timeout
   - Save and deploy

### Step 4: Configure Bot Protection
1. Navigate to **Security > Bots**
2. Enable Bot Fight Mode
3. Configure Super Bot Fight Mode (if on Pro plan):
   - Definitely automated: Block
   - Likely automated: Managed Challenge
   - Verified bots: Allow

## Applying Rules via Cloudflare API

```bash
# Set your API credentials
CF_API_TOKEN="your-api-token"
CF_ZONE_ID="your-zone-id"

# List existing WAF rules
curl -X GET "https://api.cloudflare.com/client/v4/zones/${CF_ZONE_ID}/rulesets" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json"

# Create a custom WAF rule (example: SQL injection)
curl -X POST "https://api.cloudflare.com/client/v4/zones/${CF_ZONE_ID}/rulesets" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  --data '{
    "name": "SENTINEL SQL Injection Protection",
    "kind": "zone",
    "phase": "http_request_firewall_custom",
    "rules": [{
      "action": "block",
      "expression": "(http.request.uri.query contains \"'"'"' OR \" or http.request.uri.query contains \"1=1\")",
      "description": "Block SQL injection attempts"
    }]
  }'

# Create rate limiting rule (example: AI chat)
curl -X POST "https://api.cloudflare.com/client/v4/zones/${CF_ZONE_ID}/rulesets" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  --data '{
    "name": "SENTINEL AI Chat Rate Limit",
    "kind": "zone",
    "phase": "http_ratelimit",
    "rules": [{
      "action": "block",
      "ratelimit": {
        "characteristics": ["ip.src"],
        "period": 60,
        "requests_per_period": 30,
        "mitigation_timeout": 60
      },
      "expression": "(http.request.uri.path eq \"/api/chat\" or http.request.uri.path eq \"/api/hybrid-chat\")",
      "description": "Rate limit AI chat to 30 req/min/IP"
    }]
  }'
```

## Reviewing WAF Events

### Dashboard
1. Navigate to **Security > Events**
2. Filter by:
   - Service: WAF
   - Action: Block, Challenge
   - Date range: Last 24 hours
3. Review blocked requests for false positives
4. Adjust rule sensitivity if needed

### API
```bash
# Get WAF events for last 24 hours
curl -X GET "https://api.cloudflare.com/client/v4/zones/${CF_ZONE_ID}/security/events?per_page=50&since=2026-02-04T00:00:00Z" \
  -H "Authorization: Bearer ${CF_API_TOKEN}"
```

## Maintenance

- **Daily:** Review Cloudflare Security Events for false positives
- **Weekly:** Check rate limiting metrics and adjust thresholds
- **Monthly:** Review blocked countries list and update as needed
- **Quarterly:** Review OWASP rule sensitivity against application changes

## References

- [Cloudflare WAF Documentation](https://developers.cloudflare.com/waf/)
- [Cloudflare Rate Limiting](https://developers.cloudflare.com/waf/rate-limiting-rules/)
- [Cloudflare Bot Management](https://developers.cloudflare.com/bots/)
- [OWASP ModSecurity Core Rule Set](https://owasp.org/www-project-modsecurity-core-rule-set/)
