"""Workflow contract tests for Staff, Technician, and Manager bot handoffs."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config.settings import settings


_TEST_API_KEY = "test-sentry-api-key"
_TEST_SECRET = "test-sentry-secret"
_TEST_OPERATOR_PASSWORD = "test-operator-password"


class _FakeQuery:
    def __init__(self, data=None):
        self.data = data or []

    def select(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def neq(self, *args, **kwargs):
        return self

    def gte(self, *args, **kwargs):
        return self

    def ilike(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def in_(self, *args, **kwargs):
        return self

    def insert(self, *args, **kwargs):
        return self

    def update(self, *args, **kwargs):
        return self

    def upsert(self, *args, **kwargs):
        return self

    def execute(self):
        return MagicMock(data=self.data)


class _FakeSupabase:
    def table(self, name):
        if name == "sites":
            return _FakeQuery([{"id": "site-uuid-002"}])
        return _FakeQuery([])


@pytest.fixture(autouse=True)
def sentry_test_settings():
    original_api_key = settings.sentry_bot_api_key
    original_secret = settings.sentry_webhook_secret
    original_operator_password = settings.sentinel_operator_password
    original_demo_mode = settings.demo_mode
    original_ingestion_mode = settings.ingestion_mode
    original_tech_token = settings.sentry_tech_bot_token
    original_staff_token = settings.sentry_client_bot_token
    original_manager_token = settings.sentry_manager_bot_token
    try:
        settings.sentry_bot_api_key = _TEST_API_KEY
        settings.sentry_webhook_secret = _TEST_SECRET
        settings.sentinel_operator_password = _TEST_OPERATOR_PASSWORD
        settings.demo_mode = False
        settings.ingestion_mode = "live_control"
        settings.sentry_tech_bot_token = "test-tech-token"
        settings.sentry_client_bot_token = "test-staff-token"
        settings.sentry_manager_bot_token = "test-manager-token"
        yield
    finally:
        settings.sentry_bot_api_key = original_api_key
        settings.sentry_webhook_secret = original_secret
        settings.sentinel_operator_password = original_operator_password
        settings.demo_mode = original_demo_mode
        settings.ingestion_mode = original_ingestion_mode
        settings.sentry_tech_bot_token = original_tech_token
        settings.sentry_client_bot_token = original_staff_token
        settings.sentry_manager_bot_token = original_manager_token


@pytest.fixture
def sentry_headers():
    return {
        "X-Sentry-API-Key": _TEST_API_KEY,
        "X-Sentry-Secret": _TEST_SECRET,
    }


@pytest.mark.asyncio
async def test_staff_bot_call_log_creates_work_order_and_notifies_technician(sentry_headers, monkeypatch):
    """Staff bot: confirmed complaint creates a WO and hands it to the technician notifier."""

    captured_work_order: dict = {}

    class _FakeWorkOrderRepository:
        client = _FakeSupabase()

        async def create_work_order(self, payload):
            captured_work_order.update(payload)
            return {"id": "wo-staff-id", "code": "WO-2026-9101", **payload}

    notify = AsyncMock(return_value={"success": True})

    monkeypatch.setattr(
        "app.database.repositories.work_order_repository.WorkOrderRepository",
        _FakeWorkOrderRepository,
    )
    monkeypatch.setattr("app.database.supabase_client.get_supabase_client", lambda: _FakeSupabase())
    monkeypatch.setattr("app.api.sentry_webhooks.work_order_notifier.notify_technician", notify)

    from app.api.sentry_webhooks import CallLogRequest, sentry_call_log

    data = await sentry_call_log(
        CallLogRequest(
            site_id="site-002",
            zone_id="Zone-208",
            floor="L2",
            desk_id="208",
            category="HVAC",
            sub_category="Too hot",
            specialty="hvac",
            priority="high",
            title="HVAC: Too hot",
            description="Desk 208 is too hot.",
            reported_by="Jane Staff",
            reporter_telegram_id="12345678",
            reporter_phone="+27721234567",
            channel="telegram",
            original_message="desk 208 is too hot",
        ),
        x_sentry_secret=sentry_headers["X-Sentry-Secret"],
    )

    assert data["success"] is True
    assert data["work_order_code"] == "WO-2026-9101"
    assert captured_work_order["created_by"] == "sentry:call_log:12345678"
    assert captured_work_order["service_type"] == "callout"
    assert "call_log_dedupe_key=" in captured_work_order["notes"]
    notify.assert_awaited_once()
    notify_payload = notify.await_args.args[0]
    assert notify_payload["code"] == "WO-2026-9101"
    assert notify_payload["site_id"] == "site-002"
    assert notify_payload["desk_id"] == "208"
    assert notify_payload["service_type"] == "callout"


@pytest.mark.asyncio
async def test_staff_bot_status_checks_progress_for_reporter_logged_work_order(sentry_headers, monkeypatch):
    """Staff bot: status lookup shows progress only for the staff member who logged the WO."""

    logged_work_order = {
        "id": "wo-staff-status-id",
        "code": "WO-2026-9104",
        "status": "scheduled",
        "milestone_status": "resolved",
        "resolved_at": "2026-06-30T08:30:00+00:00",
        "created_by": "sentry:call_log:12345678",
        "priority": "high",
        "category": "HVAC",
        "title": "HVAC: Too hot",
        "description": "Desk 208 is too hot.",
        "notes": "Technician attended and resolved the issue.",
        "assigned_to": "John Smith",
    }

    class _FakeWorkOrderRepository:
        async def get_work_order_by_code(self, code):
            assert code == "WO-2026-9104"
            return logged_work_order

    monkeypatch.setattr(
        "app.database.repositories.work_order_repository.WorkOrderRepository",
        _FakeWorkOrderRepository,
    )

    from app.api.sentry_webhooks import sentry_wo_status

    own_status = await sentry_wo_status(
        code="WO-2026-9104",
        reporter_telegram_id="12345678",
        x_sentry_secret=sentry_headers["X-Sentry-Secret"],
    )
    own_payload = own_status.model_dump()

    assert own_payload["success"] is True
    assert own_payload["found"] is True
    assert own_payload["code"] == "WO-2026-9104"
    assert own_payload["display_status"] == "Resolved"
    assert "Manager closure is still pending" in own_payload["staff_summary"]
    assert own_payload["assigned_to"] == "John Smith"
    assert "Technician attended" in own_payload["notes"]

    other_status = await sentry_wo_status(
        code="WO-2026-9104",
        reporter_telegram_id="99999999",
        x_sentry_secret=sentry_headers["X-Sentry-Secret"],
    )
    other_payload = other_status.model_dump()

    assert other_payload["success"] is True
    assert other_payload["found"] is False


@pytest.mark.asyncio
async def test_technician_bot_closeout_advances_work_order_milestone(sentry_headers, monkeypatch):
    """Technician bot: closeout milestone updates the WO and appends technician notes."""

    existing = {
        "id": "wo-tech-id",
        "code": "WO-2026-9102",
        "created_by": "sentry:call_log:12345678",
        "notes": "Original staff issue",
    }
    advanced = {
        **existing,
        "milestone_status": "resolved",
        "status": "scheduled",
        "resolved_at": "2026-06-30T08:00:00+00:00",
    }

    repo = MagicMock()
    repo.get_work_order_by_code = AsyncMock(return_value=existing)
    repo.advance_work_order_milestone = AsyncMock(return_value=advanced)
    repo.update_work_order = AsyncMock(return_value={**advanced, "notes": "updated"})

    sender = MagicMock()
    sender.send_text = AsyncMock(return_value={"ok": True})

    monkeypatch.setattr("app.database.repositories.work_order_repository.WorkOrderRepository", lambda: repo)

    with patch("app.services.telegram_message_sender.TelegramMessageSender", return_value=sender):
        from app.api.sentry_webhooks import WoMilestoneRequest, advance_wo_milestone

        data = await advance_wo_milestone(
            WoMilestoneRequest(
                wo_code="WO-2026-9102",
                milestone="resolved",
                notes="Replaced faulty actuator and confirmed operation.",
                outcome="fixed",
            ),
            x_sentry_secret=sentry_headers["X-Sentry-Secret"],
        )

    payload = data.model_dump() if hasattr(data, "model_dump") else data
    assert payload["success"] is True
    assert payload["wo_code"] == "WO-2026-9102"
    assert payload["milestone_status"] == "resolved"
    repo.advance_work_order_milestone.assert_awaited_once_with("wo-tech-id", "resolved")
    repo.update_work_order.assert_awaited_once()
    update_payload = repo.update_work_order.await_args.args[1]
    assert "Original staff issue" in update_payload["notes"]
    assert "Replaced faulty actuator" in update_payload["notes"]
    sender.send_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_technician_bot_notification_uses_tech_bot_and_done_button(monkeypatch):
    """Technician bot: assignment notification is sent through tech bot with a Done closeout action."""

    captured: dict = {}

    class _FakeResponse:
        def json(self):
            return {"ok": True, "result": {"message_id": 42}}

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json):
            captured["url"] = url
            captured["payload"] = json
            return _FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)

    from app.services.sentry_integration.work_order_notifier import WorkOrderNotifier

    notifier = WorkOrderNotifier()
    notifier._log_delivery = AsyncMock()

    sent = await notifier._send_telegram_notification(
        {
            "code": "WO-2026-9105",
            "work_order_id": "wo-tech-notify-id",
            "technician_id": "8359288792",
            "technician_name": "John Smith",
            "service_type": "callout",
            "criticality": "HIGH",
            "reported_by": "Jane Staff",
            "desk_id": "208",
            "zone_id": "Zone-208",
            "problem_description": "Desk 208 is too hot.",
        },
        service_record={},
    )

    assert sent is True
    assert "/bottest-tech-token/sendMessage" in captured["url"]
    assert captured["payload"]["chat_id"] == "8359288792"
    assert "Work Order Created #WO-2026-9105" in captured["payload"]["text"]
    keyboard = captured["payload"]["reply_markup"]["inline_keyboard"]
    assert keyboard[-1][0]["callback_data"] == "done #WO-2026-9105"
    notifier._log_delivery.assert_awaited_once()


@pytest.mark.asyncio
async def test_technician_bot_open_queue_filters_resolved_and_scopes_to_technician(sentry_headers, monkeypatch):
    """Technician bot: open queue returns actionable WOs only for the requested tech."""

    rows = [
        {
            "id": "wo-open",
            "code": "WO-2026-9106",
            "status": "scheduled",
            "milestone_status": "assigned",
            "equipment_id": "eq-ahu",
            "notified_technician_telegram_id": 8359288792,
        },
        {
            "id": "wo-resolved",
            "code": "WO-2026-9107",
            "status": "scheduled",
            "milestone_status": "resolved",
            "equipment_id": "eq-fcu",
            "notified_technician_telegram_id": 8359288792,
        },
        {
            "id": "wo-other-tech",
            "code": "WO-2026-9108",
            "status": "scheduled",
            "milestone_status": "assigned",
            "equipment_id": "eq-pump",
            "notified_technician_telegram_id": 1111111111,
        },
    ]

    class _WorkOrderQuery(_FakeQuery):
        def __init__(self, data):
            super().__init__(data)
            self.telegram_id = None

        def eq(self, field, value):
            if field == "notified_technician_telegram_id":
                self.telegram_id = value
            return self

        def execute(self):
            data = self.data
            if self.telegram_id is not None:
                data = [row for row in data if row.get("notified_technician_telegram_id") == self.telegram_id]
            return MagicMock(data=data)

    class _WorkOrderClient:
        def table(self, name):
            assert name == "work_orders"
            return _WorkOrderQuery(rows)

    class _FakeWorkOrderRepository:
        _DETAIL_COLUMNS = "*"
        client = _WorkOrderClient()

    class _EquipmentSupabase:
        def table(self, name):
            assert name == "equipment"
            return _FakeQuery([{"id": "eq-ahu", "code": "S002-AHU-B1-001", "name": "AHU", "type": "ahu"}])

    monkeypatch.setattr(
        "app.database.repositories.work_order_repository.WorkOrderRepository",
        _FakeWorkOrderRepository,
    )
    monkeypatch.setattr("app.database.supabase_client.get_supabase_client", lambda: _EquipmentSupabase())

    from app.api.sentry_webhooks import get_open_work_orders_for_technician

    data = await get_open_work_orders_for_technician(
        x_sentry_secret=sentry_headers["X-Sentry-Secret"],
        telegram_id="8359288792",
    )

    assert data["open_count"] == 1
    assert data["work_orders"][0]["code"] == "WO-2026-9106"
    assert data["work_orders"][0]["technician_status"] == "open"
    assert data["work_orders"][0]["equipment_code"] == "S002-AHU-B1-001"
    assert data["work_orders"][0]["closeout_tier"] == "equipment"


@pytest.mark.asyncio
async def test_technician_bot_work_order_detail_returns_closeout_tier(sentry_headers, monkeypatch):
    """Technician bot: detail lookup classifies the closeout path for done #WO."""

    class _FakeWorkOrderRepository:
        async def get_work_order_by_code(self, code):
            assert code == "WO-2026-9109"
            return {
                "id": "wo-detail-id",
                "code": "WO-2026-9109",
                "status": "scheduled",
                "created_by": "sentry:call_log:12345678",
                "service_type": "callout",
                "category": "HVAC",
                "title": "HVAC: Too hot",
                "description": "Desk 208 is too hot.",
            }

    monkeypatch.setattr(
        "app.database.repositories.work_order_repository.WorkOrderRepository",
        _FakeWorkOrderRepository,
    )

    from app.api.sentry_webhooks import sentry_work_order_detail

    data = await sentry_work_order_detail(
        code="WO-2026-9109",
        x_sentry_secret=sentry_headers["X-Sentry-Secret"],
    )

    assert data["success"] is True
    assert data["found"] is True
    assert data["work_order_type"] == "Staff comfort complaint"
    assert data["closeout_tier"] == "comfort"
    assert data["technician_status"] == "open"


