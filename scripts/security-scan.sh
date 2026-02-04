#!/bin/bash
# =============================================================================
# SENTINEL Security Scan - Local Development
# =============================================================================
#
# Runs all security checks locally without needing GitHub Actions.
# This is the same set of checks that run in the CI/CD pipeline.
#
# Usage:
#   ./scripts/security-scan.sh           # Run all scans
#   ./scripts/security-scan.sh --quick   # Skip container scan (faster)
#
# Prerequisites:
#   - Python 3.11+ with pip
#   - Node.js 18+ with npm
#   - Trivy (optional, for container scanning)
#   - Docker (optional, for container scanning)
#
# Addresses FSR domains:
#   4.9  Application Security
#   4.10 Vulnerability Management
# =============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Track results
PASSED=0
WARNED=0
FAILED=0

# Find project root (parent of scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo -e "${BLUE}=============================================${NC}"
echo -e "${BLUE}  SENTINEL Security Scan - Local Development ${NC}"
echo -e "${BLUE}=============================================${NC}"
echo ""
echo "Project root: $PROJECT_ROOT"
echo "Date: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# Parse arguments
QUICK_MODE=false
if [ "${1:-}" = "--quick" ]; then
    QUICK_MODE=true
    echo -e "${YELLOW}Quick mode: skipping container scan${NC}"
    echo ""
fi

# -------------------------------------------------------------------------
# 1. Python SAST (Bandit)
# -------------------------------------------------------------------------
echo -e "${BLUE}[1/5] Running Python SAST (Bandit)...${NC}"
echo "----------------------------------------------"

if ! command -v bandit &>/dev/null; then
    pip install -q bandit 2>/dev/null
fi

if bandit -r "$PROJECT_ROOT/backend/app/" \
    -f screen \
    --severity-level medium \
    --confidence-level medium \
    -x "$PROJECT_ROOT/backend/app/data" \
    2>/dev/null; then
    echo -e "${GREEN}  PASSED: No medium+ severity findings${NC}"
    ((PASSED++))
else
    BANDIT_EXIT=$?
    if [ $BANDIT_EXIT -eq 1 ]; then
        echo -e "${YELLOW}  WARNING: Bandit found security findings (review above)${NC}"
        ((WARNED++))
    else
        echo -e "${RED}  FAILED: Bandit scan encountered errors${NC}"
        ((FAILED++))
    fi
fi
echo ""

# -------------------------------------------------------------------------
# 2. Python Dependency Audit (pip-audit)
# -------------------------------------------------------------------------
echo -e "${BLUE}[2/5] Running Python dependency audit (pip-audit)...${NC}"
echo "----------------------------------------------"

if ! command -v pip-audit &>/dev/null; then
    pip install -q pip-audit 2>/dev/null
fi

if pip-audit -r "$PROJECT_ROOT/backend/requirements.txt" 2>/dev/null; then
    echo -e "${GREEN}  PASSED: No known vulnerabilities in Python dependencies${NC}"
    ((PASSED++))
else
    echo -e "${YELLOW}  WARNING: Vulnerabilities found in Python dependencies${NC}"
    ((WARNED++))
fi
echo ""

# -------------------------------------------------------------------------
# 3. Container Scan (Trivy)
# -------------------------------------------------------------------------
echo -e "${BLUE}[3/5] Running container/filesystem scan (Trivy)...${NC}"
echo "----------------------------------------------"

if [ "$QUICK_MODE" = true ]; then
    echo -e "${YELLOW}  SKIPPED: Quick mode enabled${NC}"
elif ! command -v trivy &>/dev/null; then
    echo -e "${YELLOW}  SKIPPED: Trivy not installed${NC}"
    echo "  Install: https://aquasecurity.github.io/trivy/latest/getting-started/installation/"
    echo "  Or: curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin"
else
    if trivy fs \
        --config "$PROJECT_ROOT/infrastructure/trivy/trivy.yaml" \
        --severity CRITICAL,HIGH \
        "$PROJECT_ROOT/backend/" 2>/dev/null; then
        echo -e "${GREEN}  PASSED: No critical/high vulnerabilities found${NC}"
        ((PASSED++))
    else
        echo -e "${YELLOW}  WARNING: Trivy found vulnerabilities${NC}"
        ((WARNED++))
    fi
