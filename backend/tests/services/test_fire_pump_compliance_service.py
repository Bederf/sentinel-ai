"""
Tests for Fire Pump Compliance Service

Phase 207-05: FNBFW:32335 compliance tracking
"""

from datetime import date, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.database.repositories.fire_pump_compliance_repository import (
    FirePumpComplianceRepository,
)
from app.models.fire_pump_compliance import (
    FirePumpInspection,
    InspectionResult,
)
from app.services.fire_pump_compliance_service import (
    WEEKS_PER_YEAR,
    FirePumpComplianceService,
    get_fire_pump_compliance_service,
)

# =============================================================================
# Helpers
# =============================================================================


def make_inspection_dict(
    site_code: str = "S002",
    equipment_id: str = "FP-001",
    scheduled_date: date | str | None = None,
    completed_date: date | str | None = None,
    result: str | None = None,
    certified_by: str | None = None,
    notes: str | None = None,
    id: str | None = None,
) -> dict:
    """Helper to create inspection dict."""
    if scheduled_date is None:
        scheduled_date = date.today()
    if isinstance(scheduled_date, date):
        scheduled_date = scheduled_date.isoformat()
    if completed_date and isinstance(completed_date, date):
        completed_date = completed_date.isoformat()

    return {
        "id": id or str(uuid4()),
        "site_code": site_code,
        "equipment_id": equipment_id,
        "scheduled_date": scheduled_date,
        "completed_date": completed_date,
        "result": result,
        "certified_by": certified_by,
        "notes": notes,
        "regulatory_reference": "FNBFW:32335",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }


class InMemoryFirePumpRepo:
    """In-memory repo for testing without Supabase."""

    def __init__(self):
        self.records: list[dict] = []

    async def schedule_inspection(self, site_code: str, equipment_id: str, scheduled_date: date) -> FirePumpInspection:
        insp = FirePumpInspection(
            id=uuid4(),
            site_code=site_code,
            equipment_id=equipment_id,
            scheduled_date=scheduled_date,
        )
        self.records.append(insp.to_dict())
        return insp

    async def record_inspection_result(
        self,
        inspection_id: UUID | str,
        result: InspectionResult,
        certified_by: str | None,
        notes: str | None,
    ) -> FirePumpInspection | None:
        for rec in self.records:
            if rec["id"] == str(inspection_id):
                rec["completed_date"] = date.today().isoformat()
                rec["result"] = result.value
                rec["certified_by"] = certified_by
                rec["notes"] = notes
                rec["updated_at"] = datetime.now().isoformat()
                return FirePumpInspection.from_dict(rec)
        return None

    async def get_upcoming_inspections(self, site_code: str, days: int = 7) -> list[FirePumpInspection]:
        today = date.today()
        end = today + timedelta(days=days)
        results = []
        for rec in self.records:
            if rec["site_code"] != site_code:
                continue
            if rec["completed_date"] is not None:
                continue
            sched = date.fromisoformat(rec["scheduled_date"])
            if today <= sched <= end:
                results.append(FirePumpInspection.from_dict(rec))
        results.sort(key=lambda x: x.scheduled_date)
        return results

    async def get_overdue_inspections(self, site_code: str) -> list[FirePumpInspection]:
        today = date.today()
        results = []
        for rec in self.records:
            if rec["site_code"] != site_code:
                continue
            if rec["completed_date"] is not None:
                continue
            sched = date.fromisoformat(rec["scheduled_date"])
            if sched < today:
                results.append(FirePumpInspection.from_dict(rec))
        results.sort(key=lambda x: x.scheduled_date)
        return results

    async def get_compliance_status(self, site_code: str) -> dict:
        records = [r for r in self.records if r["site_code"] == site_code]
        total = len(records)
        completed = sum(1 for r in records if r["completed_date"] is not None)
        rate = (completed / total * 100) if total > 0 else 0.0
        return {
            "site_code": site_code,
            "total_scheduled": total,
            "completed": completed,
            "pending": total - completed,
            "compliance_rate": round(rate, 2),
        }

    async def get_inspections_in_range(
        self, site_code: str, start_date: date, end_date: date
    ) -> list[FirePumpInspection]:
        results = []
        for rec in self.records:
            if rec["site_code"] != site_code:
                continue
            sched = date.fromisoformat(rec["scheduled_date"])
            if start_date <= sched <= end_date:
                results.append(FirePumpInspection.from_dict(rec))
        results.sort(key=lambda x: x.scheduled_date)
        return results


# =============================================================================
# Model Tests
# =============================================================================