@pytest.mark.asyncio
async def test_technician_bot_inspection_session_persists_for_resume(sentry_headers, monkeypatch):
    """Technician bot: Tier 3 checklist progress can be saved and resumed."""

    store: dict = {}

    class _SessionQuery(_FakeQuery):
        def __init__(self):
            super().__init__([])
            self.filters = {}
            self.payload = None

        def upsert(self, payload, *args, **kwargs):
            self.payload = {**payload, "id": "session-1"}
            store[(payload["wo_code"], payload["telegram_user_id"])] = self.payload
            return self

        def eq(self, field, value):
            self.filters[field] = value
            return self

        def execute(self):
            if self.payload:
                return MagicMock(data=[self.payload])
            key = (self.filters.get("wo_code"), self.filters.get("telegram_user_id"))
            session = store.get(key)
            return MagicMock(data=[session] if session else [])

    class _SessionSupabase:
        def table(self, name):
            assert name == "sentry_inspection_sessions"
            return _SessionQuery()

    monkeypatch.setattr("app.database.supabase_client.get_supabase_client", lambda: _SessionSupabase())

    from app.api.sentry_webhooks import (
        InspectionSessionRequest,
        get_inspection_session,
        upsert_inspection_session,
    )

    save_data = await upsert_inspection_session(
        InspectionSessionRequest(
            wo_code="WO-2026-9110",
            telegram_user_id="8359288792",
            equipment_code="S002-AHU-B1-001",
            equipment_type="ahu",
            checklist_items=[{"item_id": "filter", "question": "Filter condition?"}],
            responses={"filter": {"status": "ok", "answer": "Clean"}},
            current_index=1,
        ),
        x_sentry_secret=sentry_headers["X-Sentry-Secret"],
    )

    assert save_data["success"] is True
    assert save_data["session_id"] == "session-1"

    resume_data = await get_inspection_session(
        wo_code="WO-2026-9110",
        telegram_user_id="8359288792",
        x_sentry_secret=sentry_headers["X-Sentry-Secret"],
    )
    resume_payload = resume_data.model_dump()

    assert resume_payload["success"] is True
    assert resume_payload["found"] is True
    assert resume_payload["session"]["current_index"] == 1
    assert resume_payload["session"]["responses"]["filter"]["status"] == "ok"


