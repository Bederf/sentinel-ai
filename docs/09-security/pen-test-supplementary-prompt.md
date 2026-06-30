# Supplementary Pen Test — Additional Tooling

Run these after the initial ZAP/WhatWeb scan completes. Focus on depth, not breadth.

## Phase 2b: Content Discovery
```bash
gobuster dir -u https://sentinel-ai.co.za -w /usr/share/wordlists/dirbuster/directory-list-2.3-medium.txt -x py,json,yml,yaml,conf,config,bak,txt,md,log -t 30 -o ~/sentinel-pentest-20260623/gobuster-landing.txt

gobuster dir -u https://bms.sentinel-ai.co.za -w /usr/share/wordlists/dirbuster/directory-list-2.3-medium.txt -x py,json,yml,yaml,conf,config,bak,txt,md,log -t 30 -o ~/sentinel-pentest-20260623/gobuster-api.txt
```
Document any discovered paths that return 200/403 (not 404).

## Phase 2c: Template-Based Vulnerability Scan
```bash
nuclei -u https://sentinel-ai.co.za -severity critical,high,medium -o ~/sentinel-pentest-20260623/nuclei-landing.txt
nuclei -u https://bms.sentinel-ai.co.za -severity critical,high,medium -o ~/sentinel-pentest-20260623/nuclei-api.txt
```

## Phase 2d: Web Server Hardening
```bash
# Against the origin IP (not Cloudflare-proxied)
nikto -h https://sentinel-ai.co.za -ssl -Format txt -output ~/sentinel-pentest-20260623/nikto-landing.txt

# Against the API subdomain (expect Cloudflare blocks)
nikto -h https://bms.sentinel-ai.co.za -ssl -Format txt -output ~/sentinel-pentest-20260623/nikto-api.txt
```

## Phase 2e: API Fuzzing (if you discovered any endpoints)
```bash
# Example: fuzz API version paths
ffuf -u https://bms.sentinel-ai.co.za/api/FUZZ -w /usr/share/wordlists/api/objects.txt -ac -o ~/sentinel-pentest-20260623/ffuf-api-endpoints.json

# Example: fuzz site IDs for BOLA testing
ffuf -u https://bms.sentinel-ai.co.za/api/sites/FUZZ/status -w /usr/share/wordlists/api/site-ids.txt -ac -o ~/sentinel-pentest-20260623/ffuf-site-ids.json
```

## Consolidation
Append all new findings to the master findings table with tool name as source. Flag any critical/high findings immediately.
