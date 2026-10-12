"""AES-256-GCM Authenticated Encryption Service.

Operational Risk & Architectural Context:
This service provides Application-Level AES-256-GCM Authenticated Encryption with versioned keys.
- Each encryption operation generates a unique, cryptographically secure 12-byte initialization vector (IV).
- Data integrity and authenticity are verified via a 16-byte authentication tag produced by Galois/Counter Mode.
- Master keys are stored in environment variables (e.g., ENCRYPTION_KEYS={"v1": "<hex>", "v2": "<hex>"}).
- OPERATIONAL RISK: Storing master keys in memory/environment is vulnerable if the container is compromised.
  For enterprise multi-tenant environments, this module implements the ICryptoService interface,
  allowing seamless migration to AWS KMS or Google Cloud KMS envelope encryption.
"""

import os
import binascii
from abc import ABC, abstractmethod
from typing import Dict, Tuple
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.core.config import settings


class CryptoException(Exception):
    """Base exception for cryptographic operations."""
    pass


class TamperDetectedException(CryptoException):
    """Raised when ciphertext or authentication tag fails verification."""
    pass


class KeyNotFoundException(CryptoException):
    """Raised when the specified key version does not exist."""
    pass


class ICryptoService(ABC):
    @abstractmethod
    def encrypt(self, plaintext: str, key_version: str | None = None) -> str:
        """Encrypts plaintext string and returns a versioned serialized token."""
        pass

    @abstractmethod
    def decrypt(self, token: str) -> str:
        """Decrypts a serialized token, verifying authenticity."""
        pass

    @abstractmethod
    def rotate(self, token: str, target_version: str | None = None) -> str:
        """Re-encrypts a token under the target (or active) key version."""
        pass


class AESGCMCryptoService(ICryptoService):
    def __init__(self, keys: Dict[str, str] | None = None, active_version: str | None = None):
        raw_keys = keys or settings.ENCRYPTION_KEYS
        self.active_version = active_version or settings.ACTIVE_ENCRYPTION_KEY_VERSION
        self.keys: Dict[str, bytes] = {}

        for version, hex_key in raw_keys.items():
            try:
                key_bytes = binascii.unhexlify(hex_key)
                if len(key_bytes) != 32:
                    raise CryptoException(f"Key for version {version} must be exactly 32 bytes (64 hex characters), got {len(key_bytes)} bytes.")
                self.keys[version] = key_bytes
            except binascii.Error as e:
                raise CryptoException(f"Invalid hex string for key version {version}: {e}")

        if self.active_version not in self.keys:
            raise KeyNotFoundException(f"Active key version '{self.active_version}' is not present in configured keys.")

    def _get_key(self, version: str) -> bytes:
        if version not in self.keys:
            raise KeyNotFoundException(f"Key version '{version}' not found in active key store.")
        return self.keys[version]

    def encrypt(self, plaintext: str, key_version: str | None = None) -> str:
        """Encrypts plaintext using AES-256-GCM.
        
        Returns a formatted token:
        v{version}:{iv_hex}:{ciphertext_hex}:{tag_hex}
        """
        if not isinstance(plaintext, str):
            raise CryptoException("Plaintext must be a string.")

        version = key_version or self.active_version
        key_bytes = self._get_key(version)
        aesgcm = AESGCM(key_bytes)

        # 96-bit (12-byte) random nonce/IV as recommended by NIST SP 800-38D
        iv = os.urandom(12)
        plaintext_bytes = plaintext.encode("utf-8")

        # AESGCM.encrypt in cryptography produces ciphertext with the 16-byte tag appended at the end
        ciphertext_and_tag = aesgcm.encrypt(iv, plaintext_bytes, None)
        ciphertext = ciphertext_and_tag[:-16]
        tag = ciphertext_and_tag[-16:]

        iv_hex = binascii.hexlify(iv).decode("ascii")
        ciphertext_hex = binascii.hexlify(ciphertext).decode("ascii")
        tag_hex = binascii.hexlify(tag).decode("ascii")

        return f"{version}:{iv_hex}:{ciphertext_hex}:{tag_hex}"

    def _parse_token(self, token: str) -> Tuple[str, bytes, bytes, bytes]:
        parts = token.split(":")
        if len(parts) != 4:
            raise CryptoException(f"Malformed encryption token. Expected 4 colon-delimited segments, got {len(parts)}.")

        version, iv_hex, ciphertext_hex, tag_hex = parts
        try:
            iv = binascii.unhexlify(iv_hex)
            ciphertext = binascii.unhexlify(ciphertext_hex)
            tag = binascii.unhexlify(tag_hex)
        except binascii.Error as e:
            raise CryptoException(f"Malformed hex encoding in encryption token: {e}")

        if len(iv) != 12:
            raise CryptoException(f"Invalid IV length. Expected 12 bytes, got {len(iv)}.")
        if len(tag) != 16:
            raise CryptoException(f"Invalid auth tag length. Expected 16 bytes, got {len(tag)}.")

        return version, iv, ciphertext, tag

    def decrypt(self, token: str) -> str:
        """Decrypts a serialized AES-256-GCM token and verifies authenticity tag.
        
        Raises TamperDetectedException if ciphertext, IV, or tag has been modified.
        """
        version, iv, ciphertext, tag = self._parse_token(token)
        key_bytes = self._get_key(version)
        aesgcm = AESGCM(key_bytes)

        try:
            # Reassemble ciphertext + tag for AESGCM.decrypt
            ciphertext_and_tag = ciphertext + tag
            decrypted_bytes = aesgcm.decrypt(iv, ciphertext_and_tag, None)
            return decrypted_bytes.decode("utf-8")
        except Exception as e:
            # Cryptography library raises InvalidTag if verification fails
            raise TamperDetectedException(f"Decryption failed: authenticity tag verification failed or ciphertext corrupted ({e}).")

    def rotate(self, token: str, target_version: str | None = None) -> str:
        """Decrypts token under its existing version and re-encrypts with target version."""
        plaintext = self.decrypt(token)
        target = target_version or self.active_version
        return self.encrypt(plaintext, key_version=target)


# Global singleton instance
crypto_service = AESGCMCryptoService()
