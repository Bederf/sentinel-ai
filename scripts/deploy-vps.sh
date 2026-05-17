#!/bin/bash
# =============================================================================
# SENTINEL BMS — VPS Deployment Script
# =============================================================================
# This script automates the deployment of SENTINEL BMS on a fresh VPS
# Tested on: Ubuntu 22.04 LTS, Debian 12
#
# Usage:
#   ./deploy-vps.sh [options]
#
# Options:
#   --domain DOMAIN          Domain name for SSL (required)
#   --email EMAIL            Email for SSL certificates (required)
#   --install-docker         Install Docker and Docker Compose
#   --use-docker             Use Docker deployment (default: systemd)
#   --with-monitoring        Include monitoring stack (Loki, Wazuh)
#   --skip-ssl               Skip SSL certificate setup
#   --env-file FILE          Path to environment file
#   --help                   Show this help message
#
# Example:
#   ./deploy-vps.sh --domain bms.sentinel-ai.co.za --email admin@sentinel-ai.co.za
# =============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
INSTALL_DIR="/opt/bms-intelligence"
DOMAIN=""
EMAIL=""
INSTALL_DOCKER=false
USE_DOCKER=false
WITH_MONITORING=false
SKIP_SSL=false
ENV_FILE=""

# Logging
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Help
show_help() {
    head -n 25 "$0" | tail -n 23
    exit 0
}

# Parse arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --domain)
                DOMAIN="$2"
                shift 2
                ;;
            --email)
                EMAIL="$2"
                shift 2
                ;;
            --install-docker)
                INSTALL_DOCKER=true
                shift
                ;;
            --use-docker)
                USE_DOCKER=true
                shift
                ;;
            --with-monitoring)
                WITH_MONITORING=true
                shift
                ;;
            --skip-ssl)
                SKIP_SSL=true
                shift
                ;;
            --env-file)
                ENV_FILE="$2"
                shift 2
                ;;
            --help)
                show_help
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                ;;
        esac
    done
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check if running as root
    if [[ $EUID -eq 0 ]]; then
        log_error "Do not run this script as root. Use a user with sudo privileges."
        exit 1
    fi

    # Check sudo access
    if ! sudo -n true 2>/dev/null; then
        log_error "This script requires sudo privileges. Please configure passwordless sudo."
        exit 1
    fi

    # Check OS
    if [[ ! -f /etc/os-release ]]; then
        log_error "Cannot determine OS version"
        exit 1
    fi

    source /etc/os-release
    if [[ "$ID" != "ubuntu" && "$ID" != "debian" ]]; then
        log_warn "This script is designed for Ubuntu/Debian. Proceed with caution."
    fi

    # Check required parameters
    if [[ -z "$DOMAIN" ]]; then
        log_error "Domain is required. Use --domain flag."
        exit 1
    fi

    if [[ -z "$EMAIL" && "$SKIP_SSL" == false ]]; then
        log_error "Email is required for SSL. Use --email flag or --skip-ssl"
        exit 1
    fi

    log_success "Prerequisites check passed"
}

# Install system dependencies
install_system_deps() {
    log_info "Installing system dependencies..."

    sudo apt-get update
    sudo apt-get install -y \
        curl \
        wget \
        git \
        vim \
        htop \
        jq \
        unzip \
        certbot \
        python3-certbot-nginx \
        ufw \
        fail2ban \
        logrotate \
        ncdu \
        tree

    log_success "System dependencies installed"
}

# Install Docker
install_docker() {
    log_info "Installing Docker..."

    # Remove old versions
    sudo apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true

    # Install prerequisites
    sudo apt-get install -y \
        ca-certificates \
        gnupg \
        lsb-release

    # Add Docker GPG key
    sudo mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/$ID/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

    # Add repository
    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/$ID \
        $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    # Install Docker
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

    # Add user to docker group
    sudo usermod -aG docker $USER

    # Enable Docker service
    sudo systemctl enable docker
    sudo systemctl start docker

    log_success "Docker installed successfully"
    log_warn "You may need to log out and back in for docker group changes to take effect"
}

# Setup firewall
setup_firewall() {
    log_info "Configuring firewall..."

    sudo ufw default deny incoming
    sudo ufw default allow outgoing

    # Allow SSH
    sudo ufw allow 22/tcp

    # Allow HTTP/HTTPS
    sudo ufw allow 80/tcp
    sudo ufw allow 443/tcp

    # Allow SENTINEL backend (if not using Docker)
    if [[ "$USE_DOCKER" == false ]]; then
        sudo ufw allow 9095/tcp
        sudo ufw allow 9096/tcp
    fi

    # Enable firewall
    sudo ufw --force enable

    log_success "Firewall configured"
}

