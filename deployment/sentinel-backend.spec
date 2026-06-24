# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

DEPLOYMENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = DEPLOYMENT_DIR.parent
BACKEND_ENTRY = REPO_ROOT / "backend" / "run_sentinel.py"
RUNTIME_HOOK = DEPLOYMENT_DIR / "runtime_hook.py"

datas = [
    ("app/data", "app/data"),
    ("app/data/modules", "app/data/modules"),
    ("app/data/sites", "app/data/sites"),
    ("app/data/demo_workflow", "app/data/demo_workflow"),
]
binaries = []
hiddenimports = [
    "app.main",
    "app.config.settings",
    "app.startup.events",
    "app.startup.middleware",
    "app.startup.routes",
    "app.database.supabase_client",
    "app.services.background_scheduler",
    "app.services.simbiot_service",
    "app.services.cache_service",
    "app.services.token_blacklist_service",
    "app.services.embedding_service",
    "app.services.rag_auto_loader",
    "app.services.sentry_auth_service",
    "app.services.event_subscribers",
    "app.services.n8n_event_subscriber",
    "app.services.sentry_event_subscriber",
    "app.services.dashboard_gen_subscriber",
    "app.services.event_bus_subscribers",
    "app.services.module_registry_service",
    "app.services.autonomous_decision_engine",
    "app.services.escalation_engine",
    "app.services.safety_boundary_service",
    "app.services.ml_registry_sync",
    "app.services.audit_logger",
    "app.services.space_mqtt_listener",
    "app.services.fuel_mqtt_listener",
    "app.services.notification_tasks",
    "app.core.site_resolver",
    "app.api.devices",
    "app.api.health",
    "app.api.decisions",
    "app.api.events",
    "app.api.cockpit",
    "app.api.buildings",
    "app.api.chat",
    "app.api.modules",
    "app.api.simbiot",
    "app.api.sentry_webhooks",
    "app.api.niagara_discovery",
    "app.migrations.runner",
    "app.services.decision_moment_aggregator",
    "app.database.repositories.user_repository",
    "app.database.repositories.system_settings_repository",
    "app.logging_config",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.lifespan.on",
]
tmp_ret = collect_all("supabase")
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

a = Analysis(
    [str(BACKEND_ENTRY)],
    pathex=[str(REPO_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(RUNTIME_HOOK)],
    excludes=["tensorflow", "torch", "docling", "BAC0", "pymupdf", "matplotlib"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="sentinel-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
