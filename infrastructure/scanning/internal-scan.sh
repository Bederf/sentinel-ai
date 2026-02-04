#!/bin/bash
# =============================================================================
# SENTINEL Internal Infrastructure Vulnerability Scan
# =============================================================================
# Schedule: Quarterly (1st Monday of Jan/Apr/Jul/Oct, via cron)
# Scope:    Contabo VM, Docker containers, databases, configuration
# Domain:   FSR 4.10 - Vulnerability Management
#
# This script covers both SENTINEL and AimTheLaw as they share the Contabo VM.
#
# Prerequisites:
#   - lynis installed (apt install lynis)
#   - trivy installed (see infrastructure/trivy/ or 63-03)
#   - Must run as root or with sudo
#
# Usage:
#   sudo ./internal-scan.sh
#
# =============================================================================

set -euo pipefail

# --- Configuration -----------------------------------------------------------
SCAN_DATE=$(date +%Y-%m-%d)
SCAN_TIME=$(date +%H:%M:%S)
REPORT_DIR="/opt/bms-intelligence/security-reports/internal/${SCAN_DATE}"

# Colour codes for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# --- Argument parsing --------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case $1 in
        --help)
            echo "Usage: sudo $0"
            echo ""
            echo "Runs a comprehensive internal infrastructure vulnerability scan."
            echo "Must be run as root or with sudo for full system access."
            echo ""
            echo "Scan categories:"
            echo "  1. Host security audit (Lynis)"
            echo "  2. Docker security assessment"
            echo "  3. OS patch status"
            echo "  4. User and access audit"
            echo "  5. Service and process audit"
            echo "  6. File permission audit"
            echo "  7. Database security check"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# --- Privilege check ---------------------------------------------------------
if [ "$(id -u)" -ne 0 ]; then
    echo -e "${RED}Error: This script must be run as root or with sudo${NC}"
    echo "Usage: sudo $0"
    exit 1
fi

# --- Setup -------------------------------------------------------------------
mkdir -p "$REPORT_DIR"

# Start report
SUMMARY_FILE="${REPORT_DIR}/scan-summary.txt"
cat > "$SUMMARY_FILE" <<EOF
================================================================================
SENTINEL Internal Infrastructure Vulnerability Scan Report
================================================================================
Date:       ${SCAN_DATE}
Time:       ${SCAN_TIME} SAST
Host:       $(hostname)
OS:         $(lsb_release -ds 2>/dev/null || cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2)
Kernel:     $(uname -r)
Scanner:    $(whoami)
================================================================================

EOF

echo -e "${GREEN}=== SENTINEL Internal Infrastructure Scan - ${SCAN_DATE} ===${NC}"
echo ""

FINDINGS=0
CRITICAL=0
HIGH=0
MEDIUM=0
LOW=0
LYNIS_INDEX="N/A"

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
# CHECK 1: Host Security Audit (Lynis)
# =============================================================================
echo -e "${YELLOW}[1/7] Running host security audit (Lynis)...${NC}"
LYNIS_REPORT="${REPORT_DIR}/lynis-report.dat"

if command -v lynis &> /dev/null; then
    # Run Lynis audit
    lynis audit system --report-file "$LYNIS_REPORT" --log-file "${REPORT_DIR}/lynis.log" \
        --no-colors --quick 2>/dev/null || true

    # Extract hardening index
    if [ -f "$LYNIS_REPORT" ]; then
        LYNIS_INDEX=$(grep "hardening_index=" "$LYNIS_REPORT" 2>/dev/null | cut -d= -f2 || echo "N/A")
        echo "  Hardening Index: ${LYNIS_INDEX}" >> "$SUMMARY_FILE"

        if [ "$LYNIS_INDEX" != "N/A" ] && [ "$LYNIS_INDEX" -lt 50 ] 2>/dev/null; then
            log_finding "CRITICAL" "Lynis" "Hardening index critically low: ${LYNIS_INDEX}/100"
        elif [ "$LYNIS_INDEX" != "N/A" ] && [ "$LYNIS_INDEX" -lt 70 ] 2>/dev/null; then
            log_finding "HIGH" "Lynis" "Hardening index below target: ${LYNIS_INDEX}/100 (target: 70+)"
        fi

        # Extract warnings and suggestions count
        WARNINGS=$(grep -c "^warning\[\]=" "$LYNIS_REPORT" 2>/dev/null || echo "0")
        SUGGESTIONS=$(grep -c "^suggestion\[\]=" "$LYNIS_REPORT" 2>/dev/null || echo "0")
        echo "  Warnings: ${WARNINGS}" >> "$SUMMARY_FILE"
        echo "  Suggestions: ${SUGGESTIONS}" >> "$SUMMARY_FILE"

        # Log critical warnings
        grep "^warning\[\]=" "$LYNIS_REPORT" 2>/dev/null | while IFS= read -r line; do
            WARNING_TEXT=$(echo "$line" | cut -d= -f2 | cut -d\| -f1)
            log_finding "HIGH" "Lynis" "Warning: ${WARNING_TEXT}"
        done
    fi

    echo -e "  ${GREEN}Lynis audit complete (index: ${LYNIS_INDEX})${NC}"
