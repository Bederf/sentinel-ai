"""Abstract storage provider and implementations.

Defines StorageProvider interface for file storage operations.
Default: SupabaseStorageProvider. On-prem fallback: FilesystemStorageProvider.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path

from app.config.settings import settings

logger = logging.getLogger(__name__)

STORAGE_BUCKET = "building-documents"


class StorageProvider(ABC):
    @abstractmethod
    async def upload(
        self, bucket: str, path: str, content: bytes, content_type: str = "application/octet-stream"
    ) -> str: ...

    @abstractmethod
    async def download(self, path: str) -> bytes: ...

    @abstractmethod
    async def get_signed_url(self, path: str, expires_in: int = 3600) -> str: ...

    @abstractmethod
    async def delete(self, path: str) -> bool: ...


class SupabaseStorageProvider(StorageProvider):
    def __init__(self) -> None:
        from app.database.supabase_client import get_supabase_client

        self._client = get_supabase_client()

    async def upload(
        self, bucket: str, path: str, content: bytes, content_type: str = "application/octet-stream"
    ) -> str:
        self._client.storage.from_(bucket).upload(
            path=path,
            file=content,
            file_options={"content-type": content_type},
        )
        logger.info("Uploaded to Supabase storage: %s/%s", bucket, path)
        return path

    async def download(self, path: str) -> bytes:
        bucket, *path_parts = path.split("/", 1)
        file_path = path_parts[0] if path_parts else ""
        response = self._client.storage.from_(bucket).download(file_path)
        return response

    async def get_signed_url(self, path: str, expires_in: int = 3600) -> str:
        response = self._client.storage.from_(STORAGE_BUCKET).create_signed_url(
            path=path,
            expires_in=expires_in,
        )
        return response["signedURL"]

    async def delete(self, path: str) -> bool:
        bucket, *path_parts = path.split("/", 1)
        file_path = path_parts[0] if path_parts else ""
        self._client.storage.from_(bucket).remove([file_path])
        return True


class FilesystemStorageProvider(StorageProvider):
    def __init__(self, base_path: str | None = None) -> None:
        self._base_path = Path(base_path or settings.storage_local_path or "/var/sentinel/storage")
        self._base_path.mkdir(parents=True, exist_ok=True)
        logger.info("Filesystem storage root: %s", self._base_path)

    async def upload(
        self, bucket: str, path: str, content: bytes, content_type: str = "application/octet-stream"
    ) -> str:
        full_path = self._base_path / bucket / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(content)
        logger.info("Uploaded to filesystem: %s", full_path)
        return f"{bucket}/{path}"

    async def download(self, path: str) -> bytes:
        full_path = self._base_path / path
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {full_path}")
        return full_path.read_bytes()

    async def get_signed_url(self, path: str, expires_in: int = 3600) -> str:
        full_path = self._base_path / path
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {full_path}")
        return full_path.as_uri()

    async def delete(self, path: str) -> bool:
        full_path = self._base_path / path
        if full_path.exists():
            full_path.unlink()
            parent = full_path.parent
            try:
                parent.rmdir()
            except OSError:
                pass
            return True
        return False


_provider: StorageProvider | None = None


def get_storage_provider() -> StorageProvider:
    global _provider
    if _provider is not None:
        return _provider

    provider_type = os.getenv("STORAGE_PROVIDER", "supabase").lower()
    if provider_type == "filesystem":
        base_path = os.getenv("STORAGE_LOCAL_PATH", settings.storage_local_path)
        _provider = FilesystemStorageProvider(base_path=base_path)
    elif provider_type == "supabase":
        _provider = SupabaseStorageProvider()
    else:
        logger.warning("Unknown STORAGE_PROVIDER=%r, falling back to supabase", provider_type)
        _provider = SupabaseStorageProvider()

    logger.info("Active storage provider: %s", type(_provider).__name__)
    return _provider


def reset_storage_provider() -> None:
    global _provider
    _provider = None
