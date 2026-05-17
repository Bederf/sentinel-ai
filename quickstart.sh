#!/bin/bash
# =============================================================================
# SENTINEL BMS — Quick Start Deployment
# =============================================================================
# One-command deployment for common scenarios
#
# Usage:
#   ./quickstart.sh [scenario]
#
# Scenarios:
#   production    Full production deployment with Docker
#   systemd       Production deployment with systemd services
#   minimal       Minimal deployment without monitoring
#   local         Local development setup
#   update        Update existing deployment
#
# Examples:
#   ./quickstart.sh production
#   DOMAIN=bms.example.com EMAIL=admin@example.com ./quickstart.sh production
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${CYAN}[STEP]${NC} $1"; }

# Get configuration from environment or prompt
get_config() {
    if [[ -z "${DOMAIN:-}" ]]; then
        read -p "Enter your domain (e.g., bms.yourdomain.com): " DOMAIN
    fi

    if [[ -z "${EMAIL:-}" ]]; then
        read -p "Enter your email for SSL certificates: " EMAIL
    fi

    if [[ -z "$DOMAIN" || -z "$EMAIL" ]]; then
        log_error "Domain and email are required"
        exit 1
    fi
}

# Production deployment with Docker
deploy_production() {
    log_step "Production Deployment (Docker)"
    echo ""

    get_config

    log_info "This will deploy SENTINEL with the following configuration:"
    echo "  Domain: $DOMAIN"
    echo "  Email: $EMAIL"
    echo "  Deployment: Docker Compose"
    echo "  Monitoring: Yes"
    echo "  SSL: Let's Encrypt"
    echo ""
    read -p "Continue? (Y/n): " confirm

    if [[ ! $confirm =~ ^[Nn]$ ]]; then
        ./scripts/deploy-vps.sh \
            --domain "$DOMAIN" \
            --email "$EMAIL" \
            --use-docker \
            --install-docker \
            --with-monitoring

        echo ""
        log_success "Production deployment complete!"
        echo ""
        echo "Access your SENTINEL instance at:"
        echo "  https://$DOMAIN"
        echo ""
        echo "Next steps:"
        echo "  1. Configure API keys in /opt/bms-intelligence/backend/.env"
        echo "  2. Run: ./scripts/troubleshoot.sh health"
        echo "  3. Access the web UI and complete setup"
    fi
}

# Systemd deployment
deploy_systemd() {
    log_step "Production Deployment (Systemd)"
    echo ""

    get_config

    log_info "This will deploy SENTINEL with the following configuration:"
    echo "  Domain: $DOMAIN"
    echo "  Email: $EMAIL"
    echo "  Deployment: Systemd services"
    echo "  Monitoring: No"
    echo "  SSL: Let's Encrypt + Nginx"
    echo ""
    read -p "Continue? (Y/n): " confirm

    if [[ ! $confirm =~ ^[Nn]$ ]]; then
        ./scripts/deploy-vps.sh \
            --domain "$DOMAIN" \
            --email "$EMAIL"

        echo ""
        log_success "Systemd deployment complete!"
        echo ""
        echo "Access your SENTINEL instance at:"
        echo "  https://$DOMAIN"
    fi
}

# Minimal deployment
deploy_minimal() {
    log_step "Minimal Deployment"
    echo ""

    get_config

    log_warn "This is a minimal deployment without monitoring stack"
    echo ""

    ./scripts/deploy-vps.sh \
        --domain "$DOMAIN" \
        --email "$EMAIL" \
        --use-docker \
        --install-docker

    echo ""
    log_success "Minimal deployment complete!"
}