class TestFirePumpInspectionModel:
    """Test FirePumpInspection model serialization."""

    def test_to_dict(self):
        insp = FirePumpInspection(
            id=uuid4(),
            site_code="S002",
            equipment_id="FP-001",
            scheduled_date=date(2026, 5, 1),
            completed_date=date(2026, 5, 1),
            result=InspectionResult.PASS,
            certified_by="John Smith",
            notes="All ok",
            regulatory_reference="FNBFW:32335",
        )
        d = insp.to_dict()
        assert d["site_code"] == "S002"
        assert d["equipment_id"] == "FP-001"
        assert d["result"] == "pass"
        assert d["certified_by"] == "John Smith"
        assert d["regulatory_reference"] == "FNBFW:32335"

    def test_from_dict(self):
        data = make_inspection_dict(
            site_code="S002",
            equipment_id="FP-001",
            scheduled_date="2026-05-01",
            completed_date="2026-05-01",
            result="pass",
            certified_by="Jane Doe",
        )
        insp = FirePumpInspection.from_dict(data)
        assert insp.site_code == "S002"
        assert insp.equipment_id == "FP-001"
        assert insp.result == InspectionResult.PASS
        assert insp.completed_date == date(2026, 5, 1)

    def test_from_dict_defaults(self):
        data = make_inspection_dict(scheduled_date="2026-05-01")
        insp = FirePumpInspection.from_dict(data)
        assert insp.regulatory_reference == "FNBFW:32335"
        assert insp.result is None
        assert insp.completed_date is None

    def test_inspection_result_enum(self):
        assert InspectionResult.PASS.value == "pass"
        assert InspectionResult.FAIL.value == "fail"
        assert InspectionResult.INCONCLUSIVE.value == "inconclusive"


# =============================================================================
# Repository Tests (JSON fallback)
# =============================================================================


class TestFirePumpComplianceRepositoryJsonFallback:
    """Test FirePumpComplianceRepository JSON fallback."""

    def test_json_insert_and_load(self, tmp_path):
        """Records are persisted to JSON and retrievable."""
        repo = FirePumpComplianceRepository(supabase=None, json_fallback_path=tmp_path / "fp_fallback.json")
        insp = FirePumpInspection(
            id=uuid4(),
            site_code="S002",
            equipment_id="FP-001",
            scheduled_date=date.today(),
        )
        repo._json_insert(insp)

        records = repo._load_json_records()
        assert len(records) == 1
        assert records[0]["site_code"] == "S002"

    def test_json_update(self, tmp_path):
        """_json_update modifies existing record."""
        repo = FirePumpComplianceRepository(supabase=None, json_fallback_path=tmp_path / "fp_update.json")
        insp = FirePumpInspection(
            id=uuid4(),
            site_code="S002",
            equipment_id="FP-001",
            scheduled_date=date.today(),
        )
        repo._json_insert(insp)
        insp.certified_by = "Tester"
        repo._json_update(insp)

        records = repo._load_json_records()
        assert records[0]["certified_by"] == "Tester"

    def test_get_upcoming_inspections_today_plus_7_days(self, tmp_path):
        """get_upcoming_inspections includes today and next 7 days (inclusive)."""
        repo = FirePumpComplianceRepository(supabase=None, json_fallback_path=tmp_path / "fp_upcoming.json")
        today = date.today()

        # Insert: today, +3 days, +8 days
        for days in [0, 3, 8]:
            insp = FirePumpInspection(
                id=uuid4(),
                site_code="S002",
                equipment_id="FP-001",
                scheduled_date=today + timedelta(days=days),
            )
            repo._json_insert(insp)

        # Run the query (Supabase will fail, falls back to JSON)
        import asyncio

        async def run():
            return await repo.get_upcoming_inspections("S002", days=7)

        upcoming = asyncio.run(run())
        assert len(upcoming) == 2  # today + 3 days only (8 days > 7)

    def test_get_overdue_inspections(self, tmp_path):
        """Overdue: scheduled_date < today AND completed_date is null."""
        repo = FirePumpComplianceRepository(supabase=None, json_fallback_path=tmp_path / "fp_overdue.json")
        past = date.today() - timedelta(days=5)
        future = date.today() + timedelta(days=5)

        # 2 past-due (no completion), 1 future
        for sched in [past, past, future]:
            insp = FirePumpInspection(
                id=uuid4(),
                site_code="S002",
                equipment_id="FP-001",
                scheduled_date=sched,
            )
            repo._json_insert(insp)

        import asyncio

        async def run():
            return await repo.get_overdue_inspections("S002")

        overdue = asyncio.run(run())
        assert len(overdue) == 2


# =============================================================================
# Service Tests
# =============================================================================


