from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_info_for_logical_zone_scope_returns_work_order_brief(monkeypatch):
    from app.services import slash_command_router

    repo = MagicMock()
    repo.get_all_work_orders = AsyncMock(
        return_value=[
            {
                "code": "WO-2026-0016",
                "title": "SENTINEL Advisory Action: SITE-002-HVAC-ZONE-SCOPE",
                "description": "Created from SENTINEL AI advisory recommendation.",
                "equipment_id": "SITE-002-HVAC-ZONE-SCOPE",
                "action_value": "Block blanket site HVAC shutdown; use scoped zone/floor control only.",
                "recommendation_id": "bc89adc4-272c-486e-b916-ec00aea4bffb",
            }
        ]
    )
    repo.get_work_order_by_code = AsyncMock(
        return_value={
            "code": "WO-2026-0016",
            "title": "SENTINEL Advisory Action: SITE-002-HVAC-ZONE-SCOPE",
            "status": "scheduled",
            "assigned_to": "John Smith",
            "assigned_team": "electrical",
            "equipment_id": "SITE-002-HVAC-ZONE-SCOPE",
            "action_value": "Block blanket site HVAC shutdown; use scoped zone/floor control only.",
            "recommendation_id": "bc89adc4-272c-486e-b916-ec00aea4bffb",
        }
    )

    monkeypatch.setattr(
        "app.database.repositories.work_order_repository.get_work_order_repository",
        lambda: repo,
    )
    monkeypatch.setattr(
        slash_command_router,
        "_load_recommendation_for_work_order",
        AsyncMock(
            return_value={
                "id": "bc89adc4-272c-486e-b916-ec00aea4bffb",
                "target_equipment": "SITE-002-HVAC-ZONE-SCOPE",
                "action": {"value": "Block blanket site HVAC shutdown"},
                "reason": "Occupancy signals conflict.",
            }
        ),
    )

    result = await slash_command_router._handle_info("SITE-002-HVAC-ZONE-SCOPE", None, None)

    assert result.success is True
    assert "Logical SENTINEL advisory scope" in result.message
    assert "What to do" in result.message
    assert "Block blanket site HVAC shutdown" in result.message
    assert "Do not perform a blanket HVAC shutdown" in result.message
    assert "bc89adc4-272c-486e-b916-ec00aea4bffb" not in result.message
    assert "Recommendation:" not in result.message


@pytest.mark.asyncio
async def test_info_for_work_order_code_returns_chiller_brief(monkeypatch):
    from app.services import slash_command_router

    class _FakeWorkOrderRepository:
        async def get_work_order_by_code(self, code):
            assert code == "WO-2026-0017"
            return {
                "id": "30cdcda1-ebb2-479c-99f1-d13cfc426958",
                "code": "WO-2026-0017",
                "status": "scheduled",
                "priority": "medium",
                "title": "Maintenance — S002-CHILLER-B1",
                "description": "Maintenance work order for S002-CHILLER-B1.",
                "assigned_to": "John Smith",
                "assigned_team": "TECH-001",
                "equipment_id": "e69bcd53-3e4c-44c6-a42a-e8c7113e210e",
                "work_type": "repair",
                "work_order_type": "Equipment fault",
                "closeout_tier": "equipment",
            }

    class _FakeServiceRecordRepository:
        async def list(self, filters=None):
            assert filters == {"work_order_id": "30cdcda1-ebb2-479c-99f1-d13cfc426958"}
            return [
                {
                    "code": "SR-2026-906C21",
                    "status": "notified",
                    "service_type": "callout",
                    "technician_name": "John Smith",
                }
            ]

    class _FakeSupabase:
        def table(self, name):
            assert name == "equipment"
            return self

        def select(self, *args, **kwargs):
            return self

        def eq(self, field, value):
            assert field in {"id", "code"}
            assert value == "e69bcd53-3e4c-44c6-a42a-e8c7113e210e"
            return self

        def limit(self, *args, **kwargs):
            return self

        def execute(self):
            return MagicMock(
                data=[
                    {
                        "id": "e69bcd53-3e4c-44c6-a42a-e8c7113e210e",
                        "code": "S002-CHILLER-B1-001",
                        "name": "chiller Basement",
                        "type": "chiller",
                        "status": "normal",
                    }
                ]
            )

    class _FakeFeedbackTemplate:
        template_name = "Chiller Service Closeout"
        required_items = ["service_sheet", "compressor_audio", "sight_glass_photo"]
        optional_items = ["oil_sight_glass", "thermal_image"]
        prompts = {
            "service_sheet": "Send chiller service sheet with pressures and temperatures",
            "compressor_audio": "Record 30 seconds of compressor running",
            "sight_glass_photo": "Photo of refrigerant sight glass (check for bubbles/moisture)",
            "oil_sight_glass": "Photo of oil sight glass (if accessible)",
            "thermal_image": "Thermal image of compressor and electrical connections",
        }

    class _FakeFeedbackService:
        def get_template(self, equipment_type, service_type):
            assert equipment_type == "chiller"
            assert service_type == "callout"
            return _FakeFeedbackTemplate()

    monkeypatch.setattr(
        "app.database.repositories.work_order_repository.get_work_order_repository",
        lambda: _FakeWorkOrderRepository(),
    )
    monkeypatch.setattr(
        "app.database.repositories.service_record_repository.ServiceRecordRepository",
        _FakeServiceRecordRepository,
    )
    monkeypatch.setattr("app.database.supabase_client.get_supabase_client", lambda: _FakeSupabase())
    monkeypatch.setattr(
        "app.services.feedback_collection_service.get_feedback_collection_service",
        lambda: _FakeFeedbackService(),
    )

    result = await slash_command_router._handle_info("WO-2026-0017", None, None)

    assert result.success is True
    assert "Work Order Info: WO-2026-0017" in result.message
    assert "Equipment Type: chiller" in result.message
    assert "Service Record: SR-2026-906C21" in result.message
    assert "Chiller Service Closeout" in result.message
    assert "Send chiller service sheet with pressures and temperatures" in result.message
    assert "/done-WO-2026-0017" in result.message


def test_parse_accepts_done_closeout_command():
    from app.services import slash_command_router

    assert slash_command_router.parse("/done-WO-2026-0016") == ("done", "WO-2026-0016", None)
    assert slash_command_router.parse("/done-WO-2026-0016 please review") == (
        "done",
        "WO-2026-0016",
        "please review",
    )


@pytest.mark.asyncio
async def test_done_command_starts_closeout_flow():
    from app.services import slash_command_router

    result = await slash_command_router._handle_done("WO-2026-0016", None, None)

    assert result.success is True
    assert "/done-WO-2026-0016" in result.message
    assert "guided closeout feedback" in result.message