# Setup fail2ban
setup_fail2ban() {
    log_info "Configuring fail2ban..."

    sudo systemctl enable fail2ban
    sudo systemctl start fail2ban

    log_success "Fail2ban configured"
}

# Create project directory
setup_project() {
    log_info "Setting up project directory..."

    sudo mkdir -p "$INSTALL_DIR"
    sudo chown $USER:$USER "$INSTALL_DIR"

    # Copy project files
    if [[ "$PROJECT_ROOT" != "$INSTALL_DIR" ]]; then
        log_info "Copying project files to $INSTALL_DIR..."
        rsync -av --exclude='.git' --exclude='node_modules' --exclude='venv' \
            --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' \
            "$PROJECT_ROOT/" "$INSTALL_DIR/"
    fi

    log_success "Project directory ready at $INSTALL_DIR"
}

# Setup environment file
setup_environment() {
    log_info "Setting up environment configuration..."

    cd "$INSTALL_DIR"

    if [[ -n "$ENV_FILE" && -f "$ENV_FILE" ]]; then
        log_info "Using provided environment file: $ENV_FILE"
        cp "$ENV_FILE" "$INSTALL_DIR/backend/.env"
    elif [[ -f "$INSTALL_DIR/backend/.env" ]]; then
        log_info "Existing .env file found"
    else
        log_warn "No .env file found. Creating from example..."
        cp "$INSTALL_DIR/backend/.env.example" "$INSTALL_DIR/backend/.env"

        # Generate secrets
        JWT_SECRET=$(openssl rand -hex 32)
        ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || echo "")

        # Update .env with generated values
        sed -i "s/JWT_SECRET_KEY=.*/JWT_SECRET_KEY=$JWT_SECRET/" "$INSTALL_DIR/backend/.env"
        if [[ -n "$ENCRYPTION_KEY" ]]; then
            sed -i "s/ENCRYPTION_KEY=.*/ENCRYPTION_KEY=$ENCRYPTION_KEY/" "$INSTALL_DIR/backend/.env"
        fi

        log_warn "Please edit $INSTALL_DIR/backend/.env with your actual API keys and credentials"
    fi

    # Setup frontend env
    if [[ ! -f "$INSTALL_DIR/frontend/.env.production" ]]; then
        echo "VITE_API_URL=https://$DOMAIN/api" > "$INSTALL_DIR/frontend/.env.production"
    fi

    log_success "Environment configured"
}

# Setup SSL certificates
setup_ssl() {
    if [[ "$SKIP_SSL" == true ]]; then
        log_warn "Skipping SSL setup"
        return
    fi

    log_info "Setting up SSL certificates..."

    # Obtain certificate
    sudo certbot certonly --standalone -d "$DOMAIN" --agree-tos --email "$EMAIL" --non-interactive

    # Setup auto-renewal
    echo "0 3 * * * root certbot renew --quiet" | sudo tee -a /etc/crontab > /dev/null

    log_success "SSL certificates configured for $DOMAIN"
}

# Deploy with Docker
deploy_docker() {
    log_info "Deploying with Docker Compose..."

    cd "$INSTALL_DIR"

    # Update Caddyfile with domain
    sed -i "s/bms.aimthelaw.co.za/$DOMAIN/g" "$INSTALL_DIR/infrastructure/caddy/Caddyfile"

    # Choose compose file based on monitoring flag
    if [[ "$WITH_MONITORING" == true ]]; then
        COMPOSE_FILE="docker-compose.yml"
    else
        COMPOSE_FILE="docker-compose.yml"
        # Remove monitoring services if not needed
        log_info "Starting without monitoring stack (use --with-monitoring to include)"
    fi

    # Build and start services
    docker compose -f "$COMPOSE_FILE" down 2>/dev/null || true
    docker compose -f "$COMPOSE_FILE" pull
    docker compose -f "$COMPOSE_FILE" up -d --build

    # Wait for health checks
    log_info "Waiting for services to be healthy..."
    sleep 30

    # Verify
    if curl -sf "http://localhost:8082/api/health" > /dev/null 2>&1; then
        log_success "Backend is healthy"
    else
        log_warn "Backend health check failed. Check logs with: docker compose logs backend"
    fi

    log_success "Docker deployment complete"
}

