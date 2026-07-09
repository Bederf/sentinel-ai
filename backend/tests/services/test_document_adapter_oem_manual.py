from unittest.mock import MagicMock, patch

import pytest

from app.models.document_record import DocumentType, ExtractionStatus
from app.models.document_source import SourceSystem
from app.services.document_adapter_oem_manual import OEMManualAdapter


class TestOEMManualAdapter:
    def test_source_system_is_oem_manual(self):
        with patch("app.services.document_source_adapter._get_supabase"):
            adapter = OEMManualAdapter()
            assert adapter.source_system == SourceSystem.OEM_MANUAL

    def test_normalise_manual_creates_equipment_manual_record(self):
        with patch("app.services.document_source_adapter._get_supabase"):
            adapter = OEMManualAdapter()
            record = adapter.normalise_manual(
                site_id="site-002",
                equipment_code="S002-CHILLER-B1-001",
                equipment_type="chiller",
                manufacturer="York",
                model="YCIV",
                source_url="https://example.com/york-yciv-manual.pdf",
                ocr_text="York YCIV maintenance instructions",
            )

        assert record.source_system == SourceSystem.OEM_MANUAL
        assert record.source_document_id
        assert record.source_document_id.startswith("oem-manual-")
        assert record.document_type == DocumentType.EQUIPMENT_MANUAL
        assert record.sub_class == "chiller"
        assert record.source_url == "https://example.com/york-yciv-manual.pdf"
        assert record.asset_id == "S002-CHILLER-B1-001"
        assert record.contractor_vendor == "York"
        assert record.extraction_status == ExtractionStatus.EXTRACTED
        assert record.needs_human_review is True
        assert "oem_manual_requires_checklist_approval" in record.review_flags
        assert record.extra["manufacturer"] == "York"
        assert record.extra["model"] == "YCIV"
        assert record.extra["equipment_code"] == "S002-CHILLER-B1-001"
        assert record.extra["manual_source"] == "example.com"

    def test_source_document_id_is_stable_for_same_manual_identity(self):
        with patch("app.services.document_source_adapter._get_supabase"):
            adapter = OEMManualAdapter()
            first = adapter.normalise_manual(
                site_id="site-002",
                equipment_code="S002-CHILLER-B1-001",
                equipment_type="chiller",
                manufacturer="York",
                model="YCIV",
                source_url="https://example.com/york-yciv-manual.pdf",
            )
            second = adapter.normalise_manual(
                site_id="site-002",
                equipment_code="S002-CHILLER-B1-001",
                equipment_type="chiller",
                manufacturer="York",
                model="YCIV",
                source_url="https://example.com/york-yciv-manual.pdf",
            )

        assert first.source_document_id == second.source_document_id

    @pytest.mark.asyncio
    async def test_upsert_payload_uses_oem_manual_source_and_metadata(self):
        with patch("app.services.document_source_adapter._get_supabase") as mock_get:
            mock_db = MagicMock()
            mock_get.return_value = mock_db
            mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock(data=[{"id": "doc-123"}])
            adapter = OEMManualAdapter()
            record = adapter.normalise_manual(
                site_id="site-002",
                equipment_code="S002-CHILLER-B1-001",
                equipment_type="chiller",
                manufacturer="York",
                model="YCIV",
                source_document_id="york-yciv-s002",
                source_url="https://example.com/york-yciv-manual.pdf",
                ocr_text="York YCIV maintenance instructions",
            )

            with (
                patch.object(adapter, "_columns_exist", return_value=True),
                patch.object(adapter, "_resolve_site_uuid", return_value="site-uuid"),
            ):
                result = await adapter._upsert(record)

        assert result == "doc-123"
        payload = mock_db.table.return_value.upsert.call_args.args[0]
        assert payload["code"] == "OEM-MANUAL-YORK-YCIV-S002"
        assert payload["document_type"] == "equipment_manual"
        assert payload["equipment_type"] == "chiller"
        assert payload["source"] == "oem_manual"
        assert payload["source_system"] == "oem_manual"
        assert payload["source_document_id"] == "york-yciv-s002"
        assert payload["site_id"] == "site-uuid"
        assert payload["asset_id"] == "S002-CHILLER-B1-001"
        assert payload["manufacturer"] == "York"
        assert payload["model"] == "YCIV"
        assert "equipment_code" not in payload
        assert "S002-CHILLER-B1-001" in payload["keywords"]
        assert "York" in payload["keywords"]
        assert "YCIV" in payload["keywords"]

    def test_get_document_file_uses_oem_manual_source_filter(self):
        with patch("app.services.document_source_adapter._get_supabase") as mock_get:
            mock_db = MagicMock()
            mock_get.return_value = mock_db
            mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[{"source_file_path": "manuals/york.pdf"}]
            )
            mock_db.storage.from_.return_value.download.return_value = b"manual bytes"

            adapter = OEMManualAdapter()
            result = adapter.get_document_file("york-yciv-s002")

        assert result == b"manual bytes"
        first_eq = mock_db.table.return_value.select.return_value.eq
        assert first_eq.call_args.args == ("source_system", "oem_manual")