else
    echo "  WARNING: Lynis not installed" >> "$SUMMARY_FILE"
    log_finding "LOW" "Lynis" "Lynis not installed - install with: apt install lynis"
    echo -e "  ${YELLOW}Lynis not installed - skipping${NC}"
fi

# =============================================================================
# CHECK 2: Docker Security Assessment
# =============================================================================
echo -e "${YELLOW}[2/7] Scanning Docker configuration...${NC}"
DOCKER_REPORT="${REPORT_DIR}/docker-security-report.txt"

echo "--- Docker Security Assessment ---" > "$DOCKER_REPORT"

if command -v docker &> /dev/null; then
    # Docker daemon configuration
    echo "" >> "$DOCKER_REPORT"
    echo "Docker Daemon Configuration:" >> "$DOCKER_REPORT"
    DOCKER_INFO=$(docker info 2>/dev/null || echo "FAILED")

    if [ "$DOCKER_INFO" != "FAILED" ]; then
        # Check if live restore is enabled
        if echo "$DOCKER_INFO" | grep -q "Live Restore Enabled: true"; then
            echo "  OK: Live Restore enabled" >> "$DOCKER_REPORT"
        else
            log_finding "LOW" "Docker" "Live Restore not enabled"
            echo "  NOTE: Live Restore not enabled" >> "$DOCKER_REPORT"
        fi

        # Check Docker version
        DOCKER_VERSION=$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo "unknown")
        echo "  Docker version: ${DOCKER_VERSION}" >> "$DOCKER_REPORT"
    fi

    # Container privilege audit
    echo "" >> "$DOCKER_REPORT"
    echo "Container Privilege Audit:" >> "$DOCKER_REPORT"

    docker ps --format '{{.Names}}' 2>/dev/null | while IFS= read -r container; do
        [ -z "$container" ] && continue

        # Check privileged mode
        PRIVILEGED=$(docker inspect --format '{{.HostConfig.Privileged}}' "$container" 2>/dev/null || echo "unknown")
        if [ "$PRIVILEGED" = "true" ]; then
            log_finding "HIGH" "Docker" "Container '${container}' running in privileged mode"
            echo "  WARNING: ${container} - PRIVILEGED" >> "$DOCKER_REPORT"
        fi

        # Check if running as root
        USER=$(docker inspect --format '{{.Config.User}}' "$container" 2>/dev/null || echo "")
        if [ -z "$USER" ] || [ "$USER" = "root" ] || [ "$USER" = "0" ]; then
            log_finding "MEDIUM" "Docker" "Container '${container}' running as root"
            echo "  NOTE: ${container} - runs as root (user: '${USER:-not set}')" >> "$DOCKER_REPORT"
        else
            echo "  OK: ${container} - runs as user '${USER}'" >> "$DOCKER_REPORT"
        fi

        # Check host network mode
        NETWORK_MODE=$(docker inspect --format '{{.HostConfig.NetworkMode}}' "$container" 2>/dev/null || echo "")
        if [ "$NETWORK_MODE" = "host" ]; then
            log_finding "MEDIUM" "Docker" "Container '${container}' uses host network mode"
            echo "  NOTE: ${container} - host network mode" >> "$DOCKER_REPORT"
        fi

        # Check mounted volumes for sensitive paths
        MOUNTS=$(docker inspect --format '{{range .Mounts}}{{.Source}}:{{.Destination}} {{end}}' "$container" 2>/dev/null || echo "")
        for mount in $MOUNTS; do
            SRC=$(echo "$mount" | cut -d: -f1)
            if echo "$SRC" | grep -qE "^/(etc|root|var/run/docker.sock)"; then
                log_finding "MEDIUM" "Docker" "Container '${container}' mounts sensitive path: ${SRC}"
                echo "  NOTE: ${container} - mounts ${SRC}" >> "$DOCKER_REPORT"
            fi
        done
    done

    # Container image scanning with Trivy
    echo "" >> "$DOCKER_REPORT"
    echo "Container Image Vulnerability Scan:" >> "$DOCKER_REPORT"

    if command -v trivy &> /dev/null; then
        docker ps --format '{{.Image}}' 2>/dev/null | sort -u | while IFS= read -r image; do
            [ -z "$image" ] && continue
            echo "  Scanning: ${image}" >> "$DOCKER_REPORT"

            TRIVY_OUTPUT=$(trivy image --severity HIGH,CRITICAL --no-progress \
                --format table "$image" 2>/dev/null || echo "SCAN FAILED")
            echo "$TRIVY_OUTPUT" >> "${REPORT_DIR}/trivy-${image//\//-}.txt" 2>/dev/null

            CRIT_COUNT=$(echo "$TRIVY_OUTPUT" | grep -c "CRITICAL" 2>/dev/null || echo "0")
            HIGH_COUNT=$(echo "$TRIVY_OUTPUT" | grep -c "HIGH" 2>/dev/null || echo "0")

            if [ "$CRIT_COUNT" -gt 0 ] 2>/dev/null; then
                log_finding "CRITICAL" "Docker" "Image '${image}' has ${CRIT_COUNT} CRITICAL vulnerabilities"
            fi
            if [ "$HIGH_COUNT" -gt 0 ] 2>/dev/null; then
                log_finding "HIGH" "Docker" "Image '${image}' has ${HIGH_COUNT} HIGH vulnerabilities"
            fi

            echo "    Critical: ${CRIT_COUNT}, High: ${HIGH_COUNT}" >> "$DOCKER_REPORT"
        done
    else
        echo "  WARNING: Trivy not installed - image scanning skipped" >> "$DOCKER_REPORT"
        log_finding "MEDIUM" "Docker" "Trivy not installed - container image scanning skipped"
    fi

    echo -e "  ${GREEN}Docker security report saved${NC}"