@pytest.mark.asyncio
async def test_manager_bot_create_work_order_assigns_and_notifies_technician(sentry_headers, monkeypatch):
    """Manager bot: explicit WO creation resolves technician and notifies Tech bot."""

    tech_repo = MagicMock()
    tech_repo.get_technician_for_equipment_code = AsyncMock(
        return_value={
            "name": "John Smith",
            "specialty": "hvac",
            "telegram_id": "8359288792",
            "email": "john@example.com",
        }
    )
    work_order_repo = MagicMock()
    work_order_repo.create_work_order = AsyncMock(
        return_value={
            "id": "wo-manager-id",
            "code": "WO-2026-9103",
            "equipment_code": "S002-AHU-B1-001",
        }
    )
    notify = AsyncMock(return_value={"success": True})

    monkeypatch.setattr(
        "app.database.repositories.technician_repository.get_technician_repository",
        lambda: tech_repo,
    )
    monkeypatch.setattr(
        "app.database.repositories.work_order_repository.get_work_order_repository",
        lambda: work_order_repo,
    )
    monkeypatch.setattr("app.api.sentry_webhooks.work_order_notifier.notify_technician", notify)

    from app.api.sentry_webhooks import SentryWorkOrderRequest, sentry_create_work_order

    data = await sentry_create_work_order(
        SentryWorkOrderRequest(
            equipment_code="S002-AHU-B1-001",
            title="AHU fault follow-up",
            description="Manager requested technician inspection after repeated AHU fault.",
            priority="high",
            created_by="manager_bot",
            operator_password=_TEST_OPERATOR_PASSWORD,
        ),
        x_sentry_secret=sentry_headers["X-Sentry-Secret"],
    )

    assert data["success"] is True
    assert data["code"] == "WO-2026-9103"
    assert data["assigned_to"] == "John Smith"
    assert data["technician_telegram_id"] == "8359288792"
    assert data["technician_notified"] is True
    work_order_payload = work_order_repo.create_work_order.await_args.args[0]
    assert work_order_payload["assigned_to"] == "John Smith"
    assert work_order_payload["assigned_team"] == "hvac"
    assert work_order_payload["notified_technician_telegram_id"] == 8359288792
    notify.assert_awaited_once()
    notify_payload = notify.await_args.args[0]
    assert notify_payload["work_order_code"] == "WO-2026-9103"
    assert notify_payload["technician_id"] == "8359288792"


