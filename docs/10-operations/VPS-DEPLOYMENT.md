# SENTINEL BMS — VPS Deployment Guide

Complete deployment guide for SENTINEL BMS on a Virtual Private Server (VPS).

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/your-org/bms-intelligence.git
cd bms-intelligence

# 2. Run the interactive environment setup
./scripts/setup-env.sh

# 3. Deploy to your VPS
./scripts/deploy-vps.sh --domain bms.yourdomain.com --email admin@yourdomain.com
```

## Prerequisites

### Hardware Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 4 cores | 8 cores |
| RAM | 8 GB | 16 GB |
| Disk | 40 GB SSD | 100 GB SSD |
| Network | 10 Mbps | 100 Mbps |

### Software Requirements

- Ubuntu 22.04 LTS or Debian 12
- Root access or sudo privileges
- Domain name with DNS A record pointing to VPS IP

### Required Accounts

- **Supabase**: Cloud PostgreSQL database (or self-hosted)
- **Anthropic**: Claude API access (or OpenAI)
- **Cloudflare/LetsEncrypt**: For SSL certificates (optional, auto-configured)

## Deployment Options

### Option 1: Docker Compose (Recommended)

Best for most deployments. Includes automatic SSL, easy scaling, and simple management.

```bash
./scripts/deploy-vps.sh \
  --domain bms.sentinel-ai.co.za \
  --email admin@sentinel-ai.co.za \
  --use-docker \
  --install-docker
```

### Option 2: Systemd Services

Best for resource-constrained environments or when Docker is not preferred.

```bash
./scripts/deploy-vps.sh \
  --domain bms.sentinel-ai.co.za \
  --email admin@sentinel-ai.co.za
```

## Deployment Scripts

### `deploy-vps.sh`

Main deployment automation script.

**Usage:**
```bash
./scripts/deploy-vps.sh [options]
```

**Options:**
- `--domain DOMAIN` - Domain name for SSL (required)
- `--email EMAIL` - Email for SSL certificates (required)
- `--install-docker` - Install Docker and Docker Compose
- `--use-docker` - Use Docker deployment (default: systemd)
- `--with-monitoring` - Include monitoring stack (Loki, Wazuh)
- `--skip-ssl` - Skip SSL certificate setup
- `--env-file FILE` - Path to pre-configured environment file
- `--help` - Show help message

### `setup-env.sh`

Interactive environment configuration.

**Usage:**
```bash
./scripts/setup-env.sh
```

Guides you through:
1. Basic configuration (domain, site ID)
2. Security key generation
3. Supabase configuration
4. AI/LLM provider setup
5. Redis and InfluxDB settings
6. Notification channels
7. SIMBIOT/Bridge configuration

### `troubleshoot.sh`

Diagnostics and troubleshooting helper.

**Usage:**
```bash
./scripts/troubleshoot.sh [command]
```

**Commands:**
- `health` - Check system health
- `logs [service]` - View logs (backend|frontend|nginx|all)
- `restart` - Restart all services
- `reset` - Reset services and clear caches
- `ssl` - Check SSL certificate status
- `db` - Check database connectivity
- `disk` - Check disk usage
- `ports` - Check port availability
- `all` - Run all checks (default)

## Post-Deployment

### 1. Verify Installation

```bash
# Run verification
./verify-deployment.sh bms.yourdomain.com

# Or check manually
curl https://bms.yourdomain.com/api/health
```

### 2. First Login

1. Navigate to `https://bms.yourdomain.com`
2. Login with admin email configured in `.env`
3. Go to **Settings** → **System Health**
4. Verify all services show green status

### 3. Configure Building Profile

1. Go to **Settings** → **Building Profile**
2. Update site information
3. Configure equipment naming conventions

### 4. Add Technicians

1. Go to **Settings** → **Team & Technicians**
2. Add technicians with their disciplines
3. Configure notification preferences

### 5. Setup SIMBIOT Connection

1. Go to **SIMBIOT** tab
2. Follow the wizard to connect your BMS
3. Map equipment points

## Security

### Firewall

