"""Document text extraction service for multiple file types."""

import logging
from pathlib import Path
from typing import Tuple

from fastapi import UploadFile

logger = logging.getLogger(__name__)


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from PDF using PyPDF2.

    Args:
        file_bytes: Raw PDF file bytes

    Returns:
        Extracted text content
    """
    try:
        from PyPDF2 import PdfReader
        from io import BytesIO

        pdf_reader = PdfReader(BytesIO(file_bytes))
        text_parts = []

        for page_num, page in enumerate(pdf_reader.pages):
            try:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
            except Exception as e:
                logger.warning(f"Failed to extract text from PDF page {page_num}: {e}")

        return "\n\n".join(text_parts)

    except ImportError:
        raise ImportError("PyPDF2 is required for PDF extraction. Install with: pip install PyPDF2")
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}")
        raise


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract text from DOCX using python-docx.

    Args:
        file_bytes: Raw DOCX file bytes

    Returns:
        Extracted text content
    """
    try:
        from docx import Document
        from io import BytesIO

        doc = Document(BytesIO(file_bytes))
        text_parts = []

        for para in doc.paragraphs:
            if para.text.strip():
                text_parts.append(para.text)

        # Also extract text from tables if present
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text.strip():
                        text_parts.append(cell.text)

        return "\n\n".join(text_parts)

    except ImportError:
        raise ImportError("python-docx is required for DOCX extraction. Install with: pip install python-docx")
    except Exception as e:
        logger.error(f"Error extracting text from DOCX: {e}")
        raise


async def extract_text(file: UploadFile) -> Tuple[str, dict]:
    """Extract text from uploaded file based on file type.

    Supports: PDF, DOCX, TXT

    Args:
        file: UploadFile from FastAPI multipart form

    Returns:
        Tuple of (extracted_text, metadata_dict)

    Raises:
        ValueError: If file type is not supported
        ImportError: If required package is not installed
    """
    # Read file content
    content = await file.read()

    # Determine file type from extension
    file_ext = Path(file.filename or "").suffix.lower()

    if file_ext == ".pdf":
        text = extract_text_from_pdf(content)
    elif file_ext == ".docx":
        text = extract_text_from_docx(content)
    elif file_ext == ".txt":
        text = content.decode("utf-8")
    else:
        raise ValueError(f"Unsupported file type: {file_ext}. Supported types: .pdf, .docx, .txt")

    # Build metadata
    metadata = {
        "filename": file.filename,
        "size_bytes": len(content),
        "file_type": file_ext,
    }

    logger.info(f"Extracted text from {file.filename}: {len(text)} characters")

    return text, metadata