@pytest.mark.asyncio
async def test_manager_bot_follow_up_sends_message_through_tech_bot(sentry_headers, monkeypatch):
    """Manager bot: follow-up messages are delivered to the technician via the Tech bot."""

    sent = {}

    class _FakeSender:
        def __init__(self, token):
            sent["token"] = token

        async def send_text(self, chat_id, text, parse_mode=None):
            sent.update({"chat_id": chat_id, "text": text, "parse_mode": parse_mode})
            return {"ok": True}

    class _AuditSupabase:
        def table(self, name):
            return _FakeQuery([])

    monkeypatch.setattr("app.database.supabase_client.get_supabase_client", lambda: _AuditSupabase())

    with patch("app.services.telegram_message_sender.TelegramMessageSender", _FakeSender):
        from app.api.sentry_webhooks import TechnicianFollowUpRequest, send_technician_message

        data = await send_technician_message(
            TechnicianFollowUpRequest(
                technician_telegram_id="8359288792",
                message="Please confirm the AHU fault is still active before replacing parts.",
                wo_code="WO-2026-9111",
                source="manager_bot",
            ),
            x_sentry_secret=sentry_headers["X-Sentry-Secret"],
        )

    assert data["success"] is True
    assert data["sent"] is True
    assert sent["token"] == "test-tech-token"
    assert sent["chat_id"] == "8359288792"
    assert sent["parse_mode"] is None
    assert sent["text"] == "WO-2026-9111 — Please confirm the AHU fault is still active before replacing parts."


