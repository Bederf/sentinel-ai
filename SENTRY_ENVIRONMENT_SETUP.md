# SENTRY Environment Variable Setup

**Portable configuration for VM, Jetson, and multi-site deployments**

---

## Overview

After renaming from OpenClaw to SENTRY, all hardcoded paths are replaced with the `$SENTRY_HOME` environment variable. This enables **single deployment image** to work across:

- ✅ Development VM (`/home/bederf/.sentry`)
- ✅ Jetson appliance (`/opt/sentry`)
- ✅ Multiple buildings (configured via env)
- ✅ Docker Compose (environment injection)
- ✅ Systemd services (environment file)

---

## Setting `$SENTRY_HOME`

### Local Development (VM)

```bash
# Temporary (current session only)
export SENTRY_HOME=/home/bederf/.sentry

# Permanent (add to ~/.bashrc or ~/.zshrc)
echo 'export SENTRY_HOME=/home/bederf/.sentry' >> ~/.bashrc
source ~/.bashrc

# Verify
echo $SENTRY_HOME
```

### Jetson Appliance

```bash
# In systemd environment file (/etc/systemd/system/sentry-bot.service.d/override.conf)
[Service]
Environment=SENTRY_HOME=/opt/sentry

# Or in /etc/environment (system-wide)
SENTRY_HOME=/opt/sentry
```

### Docker Compose

```yaml
# docker-compose.yml
services:
  sentry:
    image: sentry:latest
    environment:
      SENTRY_HOME: /opt/sentry
    volumes:
      - sentry_data:/opt/sentry

  sentinel-backend:
    environment:
      SENTRY_HOME: /opt/sentry
      SENTRY_BOT_USERNAME: sentry-bot
      SENTRY_BOT_PASSWORD: ${SENTRY_BOT_PASSWORD}

volumes:
  sentry_data:
```

### Systemd Service

**File:** `/etc/systemd/system/sentry-bot.service`

```ini
[Unit]
Description=SENTRY Bot - Building Management AI
After=network.target

[Service]
Type=simple
User=bederf
Environment=SENTRY_HOME=/home/bederf/.sentry
Environment=SENTRY_BOT_USERNAME=sentry-bot
Environment=PYTHONUNBUFFERED=1
WorkingDirectory=/home/bederf/.sentry
ExecStart=/usr/bin/python3 bot.py
Restart=on-failure
RestartSec=10s

[Install]
WantedBy=multi-user.target
```

After updating:
```bash
sudo systemctl daemon-reload
sudo systemctl enable sentry-bot.service
sudo systemctl start sentry-bot.service
sudo systemctl status sentry-bot.service
```

---

## Path Resolution

After rename, all references will use `$SENTRY_HOME`. The resolution order is:

| Context | Resolution |
|---------|-----------|
| Python code | `os.environ['SENTRY_HOME']` or `os.path.expandvars('$SENTRY_HOME')` |
| Shell scripts | `${SENTRY_HOME}` or `$SENTRY_HOME` |
| Documentation | Literal `$SENTRY_HOME` (user replaces with actual path) |
| Configuration files | Environment variable substitution (Compose, systemd, Docker) |

---

## Example: Reference in Python Code

```python
# Before rename:
BOT_HOME = "$SENTRY_HOME"
TOOLS_DIR = f"{BOT_HOME}/tools"
CONFIG_FILE = f"{BOT_HOME}/config/settings.json"

# After rename with $SENTRY_HOME:
BOT_HOME = os.environ.get('SENTRY_HOME', '/home/bederf/.sentry')
TOOLS_DIR = f"{BOT_HOME}/tools"
CONFIG_FILE = f"{BOT_HOME}/config/settings.json"
```

**The rename script handles this automatically** — all hardcoded paths become `$SENTRY_HOME`.

---

## Example: Reference in Shell Script

```bash
# Before rename:
cd $SENTRY_HOME
python3 bot.py

# After rename with $SENTRY_HOME:
cd ${SENTRY_HOME:=/home/bederf/.sentry}
python3 bot.py
```

The `:=` provides a fallback if `$SENTRY_HOME` is not set.

---

## Example: Reference in Config Files

**JSON Configuration** (`config/sentry.json`):

```json
{
  "bot": {
    "name": "SENTRY",
    "home": "$SENTRY_HOME",
    "tools_dir": "$SENTRY_HOME/tools",
    "config_dir": "$SENTRY_HOME/config",
    "memory_dir": "$SENTRY_HOME/memory",
    "handlers_dir": "$SENTRY_HOME/handlers"
  },
  "api": {
    "sentinel_url": "http://localhost:9095",
    "sentry_webhooks_url": "/api/sentry-webhooks"
  },
  "ai": {
    "tier_1": "claude",
    "tier_2": ["openai", "gemini", "moonshot", "zai"],
    "tier_3": ["ollama"]
  }
}
```

**YAML Configuration** (`config/sentry.yaml`):

```yaml
bot:
  name: SENTRY
  home: $SENTRY_HOME
  dirs:
    tools: $SENTRY_HOME/tools
    config: $SENTRY_HOME/config
    memory: $SENTRY_HOME/memory
    handlers: $SENTRY_HOME/handlers
    logs: $SENTRY_HOME/logs

api:
  sentinel_url: http://localhost:9095
  sentry_webhooks: /api/sentry-webhooks

ai:
  providers:
    tier_1: [claude]
    tier_2: [openai, gemini, moonshot, zai]
    tier_3: [ollama]
```

