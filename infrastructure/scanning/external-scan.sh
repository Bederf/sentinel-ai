#!/bin/bash
# =============================================================================
# SENTINEL External Vulnerability Scan
# =============================================================================
# Schedule: Monthly (1st Monday, via cron)
# Scope:    Internet-facing endpoints via Cloudflare
# Domain:   FSR 4.10 - Vulnerability Management
#
# Prerequisites:
#   - nmap installed (apt install nmap)
#   - openssl installed (standard)
#   - curl installed (standard)
#   - dig installed (apt install dnsutils)
#
# Usage:
#   ./external-scan.sh [--domain example.com] [--vps-ip x.x.x.x]
#
# =============================================================================

set -euo pipefail

# --- Configuration -----------------------------------------------------------
SCAN_DATE=$(date +%Y-%m-%d)
SCAN_TIME=$(date +%H:%M:%S)
REPORT_DIR="/opt/bms-intelligence/security-reports/external/${SCAN_DATE}"

# Default targets - override with flags
SENTINEL_DOMAIN="${SENTINEL_DOMAIN:-sentinel.bfrancois.com}"
AIMTHELAW_DOMAIN="${AIMTHELAW_DOMAIN:-aimthelaw.bfrancois.com}"
VPS_PUBLIC_IP="${VPS_PUBLIC_IP:-}"

# Colour codes for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# --- Argument parsing --------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case $1 in
        --domain) SENTINEL_DOMAIN="$2"; shift 2 ;;
        --vps-ip) VPS_PUBLIC_IP="$2"; shift 2 ;;
        --help)
            echo "Usage: $0 [--domain example.com] [--vps-ip x.x.x.x]"
            echo ""
            echo "Options:"
            echo "  --domain    SENTINEL domain (default: sentinel.bfrancois.com)"
            echo "  --vps-ip    Contabo VPS public IP for port scanning"
            echo "  --help      Show this help message"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# --- Setup -------------------------------------------------------------------
mkdir -p "$REPORT_DIR"

# Start report
SUMMARY_FILE="${REPORT_DIR}/scan-summary.txt"
cat > "$SUMMARY_FILE" <<EOF
================================================================================
SENTINEL External Vulnerability Scan Report
================================================================================
Date:       ${SCAN_DATE}
Time:       ${SCAN_TIME} SAST
Domains:    ${SENTINEL_DOMAIN}, ${AIMTHELAW_DOMAIN}
VPS IP:     ${VPS_PUBLIC_IP:-"Not specified (port scan skipped)"}
Scanner:    $(whoami)@$(hostname)
================================================================================

EOF

echo -e "${GREEN}=== SENTINEL External Vulnerability Scan - ${SCAN_DATE} ===${NC}"
echo ""

FINDINGS=0
CRITICAL=0
HIGH=0
MEDIUM=0
LOW=0

# --- Helper functions --------------------------------------------------------
log_finding() {
    local severity=$1
    local category=$2
    local description=$3
    echo "[${severity}] ${category}: ${description}" >> "$SUMMARY_FILE"
    FINDINGS=$((FINDINGS + 1))
    case $severity in
        CRITICAL) CRITICAL=$((CRITICAL + 1)) ;;
        HIGH) HIGH=$((HIGH + 1)) ;;
        MEDIUM) MEDIUM=$((MEDIUM + 1)) ;;
        LOW) LOW=$((LOW + 1)) ;;
    esac
}

# =============================================================================
# CHECK 1: SSL/TLS Certificate Validation
# =============================================================================
echo -e "${YELLOW}[1/5] Checking TLS configuration...${NC}"
TLS_REPORT="${REPORT_DIR}/tls-report.txt"