# Deploy with systemd
deploy_systemd() {
    log_info "Deploying with systemd services..."

    cd "$INSTALL_DIR"

    # Setup backend
    log_info "Setting up backend..."
    cd "$INSTALL_DIR/backend"

    if [[ ! -d "venv" ]]; then
        python3 -m venv venv
    fi
    source venv/bin/activate
    pip install -r requirements.txt

    # Setup frontend
    log_info "Setting up frontend..."
    cd "$INSTALL_DIR/frontend"

    if [[ ! -d "node_modules" ]]; then
        npm ci
    fi
    npm run build

    # Install services
    log_info "Installing systemd services..."

    # Update service files with correct paths and user
    sudo sed -i "s|/opt/bms-intelligence|$INSTALL_DIR|g" "$INSTALL_DIR/infra/systemd/sentinel-backend.service"
    sudo sed -i "s|User=.*|User=$USER|g" "$INSTALL_DIR/infra/systemd/sentinel-backend.service"
    sudo sed -i "s|Group=.*|Group=$USER|g" "$INSTALL_DIR/infra/systemd/sentinel-backend.service"

    sudo sed -i "s|/opt/bms-intelligence|$INSTALL_DIR|g" "$INSTALL_DIR/infra/systemd/sentinel-frontend.service"
    sudo sed -i "s|User=.*|User=$USER|g" "$INSTALL_DIR/infra/systemd/sentinel-frontend.service"
    sudo sed -i "s|Group=.*|Group=$USER|g" "$INSTALL_DIR/infra/systemd/sentinel-frontend.service"

    # Copy services
    sudo cp "$INSTALL_DIR/infra/systemd/sentinel-backend.service" /etc/systemd/system/
    sudo cp "$INSTALL_DIR/infra/systemd/sentinel-frontend.service" /etc/systemd/system/

    # Setup Nginx
    setup_nginx

    # Reload and start
    sudo systemctl daemon-reload
    sudo systemctl enable sentinel-backend sentinel-frontend
    sudo systemctl restart sentinel-backend sentinel-frontend

    # Wait for startup
    sleep 10

    # Verify
    if systemctl is-active --quiet sentinel-backend; then
        log_success "Backend service is running"
    else
        log_error "Backend service failed to start. Check: sudo journalctl -u sentinel-backend"
        exit 1
    fi

    if systemctl is-active --quiet sentinel-frontend; then
        log_success "Frontend service is running"
    else
        log_error "Frontend service failed to start. Check: sudo journalctl -u sentinel-frontend"
        exit 1
    fi

    log_success "Systemd deployment complete"
}

# Setup Nginx
setup_nginx() {
    log_info "Setting up Nginx..."

    sudo apt-get install -y nginx

    # Create Nginx config
    sudo tee /etc/nginx/sites-available/sentinel > /dev/null <<EOF
server {
    listen 80;
    server_name $DOMAIN;

    # Redirect HTTP to HTTPS
    location / {
        return 301 https://\$server_name\$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name $DOMAIN;

    # SSL certificates
    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/$DOMAIN/chain.pem;

    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;

    # Frontend
    location / {
        proxy_pass http://localhost:9096;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_cache_bypass \$http_upgrade;
    }

    # Backend API
    location /api/ {
        proxy_pass http://localhost:9095;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Authorization \$http_authorization;
        proxy_set_header Cookie \$http_cookie;
        proxy_cache_bypass \$http_upgrade;

        # Timeout for long-running requests
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }

    # Health check
    location /health {
        access_log off;
        return 200 "OK\n";
        add_header Content-Type text/plain;
    }
}
EOF

    # Enable site
    sudo ln -sf /etc/nginx/sites-available/sentinel /etc/nginx/sites-enabled/
    sudo rm -f /etc/nginx/sites-enabled/default

    # Test and reload
    sudo nginx -t
    sudo systemctl restart nginx
    sudo systemctl enable nginx

    log_success "Nginx configured"
}

# Setup log rotation
setup_logrotate() {
    log_info "Setting up log rotation..."

    sudo tee /etc/logrotate.d/sentinel > /dev/null <<EOF
$INSTALL_DIR/backend/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0644 $USER $USER
    sharedscripts
    postrotate
        systemctl reload sentinel-backend 2>/dev/null || true
    endscript
}
EOF

    log_success "Log rotation configured"
}

