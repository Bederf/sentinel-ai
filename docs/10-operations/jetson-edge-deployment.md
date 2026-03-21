---
title: SENTINEL Jetson Edge Deployment Guide
category: operations
date: 2026-03-21
tags: [edge, jetson, ollama, deployment, systemd]
---

# SENTINEL Jetson Edge Deployment Guide

Step-by-step guide for deploying SENTINEL in edge mode on an NVIDIA Jetson Orin.
Edge mode routes all LLM inference through local Ollama (no internet required after setup).

**Estimated time:** 45 minutes | **Prerequisites:** Jetson Orin, JetPack 5+, 16 GB+ RAM, 64 GB+ NVMe

---

## 1. System Prep (5 min)

```bash
# Create service account
sudo adduser --system --group --home /opt/sentinel sentinel

# Create directory structure
sudo mkdir -p /opt/sentinel/{backend,ml/models}
sudo chown -R sentinel:sentinel /opt/sentinel
```

## 2. Clone & Install (15 min)

```bash
# Clone the clean repo (no dev data)
sudo -u sentinel git clone https://github.com/Bederf/sentinel-ai.git /opt/sentinel/repo
cd /opt/sentinel/repo

# Backend
cd backend
sudo -u sentinel python3 -m venv /opt/sentinel/backend/venv
sudo -u sentinel /opt/sentinel/backend/venv/bin/pip install -r requirements.txt

# Link app directory
sudo ln -s /opt/sentinel/repo/backend/app /opt/sentinel/backend/app
```

## 3. Configure Environment (5 min)

```bash
cp /opt/sentinel/repo/backend/.env.example /opt/sentinel/backend/.env
# Edit /opt/sentinel/backend/.env — minimum required:
#   EDGE_MODE=true
#   OLLAMA_MODEL=deepseek-r1:14b
#   MODEL_STORAGE_PATH=/opt/sentinel/ml/models
#   DEMO_MODE=false
#   ENABLE_SITE002_SOURCE=false
#   (Add SUPABASE_URL / SUPABASE_KEY if using cloud DB, else leave blank for JSON fallback)
```

## 4. Install Ollama & Pull Model (15 min)

```bash
# Install Ollama (ARM64 build for Jetson)
curl -fsSL https://ollama.com/install.sh | sh

# Pull the inference model
ollama pull deepseek-r1:14b

# Install Ollama as a service
sudo cp /opt/sentinel/repo/infra/systemd/ollama.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ollama.service
```

## 5. Install SENTINEL Backend Service (5 min)

```bash
sudo cp /opt/sentinel/repo/infra/systemd/sentinel-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sentinel-backend.service

# Verify startup (watch for "Application startup complete")
journalctl -u sentinel-backend -f --no-pager
```

## 6. Verify Edge Mode Boot

```bash
# Confirm EDGE_MODE forced routing profile to local_full
curl http://localhost:9095/api/health | python3 -m json.tool

# Confirm Ollama is reachable
curl http://localhost:11434/api/tags | python3 -m json.tool

# Run smoke test
cd /opt/sentinel/repo/backend
EDGE_MODE=true /opt/sentinel/backend/venv/bin/python -m pytest tests/startup/test_edge_mode.py -v
```

## Troubleshooting

| Issue | Command |
|-------|---------|
| Backend not starting | `journalctl -u sentinel-backend -n 50` |
| Ollama unreachable | `systemctl status ollama` |
| Wrong routing profile | `grep EDGE_MODE /opt/sentinel/backend/.env` |
| Model not found | `ollama list` |

## Related

- `deployment-runbook.md` — general cloud deployment guide
- `../infra/systemd/sentinel-backend.service` — service unit file
- `../infra/systemd/ollama.service` — Ollama service unit