@pytest.mark.asyncio
async def test_manager_bot_follow_up_resolves_technician_name_and_audits_delivery(sentry_headers, monkeypatch):
    """Manager bot: technician follow-up can resolve a named technician and writes delivery audit."""

    sent = {}
    inserted = {}

    class _FakeSender:
        def __init__(self, token):
            sent["token"] = token

        async def send_text(self, chat_id, text, parse_mode=None):
            sent.update({"chat_id": chat_id, "text": text, "parse_mode": parse_mode})
            return {"ok": True}

    class _TechnicianQuery(_FakeQuery):
        def execute(self):
            return MagicMock(data=[{"name": "John Smith", "telegram_id": "8359288792"}])

    class _InsertQuery(_FakeQuery):
        def insert(self, payload):
            inserted.update(payload)
            return self

    class _FollowUpSupabase:
        def table(self, name):
            if name == "technicians":
                return _TechnicianQuery([])
            if name == "notification_delivery_log":
                return _InsertQuery([])
            return _FakeQuery([])

    monkeypatch.setattr("app.database.supabase_client.get_supabase_client", lambda: _FollowUpSupabase())

    with patch("app.services.telegram_message_sender.TelegramMessageSender", _FakeSender):
        from app.api.sentry_webhooks import TechnicianFollowUpRequest, send_technician_message

        data = await send_technician_message(
            TechnicianFollowUpRequest(
                technician_name="John Smith",
                message="Please add closeout photos before resolving.",
                wo_code="WO-2026-9112",
                source="manager_bot",
            ),
            x_sentry_secret=sentry_headers["X-Sentry-Secret"],
        )

    assert data["success"] is True
    assert data["technician_name"] == "John Smith"
    assert data["technician_telegram_id"] == "8359288792"
    assert sent["token"] == "test-tech-token"
    assert sent["chat_id"] == "8359288792"
    assert sent["text"].startswith("WO-2026-9112")
    assert inserted["notification_type"] == "technician_follow_up"
    assert inserted["reference_id"] == "WO-2026-9112"