# Create verification script
create_verify_script() {
    log_info "Creating verification script..."

    cat > "$INSTALL_DIR/verify-deployment.sh" <<'EOF'
#!/bin/bash
# SENTINEL Deployment Verification Script

set -e

DOMAIN="$1"
if [[ -z "$DOMAIN" ]]; then
    echo "Usage: $0 <domain>"
    exit 1
fi

echo "=========================================="
echo "SENTINEL BMS Deployment Verification"
echo "=========================================="
echo ""

# Check services
echo "Checking services..."
if systemctl is-active --quiet sentinel-backend 2>/dev/null; then
    echo "✓ Backend service is running"
else
    echo "✗ Backend service is not running"
fi

if systemctl is-active --quiet sentinel-frontend 2>/dev/null; then
    echo "✓ Frontend service is running"
else
    echo "✗ Frontend service is not running"
fi

if systemctl is-active --quiet nginx 2>/dev/null; then
    echo "✓ Nginx is running"
else
    echo "✗ Nginx is not running"
fi

# Check endpoints
echo ""
echo "Checking endpoints..."

if curl -sf "http://localhost:9095/api/health" > /dev/null 2>&1; then
    echo "✓ Backend health endpoint (local)"
else
    echo "✗ Backend health endpoint failed"
fi

if curl -sf "https://$DOMAIN/api/health" > /dev/null 2>&1; then
    echo "✓ Backend health endpoint (HTTPS)"
else
    echo "✗ Backend health endpoint (HTTPS) failed"
fi

if curl -sf "https://$DOMAIN" > /dev/null 2>&1; then
    echo "✓ Frontend (HTTPS)"
else
    echo "✗ Frontend (HTTPS) failed"
fi

# Check SSL
echo ""
echo "Checking SSL certificate..."
if echo | openssl s_client -servername "$DOMAIN" -connect "$DOMAIN:443" 2>/dev/null | openssl x509 -noout -dates > /dev/null 2>&1; then
    EXPIRY=$(echo | openssl s_client -servername "$DOMAIN" -connect "$DOMAIN:443" 2>/dev/null | openssl x509 -noout -enddate | cut -d= -f2)
    echo "✓ SSL certificate valid until: $EXPIRY"
else
    echo "✗ SSL certificate check failed"
fi

# Check disk space
echo ""
echo "System resources..."
DISK_USAGE=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
echo "Disk usage: ${DISK_USAGE}%"

MEMORY_USAGE=$(free | awk 'NR==2{printf "%.0f", $3*100/$2}')
echo "Memory usage: ${MEMORY_USAGE}%"

echo ""
echo "=========================================="
echo "Verification complete"
echo "=========================================="
EOF

    chmod +x "$INSTALL_DIR/verify-deployment.sh"
    log_success "Verification script created at $INSTALL_DIR/verify-deployment.sh"
}

# Print summary
print_summary() {
    echo ""
    echo "=========================================="
    echo "  SENTINEL BMS Deployment Complete!"
    echo "=========================================="
    echo ""
    echo "Domain: https://$DOMAIN"
    echo "Backend: https://$DOMAIN/api"
    echo "Health: https://$DOMAIN/api/health"
    echo ""
    echo "Installation directory: $INSTALL_DIR"
    echo ""
    if [[ "$USE_DOCKER" == true ]]; then
        echo "Deployment type: Docker Compose"
        echo "Logs: docker compose logs -f"
    else
        echo "Deployment type: Systemd services"
        echo "Backend logs: sudo journalctl -u sentinel-backend -f"
        echo "Frontend logs: sudo journalctl -u sentinel-frontend -f"
    fi
    echo ""
    echo "Verification: $INSTALL_DIR/verify-deployment.sh $DOMAIN"
    echo ""
    echo "Next steps:"
    echo "  1. Configure your API keys in: $INSTALL_DIR/backend/.env"
    echo "  2. Restart services after config changes"
    echo "  3. Access the web UI at: https://$DOMAIN"
    echo "  4. Complete the setup wizard"
    echo ""
    echo "=========================================="
}

# Main
main() {
    parse_args "$@"
    check_prerequisites
    install_system_deps

    if [[ "$INSTALL_DOCKER" == true ]]; then
        install_docker
    fi

    setup_firewall
    setup_fail2ban
    setup_project
    setup_environment
    setup_ssl

    if [[ "$USE_DOCKER" == true ]]; then
        deploy_docker
    else
        deploy_systemd
    fi

    setup_logrotate
    create_verify_script
    print_summary
}

main "$@"
