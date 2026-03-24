"""
Asset Evidence Service (Phase 171-03)

Classification, normalization, and intake methods for evidence from multiple sources:
- Documents (uploads)
- Feedback collection
- Telemetry data

Non-blocking pattern: evidence creation failures do not block upload/feedback operations.
"""

from typing import Optional, List
from datetime import datetime
from uuid import UUID
import logging

from backend.app.models.asset_evidence import (
    CreateAssetEvidenceInput,
    SourceType,
    ArtifactType,
    EvidenceClass,
    ProvenanceType,
)
from backend.app.database.repositories.asset_evidence_repository import AssetEvidenceRepository

logger = logging.getLogger(__name__)


# ============================================================================
# Evidence Classifier
# ============================================================================


class EvidenceClassifier:
    """
    Classify evidence based on source, artifact type, and metadata.

    Uses deterministic rules to classify evidence into business categories.
    """

    # Classification rules: (source_type, artifact_type, category) -> EvidenceClass
    CLASSIFICATION_RULES = {
        # Upload-based classifications
        ("upload", "document", "inspection"): EvidenceClass.INSPECTION_CHECKLIST,
        ("upload", "document", "service"): EvidenceClass.SERVICE_REPORT,
        ("upload", "document", "condition"): EvidenceClass.CONDITION_ASSESSMENT,
        ("upload", "document", "certificate"): EvidenceClass.CERTIFICATE,
        ("upload", "document", "incident"): EvidenceClass.INCIDENT_REPORT,
        # Feedback-based classifications
        ("feedback", "structured_data", "observation"): EvidenceClass.TECHNICIAN_OBSERVATION,
        ("feedback", "structured_data", "repair"): EvidenceClass.REPAIR_EVENT,
        # Telemetry classifications
        ("telemetry", "structured_data", None): EvidenceClass.TELEMETRY_SUMMARY,
        # Media classifications
        ("upload", "image", None): EvidenceClass.MEDIA_EVIDENCE,
        ("upload", "audio", None): EvidenceClass.MEDIA_EVIDENCE,
    }

    @staticmethod
    def classify(
        source_type: SourceType,
        artifact_type: ArtifactType,
        category: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> EvidenceClass:
        """
        Classify evidence based on source, artifact type, and optional category.

        Args:
            source_type: Evidence source
            artifact_type: Artifact format
            category: Optional category hint (from upload metadata or feedback type)
            metadata: Optional additional metadata

        Returns:
            Classified evidence class

        Notes:
            - Classification is deterministic: same inputs always produce same output
            - Unknown combinations fallback to sensible defaults
            - Category hints are case-sensitive
        """
        # Try with category
        key = (source_type.value, artifact_type.value, category)
        if key in EvidenceClassifier.CLASSIFICATION_RULES:
            return EvidenceClassifier.CLASSIFICATION_RULES[key]

        # Try without category
        key = (source_type.value, artifact_type.value, None)
        if key in EvidenceClassifier.CLASSIFICATION_RULES:
            return EvidenceClassifier.CLASSIFICATION_RULES[key]

        # Default fallback
        if source_type == SourceType.UPLOAD:
            return EvidenceClass.SERVICE_REPORT
        elif source_type == SourceType.FEEDBACK:
            return EvidenceClass.TECHNICIAN_OBSERVATION
        elif source_type == SourceType.TELEMETRY:
            return EvidenceClass.TELEMETRY_SUMMARY
        else:
            return EvidenceClass.CONDITION_ASSESSMENT


# ============================================================================
# Payload Normalizer
# ============================================================================


class PayloadNormalizer:
    """
    Normalize various payload formats into standard structure.

    Extracts standard fields from different intake sources for consistent processing.
    """

    # Standard fields that should be extracted/normalized
    STANDARD_FIELDS = {
        "document_name",
        "document_sub_class",
        "category_discipline",
        "document_creation_date",
        "trigger_date",
        "retention_rule_key",
        "storage_mode",
        "extracted_keywords",
        "structured_data",
    }

    @staticmethod
    def normalize_upload(raw_payload: dict, upload_metadata: dict) -> dict:
        """
        Normalize upload metadata into standard structure.

        Args:
            raw_payload: Raw file upload metadata
            upload_metadata: Upload form data

        Returns:
            Normalized payload with standard fields
        """
        normalized = {}

        # Direct mappings from upload_metadata
        if "document_name" in upload_metadata:
            normalized["document_name"] = upload_metadata["document_name"]
        if "document_sub_class" in upload_metadata:
            normalized["document_sub_class"] = upload_metadata["document_sub_class"]
        if "category_discipline" in upload_metadata:
            normalized["category_discipline"] = upload_metadata["category_discipline"]
        if "document_creation_date" in upload_metadata:
            normalized["document_creation_date"] = upload_metadata["document_creation_date"]
        if "trigger_date" in upload_metadata:
            normalized["trigger_date"] = upload_metadata["trigger_date"]
        if "retention_rule_key" in upload_metadata:
            normalized["retention_rule_key"] = upload_metadata["retention_rule_key"]
        if "storage_mode" in upload_metadata:
            normalized["storage_mode"] = upload_metadata["storage_mode"]

        # Extract keywords if available
        if "keywords" in raw_payload:
            normalized["extracted_keywords"] = raw_payload["keywords"]

        # Remove None values
        return {k: v for k, v in normalized.items() if v is not None}

    @staticmethod
    def normalize_feedback(feedback_data: dict) -> dict:
        """
        Normalize feedback form data into standard structure.

        Args:
            feedback_data: Service feedback form submission

        Returns:
            Normalized payload with standard fields
        """
        normalized = {}

        # Feedback-specific normalization
        if "feedback_type" in feedback_data:
            normalized["feedback_class"] = feedback_data["feedback_type"]
        if "readings" in feedback_data:
            normalized["reading_values"] = feedback_data["readings"]
        if "observations" in feedback_data:
            normalized["observation_text"] = feedback_data["observations"]
        if "checklist_completion" in feedback_data:
            normalized["checklist_completion_pct"] = feedback_data["checklist_completion"]
        if "photos" in feedback_data:
            normalized["photo_count"] = len(feedback_data["photos"])

        # Extract structured data if available
        if "structured_data" in feedback_data:
            normalized["structured_data"] = feedback_data["structured_data"]

        # Remove None values
        return {k: v for k, v in normalized.items() if v is not None}

    @staticmethod
    def normalize_telemetry(telemetry_data: dict) -> dict:
        """
        Normalize telemetry into standard structure.

        Args:
            telemetry_data: Time-series telemetry measurement

        Returns:
            Normalized payload with standard fields
        """
        normalized = {}

        if "type" in telemetry_data:
            normalized["telemetry_type"] = telemetry_data["type"]
        if "timestamp" in telemetry_data:
            normalized["measurement_timestamp"] = telemetry_data["timestamp"]
        if "readings" in telemetry_data:
            normalized["readings"] = telemetry_data["readings"]
        if "anomalies" in telemetry_data:
            normalized["anomalies_detected"] = telemetry_data["anomalies"]

        # Remove None values
        return {k: v for k, v in normalized.items() if v is not None}


# ============================================================================
# Asset Evidence Service
# ============================================================================


class AssetEvidenceService:
    """
    Service for managing asset evidence across all intake sources.

    Provides convenience methods for creating evidence from uploads, feedback, and telemetry.
    Handles classification, normalization, and persistence.

    Non-blocking pattern: failures logged but do not block caller operations.
    """

    def __init__(self, repository: AssetEvidenceRepository):
        """
        Initialize with repository.

        Args:
            repository: Asset evidence repository for persistence
        """
        self.repo = repository
        self.classifier = EvidenceClassifier()
        self.normalizer = PayloadNormalizer()

    async def create_from_upload(
        self,
        site_id: UUID,
        equipment_id: UUID,
        document_id: UUID,
        upload_metadata: dict,
        uploader_user_id: UUID,
        uploader_user_email: Optional[str] = None,
        confidence_score: float = 1.0,
        raw_payload: Optional[dict] = None,
    ) -> Optional[UUID]:
        """
        Create evidence record from technician document upload.

        Args:
            site_id: Site UUID
            equipment_id: Equipment UUID
            document_id: Document UUID (FK to documents table)
            upload_metadata: Upload form data (document_name, discipline, etc.)
            uploader_user_id: User who uploaded
            uploader_user_email: User email (for provenance)
            confidence_score: Confidence in evidence validity (default: 1.0 for uploads)
            raw_payload: Optional raw file metadata

        Returns:
            Created evidence UUID, or None if creation failed (non-blocking)

        Notes:
            - Non-blocking: exceptions are logged, not raised
            - Confidence defaults to 1.0 (uploads are high-confidence)
            - Classification based on upload_metadata.category_discipline
        """
        try:
            # Classify and normalize
            artifact_type = ArtifactType.DOCUMENT
            evidence_class = self.classifier.classify(
                SourceType.UPLOAD,
                artifact_type,
                category=upload_metadata.get("category_discipline"),
            )

            normalized_payload = self.normalizer.normalize_upload(raw_payload or {}, upload_metadata)

            # Create evidence record
            input_model = CreateAssetEvidenceInput(
                site_id=site_id,
                equipment_id=equipment_id,
                source_type=SourceType.UPLOAD,
                artifact_type=artifact_type,
                evidence_class=evidence_class,
                document_id=document_id,
                event_timestamp=datetime.utcnow(),
                raw_payload=raw_payload or {},
                normalized_payload=normalized_payload,
                confidence_score=confidence_score,
                assessment_relevance=True,  # Uploads are relevant by default
                provenance_type=ProvenanceType.USER_UPLOAD,
                provenance_uri=f"user:{uploader_user_id}:upload",
                uploader_user_id=uploader_user_id,
            )

            evidence = await self.repo.create(input_model)
            logger.info(f"Created upload evidence {evidence.evidence_id} for equipment {equipment_id}")
            return evidence.evidence_id

        except Exception as e:
            # Non-blocking: log failure but return None
            logger.error(f"Failed to create upload evidence: {e}", exc_info=True)
            return None

    async def create_from_feedback(
        self,
        site_id: UUID,
        equipment_id: UUID,
        feedback_data: dict,
        feedback_author_id: UUID,
        feedback_author_email: Optional[str] = None,
        confidence_score: float = 0.95,
    ) -> Optional[UUID]:
        """
        Create evidence record from service feedback completion.

        Args:
            site_id: Site UUID
            equipment_id: Equipment UUID
            feedback_data: Feedback form submission
            feedback_author_id: User who submitted feedback
            feedback_author_email: User email (for provenance)
            confidence_score: Confidence in feedback validity (default: 0.95)

        Returns:
            Created evidence UUID, or None if creation failed (non-blocking)

        Notes:
            - Non-blocking: exceptions are logged, not raised
            - Confidence defaults to 0.95 (feedback is high-confidence but human-input)
            - Classification based on feedback_data.feedback_type
        """
        try:
            # Classify and normalize
            artifact_type = ArtifactType.STRUCTURED_DATA
            evidence_class = self.classifier.classify(
                SourceType.FEEDBACK,
                artifact_type,
                category=feedback_data.get("feedback_type"),
            )

            normalized_payload = self.normalizer.normalize_feedback(feedback_data)

            input_model = CreateAssetEvidenceInput(
                site_id=site_id,
                equipment_id=equipment_id,
                source_type=SourceType.FEEDBACK,
                artifact_type=artifact_type,
                evidence_class=evidence_class,
                event_timestamp=datetime.utcnow(),
                raw_payload=feedback_data,
                normalized_payload=normalized_payload,
                confidence_score=confidence_score,
                assessment_relevance=True,  # Feedback always relevant
                provenance_type=ProvenanceType.USER_UPLOAD,
                provenance_uri=f"user:{feedback_author_id}:feedback",
                uploader_user_id=feedback_author_id,
            )

            evidence = await self.repo.create(input_model)
            logger.info(f"Created feedback evidence {evidence.evidence_id} for equipment {equipment_id}")
            return evidence.evidence_id

        except Exception as e:
            # Non-blocking: log failure but return None
            logger.error(f"Failed to create feedback evidence: {e}", exc_info=True)
            return None

    async def create_from_telemetry(
        self,
        site_id: UUID,
        equipment_id: UUID,
        telemetry_data: dict,
        confidence_score: float = 0.8,
    ) -> Optional[UUID]:
        """
        Create evidence record from telemetry data.

        Args:
            site_id: Site UUID
            equipment_id: Equipment UUID
            telemetry_data: Time-series telemetry measurement
            confidence_score: Confidence in telemetry validity (default: 0.8)

        Returns:
            Created evidence UUID, or None if creation failed (non-blocking)

        Notes:
            - Non-blocking: exceptions are logged, not raised
            - Confidence defaults to 0.8 (auto-generated, needs validation)
            - Marked as system_ingest with no uploader_user_id
            - assessment_relevance=False (telemetry needs manual assessment)
        """
        try:
            artifact_type = ArtifactType.STRUCTURED_DATA
            evidence_class = self.classifier.classify(SourceType.TELEMETRY, artifact_type)

            normalized_payload = self.normalizer.normalize_telemetry(telemetry_data)

            input_model = CreateAssetEvidenceInput(
                site_id=site_id,
                equipment_id=equipment_id,
                source_type=SourceType.TELEMETRY,
                artifact_type=artifact_type,
                evidence_class=evidence_class,
                event_timestamp=telemetry_data.get("timestamp", datetime.utcnow()),
                raw_payload=telemetry_data,
                normalized_payload=normalized_payload,
                confidence_score=confidence_score,
                assessment_relevance=False,  # Telemetry needs manual assessment
                provenance_type=ProvenanceType.SYSTEM_INGEST,
                provenance_uri="system:telemetry_ingest",
                uploader_user_id=None,  # System-generated, no user
            )

            evidence = await self.repo.create(input_model)
            logger.info(f"Created telemetry evidence {evidence.evidence_id} for equipment {equipment_id}")
            return evidence.evidence_id

        except Exception as e:
            # Non-blocking: log failure but return None
            logger.error(f"Failed to create telemetry evidence: {e}", exc_info=True)
            return None

    async def get_evidence_for_equipment(
        self,
        equipment_id: UUID,
        active_only: bool = True,
        limit: int = 100,
    ) -> List:
        """
        Retrieve all evidence for an equipment.

        Args:
            equipment_id: Equipment UUID
            active_only: Filter to non-superseded evidence only
            limit: Max records to return

        Returns:
            List of evidence records
        """
        try:
            return await self.repo.list_by_equipment(equipment_id, limit=limit, active_only=active_only)
        except Exception as e:
            logger.error(f"Failed to retrieve equipment evidence: {e}")
            return []

    async def get_evidence_for_site(
        self,
        site_id: UUID,
        active_only: bool = True,
        limit: int = 100,
    ) -> List:
        """
        Retrieve all evidence for a site.

        Args:
            site_id: Site UUID
            active_only: Filter to non-superseded evidence only
            limit: Max records to return

        Returns:
            List of evidence records
        """
        try:
            return await self.repo.list_by_site(site_id, limit=limit, active_only=active_only)
        except Exception as e:
            logger.error(f"Failed to retrieve site evidence: {e}")
            return []
