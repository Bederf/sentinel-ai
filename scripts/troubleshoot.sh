#!/bin/bash
# =============================================================================
# SENTINEL BMS — Troubleshooting Helper
# =============================================================================
# Quick diagnostics and common fixes for SENTINEL deployments
#
# Usage:
#   ./scripts/troubleshoot.sh [command]
#
# Commands:
#   health      Check overall system health
#   logs        View recent logs
#   restart     Restart all services
#   reset       Reset services and clear caches
#   ssl         Check SSL certificate status
#   db          Check database connectivity
#   disk        Check disk usage
#   ports       Check port availability
#   all         Run all checks
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

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

# Check if running as systemd or docker
detect_deployment_type() {
    if docker compose ps 2>/dev/null | grep -q "sentinel"; then
        echo "docker"
    elif systemctl is-active --quiet sentinel-backend 2>/dev/null; then
        echo "systemd"
    else
        echo "unknown"
    fi
}

# Check overall health
check_health() {
    log_info "Checking system health..."
    echo ""

    DEPLOY_TYPE=$(detect_deployment_type)
    log_info "Deployment type: $DEPLOY_TYPE"
    echo ""

    # Check services
    if [[ "$DEPLOY_TYPE" == "docker" ]]; then
        echo "Docker containers:"
        docker compose ps
    elif [[ "$DEPLOY_TYPE" == "systemd" ]]; then
        echo "Systemd services:"
        systemctl status sentinel-backend --no-pager -l || true
        echo ""
        systemctl status sentinel-frontend --no-pager -l || true
        echo ""
        systemctl status nginx --no-pager -l || true
    fi

    # Check endpoints
    echo ""
    echo "Endpoint health checks:"

    if curl -sf "http://localhost:9095/api/health" > /dev/null 2>&1; then
        log_success "Backend (localhost:9095) - OK"
    else
        log_error "Backend (localhost:9095) - FAILED"
    fi

    if curl -sf "http://localhost:9096" > /dev/null 2>&1; then
        log_success "Frontend (localhost:9096) - OK"
    else
        log_error "Frontend (localhost:9096) - FAILED"
    fi
}

# View logs
view_logs() {
    local service="${1:-all}"
    local lines="${2:-100}"

    DEPLOY_TYPE=$(detect_deployment_type)

    if [[ "$DEPLOY_TYPE" == "docker" ]]; then
        if [[ "$service" == "all" ]]; then
            docker compose logs --tail=$lines -f
        else
            docker compose logs --tail=$lines -f "$service"
        fi
    elif [[ "$DEPLOY_TYPE" == "systemd" ]]; then
        if [[ "$service" == "all" || "$service" == "backend" ]]; then
            log_info "Backend logs:"
            sudo journalctl -u sentinel-backend --no-pager -n $lines
        fi
        if [[ "$service" == "all" || "$service" == "frontend" ]]; then
            log_info "Frontend logs:"
            sudo journalctl -u sentinel-frontend --no-pager -n $lines
        fi
        if [[ "$service" == "all" || "$service" == "nginx" ]]; then
            log_info "Nginx logs:"
            sudo journalctl -u nginx --no-pager -n $lines
        fi
    else
        log_error "Cannot detect deployment type"
    fi
}

# Restart services
restart_services() {
    log_info "Restarting services..."

    DEPLOY_TYPE=$(detect_deployment_type)

    if [[ "$DEPLOY_TYPE" == "docker" ]]; then
        cd "$PROJECT_ROOT"
        docker compose restart
    elif [[ "$DEPLOY_TYPE" == "systemd" ]]; then
        sudo systemctl restart sentinel-backend
        sudo systemctl restart sentinel-frontend
        sudo systemctl restart nginx
    else
        log_error "Cannot detect deployment type"
        return 1
    fi

    log_success "Services restarted"
}

# Reset services (clear caches, etc.)
reset_services() {
    log_warn "This will restart services and clear caches. Continue? (y/N)"
    read -r confirm
    if [[ ! $confirm =~ ^[Yy]$ ]]; then
        log_info "Cancelled"
        return 0
    fi

    log_info "Resetting services..."

    DEPLOY_TYPE=$(detect_deployment_type)

    if [[ "$DEPLOY_TYPE" == "docker" ]]; then
        cd "$PROJECT_ROOT"
        docker compose down
        docker system prune -f
        docker compose up -d
    elif [[ "$DEPLOY_TYPE" == "systemd" ]]; then
        sudo systemctl stop sentinel-backend sentinel-frontend
        # Clear Python cache
        find "$PROJECT_ROOT/backend" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
        sudo systemctl start sentinel-backend sentinel-frontend
    fi

    log_success "Services reset"
}

