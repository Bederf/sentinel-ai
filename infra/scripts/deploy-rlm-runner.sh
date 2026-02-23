#!/usr/bin/env bash
# deploy-rlm-runner.sh — Deploy the SENTINEL RLM Runner service
#
# Creates user, directories, venv, symlinks, and starts systemd service.
# Must be run as root.
#
# Usage:
#   sudo bash infra/scripts/deploy-rlm-runner.sh
#
# Phase: 113-03
# See: docs/02-architecture/SENTINEL-RLM-ARCHITECTURE-SPEC-v1.0.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# --- Configuration --------------------------------------------------------

RUNNER_USER="sentinel-runner"
RUNNER_GROUP="sentinel-runner"
RUNNER_INSTALL="/opt/rlm-runner"
CASES_DIR="/var/lib/sentinel/cases"
OUTPUT_DIR="/var/lib/sentinel/rlm_out"
LOG_DIR="/var/log/rlm-runner"
SECRETS_DIR="/etc/sentinel"
PYTHON_BIN="python3.11"

# --- Preflight checks -----------------------------------------------------

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: This script must be run as root."
    exit 1
fi

if ! command -v "${PYTHON_BIN}" &>/dev/null; then
    echo "ERROR: ${PYTHON_BIN} not found. Install Python 3.11 first."
    exit 1
fi

if [[ ! -d "${REPO_ROOT}/runner" ]]; then
    echo "ERROR: ${REPO_ROOT}/runner directory not found."
    echo "       Build the runner (plan 113-01) before deploying."
    exit 1
fi

# --- Create system user ---------------------------------------------------

if ! id "${RUNNER_USER}" &>/dev/null; then
    echo "Creating system user: ${RUNNER_USER}"
    useradd --system --no-create-home --shell /usr/sbin/nologin "${RUNNER_USER}"
else
    echo "User ${RUNNER_USER} already exists."
fi

# --- Create directories ---------------------------------------------------

echo "Creating directories..."

mkdir -p "${RUNNER_INSTALL}"
mkdir -p "${CASES_DIR}"
mkdir -p "${OUTPUT_DIR}"
mkdir -p "${LOG_DIR}"
mkdir -p "${SECRETS_DIR}"

# Cases: backend (bederf) writes, runner reads
chown bederf:"${RUNNER_GROUP}" "${CASES_DIR}"
chmod 750 "${CASES_DIR}"

# Output: runner writes, backend reads
chown "${RUNNER_USER}":"${RUNNER_GROUP}" "${OUTPUT_DIR}"
chmod 750 "${OUTPUT_DIR}"

# Logs: runner writes
chown "${RUNNER_USER}":"${RUNNER_GROUP}" "${LOG_DIR}"
chmod 750 "${LOG_DIR}"

# Secrets: root-owned, group-readable by runner
chown root:"${RUNNER_GROUP}" "${SECRETS_DIR}"
chmod 750 "${SECRETS_DIR}"

# --- Venv setup (with rollback support) -----------------------------------

VENV_DIR="${RUNNER_INSTALL}/venv"

if [[ -d "${VENV_DIR}" ]]; then
    echo "Backing up existing venv to venv_prev..."
    rm -rf "${RUNNER_INSTALL}/venv_prev"
    mv "${VENV_DIR}" "${RUNNER_INSTALL}/venv_prev"
fi

echo "Creating Python venv..."
"${PYTHON_BIN}" -m venv "${VENV_DIR}"

echo "Installing runner dependencies..."
"${VENV_DIR}/bin/pip" install --upgrade pip --quiet
"${VENV_DIR}/bin/pip" install -r "${REPO_ROOT}/runner/requirements.txt" --quiet

# --- Symlink runner code --------------------------------------------------

echo "Symlinking runner app..."
ln -sfn "${REPO_ROOT}/runner/app" "${RUNNER_INSTALL}/app"

# --- Environment file template --------------------------------------------

ENV_EXAMPLE="${SECRETS_DIR}/rlm-runner.env.example"
if [[ ! -f "${ENV_EXAMPLE}" ]]; then
    echo "Creating env file template: ${ENV_EXAMPLE}"
    cat > "${ENV_EXAMPLE}" <<'ENVEOF'
# RLM Runner environment variables
# Copy to /etc/sentinel/rlm-runner.env and fill in values.
#
# Inference
MODEL_BASE_URL=http://127.0.0.1:11434/v1
MODEL_NAME=phi3:mini
EMBED_MODEL=nomic-embed-text
#
# Budget
RLM_MAX_RUNTIME_SECONDS=120
RLM_MAX_RECURSION_DEPTH=6
RLM_MAX_TOKENS_PER_CALL=1200
#
# Paths
CASES_ROOT=/var/lib/sentinel/cases
OUTPUT_ROOT=/var/lib/sentinel/rlm_out
#
# Logging
LOG_LEVEL=INFO
ENVEOF
    chown root:"${RUNNER_GROUP}" "${ENV_EXAMPLE}"
    chmod 640 "${ENV_EXAMPLE}"
fi

# --- Install systemd unit ------------------------------------------------

echo "Installing systemd unit..."
cp "${REPO_ROOT}/infra/systemd/rlm-runner.service" /etc/systemd/system/rlm-runner.service
systemctl daemon-reload
systemctl enable rlm-runner

echo "Starting rlm-runner service..."
systemctl start rlm-runner

# --- Health check ---------------------------------------------------------

echo "Waiting 3 seconds for startup..."
sleep 3

if curl -sf http://127.0.0.1:8010/health >/dev/null 2>&1; then
    echo "SUCCESS: RLM Runner is healthy."
else
    echo "WARN: Runner health check failed. Check: journalctl -u rlm-runner -n 50"
fi

echo ""
echo "Deployment complete."
echo "  Service:  systemctl status rlm-runner"
echo "  Logs:     journalctl -u rlm-runner -f"
echo "  Rollback: systemctl stop rlm-runner && mv ${RUNNER_INSTALL}/venv_prev ${VENV_DIR} && systemctl start rlm-runner"
