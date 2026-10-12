"""Tests for AES-256-GCM Reusable Encryption Service."""

import pytest
from app.core.crypto import (
    AESGCMCryptoService,
    CryptoException,
    KeyNotFoundException,
    TamperDetectedException,
)


@pytest.fixture
def crypto_service():
    keys = {
        "v1": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        "v2": "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210",
    }
    return AESGCMCryptoService(keys=keys, active_version="v1")


def test_encryption_and_decryption_success(crypto_service):
    plaintext = "shpat_live_secret_token_12345"
    token = crypto_service.encrypt(plaintext)

    assert token.startswith("v1:")
    decrypted = crypto_service.decrypt(token)
    assert decrypted == plaintext


def test_fresh_nonce_per_operation(crypto_service):
    plaintext = "identical_sensitive_api_key"
    token1 = crypto_service.encrypt(plaintext)
    token2 = crypto_service.encrypt(plaintext)

    # Different random IVs guarantee ciphertexts differ
    assert token1 != token2
    assert crypto_service.decrypt(token1) == plaintext
    assert crypto_service.decrypt(token2) == plaintext


def test_tamper_detection_ciphertext(crypto_service):
    plaintext = "webhook_secret_key"
    token = crypto_service.encrypt(plaintext)
    parts = token.split(":")

    # Corrupt ciphertext byte
    corrupted_ciphertext = "ff" + parts[2][2:]
    tampered_token = f"{parts[0]}:{parts[1]}:{corrupted_ciphertext}:{parts[3]}"

    with pytest.raises(TamperDetectedException):
        crypto_service.decrypt(tampered_token)


def test_tamper_detection_iv(crypto_service):
    plaintext = "sensitive_card_data"
    token = crypto_service.encrypt(plaintext)
    parts = token.split(":")

    # Corrupt IV byte
    corrupted_iv = "aa" + parts[1][2:]
    tampered_token = f"{parts[0]}:{corrupted_iv}:{parts[2]}:{parts[3]}"

    with pytest.raises(TamperDetectedException):
        crypto_service.decrypt(tampered_token)


def test_tamper_detection_auth_tag(crypto_service):
    plaintext = "secret_payment_credentials"
    token = crypto_service.encrypt(plaintext)
    parts = token.split(":")

    # Corrupt authentication tag byte
    corrupted_tag = "bb" + parts[3][2:]
    tampered_token = f"{parts[0]}:{parts[1]}:{parts[2]}:{corrupted_tag}"

    with pytest.raises(TamperDetectedException):
        crypto_service.decrypt(tampered_token)


def test_incorrect_key_rejection():
    keys_a = {"v1": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"}
    keys_b = {"v1": "9999999999999999999999999999999999999999999999999999999999999999"}

    svc_a = AESGCMCryptoService(keys=keys_a, active_version="v1")
    svc_b = AESGCMCryptoService(keys=keys_b, active_version="v1")

    token = svc_a.encrypt("my_secret")
    with pytest.raises(TamperDetectedException):
        svc_b.decrypt(token)


def test_key_rotation_across_versions(crypto_service):
    plaintext = "long_lived_shopify_offline_access_token"
    token_v1 = crypto_service.encrypt(plaintext, key_version="v1")
    assert token_v1.startswith("v1:")

    # Rotate token from v1 to v2
    token_v2 = crypto_service.rotate(token_v1, target_version="v2")
    assert token_v2.startswith("v2:")
    assert token_v2 != token_v1

    # Verify token_v2 decrypts correctly
    assert crypto_service.decrypt(token_v2) == plaintext


def test_missing_key_version_raises(crypto_service):
    with pytest.raises(KeyNotFoundException):
        crypto_service.encrypt("data", key_version="v99")