for domain in "$SENTINEL_DOMAIN" "$AIMTHELAW_DOMAIN"; do
    echo "--- TLS Check: ${domain} ---" >> "$TLS_REPORT"

    # Certificate expiry check
    CERT_EXPIRY=$(echo | openssl s_client -servername "$domain" -connect "${domain}:443" 2>/dev/null | \
        openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2 || echo "FAILED")

    if [ "$CERT_EXPIRY" = "FAILED" ]; then
        log_finding "HIGH" "TLS" "Cannot retrieve certificate for ${domain}"
        echo "  Certificate: FAILED to retrieve" >> "$TLS_REPORT"
    else
        EXPIRY_EPOCH=$(date -d "$CERT_EXPIRY" +%s 2>/dev/null || echo "0")
        NOW_EPOCH=$(date +%s)
        DAYS_LEFT=$(( (EXPIRY_EPOCH - NOW_EPOCH) / 86400 ))

        echo "  Certificate expires: ${CERT_EXPIRY} (${DAYS_LEFT} days remaining)" >> "$TLS_REPORT"

        if [ "$DAYS_LEFT" -lt 7 ]; then
            log_finding "CRITICAL" "TLS" "Certificate for ${domain} expires in ${DAYS_LEFT} days"
        elif [ "$DAYS_LEFT" -lt 30 ]; then
            log_finding "HIGH" "TLS" "Certificate for ${domain} expires in ${DAYS_LEFT} days"
        elif [ "$DAYS_LEFT" -lt 60 ]; then
            log_finding "MEDIUM" "TLS" "Certificate for ${domain} expires in ${DAYS_LEFT} days"
        fi
    fi

    # Protocol version check (reject SSLv3, TLSv1.0, TLSv1.1)
    for protocol in ssl3 tls1 tls1_1; do
        RESULT=$(echo | openssl s_client -"$protocol" -connect "${domain}:443" 2>&1 || true)
        if echo "$RESULT" | grep -q "BEGIN CERTIFICATE"; then
            log_finding "HIGH" "TLS" "${domain} accepts deprecated protocol: ${protocol}"
            echo "  WARNING: Accepts ${protocol}" >> "$TLS_REPORT"
        else
            echo "  OK: Rejects ${protocol}" >> "$TLS_REPORT"
        fi
    done

    # Cipher suite check - weak ciphers
    WEAK_CIPHERS=$(echo | openssl s_client -cipher 'NULL:eNULL:aNULL:RC4:DES:3DES' \
        -connect "${domain}:443" 2>&1 || true)
    if echo "$WEAK_CIPHERS" | grep -q "BEGIN CERTIFICATE"; then
        log_finding "HIGH" "TLS" "${domain} accepts weak cipher suites"
        echo "  WARNING: Accepts weak ciphers" >> "$TLS_REPORT"
    else
        echo "  OK: Rejects weak ciphers" >> "$TLS_REPORT"
    fi

    echo "" >> "$TLS_REPORT"
done

echo -e "  ${GREEN}TLS report saved${NC}"

# =============================================================================
# CHECK 2: HTTP Security Headers
# =============================================================================
echo -e "${YELLOW}[2/5] Checking HTTP security headers...${NC}"
HEADERS_REPORT="${REPORT_DIR}/headers-report.txt"

REQUIRED_HEADERS=(
    "strict-transport-security"
    "x-content-type-options"
    "x-frame-options"
    "content-security-policy"
    "x-xss-protection"
    "referrer-policy"
    "permissions-policy"
)

for domain in "$SENTINEL_DOMAIN" "$AIMTHELAW_DOMAIN"; do
    echo "--- Security Headers: ${domain} ---" >> "$HEADERS_REPORT"

    # Fetch headers
    RESPONSE_HEADERS=$(curl -sI "https://${domain}/" 2>/dev/null || echo "FAILED")

    if [ "$RESPONSE_HEADERS" = "FAILED" ]; then
        log_finding "HIGH" "Headers" "Cannot connect to ${domain}"
        echo "  FAILED to connect" >> "$HEADERS_REPORT"
        continue
    fi

    for header in "${REQUIRED_HEADERS[@]}"; do
        if echo "$RESPONSE_HEADERS" | grep -qi "^${header}:"; then
            HEADER_VALUE=$(echo "$RESPONSE_HEADERS" | grep -i "^${header}:" | head -1)
            echo "  PRESENT: ${HEADER_VALUE}" >> "$HEADERS_REPORT"
        else
            case $header in
                strict-transport-security)
                    log_finding "HIGH" "Headers" "Missing HSTS header on ${domain}" ;;
                content-security-policy)
                    log_finding "MEDIUM" "Headers" "Missing CSP header on ${domain}" ;;
                *)
                    log_finding "LOW" "Headers" "Missing ${header} on ${domain}" ;;
            esac
            echo "  MISSING: ${header}" >> "$HEADERS_REPORT"
        fi
    done

    # Check for information disclosure headers
    if echo "$RESPONSE_HEADERS" | grep -qi "^server:"; then
        SERVER_HEADER=$(echo "$RESPONSE_HEADERS" | grep -i "^server:" | head -1)
        log_finding "LOW" "Headers" "Server header disclosed on ${domain}: ${SERVER_HEADER}"
        echo "  INFO DISCLOSURE: ${SERVER_HEADER}" >> "$HEADERS_REPORT"
    fi

    if echo "$RESPONSE_HEADERS" | grep -qi "^x-powered-by:"; then
        POWERED_BY=$(echo "$RESPONSE_HEADERS" | grep -i "^x-powered-by:" | head -1)
        log_finding "LOW" "Headers" "X-Powered-By disclosed on ${domain}: ${POWERED_BY}"
        echo "  INFO DISCLOSURE: ${POWERED_BY}" >> "$HEADERS_REPORT"
    fi

    echo "" >> "$HEADERS_REPORT"
