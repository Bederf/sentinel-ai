"""Tests for DXF/DWG batch processing.

Tests batch parsing, file limit enforcement, size limit enforcement,
mixed format handling, and validation endpoint.
"""

import os
import tempfile

import pytest

ezdxf = pytest.importorskip("ezdxf", reason="ezdxf not installed")

from app.services.dxf_parser_service import BatchResult, get_dxf_parser_service  # noqa: E402


def _make_dxf_bytes(equipment_label="CH-1", layer="AE-HVAC", insert=(50, 40, 0)):
    """Generate minimal valid DXF bytes for testing."""
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    doc.layers.new("AR-WALL")
    doc.layers.new(layer)

    # Add walls
    msp.add_line((0, 0), (100, 0), dxfattribs={"layer": "AR-WALL"})
    msp.add_line((100, 0), (100, 80), dxfattribs={"layer": "AR-WALL"})
    msp.add_line((100, 80), (0, 80), dxfattribs={"layer": "AR-WALL"})
    msp.add_line((0, 80), (0, 0), dxfattribs={"layer": "AR-WALL"})

    # Add equipment
    msp.add_text(equipment_label, dxfattribs={"layer": layer, "insert": insert})

    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
        temp_path = f.name
    doc.saveas(temp_path)
    with open(temp_path, "rb") as f:
        dxf_bytes = f.read()
    os.remove(temp_path)
    return dxf_bytes


class TestBatchParsing:
    """Test batch DXF/DWG processing."""

    @pytest.mark.asyncio
    async def test_batch_with_two_dxf_files(self):
        """Batch with 2 DXF files merges equipment correctly."""
        parser = get_dxf_parser_service()

        files = [
            {"filename": "ground_floor.dxf", "content": _make_dxf_bytes("CH-1")},
            {"filename": "first_floor.dxf", "content": _make_dxf_bytes("AHU-L1-01")},
        ]

        result = await parser.parse_batch(files, "site-002", "Test Building")

        assert isinstance(result, BatchResult)
        assert result.total_equipment >= 2
        assert len(result.per_file_status) == 2
        assert all(s["success"] for s in result.per_file_status)
        assert result.validation is not None

    @pytest.mark.asyncio
    async def test_batch_with_mixed_dxf_and_dwg(self):
        """Batch with DXF + DWG: DWG fails gracefully when ODA not installed."""
        parser = get_dxf_parser_service()

        files = [
            {"filename": "floor1.dxf", "content": _make_dxf_bytes("FCU-L1-A")},
            {"filename": "floor2.dwg", "content": b"fake DWG data"},
        ]

        result = await parser.parse_batch(files, "site-002")

        assert len(result.per_file_status) == 2

        # DXF should succeed
        dxf_status = result.per_file_status[0]
        assert dxf_status["success"] is True

        # DWG should fail gracefully (ODA not installed)
        dwg_status = result.per_file_status[1]
        assert dwg_status["success"] is False
        assert "ODA" in dwg_status["error"] or "not found" in dwg_status["error"].lower()

    @pytest.mark.asyncio
    async def test_batch_empty_files_list(self):
        """Batch with empty files list returns empty result."""
        parser = get_dxf_parser_service()
        result = await parser.parse_batch([], "site-002")

        assert result.total_equipment == 0
        assert len(result.per_file_status) == 0

    @pytest.mark.asyncio
    async def test_batch_invalid_dxf_file(self):
        """Batch with invalid DXF file reports failure for that file."""
        parser = get_dxf_parser_service()

        files = [
            {"filename": "good.dxf", "content": _make_dxf_bytes("VAV-L1-01")},
            {"filename": "bad.dxf", "content": b"not valid dxf"},
        ]

        result = await parser.parse_batch(files, "site-002")

        assert len(result.per_file_status) == 2
        good = result.per_file_status[0]
        bad = result.per_file_status[1]
        assert good["success"] is True
        assert bad["success"] is False

    @pytest.mark.asyncio
    async def test_batch_deduplicates_floors(self):
        """Batch deduplicates floor definitions from multiple files."""
        parser = get_dxf_parser_service()

        # Both files have ground floor equipment
        files = [
            {"filename": "a.dxf", "content": _make_dxf_bytes("CH-1", insert=(30, 30, 0))},
            {"filename": "b.dxf", "content": _make_dxf_bytes("GEN-1", insert=(60, 40, 0))},
        ]

        result = await parser.parse_batch(files, "site-002")

        # Should not have duplicate floor levels
        levels = [f["level"] for f in result.floors]
        assert len(levels) == len(set(levels))

    @pytest.mark.asyncio
    async def test_batch_result_has_validation(self):
        """Batch result includes validation report."""
        parser = get_dxf_parser_service()

        files = [
            {"filename": "test.dxf", "content": _make_dxf_bytes("UPS-1")},
        ]

        result = await parser.parse_batch(files, "site-002")

        assert result.validation is not None
        assert "valid" in result.validation
        assert "errors" in result.validation
        assert "warnings" in result.validation
        assert "stats" in result.validation


class TestBatchResultModel:
    """Test BatchResult dataclass."""

    def test_to_dict(self):
        """BatchResult.to_dict() serializes correctly."""
        result = BatchResult(
            equipment=[{"name": "EQ-1"}],
            floors=[{"level": "L1"}],
            zones=[],
            validation={"valid": True, "errors": [], "warnings": [], "stats": {}},
            per_file_status=[{"filename": "test.dxf", "success": True}],
            total_equipment=1,
            total_floors=1,
        )
        d = result.to_dict()
        assert d["total_equipment"] == 1
        assert len(d["equipment"]) == 1
        assert d["validation"]["valid"] is True


class TestBatchAPIEndpoint:
    """Test batch API endpoint constraints."""

    @pytest.mark.asyncio
    async def test_file_limit_enforcement(self):
        """Batch rejects more than 20 files at API level."""
        from fastapi.testclient import TestClient

        from app.main import app

        client = TestClient(app)

        # Create 21 fake files
        files = [("files", (f"file_{i}.dxf", b"fake", "application/octet-stream")) for i in range(21)]

        response = client.post(
            "/api/digital-twin/batch-extract",
            files=files,
            data={"site_id": "site-002"},
        )

        assert response.status_code == 400
        assert "Too many files" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_file_size_limit_enforcement(self):
        """Batch rejects files larger than 10MB."""
        from fastapi.testclient import TestClient

        from app.main import app

        client = TestClient(app)

        # Create a file > 10MB
        large_content = b"x" * (11 * 1024 * 1024)
        files = [("files", ("huge.dxf", large_content, "application/octet-stream"))]

        response = client.post(
            "/api/digital-twin/batch-extract",
            files=files,
            data={"site_id": "site-002"},
        )

        assert response.status_code == 400
        assert "exceeds" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_unsupported_file_type_rejected(self):
        """Batch rejects non-DXF/DWG files."""
        from fastapi.testclient import TestClient

        from app.main import app

        client = TestClient(app)

        files = [("files", ("plan.pdf", b"fake pdf", "application/pdf"))]

        response = client.post(
            "/api/digital-twin/batch-extract",
            files=files,
            data={"site_id": "site-002"},
        )

        assert response.status_code == 400
        assert "Unsupported file type" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_validation_endpoint_returns_report(self):
        """GET /validate returns a validation report."""
        from fastapi.testclient import TestClient

        from app.main import app

        client = TestClient(app)

        response = client.get("/api/digital-twin/validate?site_id=site-002")

        # Should succeed (uses demo config)
        assert response.status_code == 200
        data = response.json()
        assert "validation" in data
        assert "valid" in data["validation"]
