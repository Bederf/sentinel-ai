"""Tests for GET /api/equipment/{asset_id}/knowledge endpoint.

8 tests covering:
- asset_id not found -> empty knowledge list
- asset_id found, no knowledge records -> empty list
- asset_id found, knowledge records exist -> correct fields
- knowledge_type filter works
- limit parameter respected
- limit capped at 50
- source_url attached from documents table
- equipment_type correctly looked up from DB (not parsed from asset_id string)
"""

import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("TESTING", "true")

from app.config.settings import settings

# Auth headers that pass the middleware's Sentry bot API key check
_TEST_API_KEY = "test-equipment-knowledge-api-key"
VALID_HEADERS = {"X-Sentry-API-Key": _TEST_API_KEY}


@pytest.fixture(autouse=True)
def _setup_auth():
    """Set up test Sentry bot API key and clean up after each test."""
    original = settings.sentry_bot_api_key
    settings.sentry_bot_api_key = _TEST_API_KEY
    yield
    settings.sentry_bot_api_key = original


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_supabase():
    """Return a MagicMock that behaves like a Supabase client."""
    return MagicMock()


def _make_equipment_row(id: str, code: str, equip_type: str) -> dict:
    return {"id": id, "code": code, "type": equip_type}


def _make_knowledge_row(
    id: str,
    knowledge_type: str,
    title: str,
    description: str = "Test description",
    source_document_id: str | None = None,
    confidence: str = "medium",
    created_at: str = "2026-04-06T10:00:00Z",
) -> dict:
    return {
        "id": id,
        "equipment_type": "GENERATOR",
        "knowledge_type": knowledge_type,
        "title": title,
        "description": description,
        "source_document_id": source_document_id,
        "confidence": confidence,
        "created_at": created_at,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_asset_id_not_found_returns_empty_knowledge():
    """asset_id not in equipment table -> returns empty knowledge list."""
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    mock_db = _mock_supabase()
    equip_table = MagicMock()
    equip_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    mock_db.table.return_value = equip_table

    with patch("app.api.equipment_knowledge.get_supabase_client", return_value=mock_db):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", headers=VALID_HEADERS) as client:
            response = await client.get("/api/equipment/nonexistent-id/knowledge")

    assert response.status_code == 200
    data = response.json()
    assert data["asset_id"] == "nonexistent-id"
    assert data["knowledge"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_asset_id_found_no_knowledge_records_returns_empty_list():
    """asset_id found but no knowledge records -> returns empty list."""
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    mock_db = _mock_supabase()
    equip_row = _make_equipment_row("eq-001", "S002-GEN-001", "GENERATOR")

    # Mock equipment table: table("equipment").select("*").eq("id", asset_id).execute()
    equip_table = MagicMock()
    equip_select = MagicMock()
    equip_table.select.return_value = equip_select
    equip_select.eq.return_value.execute.return_value = MagicMock(data=[equip_row])

    # Mock equipment_knowledge table: empty records
    knowledge_table = MagicMock()
    knowledge_select = MagicMock()
    knowledge_table.select.return_value = knowledge_select
    knowledge_select.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

    def table_side_effect(name):
        if name == "equipment":
            return equip_table
        elif name == "equipment_knowledge":
            return knowledge_table
        return MagicMock()

    mock_db.table.side_effect = table_side_effect

    with patch("app.api.equipment_knowledge.get_supabase_client", return_value=mock_db):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", headers=VALID_HEADERS) as client:
            response = await client.get("/api/equipment/eq-001/knowledge")

    assert response.status_code == 200
    data = response.json()
    assert data["equipment_code"] == "S002-GEN-001"
    assert data["equipment_type"] == "GENERATOR"
    assert data["knowledge"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_knowledge_records_returned_with_correct_fields():
    """asset_id found with knowledge records -> returns records with all expected fields."""
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    mock_db = _mock_supabase()
    equip_row = _make_equipment_row("eq-002", "S002-GEN-002", "GENERATOR")
    knowledge_row = _make_knowledge_row(
        id="know-001",
        knowledge_type="maintenance_record",
        title="S002-GEN-002 — Generator Service Report",
        description="Full service report description.",
        source_document_id=None,
        confidence="high",
    )

    equip_table = MagicMock()
    equip_select = MagicMock()
    equip_table.select.return_value = equip_select
    equip_select.eq.return_value.execute.return_value = MagicMock(data=[equip_row])

    knowledge_table = MagicMock()
    knowledge_select = MagicMock()
    knowledge_table.select.return_value = knowledge_select
    knowledge_select.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[knowledge_row]
    )

    def table_side_effect(name):
        if name == "equipment":
            return equip_table
        elif name == "equipment_knowledge":
            return knowledge_table
        return MagicMock()

    mock_db.table.side_effect = table_side_effect

    with patch("app.api.equipment_knowledge.get_supabase_client", return_value=mock_db):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", headers=VALID_HEADERS) as client:
            response = await client.get("/api/equipment/eq-002/knowledge")

    assert response.status_code == 200
    data = response.json()
    assert data["equipment_code"] == "S002-GEN-002"
    assert data["equipment_type"] == "GENERATOR"
    assert data["total"] == 1

    rec = data["knowledge"][0]
    assert rec["id"] == "know-001"
    assert rec["knowledge_type"] == "maintenance_record"
    assert rec["title"] == "S002-GEN-002 — Generator Service Report"
    assert rec["description"] == "Full service report description."
    assert rec["confidence"] == "high"
    assert rec["source_url"] is None


@pytest.mark.asyncio
async def test_knowledge_type_filter_works():
    """knowledge_type query param filters records correctly."""
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    mock_db = _mock_supabase()
    equip_row = _make_equipment_row("eq-003", "S002-GEN-003", "GENERATOR")
    record = _make_knowledge_row(id="k-003", knowledge_type="maintenance_record", title="Service A")

    equip_table = MagicMock()
    equip_select = MagicMock()
    equip_table.select.return_value = equip_select
    equip_select.eq.return_value.execute.return_value = MagicMock(data=[equip_row])

    knowledge_table = MagicMock()
    knowledge_select = MagicMock()
    knowledge_table.select.return_value = knowledge_select
    knowledge_select.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = (
        MagicMock(data=[record])
    )

    def table_side_effect(name):
        if name == "equipment":
            return equip_table
        elif name == "equipment_knowledge":
            return knowledge_table
        return MagicMock()

    mock_db.table.side_effect = table_side_effect

    with patch("app.api.equipment_knowledge.get_supabase_client", return_value=mock_db):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", headers=VALID_HEADERS) as client:
            response = await client.get("/api/equipment/eq-003/knowledge?knowledge_type=maintenance_record")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["knowledge"][0]["knowledge_type"] == "maintenance_record"


@pytest.mark.asyncio
async def test_limit_parameter_respected():
    """limit query param is passed through to the query."""
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    mock_db = _mock_supabase()
    equip_row = _make_equipment_row("eq-004", "S002-GEN-004", "GENERATOR")

    equip_table = MagicMock()
    equip_select = MagicMock()
    equip_table.select.return_value = equip_select
    equip_select.eq.return_value.execute.return_value = MagicMock(data=[equip_row])

    knowledge_table = MagicMock()
    knowledge_select = MagicMock()
    knowledge_table.select.return_value = knowledge_select
    knowledge_eq = MagicMock()
    knowledge_select.eq.return_value = knowledge_eq
    knowledge_eq.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

    def table_side_effect(name):
        if name == "equipment":
            return equip_table
        elif name == "equipment_knowledge":
            return knowledge_table
        return MagicMock()

    mock_db.table.side_effect = table_side_effect

    with patch("app.api.equipment_knowledge.get_supabase_client", return_value=mock_db):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", headers=VALID_HEADERS) as client:
            response = await client.get("/api/equipment/eq-004/knowledge?limit=5")

    assert response.status_code == 200
    # Verify limit(5) was called
    knowledge_eq.order.return_value.limit.assert_called_with(5)


@pytest.mark.asyncio
async def test_limit_capped_at_50():
    """limit > 50 is capped at 50 by min(limit, 50)."""
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    mock_db = _mock_supabase()
    equip_row = _make_equipment_row("eq-005", "S002-GEN-005", "GENERATOR")

    equip_table = MagicMock()
    equip_select = MagicMock()
    equip_table.select.return_value = equip_select
    equip_select.eq.return_value.execute.return_value = MagicMock(data=[equip_row])

    knowledge_table = MagicMock()
    knowledge_select = MagicMock()
    knowledge_table.select.return_value = knowledge_select
    knowledge_eq = MagicMock()
    knowledge_select.eq.return_value = knowledge_eq
    knowledge_eq.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

    def table_side_effect(name):
        if name == "equipment":
            return equip_table
        elif name == "equipment_knowledge":
            return knowledge_table
        return MagicMock()

    mock_db.table.side_effect = table_side_effect

    with patch("app.api.equipment_knowledge.get_supabase_client", return_value=mock_db):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", headers=VALID_HEADERS) as client:
            response = await client.get("/api/equipment/eq-005/knowledge?limit=200")

    assert response.status_code == 200
    # Verify limit was capped at 50
    knowledge_eq.order.return_value.limit.assert_called_with(50)


@pytest.mark.asyncio
async def test_source_url_attached_from_documents_table():
    """source_url is fetched from documents table and attached to knowledge records."""
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    mock_db = _mock_supabase()
    equip_row = _make_equipment_row("eq-006", "S002-GEN-006", "GENERATOR")
    doc_id = "doc-abc-123"
    knowledge_row = _make_knowledge_row(
        id="k-006",
        knowledge_type="maintenance_record",
        title="Generator Service",
        source_document_id=doc_id,
    )
    doc_row = {"id": doc_id, "source_url": "https://example.com/doc.pdf"}

    equip_table = MagicMock()
    equip_select = MagicMock()
    equip_table.select.return_value = equip_select
    equip_select.eq.return_value.execute.return_value = MagicMock(data=[equip_row])

    knowledge_table = MagicMock()
    knowledge_select = MagicMock()
    knowledge_table.select.return_value = knowledge_select
    knowledge_eq = MagicMock()
    knowledge_select.eq.return_value = knowledge_eq
    knowledge_eq.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[knowledge_row])

    docs_table = MagicMock()
    docs_select = MagicMock()
    docs_table.select.return_value = docs_select
    docs_select.in_.return_value.execute.return_value = MagicMock(data=[doc_row])

    def table_side_effect(name):
        return {"equipment": equip_table, "equipment_knowledge": knowledge_table, "documents": docs_table}.get(
            name, MagicMock()
        )

    mock_db.table.side_effect = table_side_effect

    with patch("app.api.equipment_knowledge.get_supabase_client", return_value=mock_db):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", headers=VALID_HEADERS) as client:
            response = await client.get("/api/equipment/eq-006/knowledge")

    assert response.status_code == 200
    data = response.json()
    assert data["knowledge"][0]["source_url"] == "https://example.com/doc.pdf"
    assert data["knowledge"][0]["source_document_id"] == doc_id


@pytest.mark.asyncio
async def test_equipment_type_from_db_not_parsed_from_asset_id():
    """equipment_type comes from DB lookup, NOT from parsing the asset_id string.

    This test uses an asset_id whose parsed type would be misleading, to prove the
    DB lookup is used instead of string parsing.
    """
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    mock_db = _mock_supabase()
    # DB says this equipment is a CHILLER even though the asset_id looks like GENERATOR
    equip_row = _make_equipment_row("eq-007", "S002-CHILLER-001", "CHILLER")
    knowledge_row = _make_knowledge_row(
        id="k-007",
        knowledge_type="maintenance_record",
        title="Chiller Maintenance",
    )

    equip_table = MagicMock()
    equip_select = MagicMock()
    equip_table.select.return_value = equip_select
    equip_select.eq.return_value.execute.return_value = MagicMock(data=[equip_row])

    knowledge_table = MagicMock()
    knowledge_select = MagicMock()
    knowledge_table.select.return_value = knowledge_select
    knowledge_eq = MagicMock()
    knowledge_select.eq.return_value = knowledge_eq
    knowledge_eq.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[knowledge_row])

    # Track what equipment_type is passed to the knowledge query
    captured_types = []

    original_eq = knowledge_select.eq

    def tracking_eq(col, val):
        captured_types.append((col, val))
        return original_eq(col, val)

    knowledge_select.eq = tracking_eq

    def table_side_effect(name):
        if name == "equipment":
            return equip_table
        elif name == "equipment_knowledge":
            return knowledge_table
        return MagicMock()

    mock_db.table.side_effect = table_side_effect

    with patch("app.api.equipment_knowledge.get_supabase_client", return_value=mock_db):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", headers=VALID_HEADERS) as client:
            response = await client.get("/api/equipment/eq-007/knowledge")

    assert response.status_code == 200
    data = response.json()
    # DB says CHILLER
    assert data["equipment_type"] == "CHILLER"
    # Verify CHILLER (DB value) was used in the query, not something parsed from "eq-007"
    assert any(t == "CHILLER" for _, t in captured_types)