done

echo -e "  ${GREEN}Headers report saved${NC}"

# =============================================================================
# CHECK 3: Open Port Scan (VPS Public IP)
# =============================================================================
echo -e "${YELLOW}[3/5] Scanning for exposed ports...${NC}"
PORT_REPORT="${REPORT_DIR}/port-scan-report.txt"

if [ -n "$VPS_PUBLIC_IP" ]; then
    echo "--- Port Scan: ${VPS_PUBLIC_IP} ---" >> "$PORT_REPORT"
    echo "Note: Cloudflare Tunnel means no direct ports should be exposed" >> "$PORT_REPORT"
    echo "Expected: Only SSH (22) if allowed, or nothing (all via tunnel)" >> "$PORT_REPORT"
    echo "" >> "$PORT_REPORT"

    # Check if nmap is available
    if command -v nmap &> /dev/null; then
        # Top 1000 ports scan
        nmap -sT -T3 --top-ports 1000 -oN "${REPORT_DIR}/nmap-full.txt" "$VPS_PUBLIC_IP" 2>/dev/null || true

        # Extract open ports
        OPEN_PORTS=$(grep "^[0-9]" "${REPORT_DIR}/nmap-full.txt" 2>/dev/null | grep "open" || true)

        if [ -n "$OPEN_PORTS" ]; then
            echo "Open ports found:" >> "$PORT_REPORT"
            echo "$OPEN_PORTS" >> "$PORT_REPORT"

            # Check for unexpected ports (anything other than SSH)
            UNEXPECTED=$(echo "$OPEN_PORTS" | grep -v "^22/" || true)
            if [ -n "$UNEXPECTED" ]; then
                while IFS= read -r line; do
                    PORT_NUM=$(echo "$line" | cut -d/ -f1)
                    log_finding "HIGH" "Ports" "Unexpected port ${PORT_NUM} open on VPS (should use Cloudflare Tunnel)"
                done <<< "$UNEXPECTED"
            fi

            # SSH-specific checks
            if echo "$OPEN_PORTS" | grep -q "^22/"; then
                log_finding "MEDIUM" "Ports" "SSH (22) directly exposed - consider restricting to VPN/specific IPs"
                echo "  NOTE: SSH directly accessible - review access restrictions" >> "$PORT_REPORT"
            fi
        else
            echo "No open ports found - all services behind Cloudflare Tunnel" >> "$PORT_REPORT"
        fi
    else
        echo "WARNING: nmap not installed - install with: apt install nmap" >> "$PORT_REPORT"
        log_finding "LOW" "Ports" "nmap not installed - port scan skipped"

        # Fallback: Check common ports with bash
        echo "Fallback: Checking common ports with /dev/tcp..." >> "$PORT_REPORT"
        for port in 22 80 443 3000 5432 8080 8443 9090 9095 9096; do
            (echo > /dev/tcp/"$VPS_PUBLIC_IP"/"$port") 2>/dev/null && \
                echo "  Port ${port}: OPEN" >> "$PORT_REPORT" && \
                log_finding "MEDIUM" "Ports" "Port ${port} appears open on VPS" || \
                echo "  Port ${port}: closed" >> "$PORT_REPORT"
        done
    fi
else
    echo "Port scan skipped: VPS_PUBLIC_IP not specified" >> "$PORT_REPORT"
    echo "Run with: $0 --vps-ip <IP_ADDRESS>" >> "$PORT_REPORT"
fi

echo -e "  ${GREEN}Port scan report saved${NC}"

# =============================================================================
# CHECK 4: API Endpoint Testing
# =============================================================================
echo -e "${YELLOW}[4/5] Testing API endpoints...${NC}"
API_REPORT="${REPORT_DIR}/api-scan-report.txt"

API_BASE="https://${SENTINEL_DOMAIN}"