else
    echo "Docker not installed or not accessible" >> "$DOCKER_REPORT"
    echo -e "  ${YELLOW}Docker not available - skipping${NC}"
fi

# =============================================================================
# CHECK 3: OS Patch Status
# =============================================================================
echo -e "${YELLOW}[3/7] Checking OS patch status...${NC}"
PATCH_REPORT="${REPORT_DIR}/patch-status-report.txt"

echo "--- OS Patch Status ---" > "$PATCH_REPORT"
echo "Date: ${SCAN_DATE}" >> "$PATCH_REPORT"
echo "" >> "$PATCH_REPORT"

# Check for available updates
if command -v apt &> /dev/null; then
    apt update -qq 2>/dev/null || true

    # All upgradable packages
    UPGRADABLE=$(apt list --upgradable 2>/dev/null | grep -v "^Listing" || true)
    UPGRADE_COUNT=$(echo "$UPGRADABLE" | grep -c "." 2>/dev/null || echo "0")

    echo "Upgradable packages: ${UPGRADE_COUNT}" >> "$PATCH_REPORT"
    echo "" >> "$PATCH_REPORT"

    if [ -n "$UPGRADABLE" ]; then
        echo "Packages available for upgrade:" >> "$PATCH_REPORT"
        echo "$UPGRADABLE" >> "$PATCH_REPORT"
        echo "" >> "$PATCH_REPORT"
    fi

    # Security-specific updates
    SECURITY_UPDATES=$(echo "$UPGRADABLE" | grep -i "security" 2>/dev/null || true)
    SECURITY_COUNT=$(echo "$SECURITY_UPDATES" | grep -c "." 2>/dev/null || echo "0")

    echo "Security updates: ${SECURITY_COUNT}" >> "$PATCH_REPORT"

    if [ "$SECURITY_COUNT" -gt 0 ] 2>/dev/null; then
        log_finding "HIGH" "Patches" "${SECURITY_COUNT} security updates pending"
        echo "$SECURITY_UPDATES" >> "$PATCH_REPORT"
    fi

    if [ "$UPGRADE_COUNT" -gt 20 ] 2>/dev/null; then
        log_finding "MEDIUM" "Patches" "${UPGRADE_COUNT} total packages pending upgrade"
    fi

    # Check last update timestamp
    if [ -f /var/log/apt/history.log ]; then
        LAST_UPDATE=$(grep "Start-Date:" /var/log/apt/history.log 2>/dev/null | tail -1 | cut -d: -f2- | xargs)
        echo "" >> "$PATCH_REPORT"
        echo "Last apt operation: ${LAST_UPDATE:-unknown}" >> "$PATCH_REPORT"
    fi

    # Check if unattended-upgrades is configured
    echo "" >> "$PATCH_REPORT"
    if dpkg -l | grep -q unattended-upgrades 2>/dev/null; then
        echo "Unattended-upgrades: installed" >> "$PATCH_REPORT"
    else
        log_finding "MEDIUM" "Patches" "unattended-upgrades not installed"
        echo "Unattended-upgrades: NOT installed (recommended)" >> "$PATCH_REPORT"
    fi
