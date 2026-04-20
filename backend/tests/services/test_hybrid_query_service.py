"""Tests for Hybrid Knowledge Layer Query Service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.hybrid_query_service import (
    HybridContext,
    HybridQueryService,
    get_hybrid_query_service,
)


# ---------------------------------------------------------------------------
# HybridContext unit tests (no mocks needed)
# ---------------------------------------------------------------------------
class TestHybridContext:
    def test_default_context(self):
        ctx = HybridContext()
        assert ctx.equipment_id is None
        assert ctx.sources_used == []

    def test_to_dict(self):
        ctx = HybridContext(
            equipment_id="S002-CHILLER-B1-001",
            equipment_type="Chiller",
            site_id="site-002",
            retrieval_telemetry={"trace_id": "trace-123", "retrieval_path": "canonical_doc_rag"},
        )
        d = ctx.to_dict()
        assert d["equipment_id"] == "S002-CHILLER-B1-001"
        assert d["equipment_type"] == "Chiller"
        assert d["site_id"] == "site-002"
        assert isinstance(d["documents"], list)
        assert isinstance(d["telemetry"], dict)
        assert d["retrievalTelemetry"]["trace_id"] == "trace-123"

    def test_format_for_prompt_empty(self):
        ctx = HybridContext()
        result = ctx.format_for_prompt()
        assert result == ""

    def test_format_for_prompt_with_identity(self):
        ctx = HybridContext(
            equipment_id="S002-CHILLER-B1-001",
            equipment_type="Chiller",
            manufacturer="Carrier",
            model="30XA-200",
        )
        text = ctx.format_for_prompt()
        assert "S002-CHILLER-B1-001" in text
        assert "Chiller" in text
        assert "Carrier" in text
        assert "30XA-200" in text

    def test_format_for_prompt_with_location(self):
        ctx = HybridContext(
            equipment_id="S002-AHU-B1-001",
            location_path=[
                {"iri": "urn:loc/site-002", "label": "Sandton Tower"},
                {"iri": "urn:loc/site-002/B1", "label": "Basement 1"},
            ],
        )
        text = ctx.format_for_prompt()
        assert "Sandton Tower" in text
        assert "Basement 1" in text

    def test_format_for_prompt_with_vendor(self):
        ctx = HybridContext(
            equipment_id="S002-GEN-B1-001",
            vendor={"name": "Cummins SA"},
            contract={"sla_response_hours": 4},
        )
        text = ctx.format_for_prompt()
        assert "Cummins SA" in text
        assert "4h response" in text

    def test_format_for_prompt_with_points(self):
        ctx = HybridContext(
            equipment_id="S002-CHILLER-B1-001",
            points=[
                {
                    "label": "ChW Supply Temp",
                    "brick_class": "Temperature_Sensor",
                    "unit": "°C",
                    "writable": False,
                },
                {
                    "label": "ChW Setpoint",
                    "brick_class": "Temperature_Setpoint",
                    "unit": "°C",
                    "writable": True,
                },
            ],
        )
        text = ctx.format_for_prompt()
        assert "Monitoring Points (2)" in text
        assert "ChW Supply Temp" in text
        assert "read-only" in text
        assert "writable" in text

    def test_format_for_prompt_caps_points_at_10(self):
        ctx = HybridContext(
            equipment_id="S002-AHU-B1-001",
            points=[{"label": f"Point-{i}", "brick_class": "Sensor"} for i in range(20)],
        )
        text = ctx.format_for_prompt()
        assert "Point-9" in text
        assert "Point-10" not in text

    def test_format_for_prompt_with_telemetry(self):
        ctx = HybridContext(
            equipment_id="S002-CHILLER-B1-001",
            telemetry={
                "operating_data": {
                    "runtime_hours": {"value": 12450, "timestamp": "2026-03-05T09:00:00Z"},
                },
                "health_score": 85,
                "status": "running",
            },
        )
        text = ctx.format_for_prompt()
        assert "runtime_hours" in text
        assert "12450" in text

    def test_format_for_prompt_with_anomalies(self):
        ctx = HybridContext(
            equipment_id="S002-CHILLER-B1-001",
            ml_context={
                "anomaly_alerts": [
                    {"equipment_id": "S002-CHILLER-B1-001", "anomaly_score": 0.87, "severity": "high"},
                ],
            },
        )
        text = ctx.format_for_prompt()
        assert "Anomaly Alerts" in text
        assert "0.87" in text

    def test_format_for_prompt_with_documents(self):
        ctx = HybridContext(
            equipment_id="S002-CHILLER-B1-001",
            documents=[
                {"type": "maintenance_report", "title": "Annual Service 2025", "excerpt": "Compressor checked OK."},
            ],
        )
        text = ctx.format_for_prompt()
        assert "Related Documents" in text
        assert "Annual Service 2025" in text
        assert "Compressor checked OK" in text


# ---------------------------------------------------------------------------
# HybridQueryService tests (mocked dependencies)
# ---------------------------------------------------------------------------
class TestHybridQueryService:
    @pytest.mark.asyncio
    async def test_query_with_equipment_id_no_services(self):
        """Query with equipment_id when no services are available."""
        svc = HybridQueryService(site_id="site-002")
        ctx = await svc.query(
            equipment_id="S002-CHILLER-B1-001",
            include_documents=False,
            include_telemetry=False,
            include_ml=False,
            include_points=False,
        )
        assert ctx.equipment_id == "S002-CHILLER-B1-001"
        assert ctx.site_id == "site-002"

    @pytest.mark.asyncio
    async def test_query_no_args_returns_empty(self):
        """No equipment_id or bacnet_ref → empty context."""
        svc = HybridQueryService(site_id="site-002")
        ctx = await svc.query(
            include_documents=False,
            include_telemetry=False,
            include_ml=False,
        )
        assert ctx.equipment_id is None
        assert ctx.sources_used == []

    @pytest.mark.asyncio
    async def test_query_with_brick_context(self):
        """Query with Brick service available."""
        svc = HybridQueryService(site_id="site-002")

        mock_brick_ctx = MagicMock()
        mock_brick_ctx.equipment_type = "Chiller"
        mock_brick_ctx.label = "Chiller B1-001"
        mock_brick_ctx.manufacturer = "Carrier"
        mock_brick_ctx.model = "30XA"
        mock_brick_ctx.protocol = "BACnet"
        mock_brick_ctx.location_path = [("urn:site-002", "Site 002"), ("urn:site-002/B1", "B1")]
        mock_brick_ctx.points = []
        mock_brick_ctx.vendor = None
        mock_brick_ctx.contract = None

        mock_brick_svc = MagicMock()
        mock_brick_svc.get_context.return_value = mock_brick_ctx

        with patch("app.services.brick_service.get_brick_service", return_value=mock_brick_svc):
            ctx = await svc.query(
                equipment_id="S002-CHILLER-B1-001",
                include_documents=False,
                include_telemetry=False,
                include_ml=False,
            )

        assert ctx.equipment_type == "Chiller"
        assert ctx.manufacturer == "Carrier"
        assert "brick_graph" in ctx.sources_used

    @pytest.mark.asyncio
    async def test_query_with_telemetry(self):
        """Query with equipment repository available."""
        svc = HybridQueryService(site_id="site-002")

        mock_repo = AsyncMock()
        mock_repo.get_by_code.return_value = {
            "operating_data": {"runtime_hours": 12000},
            "health_score": 85,
            "status": "running",
        }

        with patch(
            "app.services.hybrid_query_service.HybridQueryService._gather_brick_context",
            new_callable=AsyncMock,
        ), patch(
            "app.database.repositories.equipment_repository.get_equipment_repository",
            return_value=mock_repo,
        ):
            ctx = await svc.query(
                equipment_id="S002-CHILLER-B1-001",
                include_documents=False,
                include_ml=False,
            )

        assert ctx.telemetry.get("operating_data", {}).get("runtime_hours") == 12000
        assert "telemetry" in ctx.sources_used

    @pytest.mark.asyncio
    async def test_gather_document_context_records_retrieval_telemetry(self):
        svc = HybridQueryService(site_id="site-002")
        ctx = HybridContext(site_id="site-002", equipment_type="Generator")

        mock_search_svc = MagicMock()
        mock_search_svc.search.return_value = {
            "results": [
                {
                    "title": "Generator Annual Inspection",
                    "document_type": "report",
                    "snippet": "Inspection completed.",
                    "score": 0.91,
                    "source": "concept",
                }
            ]
        }

        with patch(
            "app.services.concept_document_search.get_concept_document_search_service",
            return_value=mock_search_svc,
        ), patch.object(svc, "_record_retrieval_telemetry") as mock_record:
            await svc._gather_document_context(
                ctx=ctx,
                equipment_id="S002-GEN-B1-001",
                question="latest generator report",
            )

        assert ctx.retrieval_telemetry is not None
        assert ctx.retrieval_telemetry["retrieval_path"] == "canonical_doc_rag"
        assert ctx.retrieval_telemetry["top_k_requested"] == 5
        assert ctx.retrieval_telemetry["hit_count"] == 1
        assert "trace_id" in ctx.retrieval_telemetry
        assert "document_rag" in ctx.sources_used
        mock_record.assert_called_once()

    @pytest.mark.asyncio
    async def test_bacnet_ref_resolution(self):
        """Test that bacnet_ref resolves to equipment_id via Brick."""
        svc = HybridQueryService(site_id="site-002")

        mock_brick_svc = MagicMock()
        mock_brick_svc.resolve_equipment_id.return_value = "S002-CHILLER-B1-001"
        mock_brick_svc.get_context.return_value = None

        with patch("app.services.brick_service.get_brick_service", return_value=mock_brick_svc):
            ctx = await svc.query(
                bacnet_ref="CH-1.ChwSupplyTemp",
                include_documents=False,
                include_telemetry=False,
                include_ml=False,
            )

        assert ctx.equipment_id == "S002-CHILLER-B1-001"
        assert "brick_resolution" in ctx.sources_used

    @pytest.mark.asyncio
    async def test_full_context_format_for_prompt(self):
        """Full context should produce a multi-section prompt string."""
        ctx = HybridContext(
            equipment_id="S002-CHILLER-B1-001",
            equipment_type="Chiller",
            manufacturer="Carrier",
            location_path=[{"iri": "urn:loc", "label": "Sandton"}],
            points=[{"label": "Temp", "brick_class": "Sensor", "unit": "°C", "writable": False}],
            vendor={"name": "Carrier SA"},
            telemetry={"operating_data": {"runtime": 100}, "health_score": 90},
            documents=[{"type": "report", "title": "Service Log", "excerpt": "All OK"}],
            ml_context={"anomaly_alerts": [{"equipment_id": "X", "anomaly_score": 0.9, "severity": "high"}]},
            sources_used=["brick_graph", "telemetry", "document_rag", "ml_models"],
        )
        text = ctx.format_for_prompt()
        assert "Chiller" in text
        assert "Carrier" in text
        assert "Sandton" in text
        assert "Monitoring Points" in text
        assert "Telemetry" in text
        assert "Anomaly" in text
        assert "Related Documents" in text


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
class TestSingleton:
    def test_get_hybrid_query_service_creates_instance(self):
        import app.services.hybrid_query_service as mod

        mod._instances.clear()
        svc = get_hybrid_query_service("site-002")
        assert svc.site_id == "site-002"

    def test_get_hybrid_query_service_caches(self):
        import app.services.hybrid_query_service as mod

        mod._instances.clear()
        svc1 = get_hybrid_query_service("site-002")
        svc2 = get_hybrid_query_service("site-002")
        assert svc1 is svc2

    def test_get_hybrid_query_service_per_site(self):
        import app.services.hybrid_query_service as mod

        mod._instances.clear()
        svc1 = get_hybrid_query_service("site-002")
        svc2 = get_hybrid_query_service("site-005")
        assert svc1 is not svc2
        assert svc1.site_id == "site-002"
        assert svc2.site_id == "site-005"
        mod._instances.clear()