# Check SSL
check_ssl() {
    log_info "Checking SSL certificates..."

    # Find domain from nginx config
    domain=$(grep -h "server_name" /etc/nginx/sites-enabled/* 2>/dev/null | head -1 | awk '{print $2}' | sed 's/;//')

    if [[ -z "$domain" ]]; then
        log_warn "Could not detect domain from Nginx config"
        read -p "Enter domain: " domain
    fi

    if [[ -n "$domain" ]]; then
        echo | openssl s_client -servername "$domain" -connect "$domain:443" 2>/dev/null | openssl x509 -noout -text | head -20

        expiry=$(echo | openssl s_client -servername "$domain" -connect "$domain:443" 2>/dev/null | openssl x509 -noout -enddate | cut -d= -f2)
        log_info "Certificate expires: $expiry"

        # Check certbot renewal
        if sudo certbot renew --dry-run 2>&1 | grep -q "success"; then
            log_success "Certbot renewal test passed"
        else
            log_warn "Certbot renewal test may have issues"
        fi
    fi
}

# Check database
check_database() {
    log_info "Checking database connectivity..."

    cd "$PROJECT_ROOT/backend"

    if [[ -f .env ]]; then
        source .env

        # Test Supabase connection
        if curl -sf "$SUPABASE_URL/rest/v1/" -H "apikey: $SUPABASE_KEY" > /dev/null 2>&1; then
            log_success "Supabase connection - OK"
        else
            log_error "Supabase connection - FAILED"
        fi

        # Test direct PostgreSQL if psql available
        if command -v psql &> /dev/null && [[ -n "$DATABASE_URL" ]]; then
            if psql "$DATABASE_URL" -c "SELECT 1" > /dev/null 2>&1; then
                log_success "PostgreSQL direct connection - OK"
            else
                log_warn "PostgreSQL direct connection - FAILED (may be normal for cloud Supabase)"
            fi
        fi
    else
        log_error ".env file not found"
    fi
}

# Check disk usage
check_disk() {
    log_info "Checking disk usage..."

    df -h /
    echo ""

    # Check Docker usage
    if command -v docker &> /dev/null; then
        log_info "Docker disk usage:"
        docker system df
    fi

    # Check log sizes
    if [[ -d "$PROJECT_ROOT/backend/logs" ]]; then
        log_info "Backend log sizes:"
        du -sh "$PROJECT_ROOT/backend/logs"/* 2>/dev/null | sort -hr | head -10
    fi
}

# Check ports
check_ports() {
    log_info "Checking port usage..."

    echo "Listening ports:"
    ss -tlnp | grep -E "(9095|9096|80|443|8000|3000)"

    echo ""
    log_info "Checking if required ports are available..."

    for port in 9095 9096 80 443; do
        if ss -tln | grep -q ":$port "; then
            service=$(ss -tlnp | grep ":$port " | awk '{print $7}' | head -1)
            log_success "Port $port - In use by $service"
        else
            log_warn "Port $port - Not in use"
        fi
    done
}

# Run all checks
run_all_checks() {
    check_health
    echo ""
    check_database
    echo ""
    check_disk
    echo ""
    check_ports
    echo ""
    check_ssl
}

# Main
main() {
    case "${1:-all}" in
        health)
            check_health
            ;;
        logs)
            view_logs "${2:-all}" "${3:-100}"
            ;;
        restart)
            restart_services
            ;;
        reset)
            reset_services
            ;;
        ssl)
            check_ssl
            ;;
        db|database)
            check_database
            ;;
        disk)
            check_disk
            ;;
        ports)
            check_ports
            ;;
        all)
            run_all_checks
            ;;
        *)
            echo "SENTINEL BMS Troubleshooting Helper"
            echo ""
            echo "Usage: $0 [command]"
            echo ""
            echo "Commands:"
            echo "  health      Check overall system health"
            echo "  logs [svc]  View logs (service: backend|frontend|nginx|all)"
            echo "  restart     Restart all services"
            echo "  reset       Reset services and clear caches"
            echo "  ssl         Check SSL certificate status"
            echo "  db          Check database connectivity"
            echo "  disk        Check disk usage"
            echo "  ports       Check port availability"
            echo "  all         Run all checks (default)"
            echo ""
            ;;
    esac
}

main "$@"
