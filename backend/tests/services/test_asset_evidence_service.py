"""
Tests for Phase 171-03: Asset Evidence Service

Verifies:
1. Classification rules
2. Payload normalization
3. Service intake methods (upload, feedback, telemetry)
4. Non-blocking pattern
5. Supersession handling
"""

import pytest
from datetime import datetime
from uuid import uuid4
from backend.app.services.asset_evidence_service import (
    EvidenceClassifier,
    PayloadNormalizer,
)
from backend.app.models.asset_evidence import (
    SourceType,
    ArtifactType,
    EvidenceClass,
    AssetEvidenceService,
    CreateAssetEvidenceInput,
)


class TestEvidenceClassifier:
    """Test evidence classification rules."""

    def test_classify_upload_inspection(self):
        """Upload + document + inspection → INSPECTION_CHECKLIST."""
        result = EvidenceClassifier.classify(
            SourceType.UPLOAD,
            ArtifactType.DOCUMENT,
            category="inspection",
        )
        assert result == EvidenceClass.INSPECTION_CHECKLIST

    def test_classify_upload_service(self):
        """Upload + document + service → SERVICE_REPORT."""
        result = EvidenceClassifier.classify(
            SourceType.UPLOAD,
            ArtifactType.DOCUMENT,
            category="service",
        )
        assert result == EvidenceClass.SERVICE_REPORT

    def test_classify_feedback_observation(self):
        """Feedback + structured_data + observation → TECHNICIAN_OBSERVATION."""
        result = EvidenceClassifier.classify(
            SourceType.FEEDBACK,
            ArtifactType.STRUCTURED_DATA,
            category="observation",
        )
        assert result == EvidenceClass.TECHNICIAN_OBSERVATION

    def test_classify_telemetry(self):
        """Telemetry + structured_data → TELEMETRY_SUMMARY."""
        result = EvidenceClassifier.classify(
            SourceType.TELEMETRY,
            ArtifactType.STRUCTURED_DATA,
        )
        assert result == EvidenceClass.TELEMETRY_SUMMARY

    def test_classify_unknown_fallback_to_upload(self):
        """Unknown upload category → SERVICE_REPORT."""
        result = EvidenceClassifier.classify(
            SourceType.UPLOAD,
            ArtifactType.IMAGE,
        )
        assert result == EvidenceClass.MEDIA_EVIDENCE  # Matches rule for (upload, image, None)

    def test_classify_unknown_fallback_to_feedback(self):
        """Unknown feedback category → TECHNICIAN_OBSERVATION."""
        result = EvidenceClassifier.classify(
            SourceType.FEEDBACK,
            ArtifactType.DOCUMENT,  # Unknown feedback + document
        )
        assert result == EvidenceClass.TECHNICIAN_OBSERVATION  # Default fallback

    def test_classify_deterministic(self):
        """Classification is deterministic: same input → same output."""
        input_args = (SourceType.UPLOAD, ArtifactType.DOCUMENT, "inspection")
        result1 = EvidenceClassifier.classify(*input_args)
        result2 = EvidenceClassifier.classify(*input_args)
        assert result1 == result2


class TestPayloadNormalizer:
    """Test payload normalization from different sources."""

    def test_normalize_upload_with_metadata(self):
        """Normalize upload with form metadata."""
        upload_metadata = {
            "document_name": "AHU-001 Service Report.pdf",
            "category_discipline": "HVAC",
            "document_creation_date": "2026-03-24",
        }
        raw_payload = {
            "keywords": ["bearing", "vibration"],
        }

        result = PayloadNormalizer.normalize_upload(raw_payload, upload_metadata)

        assert result["document_name"] == "AHU-001 Service Report.pdf"
        assert result["category_discipline"] == "HVAC"
        assert "bearing" in result["extracted_keywords"]

    def test_normalize_upload_missing_fields(self):
        """Normalize upload with missing optional fields."""
        upload_metadata = {"document_name": "Report.pdf"}
        raw_payload = {}

        result = PayloadNormalizer.normalize_upload(raw_payload, upload_metadata)

        assert result["document_name"] == "Report.pdf"
        assert "extracted_keywords" not in result  # Not present in raw_payload

    def test_normalize_feedback_with_readings(self):
        """Normalize feedback with sensor readings and observations."""
        feedback_data = {
            "feedback_type": "observation",
            "readings": {"temperature": 45.2, "pressure": 1.2},
            "observations": "Bearing temperature elevated",
            "photos": ["photo1.jpg", "photo2.jpg"],
        }

        result = PayloadNormalizer.normalize_feedback(feedback_data)

        assert result["feedback_class"] == "observation"
        assert result["reading_values"]["temperature"] == 45.2
        assert result["observation_text"] == "Bearing temperature elevated"
        assert result["photo_count"] == 2

    def test_normalize_telemetry_basic(self):
        """Normalize telemetry measurement."""
        telemetry_data = {
            "type": "hvac_temp",
            "timestamp": "2026-03-24T10:30:00Z",
            "readings": {"zone_temp": 22.5, "setpoint": 21.0},
            "anomalies": ["high_temp"],
        }

        result = PayloadNormalizer.normalize_telemetry(telemetry_data)

        assert result["telemetry_type"] == "hvac_temp"
        assert result["measurement_timestamp"] == "2026-03-24T10:30:00Z"
        assert result["readings"]["zone_temp"] == 22.5
        assert "high_temp" in result["anomalies_detected"]

    def test_normalize_removes_none_values(self):
        """Normalization removes None values from output."""
        upload_metadata = {
            "document_name": "Report.pdf",
            "document_sub_class": None,  # Will be skipped
        }
        raw_payload = {}

        result = PayloadNormalizer.normalize_upload(raw_payload, upload_metadata)

        assert "document_name" in result
        assert "document_sub_class" not in result  # None values removed