fi
echo ""

# -------------------------------------------------------------------------
# 4. Secrets Scan
# -------------------------------------------------------------------------
echo -e "${BLUE}[4/5] Scanning for hardcoded secrets...${NC}"
echo "----------------------------------------------"

SECRET_FOUND=false

# Check for common secret patterns in Python files
PATTERNS=(
    'ANTHROPIC_API_KEY\s*=\s*["\x27]sk-'
    'SUPABASE_KEY\s*=\s*["\x27]eyJ'
    'password\s*=\s*["\x27][^"\x27]{8,}'
    'api_key\s*=\s*["\x27][A-Za-z0-9]{20,}'
    'secret\s*=\s*["\x27][A-Za-z0-9]{20,}'
    'token\s*=\s*["\x27][A-Za-z0-9]{20,}'
)

for pattern in "${PATTERNS[@]}"; do
    # Search Python files, excluding config/settings and .env references
    MATCHES=$(grep -rnE "$pattern" \
        "$PROJECT_ROOT/backend/app/" \
        --include="*.py" \
        2>/dev/null \
        | grep -v '\.env\|settings\.\|config\.\|example\|demo\|mock\|test\|#.*\|os\.environ\|os\.getenv\|environ\.get' \
        || true)

    if [ -n "$MATCHES" ]; then
        echo -e "${RED}  Potential secret found:${NC}"
        echo "$MATCHES"
        SECRET_FOUND=true
    fi
done

# Check for .env files that might be committed
ENV_FILES=$(find "$PROJECT_ROOT" -name ".env" -not -path "*/.git/*" -not -path "*/node_modules/*" -not -path "*/venv/*" 2>/dev/null || true)
if [ -n "$ENV_FILES" ]; then
    # Check if any .env files are tracked by git
    for env_file in $ENV_FILES; do
        if git -C "$PROJECT_ROOT" ls-files --error-unmatch "$env_file" &>/dev/null; then
            echo -e "${YELLOW}  WARNING: .env file tracked by git: $env_file${NC}"
            SECRET_FOUND=true
        fi
    done
fi

if [ "$SECRET_FOUND" = false ]; then
    echo -e "${GREEN}  PASSED: No hardcoded secrets detected${NC}"
    ((PASSED++))
else
    echo -e "${RED}  FAILED: Potential secrets found - review above${NC}"
    ((FAILED++))
fi
echo ""

# -------------------------------------------------------------------------
# 5. Frontend Dependency Audit (npm audit)
# -------------------------------------------------------------------------
echo -e "${BLUE}[5/5] Running frontend dependency audit (npm audit)...${NC}"
echo "----------------------------------------------"

if [ -d "$PROJECT_ROOT/frontend" ] && [ -f "$PROJECT_ROOT/frontend/package.json" ]; then
    cd "$PROJECT_ROOT/frontend"
    if npm audit --audit-level=high 2>/dev/null; then
        echo -e "${GREEN}  PASSED: No high+ vulnerabilities in frontend dependencies${NC}"
        ((PASSED++))
    else
        echo -e "${YELLOW}  WARNING: Vulnerabilities found in frontend dependencies${NC}"
        ((WARNED++))
    fi
    cd "$PROJECT_ROOT"
else
    echo -e "${YELLOW}  SKIPPED: No frontend directory found${NC}"
fi
echo ""

# -------------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------------
echo -e "${BLUE}=============================================${NC}"
echo -e "${BLUE}  Scan Summary${NC}"
echo -e "${BLUE}=============================================${NC}"
echo ""
echo -e "  ${GREEN}Passed:  $PASSED${NC}"
echo -e "  ${YELLOW}Warnings: $WARNED${NC}"
echo -e "  ${RED}Failed:  $FAILED${NC}"
echo ""

if [ "$FAILED" -gt 0 ]; then
    echo -e "${RED}Security scan completed with failures. Review findings above.${NC}"
    echo ""
    echo "Remediation SLAs:"
    echo "  Critical: 7 days  | High: 14 days | Medium: 30 days"
    exit 1
elif [ "$WARNED" -gt 0 ]; then
    echo -e "${YELLOW}Security scan completed with warnings. Review recommended.${NC}"
    exit 0
else
    echo -e "${GREEN}All security checks passed.${NC}"
    exit 0
fi
