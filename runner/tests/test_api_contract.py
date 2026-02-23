"""API contract tests — verify endpoints match the locked spec (Section 5)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import AsyncClient


class TestHealthEndpoint:
    """GET /health contract."""

    @pytest.mark.asyncio
    async def test_health_returns_200(self, async_client: AsyncClient) -> None:
        """GET /health returns 200 with status, version, ollama_available."""
        resp = await async_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "1.0.0"
        assert "ollama_available" in data


class TestSubmitRun:
    """POST /run contract."""

    @pytest.mark.asyncio
    async def test_submit_run_valid(self, async_client: AsyncClient, mock_case_dir: Path) -> None:
        """POST /run with valid case returns 200, run_id, status='queued'."""
        resp = await async_client.post("/run", json={
            "case_id": "TEST001",
            "question": "Summarise the evidence",
            "model": "phi3:mini",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data
        assert data["status"] == "queued"
        assert data["run_id"].startswith("TEST001_")

    @pytest.mark.asyncio
    async def test_submit_run_invalid_model(self, async_client: AsyncClient, mock_case_dir: Path) -> None:
        """POST /run with unknown model returns 400."""
        resp = await async_client.post("/run", json={
            "case_id": "TEST001",
            "question": "test",
            "model": "gpt-4-turbo",
        })
        assert resp.status_code == 400
        assert "allowlist" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_submit_run_missing_case(self, async_client: AsyncClient) -> None:
        """POST /run with nonexistent case_id returns 404."""
        resp = await async_client.post("/run", json={
            "case_id": "NONEXISTENT_CASE",
            "question": "test",
        })
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_submit_run_default_model(self, async_client: AsyncClient, mock_case_dir: Path) -> None:
        """POST /run without model field uses default from config."""
        resp = await async_client.post("/run", json={
            "case_id": "TEST001",
            "question": "Summarise",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"


class TestGetResult:
    """GET /runs/{run_id} contract."""

    @pytest.mark.asyncio
    async def test_get_result_not_found(self, async_client: AsyncClient) -> None:
        """GET /runs/nonexistent returns 404."""
        resp = await async_client.get("/runs/nonexistent_run_id")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_result_after_submit(self, async_client: AsyncClient, mock_case_dir: Path) -> None:
        """GET /runs/{run_id} returns result with status after submit."""
        # Submit
        submit_resp = await async_client.post("/run", json={
            "case_id": "TEST001",
            "question": "test",
        })
        run_id = submit_resp.json()["run_id"]

        # Get result
        result_resp = await async_client.get(f"/runs/{run_id}")
        assert result_resp.status_code == 200
        data = result_resp.json()
        assert data["status"] == "queued"
        assert "summary" in data
        assert "findings" in data
        assert "trajectory" in data


class TestGetTrace:
    """GET /runs/{run_id}/trace contract."""

    @pytest.mark.asyncio
    async def test_get_trace_not_found(self, async_client: AsyncClient) -> None:
        """GET /runs/{nonexistent}/trace returns 404."""
        resp = await async_client.get("/runs/nonexistent_run_id/trace")
        assert resp.status_code == 404