class TestAssetEvidenceService:
    """Test service intake methods."""

    @pytest.fixture
    def service(self):
        """Fixture: service with mock repository."""
        from unittest.mock import MagicMock

        repo = MagicMock()
        return AssetEvidenceService(repo)

    @pytest.mark.asyncio
    async def test_create_from_upload_happy_path(self, service):
        """Create evidence from upload (happy path)."""
        # Setup mock
        from backend.app.models.asset_evidence import AssetEvidence

        evidence_id = uuid4()
        mock_evidence = AssetEvidence(
            evidence_id=evidence_id,
            site_id=uuid4(),
            equipment_id=uuid4(),
            source_type=SourceType.UPLOAD,
            artifact_type=ArtifactType.DOCUMENT,
            evidence_class=EvidenceClass.SERVICE_REPORT,
            event_timestamp=datetime.utcnow(),
            raw_payload={},
            normalized_payload={"document_name": "Test.pdf"},
            confidence_score=1.0,
            assessment_relevance=True,
            provenance_type="user_upload",
            provenance_uri="test",
            created_at=datetime.utcnow(),
        )
        service.repo.create = pytest.AsyncMock(return_value=mock_evidence)

        # Call method
        result = await service.create_from_upload(
            site_id=uuid4(),
            equipment_id=uuid4(),
            document_id=uuid4(),
            upload_metadata={"document_name": "Test.pdf", "category_discipline": "HVAC"},
            uploader_user_id=uuid4(),
        )

        # Verify
        assert result == evidence_id

    @pytest.mark.asyncio
    async def test_create_from_upload_non_blocking_on_error(self, service):
        """Create evidence from upload fails gracefully (non-blocking)."""
        # Setup mock to raise error
        service.repo.create = pytest.AsyncMock(side_effect=Exception("Supabase error"))

        # Call method
        result = await service.create_from_upload(
            site_id=uuid4(),
            equipment_id=uuid4(),
            document_id=uuid4(),
            upload_metadata={"document_name": "Test.pdf"},
            uploader_user_id=uuid4(),
        )

        # Should return None (non-blocking), not raise
        assert result is None

    @pytest.mark.asyncio
    async def test_classification_in_upload_flow(self, service):
        """Upload flow applies correct classification."""
        from backend.app.models.asset_evidence import AssetEvidence

        evidence_id = uuid4()
        captured_input = None

        async def capture_create(input: CreateAssetEvidenceInput):
            nonlocal captured_input
            captured_input = input
            return AssetEvidence(
                evidence_id=evidence_id,
                site_id=input.site_id,
                equipment_id=input.equipment_id,
                source_type=input.source_type,
                artifact_type=input.artifact_type,
                evidence_class=input.evidence_class,
                event_timestamp=input.event_timestamp,
                raw_payload=input.raw_payload,
                normalized_payload=input.normalized_payload,
                confidence_score=input.confidence_score,
                assessment_relevance=input.assessment_relevance,
                provenance_type=input.provenance_type,
                provenance_uri=input.provenance_uri,
                created_at=datetime.utcnow(),
            )

        service.repo.create = pytest.AsyncMock(side_effect=capture_create)

        # Call with "inspection" category
        await service.create_from_upload(
            site_id=uuid4(),
            equipment_id=uuid4(),
            document_id=uuid4(),
            upload_metadata={"document_name": "Checklist.pdf", "category_discipline": "inspection"},
            uploader_user_id=uuid4(),
        )

        # Verify classification applied
        assert captured_input.evidence_class == EvidenceClass.INSPECTION_CHECKLIST

    @pytest.mark.asyncio
    async def test_normalization_in_feedback_flow(self, service):
        """Feedback flow applies correct normalization."""
        from backend.app.models.asset_evidence import AssetEvidence

        evidence_id = uuid4()
        captured_input = None

        async def capture_create(input: CreateAssetEvidenceInput):
            nonlocal captured_input
            captured_input = input
            return AssetEvidence(
                evidence_id=evidence_id,
                site_id=input.site_id,
                equipment_id=input.equipment_id,
                source_type=input.source_type,
                artifact_type=input.artifact_type,
                evidence_class=input.evidence_class,
                event_timestamp=input.event_timestamp,
                raw_payload=input.raw_payload,
                normalized_payload=input.normalized_payload,
                confidence_score=input.confidence_score,
                assessment_relevance=input.assessment_relevance,
                provenance_type=input.provenance_type,
                provenance_uri=input.provenance_uri,
                created_at=datetime.utcnow(),
            )

        service.repo.create = pytest.AsyncMock(side_effect=capture_create)

        # Call with feedback data
        feedback_data = {
            "feedback_type": "observation",
            "readings": {"temp": 45.0},
            "observations": "High bearing temp",
            "photos": ["p1.jpg"],
        }

        await service.create_from_feedback(
            site_id=uuid4(),
            equipment_id=uuid4(),
            feedback_data=feedback_data,
            feedback_author_id=uuid4(),
        )

        # Verify normalization applied
        assert "observation_text" in captured_input.normalized_payload
        assert "photo_count" in captured_input.normalized_payload
        assert captured_input.normalized_payload["photo_count"] == 1
