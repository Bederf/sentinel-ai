"""Tests for ServiceSheetFindingsService."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.service_sheet_findings_service import (
    ServiceSheetFindingsService,
    _severity_from_checklist_value,
    _severity_from_reading,
    get_service_sheet_findings_service,
)


class TestSeverityHelpers:
    def test_checklist_severity_critical(self):
        assert _severity_from_checklist_value("critical") == "critical"
        assert _severity_from_checklist_value("fail") == "critical"
        assert _severity_from_checklist_value("danger") == "critical"

    def test_checklist_severity_warning(self):
        assert _severity_from_checklist_value("low") == "warning"
        assert _severity_from_checklist_value("warning") == "warning"
        assert _severity_from_checklist_value("needs_attention") == "warning"

    def test_checklist_severity_normal(self):
        assert _severity_from_checklist_value("good") == "normal"
        assert _severity_from_checklist_value("ok") == "normal"
        assert _severity_from_checklist_value("pass") == "normal"

    def test_reading_severity_within_range(self):
        assert _severity_from_reading(50.0, 40.0, 60.0) == "normal"
        assert _severity_from_reading(40.0, 40.0, 60.0) == "normal"
        assert _severity_from_reading(60.0, 40.0, 60.0) == "normal"

    def test_reading_severity_warning(self):
        # 10% overshoot (62 vs 60)
        assert _severity_from_reading(62.0, 40.0, 60.0) == "warning"
        assert _severity_from_reading(38.0, 40.0, 60.0) == "warning"

    def test_reading_severity_critical(self):
        # >20% overshoot
        assert _severity_from_reading(80.0, 40.0, 60.0) == "critical"
        assert _severity_from_reading(20.0, 40.0, 60.0) == "critical"


class TestServiceSheetFindingsService:
    @pytest.fixture
    def svc(self):
        service = ServiceSheetFindingsService()
        service._wo_repo = MagicMock()
        service._sr_repo = MagicMock()
        service._eq_repo = MagicMock()
        return service

    @pytest.mark.asyncio
    async def test_no_findings_when_all_normal(self, svc):
        svc._eq_repo.get_by_id.return_value = {
            "id": "eq-1",
            "site_id": "site-1",
            "name": "Chiller 1",
            "health_score": 80,
        }

        extracted = {
            "checklists": {"oil_level": {"value": "good"}, "belt": {"value": "ok"}},
            "readings": {"temperature": {"value": 45.0, "unit": "C"}},
            "notes": "All normal",
        }

        report = await svc.classify_and_flag_findings(
            extracted_data=extracted,
            equipment_code="S002-CHILLER-B1-001",
            document_id="doc-1",
        )

        assert report["findings"] == []
        assert report["created_work_orders"] == []
        assert report["added_observations"] == []
        svc._wo_repo.create_work_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_critical_checklist_creates_work_order(self, svc):
        svc._eq_repo.get_by_id.return_value = {
            "id": "eq-1",
            "site_id": "site-1",
            "name": "Chiller 1",
            "health_score": 80,
        }
        svc._wo_repo.create_work_order = AsyncMock(return_value={"code": "WO-2026-0100"})
        svc._eq_repo.update.return_value = {"health_score": 75}

        extracted = {
            "checklists": {
                "compressor_oil": {"value": "critical"},
                "belt": {"value": "ok"},
            },
        }

        report = await svc.classify_and_flag_findings(
            extracted_data=extracted,
            equipment_code="S002-CHILLER-B1-001",
            document_id="doc-1",
        )

        assert len(report["findings"]) == 1
        assert report["findings"][0]["severity"] == "critical"
        assert report["created_work_orders"] == ["WO-2026-0100"]
        svc._wo_repo.create_work_order.assert_awaited_once()
        call_args = svc._wo_repo.create_work_order.await_args[0][0]
        assert call_args["priority"] == "urgent"
        assert "compressor_oil" in call_args["title"]

    @pytest.mark.asyncio
    async def test_warning_checklist_adds_observation(self, svc):
        svc._eq_repo.get_by_id.return_value = {
            "id": "eq-1",
            "site_id": "site-1",
            "name": "Chiller 1",
            "health_score": 80,
        }
        svc._sr_repo.list = AsyncMock(return_value=[{"id": "sr-1", "updated_at": "2026-01-01T00:00:00"}])
        svc._sr_repo.add_observation = AsyncMock(return_value={"id": "obs-1"})
        svc._eq_repo.update.return_value = {"health_score": 78}

        extracted = {
            "checklists": {
                "belt": {"value": "low"},
            },
        }

        report = await svc.classify_and_flag_findings(
            extracted_data=extracted,
            equipment_code="S002-CHILLER-B1-001",
            document_id="doc-1",
        )

        assert len(report["findings"]) == 1
        assert report["findings"][0]["severity"] == "warning"
        assert report["added_observations"] == ["obs-1"]
        svc._sr_repo.add_observation.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_critical_reading_creates_work_order(self, svc):
        svc._eq_repo.get_by_id.return_value = {
            "id": "eq-1",
            "site_id": "site-1",
            "name": "Chiller 1",
            "health_score": 80,
            "specs": {"tolerances": {"compressor_current": {"min": 0, "max": 80}}},
        }
        svc._wo_repo.create_work_order = AsyncMock(return_value={"code": "WO-2026-0101"})
        svc._eq_repo.update.return_value = {"health_score": 70}

        extracted = {
            "readings": {
                "compressor_current": {"value": 120.0, "unit": "A"},
            },
        }

        report = await svc.classify_and_flag_findings(
            extracted_data=extracted,
            equipment_code="S002-CHILLER-B1-001",
            document_id="doc-1",
        )

        assert len(report["findings"]) == 1
        assert report["findings"][0]["severity"] == "critical"
        assert report["created_work_orders"] == ["WO-2026-0101"]

    @pytest.mark.asyncio
    async def test_notes_with_critical_keyword_adds_observation(self, svc):
        svc._eq_repo.get_by_id.return_value = {
            "id": "eq-1",
            "site_id": "site-1",
            "name": "Chiller 1",
            "health_score": 80,
        }
        svc._sr_repo.list = AsyncMock(return_value=[{"id": "sr-1", "updated_at": "2026-01-01T00:00:00"}])
        svc._sr_repo.add_observation = AsyncMock(return_value={"id": "obs-2"})
        svc._eq_repo.update.return_value = {"health_score": 78}

        extracted = {
            "checklists": {"oil_level": {"value": "good"}},
            "notes": "There is a critical leak in the compressor housing.",
        }

        report = await svc.classify_and_flag_findings(
            extracted_data=extracted,
            equipment_code="S002-CHILLER-B1-001",
            document_id="doc-1",
        )

        note_finding = [f for f in report["findings"] if f["source"] == "notes"]
        assert len(note_finding) == 1
        assert note_finding[0]["severity"] == "warning"
        assert report["added_observations"] == ["obs-2"]

    @pytest.mark.asyncio
    async def test_equipment_not_found_returns_error(self, svc):
        svc._eq_repo.get_by_id.return_value = None

        report = await svc.classify_and_flag_findings(
            extracted_data={"checklists": {"oil": {"value": "critical"}}},
            equipment_code="UNKNOWN-EQ",
            document_id="doc-1",
        )

        assert report["error"] == "Equipment not found: UNKNOWN-EQ"
        assert report["findings"] == []

    @pytest.mark.asyncio
    async def test_health_score_clamped_at_zero(self, svc):
        svc._eq_repo.get_by_id.return_value = {
            "id": "eq-1",
            "site_id": "site-1",
            "name": "Chiller 1",
            "health_score": 5,
        }
        svc._wo_repo.create_work_order = AsyncMock(return_value={"code": "WO-2026-0102"})
        svc._eq_repo.update.return_value = {"health_score": 0}

        extracted = {
            "checklists": {
                "a": {"value": "critical"},
                "b": {"value": "critical"},
                "c": {"value": "critical"},
            },
        }

        report = await svc.classify_and_flag_findings(
            extracted_data=extracted,
            equipment_code="S002-CHILLER-B1-001",
            document_id="doc-1",
        )

        assert report["health_changes"][0]["new_health"] == 0
        assert report["health_changes"][0]["delta"] == -15

    def test_singleton(self):
        s1 = get_service_sheet_findings_service()
        s2 = get_service_sheet_findings_service()
        assert s1 is s2