@pytest.mark.asyncio
async def test_manager_bot_reassigns_work_order_and_notifies_new_technician(sentry_headers, monkeypatch):
    """Manager bot: reassignment updates the WO and sends a Tech bot reassignment notice."""

    existing = {
        "id": "wo-reassign-id",
        "code": "WO-2026-9113",
        "title": "AHU fault follow-up",
        "assigned_to": "Old Tech",
        "assigned_team": "hvac",
        "notes": "Original assignment.",
    }
    updated_payload = {}
    sent = {}

    class _FakeWorkOrderRepository:
        async def get_work_order_by_code(self, code):
            assert code == "WO-2026-9113"
            return existing

        async def update_work_order(self, wo_id, payload):
            assert wo_id == "wo-reassign-id"
            updated_payload.update(payload)
            return {**existing, **payload}

    class _FakeSender:
        def __init__(self, token):
            sent["token"] = token

        async def send_text(self, chat_id, text, parse_mode=None):
            sent.update({"chat_id": chat_id, "text": text, "parse_mode": parse_mode})
            return {"ok": True}

    class _TechnicianSupabase:
        def table(self, name):
            assert name == "technicians"
            return _FakeQuery(
                [
                    {
                        "id": "tech-2",
                        "name": "New Tech",
                        "specialty": "hvac",
                        "telegram_id": "999888777",
                    }
                ]
            )

    monkeypatch.setattr(
        "app.database.repositories.work_order_repository.WorkOrderRepository",
        _FakeWorkOrderRepository,
    )
    monkeypatch.setattr("app.database.supabase_client.get_supabase_client", lambda: _TechnicianSupabase())

    with patch("app.services.telegram_message_sender.TelegramMessageSender", _FakeSender):
        from app.api.sentry_webhooks import WorkOrderReassignRequest, reassign_work_order

        data = await reassign_work_order(
            WorkOrderReassignRequest(
                wo_code="WO-2026-9113",
                technician_name="New Tech",
                reason="Original technician unavailable",
                notify_technician=True,
                source="manager_bot",
            ),
            x_sentry_secret=sentry_headers["X-Sentry-Secret"],
        )

    assert data["success"] is True
    assert data["previous_assigned_to"] == "Old Tech"
    assert data["assigned_to"] == "New Tech"
    assert data["technician_telegram_id"] == "999888777"
    assert data["notification_sent"] is True
    assert updated_payload["assigned_to"] == "New Tech"
    assert updated_payload["assigned_team"] == "hvac"
    assert updated_payload["milestone_status"] == "assigned"
    assert updated_payload["notified_technician_telegram_id"] == 999888777
    assert "Original technician unavailable" in updated_payload["notes"]
    assert sent["token"] == "test-tech-token"
    assert sent["chat_id"] == "999888777"
    assert "reassigned to you" in sent["text"]


