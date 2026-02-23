"""Shared fixtures for runner tests."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# Environment overrides — MUST be set before importing app modules
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _env_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Override filesystem paths to use tmp_path for all tests.

    Patches both the settings singleton AND the run_manager singleton
    so that all module-level references see the test's temp directories.
    """
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    output_dir = tmp_path / "rlm_out"
    output_dir.mkdir()

    monkeypatch.setenv("CASES_DIR", str(cases_dir))
    monkeypatch.setenv("OUTPUT_DIR", str(output_dir))

    # Reload settings to pick up overridden env vars
    from app.config import Settings

    new_settings = Settings()
    monkeypatch.setattr("app.config.settings", new_settings)

    # Patch settings everywhere it has been imported as a module-level name
    monkeypatch.setattr("app.api.runs.settings", new_settings)

    # Patch the run_manager singleton — both its settings reference and output_dir
    from app.services.run_manager import RunManager

    new_rm = RunManager(output_dir=str(output_dir))
    monkeypatch.setattr("app.services.run_manager.run_manager", new_rm)
    monkeypatch.setattr("app.services.run_manager.settings", new_settings)


# ---------------------------------------------------------------------------
# Mock case directory
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_case_dir(tmp_path: Path) -> Path:
    """Create a case folder with manifest.json and sample evidence files.

    Uses the same tmp_path as _env_overrides, so case appears under CASES_DIR.
    """
    case_id = "TEST001"
    case_dir = tmp_path / "cases" / case_id
    evidence_dir = case_dir / "evidence"
    logs_dir = evidence_dir / "logs"
    documents_dir = evidence_dir / "documents"
    media_dir = evidence_dir / "media"
    exports_dir = evidence_dir / "exports"

    for d in [logs_dir, documents_dir, media_dir, exports_dir]:
        d.mkdir(parents=True)

    # Write manifest
    manifest = {
        "case_id": case_id,
        "created_at": "2026-02-23T10:00:00Z",
        "description": "Test case for unit tests",
        "evidence_files": [
            {"name": "events.json", "category": "exports"},
            {"name": "report.csv", "category": "exports"},
            {"name": "scan.pdf", "category": "documents"},
            {"name": "notes.txt", "category": "documents"},
        ],
    }
    with open(case_dir / "manifest.json", "w") as f:
        json.dump(manifest, f)

    # Create sample evidence files
    (exports_dir / "events.json").write_text('{"events": []}')
    (exports_dir / "report.csv").write_text("col1,col2\n1,2\n")
    (documents_dir / "scan.pdf").write_bytes(b"%PDF-1.4 stub")
    (documents_dir / "notes.txt").write_text("Some notes here.")

    return case_dir


# ---------------------------------------------------------------------------
# Async HTTP client for API tests
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def async_client() -> AsyncClient:
    """httpx AsyncClient wrapping the runner ASGI app."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


# ---------------------------------------------------------------------------
# RunManager with tmp output dir
# ---------------------------------------------------------------------------

@pytest.fixture
def run_manager_instance(tmp_path: Path) -> "RunManager":
    """RunManager with output_dir pointed at tmp_path."""
    from app.services.run_manager import RunManager

    output_dir = tmp_path / "rlm_out"
    output_dir.mkdir(exist_ok=True)
    return RunManager(output_dir=str(output_dir))
