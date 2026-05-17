#!/bin/bash
# =============================================================================
# SENTINEL BMS — Environment Configuration Setup
# =============================================================================
# Interactive script to configure the .env file for production deployment
#
# Usage:
#   ./scripts/setup-env.sh
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_ROOT/backend/.env"

echo "=========================================="
echo "  SENTINEL BMS Environment Setup"
echo "=========================================="
echo ""

# Check if .env already exists
if [[ -f "$ENV_FILE" ]]; then
    log_warn "An .env file already exists at $ENV_FILE"
    read -p "Do you want to backup and create a new one? (y/N): " backup_choice
    if [[ $backup_choice =~ ^[Yy]$ ]]; then
        cp "$ENV_FILE" "$ENV_FILE.backup.$(date +%Y%m%d%H%M%S)"
        log_info "Backup created"
    else
        log_info "Keeping existing .env file"
        exit 0
    fi
fi

# Create .env from example
if [[ -f "$PROJECT_ROOT/backend/.env.example" ]]; then
    cp "$PROJECT_ROOT/backend/.env.example" "$ENV_FILE"
else
    log_error "Cannot find .env.example file"
    exit 1
fi

# Helper function to update env variable
update_env() {
    local key="$1"
    local value="$2"
    # Escape special characters for sed
    value=$(echo "$value" | sed 's/[&/\]/\\&/g')
    if grep -q "^${key}=" "$ENV_FILE"; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
    else
        echo "${key}=${value}" >> "$ENV_FILE"
    fi
}

echo ""
echo "Section 1: Basic Configuration"
echo "------------------------------"

# Domain
read -p "Enter your domain name (e.g., bms.sentinel-ai.co.za): " domain
update_env "BACKEND_URL" "https://${domain}"
update_env "FRONTEND_URL" "https://${domain}"
update_env "CORS_ORIGINS" "[\"https://${domain}\"]"

# Environment
update_env "ENVIRONMENT" "production"
update_env "DEBUG" "false"
update_env "DEMO_MODE" "false"

# Site configuration
read -p "Enter site ID (default: site-002): " site_id
site_id=${site_id:-site-002}
update_env "SITE_ID" "$site_id"

read -p "Enter plant site ID (default: FLN02): " plant_site_id
plant_site_id=${plant_site_id:-FLN02}
update_env "PLANT_SITE_ID" "$plant_site_id"

read -p "Enter building name (default: Fairland 2): " building_name
building_name=${building_name:-Fairland 2}
update_env "BUILDING_NAME" "$building_name"

echo ""
echo "Section 2: Security Keys"
echo "------------------------"

# Generate JWT secret
log_info "Generating JWT secret key..."
jwt_secret=$(openssl rand -hex 32)
update_env "JWT_SECRET_KEY" "$jwt_secret"
log_success "JWT secret generated"

# Generate encryption key
log_info "Generating encryption key..."
if python3 -c "from cryptography.fernet import Fernet" 2>/dev/null; then
    encryption_key=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    update_env "ENCRYPTION_KEY" "$encryption_key"
    log_success "Encryption key generated"
else
    log_warn "cryptography library not available. Please install it and generate manually:"
    log_warn "  python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
fi

# Admin emails
read -p "Enter admin email(s), comma-separated: " admin_emails
update_env "ADMIN_EMAILS" "$admin_emails"

echo ""
echo "Section 3: Supabase Configuration"
echo "---------------------------------"

read -p "Enter Supabase URL: " supabase_url
update_env "SUPABASE_URL" "$supabase_url"

read -p "Enter Supabase anon key: " supabase_key
update_env "SUPABASE_KEY" "$supabase_key"

read -p "Enter Supabase service role key: " supabase_service_key
update_env "SUPABASE_SERVICE_ROLE_KEY" "$supabase_service_key"