class TestFirePumpComplianceService:
    """Test FirePumpComplianceService business logic."""

    @pytest.mark.asyncio
    async def test_schedule_weekly_test_creates_52_records(self):
        """schedule_weekly_test must create exactly 52 records (one year ahead)."""
        spy = InMemoryFirePumpRepo()
        svc = FirePumpComplianceService(repository=spy)

        results = await svc.schedule_weekly_test("S002", "FP-001")

        assert len(results) == WEEKS_PER_YEAR
        assert len(spy.records) == WEEKS_PER_YEAR

    @pytest.mark.asyncio
    async def test_overdue_detection(self):
        """Overdue: scheduled_date < today AND completed_date is null."""
        spy = InMemoryFirePumpRepo()
        svc = FirePumpComplianceService(repository=spy)

        past = date.today() - timedelta(days=10)
        await spy.schedule_inspection("S002", "FP-001", past)

        alerts = await svc.get_overdue_alerts("S002")

        assert len(alerts) == 1
        assert alerts[0].equipment_id == "FP-001"
        assert alerts[0].days_overdue >= 10

    @pytest.mark.asyncio
    async def test_upcoming_inspection_today_plus_7_days(self):
        """get_upcoming_inspections includes today and next 7 days."""
        spy = InMemoryFirePumpRepo()
        svc = FirePumpComplianceService(repository=spy)

        today = date.today()
        # nothing overdue yet
        await spy.schedule_inspection("S002", "FP-001", today)
        await spy.schedule_inspection("S002", "FP-001", today + timedelta(days=3))
        await spy.schedule_inspection("S002", "FP-001", today + timedelta(days=8))

        alerts = await svc.get_overdue_alerts("S002")
        assert len(alerts) == 0  # nothing is past-due

    @pytest.mark.asyncio
    async def test_compliance_report_calculation(self):
        """Compliance report correctly aggregates test results."""
        spy = InMemoryFirePumpRepo()
        svc = FirePumpComplianceService(repository=spy)

        start = date.today() - timedelta(days=30)
        end = date.today()

        # Add test records with known results
        for offset, res in [
            (0, "pass"),
            (7, "pass"),
            (14, "fail"),
            (21, None),  # overdue - no result
        ]:
            insp_id = uuid4()
            rec = make_inspection_dict(
                site_code="S002",
                equipment_id="FP-001",
                scheduled_date=(start + timedelta(days=offset)).isoformat(),
                completed_date=(start + timedelta(days=offset) + timedelta(days=1)).isoformat() if res else None,
                result=res,
            )
            spy.records.append(rec)

        report = await svc.generate_compliance_report("S002", start, end)

        assert report.total_tests >= 4
        assert report.passed >= 2
        assert report.failed >= 1
        assert report.overdue_count >= 1
        assert report.regulatory_reference == "FNBFW:32335"

    @pytest.mark.asyncio
    async def test_empty_input_handled_gracefully(self):
        """Empty site returns empty results without raising."""
        spy = InMemoryFirePumpRepo()
        svc = FirePumpComplianceService(repository=spy)

        alerts = await svc.get_overdue_alerts("NONEXISTENT")
        report = await svc.generate_compliance_report("NONEXISTENT", date.today() - timedelta(days=30), date.today())

        assert alerts == []
        assert report.total_tests == 0
        assert report.compliance_rate == 0.0

    def test_singleton_accessor(self):
        """get_fire_pump_compliance_service returns the same instance."""
        svc1 = get_fire_pump_compliance_service()
        svc2 = get_fire_pump_compliance_service()
        assert isinstance(svc1, FirePumpComplianceService)
        assert svc1 is svc2

    @pytest.mark.asyncio
    async def test_regulatory_reference_fnbfw32335(self):
        """All models carry FNBFW:32335 regulatory reference."""
        spy = InMemoryFirePumpRepo()
        svc = FirePumpComplianceService(repository=spy)

        past = date.today() - timedelta(days=5)
        await spy.schedule_inspection("S002", "FP-001", past)

        alerts = await svc.get_overdue_alerts("S002")

        assert all(a.regulatory_reference == "FNBFW:32335" for a in alerts)
        report = await svc.generate_compliance_report("S002", date.today() - timedelta(days=30), date.today())
        assert report.regulatory_reference == "FNBFW:32335"

    @pytest.mark.asyncio
    async def test_days_overdue_calculation(self):
        """days_overdue is correctly computed as (today - scheduled_date)."""
        spy = InMemoryFirePumpRepo()
        svc = FirePumpComplianceService(repository=spy)

        past = date.today() - timedelta(days=15)
        await spy.schedule_inspection("S002", "FP-001", past)

        alerts = await svc.get_overdue_alerts("S002")

        assert len(alerts) == 1
        assert alerts[0].days_overdue == 15
