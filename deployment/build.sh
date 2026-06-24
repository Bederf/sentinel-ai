#!/usr/bin/env bash
# Build SENTINEL backend into a PyInstaller single-file executable.
# Output: deployment/dist/sentinel-backend
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"
DIST_DIR="$SCRIPT_DIR/dist"
VENV_PYTHON="${VENV_PYTHON:-$REPO_ROOT/backend/venv/bin/python}"

echo "=== SENTINEL Backend PyInstaller Build ==="
echo "Python: $($VENV_PYTHON --version)"
echo "PyInstaller: $($VENV_PYTHON -m PyInstaller --version)"

rm -rf "$BUILD_DIR" "$DIST_DIR"
mkdir -p "$DIST_DIR"

cd "$REPO_ROOT/backend"

$VENV_PYTHON -m PyInstaller \
    --name sentinel-backend \
    --onefile \
    --distpath "$DIST_DIR" \
    --workpath "$BUILD_DIR" \
    --add-data "$REPO_ROOT/backend/app/data:app/data" \
    --add-data "$REPO_ROOT/backend/app/data/modules:app/data/modules" \
    --add-data "$REPO_ROOT/backend/app/data/sites:app/data/sites" \
    --add-data "$REPO_ROOT/backend/app/data/demo_workflow:app/data/demo_workflow" \
    --hidden-import "app.main" \
    --hidden-import "app.config.settings" \
    --hidden-import "app.startup.events" \
    --hidden-import "app.startup.middleware" \
    --hidden-import "app.startup.routes" \
    --hidden-import "app.database.supabase_client" \
    --hidden-import "app.services.background_scheduler" \
    --hidden-import "app.services.simbiot_service" \
    --hidden-import "app.services.cache_service" \
    --hidden-import "app.services.token_blacklist_service" \
    --hidden-import "app.services.embedding_service" \
    --hidden-import "app.services.rag_auto_loader" \
    --hidden-import "app.services.sentry_auth_service" \
    --hidden-import "app.services.event_subscribers" \
    --hidden-import "app.services.n8n_event_subscriber" \
    --hidden-import "app.services.sentry_event_subscriber" \
    --hidden-import "app.services.dashboard_gen_subscriber" \
    --hidden-import "app.services.event_bus_subscribers" \
    --hidden-import "app.services.module_registry_service" \
    --hidden-import "app.services.autonomous_decision_engine" \
    --hidden-import "app.services.escalation_engine" \
    --hidden-import "app.services.safety_boundary_service" \
    --hidden-import "app.services.ml_registry_sync" \
    --hidden-import "app.services.audit_logger" \
    --hidden-import "app.services.space_mqtt_listener" \
    --hidden-import "app.services.fuel_mqtt_listener" \
    --hidden-import "app.services.notification_tasks" \
    --hidden-import "app.core.site_resolver" \
    --hidden-import "app.api.devices" \
    --hidden-import "app.api.health" \
    --hidden-import "app.api.decisions" \
    --hidden-import "app.api.events" \
    --hidden-import "app.api.cockpit" \
    --hidden-import "app.api.buildings" \
    --hidden-import "app.api.chat" \
    --hidden-import "app.api.modules" \
    --hidden-import "app.api.simbiot" \
    --hidden-import "app.api.sentry_webhooks" \
    --hidden-import "app.api.niagara_discovery" \
    --hidden-import "app.migrations.runner" \
    --hidden-import "app.services.decision_moment_aggregator" \
    --hidden-import "app.database.repositories.user_repository" \
    --hidden-import "app.database.repositories.system_settings_repository" \
    --hidden-import "app.logging_config" \
    --hidden-import "uvicorn.logging" \
    --hidden-import "uvicorn.loops.auto" \
    --hidden-import "uvicorn.protocols.http.auto" \
    --hidden-import "uvicorn.lifespan.on" \
    --exclude-module "tensorflow" \
    --exclude-module "torch" \
    --exclude-module "docling" \
    --exclude-module "BAC0" \
    --exclude-module "pymupdf" \
    --exclude-module "matplotlib" \
    --collect-all "supabase" \
    --runtime-hook "$SCRIPT_DIR/runtime_hook.py" \
    run_sentinel.py

echo ""
echo "=== Build complete ==="
ls -lh "$DIST_DIR/"