fi

echo -e "  ${GREEN}Patch status report saved${NC}"

# =============================================================================
# CHECK 4: User and Access Audit
# =============================================================================
echo -e "${YELLOW}[4/7] Auditing user accounts and access...${NC}"
ACCESS_REPORT="${REPORT_DIR}/access-audit-report.txt"

echo "--- User and Access Audit ---" > "$ACCESS_REPORT"
echo "" >> "$ACCESS_REPORT"

# Users with shell access
echo "Users with login shell:" >> "$ACCESS_REPORT"
SHELL_USERS=$(grep -v '/nologin\|/false\|/sync' /etc/passwd | grep -v '^#' || true)
echo "$SHELL_USERS" >> "$ACCESS_REPORT"
SHELL_USER_COUNT=$(echo "$SHELL_USERS" | grep -c "." 2>/dev/null || echo "0")
echo "  Count: ${SHELL_USER_COUNT}" >> "$ACCESS_REPORT"
echo "" >> "$ACCESS_REPORT"

# Users without passwords
echo "Users without passwords:" >> "$ACCESS_REPORT"
NOPASS=$(awk -F: '($2 == "" || $2 == "!") {print $1}' /etc/shadow 2>/dev/null || true)
if [ -n "$NOPASS" ]; then
    echo "$NOPASS" >> "$ACCESS_REPORT"
    # Only flag non-system accounts
    while IFS= read -r user; do
        UID_NUM=$(id -u "$user" 2>/dev/null || echo "0")
        if [ "$UID_NUM" -ge 1000 ] 2>/dev/null; then
            log_finding "CRITICAL" "Access" "User '${user}' has no password set"
        fi
    done <<< "$NOPASS"
else
    echo "  None found" >> "$ACCESS_REPORT"
fi
echo "" >> "$ACCESS_REPORT"

# Sudo group membership
echo "Sudo/admin group members:" >> "$ACCESS_REPORT"
SUDO_USERS=$(getent group sudo 2>/dev/null | cut -d: -f4 || echo "")
echo "  sudo: ${SUDO_USERS:-none}" >> "$ACCESS_REPORT"
ADMIN_USERS=$(getent group admin 2>/dev/null | cut -d: -f4 || echo "")
echo "  admin: ${ADMIN_USERS:-none}" >> "$ACCESS_REPORT"
echo "" >> "$ACCESS_REPORT"