The deployment script automatically configures UFW:
- Allows SSH (port 22)
- Allows HTTP (port 80)
- Allows HTTPS (port 443)
- Blocks all other incoming traffic

### SSL/TLS

Automatic SSL certificates via Let's Encrypt:
- Auto-renewal configured
- TLS 1.2+ only
- Strong cipher suites
- HSTS enabled

### Fail2Ban

Brute force protection:
- SSH protection
- API rate limiting
- Automatic IP blocking

### Security Headers

All responses include:
- X-Frame-Options: SAMEORIGIN
- X-Content-Type-Options: nosniff
- X-XSS-Protection: 1; mode=block
- Strict-Transport-Security (HSTS)

## Monitoring (Optional)

Enable monitoring stack:

```bash
./scripts/deploy-vps.sh \
  --domain bms.yourdomain.com \
  --email admin@yourdomain.com \
  --use-docker \
  --with-monitoring
```

Components:
- **Loki**: Centralized log aggregation
- **Promtail**: Log collector
- **InfluxDB**: Time-series metrics
- **Wazuh**: Host-based intrusion detection

## Backup

### Automated Backups

Add to crontab:
```bash
0 2 * * * cd /opt/bms-intelligence/backend && python3 scripts/backup_supabase_to_json.py >> /var/log/sentinel-backup.log 2>&1
```

### Manual Backup

```bash
# Database backup
cd /opt/bms-intelligence/backend
source venv/bin/activate
python scripts/backup_supabase_to_json.py

# Configuration backup
tar -czf backup-$(date +%Y%m%d).tar.gz /opt/bms-intelligence/backend/.env
```

## Troubleshooting

### Service Won't Start

```bash
# Check logs
./scripts/troubleshoot.sh logs backend

# Check configuration
./scripts/troubleshoot.sh db

# Restart services
./scripts/troubleshoot.sh restart
```

### SSL Certificate Issues

```bash
# Check certificate
./scripts/troubleshoot.sh ssl

# Renew manually
sudo certbot renew --force-renewal

# Test renewal
sudo certbot renew --dry-run
```

### Database Connection Failed

```bash
# Verify Supabase credentials
cat /opt/bms-intelligence/backend/.env | grep SUPABASE

# Test connection
curl $SUPABASE_URL/rest/v1/ -H "apikey: $SUPABASE_KEY"
```

### High Memory Usage

```bash
# Check memory
./scripts/troubleshoot.sh disk

# Restart with resource limits
docker compose restart
```

## Updating

### Docker Deployment

```bash
cd /opt/bms-intelligence
git pull
docker compose pull
docker compose up -d
```

### Systemd Deployment

```bash
cd /opt/bms-intelligence
git pull

# Backend
cd backend
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart sentinel-backend

# Frontend
cd ../frontend
npm ci
npm run build
sudo systemctl restart sentinel-frontend
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        VPS                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Caddy      │  │   Backend    │  │   Frontend   │      │
│  │  (Reverse)   │  │   (FastAPI)  │  │   (React)    │      │
│  │    :443      │  │    :9095     │  │    :9096     │      │
│  └──────┬───────┘  └──────┬───────┘  └──────────────┘      │
│         │                 │                                  │
│         └─────────────────┘                                  │
│                           │                                  │
│  ┌──────────────┐  ┌─────┴──────┐  ┌──────────────┐        │
│  │    Redis     │  │  InfluxDB  │  │   Supabase   │        │
│  │   (Cache)    │  │(Time-Series)│  │ (PostgreSQL) │        │
│  └──────────────┘  └────────────┘  └──────────────┘        │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐                        │
│  │   Fail2Ban   │  │     UFW      │                        │
│  │  (Security)  │  │  (Firewall)  │                        │
│  └──────────────┘  └──────────────┘                        │
└─────────────────────────────────────────────────────────────┘
```

## Support

- **Documentation**: `docs/10-operations/`
- **Issues**: Check `docs/10-operations/KNOWN_ISSUES.md`
- **Runbook**: `docs/10-operations/deployment-runbook.md`

## License

Proprietary - SENTINEL AI Systems
