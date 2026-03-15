"""Tests for the POPIA evidence pack service."""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from app.services.popia_evidence_pack_service import POPIAEvidencePackService


@pytest.fixture()
def tmp_data(tmp_path: Path):
    """Create temporary data files and return configured service."""
    consent_path = tmp_path / "consent_records.json"
    retention_path = tmp_path / "popia_retention_runs.json"
    privacy_path = tmp_path / "privacy_requests.json"
    packs_path = tmp_path / "popia_evidence_packs.json"

    # Seed consent records
    consent_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "records": [
                    {
                        "record_id": "r1",
                        "consent_given": True,
                        "withdrawn_at": None,
                        "given_at": "2026-03-01T10:00:00+00:00",
                    },
                    {
                        "record_id": "r2",
                        "consent_given": True,
                        "withdrawn_at": "2026-03-15T12:00:00+00:00",
                        "given_at": "2026-01-01T10:00:00+00:00",
                    },
                    {
                        "record_id": "r3",
                        "consent_given": False,
                        "withdrawn_at": None,
                        "given_at": "2026-02-01T10:00:00+00:00",
                    },
                ],
            }
        )
    )

    # Seed retention runs
    retention_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "runs": [
                    {
                        "executed_at": "2026-03-04T12:00:00+00:00",
                        "total_reviewed": 100,
                        "total_deleted": 5,
                        "categories": [
                            {"category": "consent_records", "records_overdue": 2},
                        ],
                    },
                    {
                        "executed_at": "2026-02-04T12:00:00+00:00",
                        "total_reviewed": 50,
                        "total_deleted": 1,
                        "categories": [],
                    },
                ],
            }
        )
    )

    # Seed privacy requests
    privacy_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "requests": [
                    {
                        "request_id": "p1",
                        "request_type": "access",
                        "status": "fulfilled",
                        "created_at": "2026-03-01T09:00:00+00:00",
                        "closed_at": "2026-03-05T09:00:00+00:00",
                        "due_at": "2026-03-31T09:00:00+00:00",
                    },
                    {
                        "request_id": "p2",
                        "request_type": "deletion",
                        "status": "pending",
                        "created_at": "2026-03-10T09:00:00+00:00",
                        "closed_at": None,
                        "due_at": "2026-04-09T09:00:00+00:00",
                    },
                    {
                        "request_id": "p3",
                        "request_type": "access",
                        "status": "fulfilled",
                        "created_at": "2026-03-15T09:00:00+00:00",
                        "closed_at": "2026-04-20T09:00:00+00:00",  # 36 days — over SLA
                        "due_at": "2026-04-14T09:00:00+00:00",
                    },
                    {
                        "request_id": "p4",
                        "request_type": "access",
                        "status": "fulfilled",
                        "created_at": "2026-02-10T09:00:00+00:00",  # Not in March
                        "closed_at": "2026-02-12T09:00:00+00:00",
                        "due_at": "2026-03-12T09:00:00+00:00",
                    },
                ],
            }
        )
    )

    svc = POPIAEvidencePackService(
        consent_path=consent_path,
        retention_path=retention_path,
        privacy_path=privacy_path,
        packs_path=packs_path,
    )
    return svc, packs_path


@pytest.mark.asyncio
async def test_generate_monthly_pack_returns_all_sections(tmp_data):
    svc, _ = tmp_data
    pack = await svc.generate_monthly_pack(2026, 3)

    assert "metadata" in pack
    assert "consent_metrics" in pack
    assert "retention_enforcement" in pack
    assert "dsr_completion" in pack
    assert "access_control_audit" in pack

    assert pack["metadata"]["period"] == "2026-03"
    assert pack["metadata"]["version"] == "1.0"


@pytest.mark.asyncio
async def test_generate_monthly_pack_handles_empty_data(tmp_path):
    """Empty JSON files should produce zeros, not crash."""
    consent = tmp_path / "consent.json"
    retention = tmp_path / "retention.json"
    privacy = tmp_path / "privacy.json"
    packs = tmp_path / "packs.json"

    for p in (consent, retention, privacy):
        p.write_text("{}")

    svc = POPIAEvidencePackService(
        consent_path=consent,
        retention_path=retention,
        privacy_path=privacy,
        packs_path=packs,
    )
    pack = await svc.generate_monthly_pack(2026, 3)

    assert pack["consent_metrics"]["total_active_consents"] == 0
    assert pack["consent_metrics"]["withdrawals_in_period"] == 0
    assert pack["retention_enforcement"]["runs_in_period"] == 0
    assert pack["dsr_completion"]["requests_received"] == 0


@pytest.mark.asyncio
async def test_consent_withdrawal_rate_calculation(tmp_data):
    svc, _ = tmp_data
    pack = await svc.generate_monthly_pack(2026, 3)

    cm = pack["consent_metrics"]
    # 1 withdrawal in March, 3 total records -> rate = 1/3
    assert cm["withdrawals_in_period"] == 1
    assert abs(cm["withdrawal_rate"] - round(1 / 3, 4)) < 0.001


@pytest.mark.asyncio
async def test_dsr_sla_adherence_calculation(tmp_data):
    svc, _ = tmp_data
    pack = await svc.generate_monthly_pack(2026, 3)

    dsr = pack["dsr_completion"]
    # 3 requests in March (p1, p2, p3); 2 fulfilled, 1 pending
    assert dsr["requests_received"] == 3
    assert dsr["requests_completed"] == 2
    assert dsr["requests_pending"] == 1
    # p1: 4 days (within SLA), p3: 36 days (over SLA) -> 1/2 = 50%
    assert dsr["sla_adherence_pct"] == 50.0
    # avg = (4 + 36) / 2 = 20.0
    assert dsr["avg_completion_days"] == 20.0


@pytest.mark.asyncio
async def test_save_pack_appends_and_caps_at_24(tmp_data):
    svc, packs_path = tmp_data

    # Save 25 packs
    for i in range(25):
        await svc.save_pack({"metadata": {"period": f"2024-{i + 1:02d}"}})

    data = json.loads(packs_path.read_text())
    assert len(data["packs"]) == 24
    # First pack should be i=1 (FIFO dropped i=0)
    assert data["packs"][0]["metadata"]["period"] == "2024-02"


@pytest.mark.asyncio
async def test_get_latest_pack_returns_none_when_empty(tmp_data):
    svc, _ = tmp_data
    result = await svc.get_latest_pack()
    assert result is None