# SSH authorized_keys audit
echo "SSH authorized_keys:" >> "$ACCESS_REPORT"
for user_home in /home/* /root; do
    user=$(basename "$user_home")
    AUTH_FILE="${user_home}/.ssh/authorized_keys"
    if [ -f "$AUTH_FILE" ]; then
        KEY_COUNT=$(grep -c "^ssh-" "$AUTH_FILE" 2>/dev/null || echo "0")
        echo "  ${user}: ${KEY_COUNT} keys" >> "$ACCESS_REPORT"

        # Check for keys without comments (harder to identify)
        UNCOMMENTED=$(grep "^ssh-" "$AUTH_FILE" 2>/dev/null | grep -cv "@" 2>/dev/null || echo "0")
        if [ "$UNCOMMENTED" -gt 0 ] 2>/dev/null; then
            log_finding "LOW" "Access" "User '${user}' has ${UNCOMMENTED} SSH keys without identifying comments"
        fi
    fi
done
echo "" >> "$ACCESS_REPORT"

# Check for stale accounts (no login in 90+ days)
echo "Account activity (last login):" >> "$ACCESS_REPORT"
STALE_DAYS=90
while IFS=: read -r user _ uid _ _ home _; do
    [ "$uid" -lt 1000 ] 2>/dev/null && continue
    LASTLOG=$(lastlog -u "$user" 2>/dev/null | tail -1 || echo "")
    if echo "$LASTLOG" | grep -q "Never logged in"; then
        echo "  ${user}: Never logged in" >> "$ACCESS_REPORT"
        log_finding "LOW" "Access" "User '${user}' has never logged in - consider removing"
    fi
done < /etc/passwd

echo "" >> "$ACCESS_REPORT"

# Check /etc/sudoers for NOPASSWD
echo "NOPASSWD sudo entries:" >> "$ACCESS_REPORT"
NOPASSWD=$(grep -r "NOPASSWD" /etc/sudoers /etc/sudoers.d/ 2>/dev/null | grep -v "^#" || true)
if [ -n "$NOPASSWD" ]; then
    echo "$NOPASSWD" >> "$ACCESS_REPORT"
    log_finding "MEDIUM" "Access" "NOPASSWD sudo entries found - review for least privilege"
else
    echo "  None found" >> "$ACCESS_REPORT"
fi

echo -e "  ${GREEN}Access audit report saved${NC}"

# =============================================================================
# CHECK 5: Service and Process Audit
# =============================================================================
echo -e "${YELLOW}[5/7] Auditing running services...${NC}"
SERVICE_REPORT="${REPORT_DIR}/service-audit-report.txt"

echo "--- Service and Process Audit ---" > "$SERVICE_REPORT"
echo "" >> "$SERVICE_REPORT"

# All listening services
echo "Listening services:" >> "$SERVICE_REPORT"
ss -tlnp 2>/dev/null >> "$SERVICE_REPORT" || netstat -tlnp 2>/dev/null >> "$SERVICE_REPORT" || true
echo "" >> "$SERVICE_REPORT"

# Check for services listening on all interfaces (0.0.0.0)
echo "Services on all interfaces (0.0.0.0):" >> "$SERVICE_REPORT"
EXPOSED_SERVICES=$(ss -tlnp 2>/dev/null | grep "0.0.0.0:" | grep -v "127.0.0.1" || true)
if [ -n "$EXPOSED_SERVICES" ]; then
    echo "$EXPOSED_SERVICES" >> "$SERVICE_REPORT"

    # Flag database services exposed on all interfaces
    if echo "$EXPOSED_SERVICES" | grep -q ":5432 \|:3306 \|:27017 \|:6379 "; then
        log_finding "CRITICAL" "Services" "Database service listening on all interfaces (0.0.0.0)"
    fi

    # Flag application services exposed directly (should be behind Cloudflare)
    if echo "$EXPOSED_SERVICES" | grep -q ":9095 \|:9096 \|:3000 \|:8080 "; then
        log_finding "HIGH" "Services" "Application service exposed on all interfaces (should use localhost + Cloudflare Tunnel)"
    fi
else
    echo "  None - all services properly bound" >> "$SERVICE_REPORT"
fi
echo "" >> "$SERVICE_REPORT"

# Check for unexpected services
echo "Running Docker containers:" >> "$SERVICE_REPORT"
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null >> "$SERVICE_REPORT" || true
echo "" >> "$SERVICE_REPORT"

# Check systemd services
echo "Enabled systemd services:" >> "$SERVICE_REPORT"
systemctl list-unit-files --type=service --state=enabled 2>/dev/null | head -50 >> "$SERVICE_REPORT" || true

echo -e "  ${GREEN}Service audit report saved${NC}"

# =============================================================================
# CHECK 6: File Permission Audit
# =============================================================================
echo -e "${YELLOW}[6/7] Checking file permissions...${NC}"
PERMS_REPORT="${REPORT_DIR}/permissions-report.txt"

echo "--- File Permission Audit ---" > "$PERMS_REPORT"
echo "" >> "$PERMS_REPORT"

# Check .env files
echo "Environment files:" >> "$PERMS_REPORT"
ENV_FILES=$(find /opt/bms-intelligence /opt/aimthelaw -name ".env*" -type f 2>/dev/null || true)
if [ -n "$ENV_FILES" ]; then
    while IFS= read -r env_file; do
        PERMS=$(stat -c "%a %U:%G" "$env_file" 2>/dev/null || echo "unknown")
        echo "  ${env_file}: ${PERMS}" >> "$PERMS_REPORT"

        # Check if world-readable
        WORLD_READ=$(stat -c "%a" "$env_file" 2>/dev/null || echo "000")
        if [ "${WORLD_READ: -1}" -gt 0 ] 2>/dev/null; then
            log_finding "HIGH" "Permissions" ".env file world-readable: ${env_file} (${WORLD_READ})"
        fi
    done <<< "$ENV_FILES"
else
    echo "  No .env files found" >> "$PERMS_REPORT"
fi
echo "" >> "$PERMS_REPORT"

# Check SSH key permissions
echo "SSH key permissions:" >> "$PERMS_REPORT"
for user_home in /home/* /root; do
    SSH_DIR="${user_home}/.ssh"
    if [ -d "$SSH_DIR" ]; then
        DIR_PERMS=$(stat -c "%a" "$SSH_DIR" 2>/dev/null || echo "unknown")
        echo "  ${SSH_DIR}: ${DIR_PERMS}" >> "$PERMS_REPORT"
        if [ "$DIR_PERMS" != "700" ] && [ "$DIR_PERMS" != "unknown" ]; then
            log_finding "HIGH" "Permissions" "SSH directory wrong permissions: ${SSH_DIR} (${DIR_PERMS}, should be 700)"
        fi

        # Check private keys
        find "$SSH_DIR" -name "id_*" ! -name "*.pub" -type f 2>/dev/null | while IFS= read -r key; do
            KEY_PERMS=$(stat -c "%a" "$key" 2>/dev/null || echo "unknown")
            echo "    ${key}: ${KEY_PERMS}" >> "$PERMS_REPORT"
            if [ "$KEY_PERMS" != "600" ] && [ "$KEY_PERMS" != "unknown" ]; then
                log_finding "HIGH" "Permissions" "SSH private key wrong permissions: ${key} (${KEY_PERMS}, should be 600)"
            fi
        done
    fi
done
echo "" >> "$PERMS_REPORT"

# Check Docker socket permissions
echo "Docker socket:" >> "$PERMS_REPORT"
if [ -S /var/run/docker.sock ]; then
    DOCKER_SOCK_PERMS=$(stat -c "%a %U:%G" /var/run/docker.sock 2>/dev/null || echo "unknown")
    echo "  /var/run/docker.sock: ${DOCKER_SOCK_PERMS}" >> "$PERMS_REPORT"

    # Check if group is docker (expected) vs world-accessible
    DOCKER_SOCK_OTHER=$(stat -c "%a" /var/run/docker.sock 2>/dev/null || echo "000")
    if [ "${DOCKER_SOCK_OTHER: -1}" -gt 0 ] 2>/dev/null; then
        log_finding "CRITICAL" "Permissions" "Docker socket is world-accessible"
    fi
else
    echo "  Docker socket not found (normal if using rootless Docker)" >> "$PERMS_REPORT"
fi
echo "" >> "$PERMS_REPORT"

# SUID/SGID binaries
echo "SUID/SGID binaries (non-standard):" >> "$PERMS_REPORT"
EXPECTED_SUID="/usr/bin/passwd /usr/bin/sudo /usr/bin/su /usr/bin/newgrp /usr/bin/chsh /usr/bin/chfn /usr/bin/gpasswd /usr/bin/mount /usr/bin/umount /usr/lib/openssh/ssh-keysign /usr/lib/dbus-1.0/dbus-daemon-launch-helper"

SUID_FILES=$(find / -type f \( -perm -4000 -o -perm -2000 \) -print 2>/dev/null | head -50 || true)
UNEXPECTED_SUID=""
while IFS= read -r suid_file; do
    [ -z "$suid_file" ] && continue
    if ! echo "$EXPECTED_SUID" | grep -q "$suid_file"; then
        UNEXPECTED_SUID="${UNEXPECTED_SUID}${suid_file}\n"
        echo "  UNEXPECTED: ${suid_file}" >> "$PERMS_REPORT"
    fi
done <<< "$SUID_FILES"

if [ -z "$UNEXPECTED_SUID" ]; then
    echo "  All SUID/SGID binaries are from expected set" >> "$PERMS_REPORT"
else
    UNEXPECTED_COUNT=$(echo -e "$UNEXPECTED_SUID" | grep -c "." 2>/dev/null || echo "0")
    log_finding "MEDIUM" "Permissions" "${UNEXPECTED_COUNT} unexpected SUID/SGID binaries found"
fi

echo -e "  ${GREEN}Permission audit report saved${NC}"

# =============================================================================
# CHECK 7: Database Security Check
# =============================================================================
echo -e "${YELLOW}[7/7] Checking database security...${NC}"
DB_REPORT="${REPORT_DIR}/database-security-report.txt"

echo "--- Database Security Check ---" > "$DB_REPORT"
echo "" >> "$DB_REPORT"

# Supabase/PostgreSQL connection check
echo "PostgreSQL/Supabase:" >> "$DB_REPORT"

# Check if DATABASE_URL is configured
SENTINEL_ENV="/opt/bms-intelligence/backend/.env"
if [ -f "$SENTINEL_ENV" ]; then
    # Check if SSL is used in connection string
    DB_URL=$(grep "^DATABASE_URL=" "$SENTINEL_ENV" 2>/dev/null | cut -d= -f2- || echo "")
    SUPABASE_URL=$(grep "^SUPABASE_URL=" "$SENTINEL_ENV" 2>/dev/null | cut -d= -f2- || echo "")

    if [ -n "$DB_URL" ]; then
        if echo "$DB_URL" | grep -qi "sslmode=require\|sslmode=verify"; then
            echo "  DATABASE_URL: SSL enforced" >> "$DB_REPORT"
        elif echo "$DB_URL" | grep -qi "sslmode=disable\|sslmode=prefer"; then
            log_finding "HIGH" "Database" "DATABASE_URL does not enforce SSL"
            echo "  WARNING: DATABASE_URL SSL not enforced" >> "$DB_REPORT"
        else
            log_finding "MEDIUM" "Database" "DATABASE_URL SSL mode not explicitly set"
            echo "  NOTE: DATABASE_URL SSL mode not explicit" >> "$DB_REPORT"
        fi
    else
        echo "  DATABASE_URL: Not configured (using JSON fallback)" >> "$DB_REPORT"
    fi

    if [ -n "$SUPABASE_URL" ]; then
        if echo "$SUPABASE_URL" | grep -qi "https://"; then
            echo "  SUPABASE_URL: Uses HTTPS" >> "$DB_REPORT"
        else
            log_finding "HIGH" "Database" "SUPABASE_URL does not use HTTPS"
        fi
    fi

    # Check for default/weak credentials patterns
    if grep -qi "password=postgres\|password=admin\|password=password\|password=12345" "$SENTINEL_ENV" 2>/dev/null; then
        log_finding "CRITICAL" "Database" "Default/weak database credentials detected in .env"
        echo "  CRITICAL: Default credentials in .env" >> "$DB_REPORT"
    else
        echo "  Credentials: No obvious defaults detected" >> "$DB_REPORT"
    fi

    # Check API key exposure
    ANTHROPIC_KEY=$(grep "^ANTHROPIC_API_KEY=" "$SENTINEL_ENV" 2>/dev/null | cut -d= -f2- || echo "")
    if [ -n "$ANTHROPIC_KEY" ] && [ "$ANTHROPIC_KEY" != "sk-placeholder" ]; then
        # Check .env file permissions
        ENV_PERMS=$(stat -c "%a" "$SENTINEL_ENV" 2>/dev/null || echo "unknown")
        if [ "$ENV_PERMS" != "600" ] && [ "$ENV_PERMS" != "640" ]; then
            log_finding "HIGH" "Database" "Backend .env with API keys has loose permissions (${ENV_PERMS})"
        fi
    fi
else
    echo "  Backend .env not found" >> "$DB_REPORT"
fi
echo "" >> "$DB_REPORT"

# Check InfluxDB security
echo "InfluxDB:" >> "$DB_REPORT"
if docker ps 2>/dev/null | grep -q influxdb; then
    echo "  InfluxDB container: running" >> "$DB_REPORT"

    # Check if InfluxDB is exposed on all interfaces
    INFLUX_PORT=$(ss -tlnp 2>/dev/null | grep ":8086 " || true)
    if echo "$INFLUX_PORT" | grep -q "0.0.0.0"; then
        log_finding "HIGH" "Database" "InfluxDB exposed on all interfaces (0.0.0.0:8086)"
        echo "  WARNING: Exposed on all interfaces" >> "$DB_REPORT"
    else
        echo "  Binding: Properly restricted" >> "$DB_REPORT"
    fi
else
    echo "  InfluxDB: not running" >> "$DB_REPORT"
fi
echo "" >> "$DB_REPORT"

# Check Redis security (if running)
echo "Redis:" >> "$DB_REPORT"
if docker ps 2>/dev/null | grep -q redis; then
    REDIS_PORT=$(ss -tlnp 2>/dev/null | grep ":6379 " || true)
    if echo "$REDIS_PORT" | grep -q "0.0.0.0"; then
        log_finding "CRITICAL" "Database" "Redis exposed on all interfaces without authentication"
        echo "  CRITICAL: Exposed on all interfaces" >> "$DB_REPORT"
    else
        echo "  Binding: Properly restricted" >> "$DB_REPORT"
    fi
else
    echo "  Redis: not running" >> "$DB_REPORT"
fi

echo -e "  ${GREEN}Database security report saved${NC}"

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

Lynis Hardening Index: ${LYNIS_INDEX}/100

Reports generated:
  - ${REPORT_DIR}/lynis-report.dat
  - ${REPORT_DIR}/docker-security-report.txt
  - ${REPORT_DIR}/patch-status-report.txt
  - ${REPORT_DIR}/access-audit-report.txt
  - ${REPORT_DIR}/service-audit-report.txt
  - ${REPORT_DIR}/permissions-report.txt
  - ${REPORT_DIR}/database-security-report.txt
  - ${REPORT_DIR}/scan-summary.txt

Remediation SLAs:
  Critical: 7 days
  High:     14 days
  Medium:   30 days
  Low:      90 days

Comparison with previous quarter:
  Check: /opt/bms-intelligence/security-reports/internal/
  Compare findings counts and hardening index trend

Next steps:
  1. Review all findings above
  2. Update remediation tracker: infrastructure/scanning/remediation-tracker.md
  3. Assign remediation tasks per SLA deadlines
  4. Compare with previous quarter results
  5. Schedule follow-up verification for critical/high items

Scan completed: $(date +"%Y-%m-%d %H:%M:%S SAST")
================================================================================
EOF

echo ""
echo -e "${GREEN}=== Internal Scan Complete ===${NC}"
echo -e "Reports saved to: ${REPORT_DIR}"
echo -e "Hardening Index: ${LYNIS_INDEX}/100"
echo ""
echo -e "Findings summary:"
echo -e "  Critical: ${RED}${CRITICAL}${NC}"
echo -e "  High:     ${YELLOW}${HIGH}${NC}"
echo -e "  Medium:   ${MEDIUM}"
echo -e "  Low:      ${LOW}"
echo ""
echo -e "Next step: Review findings, update remediation tracker, compare with previous quarter"