# Extract database URL from Supabase URL if possible
if [[ "$supabase_url" =~ ^https?://([^.]+) ]]; then
    project_ref="${BASH_REMATCH[1]}"
    db_url="postgresql://postgres:${supabase_service_key}@db.${project_ref}.supabase.co:5432/postgres"
    update_env "DATABASE_URL" "$db_url"
    log_info "Database URL auto-configured"
fi

echo ""
echo "Section 4: AI/LLM Providers"
echo "---------------------------"

read -p "Enter Anthropic API key (Claude): " anthropic_key
if [[ -n "$anthropic_key" ]]; then
    update_env "ANTHROPIC_API_KEY" "$anthropic_key"
    update_env "AI_CLOUD_PROVIDER" "anthropic"
fi

read -p "Enter OpenAI API key (optional): " openai_key
if [[ -n "$openai_key" ]]; then
    update_env "OPENAI_API_KEY" "$openai_key"
fi

echo ""
echo "Section 5: Redis Configuration"
echo "------------------------------"

read -p "Use Docker Redis? (Y/n): " use_docker_redis
if [[ ! $use_docker_redis =~ ^[Nn]$ ]]; then
    update_env "REDIS_URL" "redis://redis:6379/0"
else
    read -p "Enter Redis URL: " redis_url
    update_env "REDIS_URL" "${redis_url:-redis://localhost:6379/0}"
fi
update_env "REDIS_ENABLED" "true"

echo ""
echo "Section 6: Notification Channels"
echo "--------------------------------"

read -p "Enter Telegram bot token (optional): " telegram_token
if [[ -n "$telegram_token" ]]; then
    update_env "SENTRY_BOT_TOKEN" "$telegram_token"

    read -p "Enter Telegram FM chat ID: " telegram_chat_id
    update_env "SENTRY_FM_CHAT_ID" "$telegram_chat_id"
fi

read -p "Enable email notifications? (y/N): " enable_email
if [[ $enable_email =~ ^[Yy]$ ]]; then
    update_env "EMAIL_ENABLED" "true"
    update_env "EMAIL_SERVICE" "smtp"

    read -p "SMTP host: " smtp_host
    update_env "NOTIFICATION_SMTP_HOST" "$smtp_host"

    read -p "SMTP port (587): " smtp_port
    update_env "NOTIFICATION_SMTP_PORT" "${smtp_port:-587}"

    read -p "SMTP username: " smtp_user
    update_env "NOTIFICATION_SMTP_USERNAME" "$smtp_user"

    read -p "SMTP password: " smtp_pass
    update_env "NOTIFICATION_SMTP_PASSWORD" "$smtp_pass"
fi

echo ""
echo "Section 7: InfluxDB Configuration"
echo "---------------------------------"

read -p "Use Docker InfluxDB? (Y/n): " use_docker_influx
if [[ ! $use_docker_influx =~ ^[Nn]$ ]]; then
    update_env "INFLUXDB_URL" "http://influxdb:8086"

    log_info "Generating InfluxDB token..."
    influx_token=$(openssl rand -hex 32)
    update_env "INFLUXDB_TOKEN" "$influx_token"
    update_env "INFLUXDB_ADMIN_TOKEN" "$influx_token"
else
    read -p "Enter InfluxDB URL: " influx_url
    update_env "INFLUXDB_URL" "${influx_url:-http://localhost:8086}"

    read -p "Enter InfluxDB token: " influx_token
    update_env "INFLUXDB_TOKEN" "$influx_token"
fi

update_env "INFLUXDB_ORG" "sentinel"
update_env "INFLUXDB_BUCKET" "sensor_data"

echo ""
echo "Section 8: SIMBIOT/Bridge Configuration"
echo "---------------------------------------"

read -p "Enter bridge base URL (or press Enter for none): " bridge_url
if [[ -n "$bridge_url" ]]; then
    update_env "BRIDGE_BASE_URL" "$bridge_url"
    update_env "ENABLE_SITE002_SOURCE" "false"
    update_env "SENTINEL_ISLAND_MODE" "true"
else
    update_env "ENABLE_SITE002_SOURCE" "true"
    update_env "SENTINEL_ISLAND_MODE" "false"
fi

echo ""
echo "=========================================="
echo "  Configuration Complete!"
echo "=========================================="
echo ""
echo "Environment file created at: $ENV_FILE"
echo ""
echo "Important next steps:"
echo "  1. Review the .env file for any additional settings"
echo "  2. Set secure file permissions: chmod 600 $ENV_FILE"
echo "  3. Deploy using: ./scripts/deploy-vps.sh --domain $domain"
echo ""

# Set secure permissions
chmod 600 "$ENV_FILE"
log_success "File permissions set to 600 (owner read/write only)"
