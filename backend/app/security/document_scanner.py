"""
Document Upload Scanner.

Validates uploaded files before they enter the RAG pipeline:
    - Magic byte verification (PDF, JPEG, PNG)
    - File size enforcement (MAX_UPLOAD_SIZE)
    - PDF page count limits (MAX_PDF_PAGES)
    - Image dimension/pixel limits (MAX_IMAGE_PIXELS)
    - Optional antivirus integration (ClamAV)
    - Text extraction size limits (MAX_PDF_TEXT_SIZE)

Replaces the ad-hoc validation currently in documents.py.
"""