echo "--- API Security Check: ${API_BASE} ---" >> "$API_REPORT"

# Check if /docs (Swagger UI) is publicly accessible
HTTP_CODE=$(curl -sL -o /dev/null -w "%{http_code}" "${API_BASE}/docs" 2>/dev/null || echo "000")
echo "  /docs endpoint: HTTP ${HTTP_CODE}" >> "$API_REPORT"
if [ "$HTTP_CODE" = "200" ]; then
    log_finding "MEDIUM" "API" "Swagger UI (/docs) publicly accessible"
fi

# Check if /openapi.json is publicly accessible
HTTP_CODE=$(curl -sL -o /dev/null -w "%{http_code}" "${API_BASE}/openapi.json" 2>/dev/null || echo "000")
echo "  /openapi.json endpoint: HTTP ${HTTP_CODE}" >> "$API_REPORT"
if [ "$HTTP_CODE" = "200" ]; then
    log_finding "MEDIUM" "API" "OpenAPI spec (/openapi.json) publicly accessible"
fi

# Check error page information disclosure
ERROR_BODY=$(curl -sL "${API_BASE}/nonexistent-endpoint-test-404" 2>/dev/null || echo "")
echo "  404 response body: $(echo "$ERROR_BODY" | head -5)" >> "$API_REPORT"
if echo "$ERROR_BODY" | grep -qi "traceback\|stack trace\|internal server error\|debug"; then
    log_finding "HIGH" "API" "Error pages may disclose debug information"
fi

# Check CORS configuration
CORS_HEADERS=$(curl -sI -H "Origin: https://evil.example.com" "${API_BASE}/api/health" 2>/dev/null || echo "")
if echo "$CORS_HEADERS" | grep -qi "access-control-allow-origin: \*"; then
    log_finding "HIGH" "API" "CORS allows all origins (wildcard)"
    echo "  WARNING: CORS allows wildcard origin" >> "$API_REPORT"
elif echo "$CORS_HEADERS" | grep -qi "access-control-allow-origin: https://evil"; then
    log_finding "CRITICAL" "API" "CORS reflects arbitrary origins"
    echo "  CRITICAL: CORS reflects arbitrary origin" >> "$API_REPORT"
else
    echo "  CORS: Properly restricted" >> "$API_REPORT"
fi