# Local development setup
deploy_local() {
    log_step "Local Development Setup"
    echo ""

    log_info "Setting up local development environment..."

    # Check prerequisites
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is required"
        exit 1
    fi

    if ! command -v npm &> /dev/null; then
        log_error "npm is required"
        exit 1
    fi

    # Setup backend
    log_info "Setting up backend..."
    cd "$PROJECT_ROOT/backend"

    if [[ ! -d "venv" ]]; then
        python3 -m venv venv
    fi
    source venv/bin/activate
    pip install -r requirements.txt

    # Setup env if not exists
    if [[ ! -f ".env" ]]; then
        cp .env.example .env
        # Generate local secrets
        jwt_secret=$(openssl rand -hex 32)
        sed -i "s/JWT_SECRET_KEY=.*/JWT_SECRET_KEY=$jwt_secret/" .env
        log_info "Created .env file with generated secrets"
    fi

    # Setup frontend
    log_info "Setting up frontend..."
    cd "$PROJECT_ROOT/frontend"

    if [[ ! -d "node_modules" ]]; then
        npm install
    fi

    if [[ ! -f ".env.local" ]]; then
        echo "VITE_API_URL=http://localhost:9095" > .env.local
    fi

    echo ""
    log_success "Local development setup complete!"
    echo ""
    echo "Start development servers:"
    echo ""
    echo "Terminal 1 (Backend):"
    echo "  cd backend && source venv/bin/activate && python -m uvicorn app.main:app --host 0.0.0.0 --port 9095 --reload"
    echo ""
    echo "Terminal 2 (Frontend):"
    echo "  cd frontend && npm run dev"
    echo ""
    echo "Access the app at: http://localhost:9096"
}

# Update existing deployment
deploy_update() {
    log_step "Update Existing Deployment"
    echo ""

    # Detect deployment type
    if docker compose ps 2>/dev/null | grep -q "sentinel"; then
        log_info "Detected Docker deployment"

        cd "$PROJECT_ROOT"
        git pull
        docker compose pull
        docker compose up -d

        log_success "Docker deployment updated"

    elif systemctl is-active --quiet sentinel-backend 2>/dev/null; then
        log_info "Detected Systemd deployment"

        git pull

        # Update backend
        cd "$PROJECT_ROOT/backend"
        source venv/bin/activate
        pip install -r requirements.txt
        sudo systemctl restart sentinel-backend

        # Update frontend
        cd "$PROJECT_ROOT/frontend"
        npm ci
        npm run build
        sudo systemctl restart sentinel-frontend

        log_success "Systemd deployment updated"
    else
        log_error "Cannot detect existing deployment"
        exit 1
    fi
}

# Show help
show_help() {
    echo "SENTINEL BMS — Quick Start Deployment"
    echo ""
    echo "Usage: $0 [scenario]"
    echo ""
    echo "Scenarios:"
    echo "  production    Full production deployment with Docker + monitoring"
    echo "  systemd       Production deployment with systemd services"
    echo "  minimal       Minimal Docker deployment without monitoring"
    echo "  local         Local development environment setup"
    echo "  update        Update existing deployment"
    echo ""
    echo "Environment variables:"
    echo "  DOMAIN        Your domain name (e.g., bms.example.com)"
    echo "  EMAIL         Email for SSL certificates"
    echo ""
    echo "Examples:"
    echo "  $0 production"
    echo "  DOMAIN=bms.example.com EMAIL=admin@example.com $0 production"
    echo "  $0 local"
    echo ""
}

# Main
main() {
    case "${1:-}" in
        production)
            deploy_production
            ;;
        systemd)
            deploy_systemd
            ;;
        minimal)
            deploy_minimal
            ;;
        local)
            deploy_local
            ;;
        update)
            deploy_update
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            echo "SENTINEL BMS — Quick Start"
            echo ""
            echo "Select a deployment scenario:"
            echo ""
            echo "1) Production (Docker + monitoring)"
            echo "2) Production (Systemd)"
            echo "3) Minimal (Docker only)"
            echo "4) Local development"
            echo "5) Update existing"
            echo "6) Help"
            echo ""
            read -p "Enter choice (1-6): " choice

            case $choice in
                1) deploy_production ;;
                2) deploy_systemd ;;
                3) deploy_minimal ;;
                4) deploy_local ;;
                5) deploy_update ;;
                6) show_help ;;
                *) log_error "Invalid choice" ;;
            esac
            ;;
    esac
}

main "$@"
