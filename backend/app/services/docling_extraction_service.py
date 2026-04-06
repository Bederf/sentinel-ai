"""Docling OCR and layout analysis service.

Provides unified document extraction (PDF, DOCX, images) with better scanned-PDF
OCR, table extraction, and key-value pair detection than PyPDF2+pytesseract.

Phase 181-01: DoclingExtractionService foundation
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import UploadFile

logger = logging.getLogger(__name__)

# Supported file types for docling
DOCLING_SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".jpg", ".jpeg", ".png", ".tiff", ".tif"}


@dataclass
class DoclingExtractionResult:
    """Result of a docling document extraction.

    Attributes:
        raw_text: Full extracted text in markdown format.
        tables: List of markdown table strings extracted from the document.
        page_count: Number of pages processed.
        extraction_mode: One of "docling", "native_fallback", or "unavailable".
        confidence: Overall extraction confidence score (0.0-1.0).
        metadata: Additional extraction metadata (filename, size, language hints, etc.).
    """

    raw_text: str
    tables: list[str]
    page_count: int
    extraction_mode: str
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def empty(cls, reason: str = "unavailable") -> "DoclingExtractionResult":
        """Return an empty result when docling is unavailable."""
        return cls(
            raw_text="",
            tables=[],
            page_count=0,
            extraction_mode="unavailable",
            confidence=0.0,
            metadata={"unavailable_reason": reason},
        )


class DoclingExtractionService:
    """Document extraction service using Docling for OCR and layout analysis.

    Docling provides superior scanned-PDF OCR, table extraction, and structured
    key-value pair detection compared to PyPDF2+pytesseract fallback.

    Usage:
        service = DoclingExtractionService(site_id="S002")
        result = await service.extract_from_upload(file)
    """

    def __init__(self, site_id: str | None = None):
        """Initialize the service.

        Args:
            site_id: Optional site context for logging and metadata.
        """
        self.site_id = site_id
        self._converter: Any = None
        self._docling_available = None

    @property
    def converter(self) -> Any:
        """Lazy-load DocumentConverter (imports docling on first use)."""
        if self._converter is None:
            try:
                from docling.document_converter import DocumentConverter

                self._converter = DocumentConverter()
            except ImportError:
                self._converter = None
        return self._converter

    @property
    def is_available(self) -> bool:
        """Check if docling is installed and importable."""
        if self._docling_available is None:
            import importlib.util

            spec = importlib.util.find_spec("docling.document_converter")
            self._docling_available = spec is not None
        return self._docling_available

    def _detect_file_type(self, filename: str) -> str:
        """Detect file type from filename extension."""
        ext = Path(filename).suffix.lower()
        return ext if ext in DOCLING_SUPPORTED_EXTENSIONS else ""

    async def extract_from_bytes(self, file_bytes: bytes, filename: str = "document.pdf") -> DoclingExtractionResult:
        """Extract text and tables from document bytes using Docling.

        Args:
            file_bytes: Raw file bytes.
            filename: Original filename (used for format detection).

        Returns:
            DoclingExtractionResult with extracted content and metadata.
        """
        if not self.is_available:
            logger.warning("Docling unavailable — returning empty result")
            result = DoclingExtractionResult.empty("docling_not_installed")
            result.metadata["filename"] = filename
            result.metadata["size_bytes"] = len(file_bytes)
            return result

        file_ext = self._detect_file_type(filename)
        if not file_ext:
            logger.warning("Unsupported file type for docling: %s", filename)
            result = DoclingExtractionResult.empty(f"unsupported_file_type:{filename}")
            result.metadata["filename"] = filename
            result.metadata["size_bytes"] = len(file_bytes)
            return result

        try:
            import tempfile

            # Docling's convert() requires a Path or DocumentStream, not BytesIO.
            # Write bytes to a temporary file to satisfy the API.
            with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as tmp:
                tmp.write(file_bytes)
                tmp_path = Path(tmp.name)

            try:
                converter = self.converter
                result = converter.convert(tmp_path)
            finally:
                tmp_path.unlink(missing_ok=True)

            # Export full markdown
            raw_text = result.document.export_to_markdown()

            # Extract tables from markdown (docling includes tables in markdown format)
            # Also try structured table export if available
            tables: list[str] = []
            try:
                if hasattr(result.document, "export_to_tables"):
                    tables = result.document.export_to_tables()
                    if isinstance(tables, str):
                        tables = [tables]
                elif hasattr(result.document, "tables"):
                    tables = result.document.tables or []
            except Exception as e:
                logger.debug("Table extraction note: %s", e)

            # Page count from result
            page_count = len(result.pages) if hasattr(result, "pages") else 0

            # Confidence score
            confidence = float(result.confidence) if hasattr(result, "confidence") else 0.0

            logger.info(
                "Docling extracted %d chars, %d tables, %d pages from %s",
                len(raw_text),
                len(tables),
                page_count,
                filename,
            )

            return DoclingExtractionResult(
                raw_text=raw_text,
                tables=tables if tables else [],
                page_count=page_count,
                extraction_mode="docling",
                confidence=confidence,
                metadata={
                    "filename": filename,
                    "file_type": file_ext,
                    "size_bytes": len(file_bytes),
                    "site_id": self.site_id,
                    "docling_version": self._get_docling_version(),
                },
            )

        except Exception as e:
            logger.warning("Docling extraction failed for %s: %s", filename, e)
            result = DoclingExtractionResult.empty(f"extraction_error:{e}")
            result.metadata["filename"] = filename
            result.metadata["file_type"] = file_ext
            result.metadata["size_bytes"] = len(file_bytes)
            return result

    async def extract_from_upload(self, file: UploadFile) -> DoclingExtractionResult:
        """Extract text and tables from an uploaded FastAPI file.

        Args:
            file: FastAPI UploadFile from multipart form.

        Returns:
            DoclingExtractionResult with extracted content and metadata.
        """
        file_bytes = await file.read()
        return await self.extract_from_bytes(file_bytes, filename=file.filename or "upload")

    def _get_docling_version(self) -> str | None:
        """Return docling version string for metadata."""
        try:
            import docling

            return getattr(docling, "__version__", None)
        except ImportError:
            return None