@pytest.mark.asyncio
async def test_manager_created_work_order_closeout_notifies_manager_bot(sentry_headers, monkeypatch):
    """Manager bot: technician resolving a manager-created WO reports back through manager bot."""

    existing = {
        "id": "wo-manager-closeout-id",
        "code": "WO-2026-9114",
        "created_by": "sentry:telegram:456",
        "notes": "Manager created WO.",
    }
    advanced = {
        **existing,
        "milestone_status": "resolved",
        "status": "scheduled",
        "resolved_at": "2026-06-30T08:45:00+00:00",
    }
    sent = {}

    repo = MagicMock()
    repo.get_work_order_by_code = AsyncMock(return_value=existing)
    repo.advance_work_order_milestone = AsyncMock(return_value=advanced)
    repo.update_work_order = AsyncMock(return_value={**advanced, "notes": "updated"})

    class _FakeSender:
        def __init__(self, token):
            sent["token"] = token

        async def send_text(self, chat_id, text):
            sent.update({"chat_id": chat_id, "text": text})
            return {"ok": True}

    monkeypatch.setattr("app.database.repositories.work_order_repository.WorkOrderRepository", lambda: repo)

    with patch("app.services.telegram_message_sender.TelegramMessageSender", _FakeSender):
        from app.api.sentry_webhooks import WoMilestoneRequest, advance_wo_milestone

        data = await advance_wo_milestone(
            WoMilestoneRequest(
                wo_code="WO-2026-9114",
                milestone="resolved",
                notes="Fault cleared and readings normalized.",
                outcome="fixed",
            ),
            x_sentry_secret=sentry_headers["X-Sentry-Secret"],
        )

    payload = data.model_dump()
    assert payload["success"] is True
    assert payload["milestone_status"] == "resolved"
    assert sent["token"] == "test-manager-token"
    assert sent["chat_id"] == "456"
    assert "WO-2026-9114 resolved" in sent["text"]
