"""Supabase Storage service for file uploads."""

import logging
from typing import Optional

from fastapi import UploadFile

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

STORAGE_BUCKET_NAME = "building-documents"


class StorageService:
    """Wrapper for Supabase Storage operations."""

    def __init__(self, supabase_client):
        self.client = supabase_client

    async def upload_document(
        self,
        building_id: str,
        file: UploadFile,
    ) -> str:
        """Upload document to Supabase Storage.

        Storage path: building-documents/{building_id}/{filename}

        Args:
            building_id: Building UUID
            file: UploadFile from FastAPI multipart form

        Returns:
            Storage path (relative path within bucket)

        Raises:
            Exception: If upload fails
        """
        content = await file.read()

        # Generate storage path
        storage_path = f"{building_id}/{file.filename}"

        try:
            # Upload file to Supabase Storage
            response = self.client.storage.from_(STORAGE_BUCKET_NAME).upload(
                path=storage_path,
                file=content,
                file_options={"content-type": file.content_type or "application/octet-stream"},
            )

            logger.info(f"Uploaded document to {storage_path}")
            return storage_path

        except Exception as e:
            logger.error(f"Failed to upload document: {e}")
            raise

    def get_signed_url(
        self,
        storage_path: str,
        expires_in: int = 3600,
    ) -> str:
        """Get signed URL for downloading document (for Phase 2).

        Args:
            storage_path: Path within bucket (e.g., "{building_id}/{filename}")
            expires_in: URL expiration in seconds (default 1 hour)

        Returns:
            Signed download URL
        """
        try:
            response = self.client.storage.from_(STORAGE_BUCKET_NAME).create_signed_url(
                path=storage_path,
                expires_in=expires_in,
            )

            return response["signedURL"]

        except Exception as e:
            logger.error(f"Failed to get signed URL: {e}")
            raise


def get_storage_service(supabase_client=None):
    """Factory function for StorageService."""
    if supabase_client is None:
        supabase_client = get_supabase_client()
    return StorageService(supabase_client)
