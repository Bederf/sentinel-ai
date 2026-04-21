"""
Document Upload Scanner.

Validates uploaded files before they enter the RAG pipeline:
    - Magic byte verification (PDF, JPEG, PNG)
    - File size enforcement (MAX_UPLOAD_SIZE)
    - PDF page count limits (MAX_PDF_PAGES)
    - Image dimension/pixel limits (MAX_IMAGE_PIXELS)
    - Optional antivirus integration (ClamAV)
    - Text extraction size limits (MAX_PDF_TEXT_SIZE)
    - Injection scanning on extracted PDF text
    - EXIF stripping for images
    - Filename sanitization with UUID prefix
    - Path traversal protection via realpath check

Replaces the ad-hoc validation currently in documents.py.
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from app.security.constants import (
    ALLOWED_MAGIC_BYTES,
    INDIRECT_BLOCK_THRESHOLD,
    MAX_IMAGE_PIXELS,
    MAX_PDF_PAGES,
    MAX_PDF_TEXT_SIZE,
    MAX_UPLOAD_SIZE,
    PDF_PARSE_TIMEOUT_SECONDS,
    REQUIRE_AV_SCAN,
)
from app.security.prompt_guard import score_prompt

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class ScanResult:
    """Result of the document upload scan pipeline.

    Attributes:
        allowed: True if the file passed all checks.
        trust_level: Assigned trust level for the document.
        sanitized_filename: UUID-prefixed safe filename.
        safe_path: Resolved absolute path for storage.
        detected_type: File type detected from magic bytes.
        extracted_text: Text extracted from PDFs (empty for images).
        file_hash: SHA-256 hex digest of the original file content.
        rejection_reason: Human-readable reason when allowed is False.
        av_scanned: Whether antivirus scan was performed.
        injection_score: Prompt guard score for extracted text (PDFs).
        exif_stripped: Whether EXIF data was stripped from an image.
    """

    allowed: bool
    trust_level: str
    sanitized_filename: str = ""
    safe_path: str = ""
    detected_type: str = ""
    extracted_text: str = ""
    file_hash: str = ""
    rejection_reason: str = ""
    av_scanned: bool = False
    injection_score: float = 0.0
    exif_stripped: bool = False
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 2: Magic byte validation
# ---------------------------------------------------------------------------


def detect_file_type(content: bytes) -> str | None:
    """Detect file type from magic bytes.

    Returns the type name (``"JPEG"``, ``"PNG"``, ``"PDF"``) or ``None``
    if the content does not match any allowed type.
    """
    for type_name, magic in ALLOWED_MAGIC_BYTES.items():
        if content[: len(magic)] == magic:
            return type_name
    return None


# ---------------------------------------------------------------------------
# Step 3: ClamAV malware scanning
# ---------------------------------------------------------------------------


def scan_for_malware(content: bytes) -> tuple[bool, str]:
    """Scan file content with ClamAV via ``clamdscan --stream``.

    Returns:
        Tuple of (clean, message).
        - clean=True  → no malware detected
        - clean=False → infected or scan failed
    """
    try:
        proc = subprocess.run(
            ["clamdscan", "--stream", "--no-summary", "-"],
            input=content,
            capture_output=True,
            timeout=60,
        )
        if proc.returncode == 0:
            return True, "clean"
        elif proc.returncode == 1:
            # Infected
            stdout = proc.stdout.decode(errors="replace").strip()
            return False, f"malware_detected: {stdout}"
        else:
            stderr = proc.stderr.decode(errors="replace").strip()
            return False, f"scan_error: {stderr}"
    except FileNotFoundError:
        return False, "clamav_unavailable"
    except subprocess.TimeoutExpired:
        return False, "scan_timeout"
    except Exception as exc:
        return False, f"scan_exception: {exc}"


# ---------------------------------------------------------------------------
# Step 4a: PDF text extraction (subprocess with timeout)
# ---------------------------------------------------------------------------


def safe_extract_pdf_text(content: bytes, max_pages: int = MAX_PDF_PAGES) -> tuple[str, int]:
    """Extract text from a PDF in a subprocess with timeout.

    Uses ``pdftotext`` (poppler-utils) for safe extraction.
    Falls back to a Python-only approach if pdftotext is not available.

    Returns:
        Tuple of (extracted_text, page_count).

    Raises:
        ValueError: If extraction fails or limits are exceeded.
    """
    # Try pdftotext first (safer — separate process)
    try:
        proc = subprocess.run(
            ["pdftotext", "-l", str(max_pages), "-", "-"],
            input=content,
            capture_output=True,
            timeout=PDF_PARSE_TIMEOUT_SECONDS,
        )
        if proc.returncode == 0:
            text = proc.stdout.decode(errors="replace")
            # Estimate page count from form feeds
            page_count = text.count("\f") + 1
            if page_count > max_pages:
                raise ValueError(f"PDF has {page_count} pages (max {max_pages})")
            if len(text.encode("utf-8")) > MAX_PDF_TEXT_SIZE:
                text = text[:MAX_PDF_TEXT_SIZE]
            return text, page_count
    except FileNotFoundError:
        pass  # pdftotext not installed; fall through to fallback
    except subprocess.TimeoutExpired:
        raise ValueError(f"PDF text extraction timed out after {PDF_PARSE_TIMEOUT_SECONDS}s")

    # Fallback: try PyPDF2/pypdf
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        page_count = len(reader.pages)
        if page_count > max_pages:
            raise ValueError(f"PDF has {page_count} pages (max {max_pages})")

        text_parts = []
        for page in reader.pages[:max_pages]:
            text_parts.append(page.extract_text() or "")

        text = "\n".join(text_parts)
        if len(text.encode("utf-8")) > MAX_PDF_TEXT_SIZE:
            text = text[:MAX_PDF_TEXT_SIZE]
        return text, page_count
    except ImportError:
        raise ValueError("No PDF extraction tool available (install poppler-utils or pypdf)")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"PDF extraction failed: {exc}")


# ---------------------------------------------------------------------------
# Step 4b: Image dimension validation
# ---------------------------------------------------------------------------


def validate_image_dimensions(content: bytes) -> tuple[int, int]:
    """Validate image dimensions against MAX_IMAGE_PIXELS.

    Returns:
        Tuple of (width, height).

    Raises:
        ValueError: If image exceeds pixel limits or cannot be read.
    """
    try:
        from PIL import Image

        # Set PIL decompression bomb limit
        Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

        img = Image.open(io.BytesIO(content))
        width, height = img.size
        total_pixels = width * height

        if total_pixels > MAX_IMAGE_PIXELS:
            raise ValueError(
                f"Image dimensions {width}x{height} ({total_pixels:,} pixels) exceed limit of {MAX_IMAGE_PIXELS:,}"
            )

        return width, height

    except ImportError:
        raise ValueError("PIL/Pillow not available for image validation")
    except Image.DecompressionBombError:
        raise ValueError(f"Image exceeds decompression limit of {MAX_IMAGE_PIXELS:,} pixels")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Image validation failed: {exc}")


# ---------------------------------------------------------------------------
# Step 5: Filename sanitization
# ---------------------------------------------------------------------------

# Allow only alphanumeric, hyphens, underscores, and dots
_SAFE_FILENAME_RE = re.compile(r"[^a-zA-Z0-9._-]")
_MAX_BASE_LENGTH = 50


def sanitize_filename(original_filename: str) -> str:
    """Generate a safe filename with UUID prefix.

    Format: ``{uuid}_{safe_base}.{ext}``

    Strips all special characters, limits base name length,
    and prepends a UUID to prevent collisions.
    """
    if not original_filename:
        return f"{uuid.uuid4().hex[:12]}_unnamed"

    # Split extension
    parts = original_filename.rsplit(".", 1)
    base = parts[0] if parts else original_filename
    ext = parts[1].lower() if len(parts) > 1 else ""

    # Sanitize base: remove special chars, strip dots (prevent traversal),
    # collapse runs of dashes/underscores
    safe_base = _SAFE_FILENAME_RE.sub("_", base)
    safe_base = safe_base.replace(".", "_")  # dots in base name are suspicious
    safe_base = re.sub(r"[_-]{2,}", "_", safe_base).strip("_-")

    # Truncate base
    if len(safe_base) > _MAX_BASE_LENGTH:
        safe_base = safe_base[:_MAX_BASE_LENGTH]

    # Build final name
    prefix = uuid.uuid4().hex[:12]
    if ext:
        return f"{prefix}_{safe_base}.{ext}"
    return f"{prefix}_{safe_base}"


# ---------------------------------------------------------------------------
# Step 6: Path traversal protection
# ---------------------------------------------------------------------------

# Default storage root for uploaded documents
_DEFAULT_STORAGE_ROOT = Path("backend/app/data/uploads")


def build_safe_path(
    site_id: str,
    filename: str,
    storage_root: Path | str | None = None,
) -> Path:
    """Build a storage path with realpath traversal check.

    Args:
        site_id: Site identifier (e.g. ``"site-002"``).
        filename: Already-sanitized filename.
        storage_root: Root directory for uploads.

    Returns:
        Resolved absolute path.

    Raises:
        ValueError: If the resolved path escapes the storage root.
    """
    root = Path(storage_root) if storage_root else _DEFAULT_STORAGE_ROOT
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)

    # Sanitize site_id to prevent traversal
    safe_site = re.sub(r"[^a-zA-Z0-9_-]", "", site_id)

    candidate = root / safe_site / filename
    resolved = candidate.resolve()

    # Ensure resolved path is under root
    if not str(resolved).startswith(str(root)):
        raise ValueError(f"Path traversal detected: resolved path {resolved} escapes storage root {root}")

    # Ensure parent directory exists
    resolved.parent.mkdir(parents=True, exist_ok=True)

    return resolved


# ---------------------------------------------------------------------------
# Step 9: EXIF stripping
# ---------------------------------------------------------------------------


def strip_exif(content: bytes, file_type: str) -> tuple[bytes, bool]:
    """Strip EXIF metadata from image files.

    Removes GPS coordinates, camera info, and other metadata.

    Returns:
        Tuple of (cleaned_content, was_stripped).
    """
    if file_type not in ("JPEG", "PNG"):
        return content, False

    try:
        from PIL import Image

        img = Image.open(io.BytesIO(content))
        # Create a new image without EXIF
        data = list(img.getdata())
        clean_img = Image.new(img.mode, img.size)
        clean_img.putdata(data)

        buf = io.BytesIO()
        fmt = "JPEG" if file_type == "JPEG" else "PNG"
        clean_img.save(buf, format=fmt, quality=95 if fmt == "JPEG" else None)
        return buf.getvalue(), True
    except ImportError:
        logger.warning("PIL/Pillow not available for EXIF stripping")
        return content, False
    except Exception as exc:
        logger.warning("EXIF stripping failed: %s", exc)
        return content, False


# ---------------------------------------------------------------------------
# Step 10: Audit event helper
# ---------------------------------------------------------------------------


def _log_scan_event(
    event: str,
    user_id: str,
    file_hash: str,
    detected_type: str,
    trust_level: str,
    **extra,
) -> None:
    """Log a structured security audit event for document scanning."""
    logger.info(
        "document_scan_event",
        extra={
            "event": event,
            "user_id": user_id,
            "file_hash": file_hash,
            "detected_type": detected_type,
            "trust_level": trust_level,
            **extra,
        },
    )


# ---------------------------------------------------------------------------
# Main pipeline: validate_and_scan_upload
# ---------------------------------------------------------------------------


async def validate_and_scan_upload(
    file_content: bytes,
    filename: str,
    user_id: str,
    user_role: str,
    site_id: str,
    storage_root: Path | str | None = None,
) -> ScanResult:
    """Full 10-step upload validation and scanning pipeline.

    Args:
        file_content: Raw file bytes.
        filename: Original filename from the upload.
        user_id: ID of the uploading user.
        user_role: Role of the user (e.g. ``"admin"``, ``"operator"``).
        site_id: Site the upload is associated with.
        storage_root: Override storage root directory.

    Returns:
        A :class:`ScanResult` with all scan metadata.
    """
    file_hash = hashlib.sha256(file_content).hexdigest()

    def _reject(reason: str, trust: str = "QUARANTINED") -> ScanResult:
        _log_scan_event("upload_rejected", user_id, file_hash, "", trust, reason=reason)
        return ScanResult(
            allowed=False,
            trust_level=trust,
            file_hash=file_hash,
            rejection_reason=reason,
        )

    # ---- Step 1: Size check ----
    if len(file_content) > MAX_UPLOAD_SIZE:
        return _reject(f"File size {len(file_content):,} bytes exceeds limit of {MAX_UPLOAD_SIZE:,} bytes")

    if len(file_content) == 0:
        return _reject("File is empty")

    # ---- Step 2: Magic byte validation ----
    detected_type = detect_file_type(file_content)
    if detected_type is None:
        return _reject("File type not allowed (magic bytes do not match JPEG, PNG, or PDF)")

    # ---- Step 3: Malware scan ----
    av_scanned = False
    clean, av_message = scan_for_malware(file_content)

    if av_message == "clamav_unavailable":
        if REQUIRE_AV_SCAN:
            return _reject("Antivirus scan required but ClamAV is unavailable (fail closed)")
        else:
            # Mark as untrusted but allow
            logger.warning("ClamAV unavailable; marking upload as untrusted")
    elif not clean:
        _log_scan_event(
            "malware_detected",
            user_id,
            file_hash,
            detected_type,
            "QUARANTINED",
            av_result=av_message,
        )
        return _reject(f"Malware detected: {av_message}")
    else:
        av_scanned = True

    # ---- Step 4: Format-specific limits ----
    extracted_text = ""
    page_count = 0

    if detected_type == "PDF":
        try:
            extracted_text, page_count = safe_extract_pdf_text(file_content)
        except ValueError as exc:
            return _reject(f"PDF validation failed: {exc}")

    elif detected_type in ("JPEG", "PNG"):
        try:
            validate_image_dimensions(file_content)
        except ValueError as exc:
            return _reject(f"Image validation failed: {exc}")

    # ---- Step 5: Filename sanitization ----
    ext_map = {"JPEG": "jpg", "PNG": "png", "PDF": "pdf"}
    # Ensure extension matches detected type
    safe_name = sanitize_filename(filename)
    # Override extension to match detected type
    expected_ext = ext_map.get(detected_type, "")
    if expected_ext:
        name_base = safe_name.rsplit(".", 1)[0] if "." in safe_name else safe_name
        safe_name = f"{name_base}.{expected_ext}"

    # ---- Step 6: Path construction ----
    try:
        safe_path = build_safe_path(site_id, safe_name, storage_root)
    except ValueError as exc:
        return _reject(f"Path validation failed: {exc}")

    # ---- Step 7: Injection scan (PDFs with extracted text) ----
    injection_score = 0.0
    trust_level = "STANDARD"

    if detected_type == "PDF" and extracted_text.strip():
        guard_result = score_prompt(extracted_text, source="indirect")
        injection_score = guard_result.score

        if injection_score >= INDIRECT_BLOCK_THRESHOLD:
            trust_level = "QUARANTINED"
            _log_scan_event(
                "injection_detected_in_pdf",
                user_id,
                file_hash,
                detected_type,
                trust_level,
                injection_score=injection_score,
                reasons=guard_result.reasons,
            )
            # Audit: DOCUMENT_QUARANTINED (Phase 137-09)
            try:
                from app.security.audit_events import audit_document_quarantined

                audit_document_quarantined(
                    file_hash=file_hash,
                    reason=f"injection_score={injection_score:.2f}",
                    user=user_id,
                )
            except Exception:
                pass

    # ---- Step 8: Trust level assignment ----
    if trust_level != "QUARANTINED":
        trust_level = "VERIFIED" if user_role.lower() == "admin" else "STANDARD"

    # If AV scan was skipped (ClamAV unavailable, REQUIRE_AV_SCAN=false), downgrade trust
    if not av_scanned and av_message == "clamav_unavailable" and trust_level != "QUARANTINED":
        trust_level = "UNTRUSTED"

    # ---- Step 9: EXIF stripping for images ----
    exif_stripped = False
    if detected_type in ("JPEG", "PNG"):
        file_content, exif_stripped = strip_exif(file_content, detected_type)

    # ---- Step 10: Audit event ----
    warnings: list[str] = []
    if not av_scanned and av_message == "clamav_unavailable":
        warnings.append("ClamAV unavailable; file not scanned for malware")
    if trust_level == "QUARANTINED":
        warnings.append("Document quarantined due to injection patterns in PDF text")

    _log_scan_event(
        "upload_accepted",
        user_id,
        file_hash,
        detected_type,
        trust_level,
        sanitized_filename=safe_name,
        safe_path=str(safe_path),
        av_scanned=av_scanned,
        injection_score=injection_score,
        exif_stripped=exif_stripped,
        page_count=page_count,
    )

    return ScanResult(
        allowed=True,
        trust_level=trust_level,
        sanitized_filename=safe_name,
        safe_path=str(safe_path),
        detected_type=detected_type,
        extracted_text=extracted_text,
        file_hash=file_hash,
        av_scanned=av_scanned,
        injection_score=injection_score,
        exif_stripped=exif_stripped,
        warnings=warnings,
    )
