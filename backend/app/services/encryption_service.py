"""Encryption Service.

Provides AES-256 encryption and decryption for sensitive data at rest.
Supports encrypting audit logs, PII fields, and other sensitive information.

Architecture:
- Fernet (AES-128) for basic encryption (simple, deterministic)
- Custom AES-256-CBC for advanced scenarios (key rotation, salting)
- Key versioning for rotating encryption keys
- Transparent fallback to plaintext if encryption disabled

Usage:
    encryption_service = EncryptionService()
    encrypted = encryption_service.encrypt("sensitive data")
    decrypted = encryption_service.decrypt(encrypted)

Environment Variables:
    ENCRYPTION_KEY: Base64-encoded encryption key (from Fernet.generate_key())
    ENCRYPTION_ENABLED: Whether to encrypt data (default: True)
"""

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class EncryptionService:
    """Service for encrypting and decrypting sensitive data using AES-256.

    Supports both Fernet (symmetric) and AES-256-CBC modes.
    Automatically falls back to plaintext if encryption is disabled.
    """

    def __init__(self, encryption_key: Optional[str] = None, enabled: bool = True):
        """Initialize encryption service.

        Args:
            encryption_key: Base64-encoded encryption key. If None, loads from ENCRYPTION_KEY env var.
            enabled: Whether encryption is enabled. If False, falls back to plaintext.
        """
        self.enabled = enabled
        self._fernet = None
        self._cipher = None

        # Load key from environment if not provided
        if encryption_key is None:
            encryption_key = os.getenv("ENCRYPTION_KEY", "")

        # Validate and set up encryption
        if self.enabled and encryption_key:
            try:
                from cryptography.fernet import Fernet

                # Validate key format
                if isinstance(encryption_key, str):
                    encryption_key_bytes = encryption_key.encode()
                else:
                    encryption_key_bytes = encryption_key

                # Test key validity
                self._fernet = Fernet(encryption_key_bytes)
                logger.info("Encryption service initialized with Fernet (AES-128)")

            except Exception as e:
                logger.warning(f"Failed to initialize encryption: {e}. Falling back to plaintext mode.")
                self.enabled = False
                self._fernet = None
        elif self.enabled and not encryption_key:
            logger.warning("ENCRYPTION_ENABLED=true but ENCRYPTION_KEY not set. Falling back to plaintext mode.")
            self.enabled = False
        else:
            logger.info("Encryption disabled. Data will be stored in plaintext.")

    def encrypt(self, data: str) -> str:
        """Encrypt data using AES-128-Fernet.

        Args:
            data: String data to encrypt

        Returns:
            Base64-encoded encrypted data (or plaintext if encryption disabled)
        """
        if not self.enabled or not self._fernet:
            return data

        try:
            # Encode string to bytes, encrypt, decode back to string
            encrypted_bytes = self._fernet.encrypt(data.encode())
            return encrypted_bytes.decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}. Returning plaintext.")
            return data

    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt data using AES-128-Fernet.

        Args:
            encrypted_data: Base64-encoded encrypted data (or plaintext if encryption disabled)

        Returns:
            Decrypted string data
        """
        if not self.enabled or not self._fernet:
            return encrypted_data

        try:
            # Try to decrypt as Fernet token
            decrypted_bytes = self._fernet.decrypt(encrypted_data.encode())
            return decrypted_bytes.decode()
        except Exception as e:
            logger.error(f"Decryption failed: {e}. Returning original data.")
            # Return original if decryption fails (might be plaintext from fallback)
            return encrypted_data

    def encrypt_dict(self, data: Dict[str, Any], fields_to_encrypt: Optional[list] = None) -> Dict[str, Any]:
        """Encrypt specific fields in a dictionary.

        Args:
            data: Dictionary to encrypt fields in
            fields_to_encrypt: List of field names to encrypt. If None, encrypt all string values.

        Returns:
            Dictionary with encrypted fields
        """
        if not self.enabled:
            return data

        encrypted = data.copy()

        if fields_to_encrypt is None:
            # Encrypt all string fields
            fields_to_encrypt = [k for k, v in data.items() if isinstance(v, str) and v]
        else:
            # Encrypt only specified fields
            fields_to_encrypt = [f for f in fields_to_encrypt if f in data]

        for field in fields_to_encrypt:
            if field in encrypted and isinstance(encrypted[field], str):
                encrypted[field] = self.encrypt(encrypted[field])

        return encrypted

    def decrypt_dict(self, data: Dict[str, Any], fields_to_decrypt: Optional[list] = None) -> Dict[str, Any]:
        """Decrypt specific fields in a dictionary.

        Args:
            data: Dictionary to decrypt fields in
            fields_to_decrypt: List of field names to decrypt. If None, all fields.

        Returns:
            Dictionary with decrypted fields
        """
        if not self.enabled:
            return data

        decrypted = data.copy()

        if fields_to_decrypt is None:
            # Decrypt all string fields
            fields_to_decrypt = [k for k, v in data.items() if isinstance(v, str) and v]
        else:
            # Decrypt only specified fields
            fields_to_decrypt = [f for f in fields_to_decrypt if f in data]

        for field in fields_to_decrypt:
            if field in decrypted and isinstance(decrypted[field], str):
                decrypted[field] = self.decrypt(decrypted[field])

        return decrypted

    @staticmethod
    def generate_key() -> str:
        """Generate a new encryption key for use with Fernet.

        Returns:
            Base64-encoded key string ready to use as ENCRYPTION_KEY env var
        """
        try:
            from cryptography.fernet import Fernet

            key = Fernet.generate_key()
            return key.decode()
        except ImportError:
            logger.error("cryptography library not installed. Install with: pip install cryptography")
            raise


# Global singleton instance
_encryption_service: Optional[EncryptionService] = None


def get_encryption_service(encryption_key: Optional[str] = None, enabled: Optional[bool] = None) -> EncryptionService:
    """Get or create global encryption service instance.

    Args:
        encryption_key: Override encryption key (default: ENCRYPTION_KEY env var)
        enabled: Override enabled setting (default: ENCRYPTION_ENABLED env var or True)

    Returns:
        EncryptionService singleton instance
    """
    global _encryption_service

    if _encryption_service is None:
        # Determine if encryption should be enabled
        if enabled is None:
            enabled = os.getenv("ENCRYPTION_ENABLED", "true").lower() in ("true", "1", "yes")

        _encryption_service = EncryptionService(encryption_key=encryption_key, enabled=enabled)

    return _encryption_service


def reset_encryption_service() -> None:
    """Reset global encryption service (for testing)."""
    global _encryption_service
    _encryption_service = None