# Check for common sensitive endpoints
SENSITIVE_PATHS=("/admin" "/debug" "/metrics" "/env" "/.env" "/config" "/status" "/actuator")
for path in "${SENSITIVE_PATHS[@]}"; do
    HTTP_CODE=$(curl -sL -o /dev/null -w "%{http_code}" "${API_BASE}${path}" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        log_finding "HIGH" "API" "Sensitive endpoint accessible: ${path} (HTTP 200)"
        echo "  WARNING: ${path} accessible (HTTP ${HTTP_CODE})" >> "$API_REPORT"
    else
        echo "  OK: ${path} (HTTP ${HTTP_CODE})" >> "$API_REPORT"
    fi
done

echo "" >> "$API_REPORT"
echo -e "  ${GREEN}API scan report saved${NC}"

# =============================================================================
# CHECK 5: DNS and Subdomain Enumeration
# =============================================================================
echo -e "${YELLOW}[5/5] Checking DNS configuration...${NC}"
DNS_REPORT="${REPORT_DIR}/dns-report.txt"

BASE_DOMAIN=$(echo "$SENTINEL_DOMAIN" | rev | cut -d. -f1-2 | rev)

echo "--- DNS Configuration: ${BASE_DOMAIN} ---" >> "$DNS_REPORT"

if command -v dig &> /dev/null; then
    # MX records
    echo "MX Records:" >> "$DNS_REPORT"
    dig +short MX "$BASE_DOMAIN" >> "$DNS_REPORT" 2>/dev/null
    echo "" >> "$DNS_REPORT"

    # SPF record check
    echo "SPF Record:" >> "$DNS_REPORT"
    SPF=$(dig +short TXT "$BASE_DOMAIN" 2>/dev/null | grep "v=spf1" || echo "NOT FOUND")
    echo "  ${SPF}" >> "$DNS_REPORT"
    if [ "$SPF" = "NOT FOUND" ]; then
        log_finding "MEDIUM" "DNS" "No SPF record found for ${BASE_DOMAIN}"
    fi

    # DMARC record check
    echo "DMARC Record:" >> "$DNS_REPORT"
    DMARC=$(dig +short TXT "_dmarc.${BASE_DOMAIN}" 2>/dev/null || echo "NOT FOUND")
    echo "  ${DMARC}" >> "$DNS_REPORT"
    if [ -z "$DMARC" ] || [ "$DMARC" = "NOT FOUND" ]; then
        log_finding "MEDIUM" "DNS" "No DMARC record found for ${BASE_DOMAIN}"
    fi

    # DKIM check (common selectors)
    echo "DKIM Records (common selectors):" >> "$DNS_REPORT"
    for selector in default google mail dkim; do
        DKIM=$(dig +short TXT "${selector}._domainkey.${BASE_DOMAIN}" 2>/dev/null || echo "")
        if [ -n "$DKIM" ]; then
            echo "  ${selector}: Found" >> "$DNS_REPORT"
        fi
    done
    echo "" >> "$DNS_REPORT"

    # CAA records
    echo "CAA Records:" >> "$DNS_REPORT"
    CAA=$(dig +short CAA "$BASE_DOMAIN" 2>/dev/null || echo "NOT FOUND")
    if [ -z "$CAA" ]; then
        log_finding "LOW" "DNS" "No CAA records - any CA can issue certificates"
        echo "  NOT FOUND (any CA can issue certificates)" >> "$DNS_REPORT"
    else
        echo "  ${CAA}" >> "$DNS_REPORT"
    fi

    # Check for dangling CNAMEs on known subdomains
    echo "" >> "$DNS_REPORT"
    echo "Subdomain CNAME check (dangling DNS detection):" >> "$DNS_REPORT"
    for sub in www api app mail staging dev test; do
        CNAME=$(dig +short CNAME "${sub}.${BASE_DOMAIN}" 2>/dev/null || echo "")
        if [ -n "$CNAME" ]; then
            # Check if CNAME target resolves
            TARGET_IP=$(dig +short A "$CNAME" 2>/dev/null || echo "")
            if [ -z "$TARGET_IP" ]; then
                log_finding "HIGH" "DNS" "Dangling CNAME: ${sub}.${BASE_DOMAIN} -> ${CNAME} (target does not resolve)"
                echo "  DANGLING: ${sub}.${BASE_DOMAIN} -> ${CNAME}" >> "$DNS_REPORT"
            else
                echo "  OK: ${sub}.${BASE_DOMAIN} -> ${CNAME}" >> "$DNS_REPORT"
            fi
        fi
    done
else
    echo "WARNING: dig not installed - install with: apt install dnsutils" >> "$DNS_REPORT"
    log_finding "LOW" "DNS" "dig not installed - DNS checks limited"
fi

echo "" >> "$DNS_REPORT"
echo -e "  ${GREEN}DNS report saved${NC}"

# =============================================================================
# SUMMARY
# =============================================================================
echo "" >> "$SUMMARY_FILE"
cat >> "$SUMMARY_FILE" <<EOF

================================================================================
SCAN SUMMARY
================================================================================
Total findings: ${FINDINGS}
  Critical: ${CRITICAL}
  High:     ${HIGH}
  Medium:   ${MEDIUM}
  Low:      ${LOW}

Reports generated:
  - ${REPORT_DIR}/tls-report.txt
  - ${REPORT_DIR}/headers-report.txt
  - ${REPORT_DIR}/port-scan-report.txt
  - ${REPORT_DIR}/api-scan-report.txt
  - ${REPORT_DIR}/dns-report.txt
  - ${REPORT_DIR}/scan-summary.txt

Remediation SLAs:
  Critical: 7 days
  High:     14 days
  Medium:   30 days
  Low:      90 days

Next steps:
  1. Review all findings above
  2. Update remediation tracker: infrastructure/scanning/remediation-tracker.md
  3. Assign remediation tasks per SLA deadlines
  4. Schedule follow-up verification scan

Scan completed: $(date +"%Y-%m-%d %H:%M:%S SAST")
================================================================================
EOF

echo ""
echo -e "${GREEN}=== External Scan Complete ===${NC}"
echo -e "Reports saved to: ${REPORT_DIR}"
echo ""
echo -e "Findings summary:"
echo -e "  Critical: ${RED}${CRITICAL}${NC}"
echo -e "  High:     ${YELLOW}${HIGH}${NC}"
echo -e "  Medium:   ${MEDIUM}"
echo -e "  Low:      ${LOW}"
echo ""
echo -e "Next step: Review findings and update remediation tracker"