Your configuration loader should expand `$SENTRY_HOME` at runtime:

```python
import json
import os

def load_config():
    config_path = os.path.expandvars('${SENTRY_HOME}/config/sentry.json')
    with open(config_path) as f:
        config = json.load(f)

    # Recursively expand $SENTRY_HOME in all values
    def expand_vars(obj):
        if isinstance(obj, dict):
            return {k: expand_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [expand_vars(item) for item in obj]
        elif isinstance(obj, str):
            return os.path.expandvars(obj)
        return obj

    return expand_vars(config)
```

---

## Multi-Site Deployment

For multiple buildings, use site-specific environment variables:

```bash
# Site 001
export SENTRY_HOME=/opt/sentry/site-001
export SENTRY_SITE_ID=001

# Site 002
export SENTRY_HOME=/opt/sentry/site-002
export SENTRY_SITE_ID=002

# Site 003
export SENTRY_HOME=/opt/sentry/site-003
export SENTRY_SITE_ID=003
```

Docker Compose with site-specific overrides:

```yaml
services:
  sentry-site-001:
    environment:
      SENTRY_HOME: /opt/sentry/site-001
      SENTRY_SITE_ID: "001"

  sentry-site-002:
    environment:
      SENTRY_HOME: /opt/sentry/site-002
      SENTRY_SITE_ID: "002"

  sentry-site-003:
    environment:
      SENTRY_HOME: /opt/sentry/site-003
      SENTRY_SITE_ID: "003"
```

---

## Verification

After setup, verify `$SENTRY_HOME` is correctly configured:

```bash
# Check environment variable
echo $SENTRY_HOME

# Check directory exists and is accessible
ls -la $SENTRY_HOME

# Check subdirectories
ls -la $SENTRY_HOME/tools
ls -la $SENTRY_HOME/config
ls -la $SENTRY_HOME/memory

# Check bot can find its home
python3 -c "import os; print(f'SENTRY_HOME={os.environ.get(\"SENTRY_HOME\", \"NOT SET\")}')"

# Run bot with verbose output
SENTRY_HOME=/home/bederf/.sentry python3 $SENTRY_HOME/bot.py --version
```

---

## Migration Path: VM → Jetson

**Step 1: On VM (before migration)**
```bash
# Verify bot works with $SENTRY_HOME
export SENTRY_HOME=/home/bederf/.sentry
cd $SENTRY_HOME && python3 bot.py --test
```

**Step 2: On Jetson (after copying)**
```bash
# Set different path
export SENTRY_HOME=/opt/sentry

# Copy from VM
scp -r bederf@vm:/home/bederf/.sentry /opt/sentry

# Test on Jetson
cd $SENTRY_HOME && python3 bot.py --test
```

**Step 3: Update systemd on Jetson**
```bash
# Edit service file
sudo nano /etc/systemd/system/sentry-bot.service

# Change Environment= line:
# Environment=SENTRY_HOME=/opt/sentry

# Restart
sudo systemctl daemon-reload
sudo systemctl restart sentry-bot.service
```

---

## Troubleshooting

### `$SENTRY_HOME` not set

```bash
# Symptom:
python3: can't open file '$SENTRY_HOME/bot.py': [Errno 2] No such file or directory

# Solution:
export SENTRY_HOME=/home/bederf/.sentry
# Then run bot again
```

### Path expansion not working in scripts

```bash
# Symptom:
cd: $SENTRY_HOME: No such file or directory

# Solution: Use braces for proper expansion
cd ${SENTRY_HOME}  # ✅ Correct
cd $SENTRY_HOME    # ✅ Also works in most cases
cd "${SENTRY_HOME}" # ✅ Always safe (quoted)
```

### Docker service can't find files

```bash
# Symptom:
FileNotFoundError: [Errno 2] No such file or directory: '$SENTRY_HOME/tools'

# Solution: Verify environment is passed in docker-compose.yml
environment:
  - SENTRY_HOME=/opt/sentry

# Then rebuild and restart
docker-compose up -d --build
```

### Systemd service fails to start

```bash
# Check service logs
sudo journalctl -u sentry-bot.service -n 50 --no-pager

# Verify environment file exists
sudo systemctl cat sentry-bot.service | grep Environment

# Edit and reload
sudo systemctl edit sentry-bot.service
sudo systemctl daemon-reload
sudo systemctl restart sentry-bot.service
```

---

## Reference: All Path Replacements

After rename, these hardcoded paths become `$SENTRY_HOME`:

| Before | After | Files Affected |
|--------|-------|-----------------|
| `$SENTRY_HOME` | `$SENTRY_HOME` | bot.py, tools/*.py, handlers/*.py |
| `$SENTRY_HOME` | `$SENTRY_HOME` | config files, docs |
| `$SENTRY_HOME` | `$SENTRY_HOME` | shell scripts |
| `~/.clawd` | `$SENTRY_HOME` | shell scripts, documentation |

All are replaced with the literal string `$SENTRY_HOME` so that at runtime, the environment variable is expanded.

---

**Last Updated:** 2026-02-18  
**Platform Support:** Linux (VM + Jetson), Docker Compose, Systemd services
