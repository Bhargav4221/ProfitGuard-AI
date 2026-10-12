"""Authentication, Password Hashing, and JWT Token Management.

Never store passwords in plaintext. Passwords are salted and hashed using bcrypt (or PBKDF2 fallback).
JWTs include an expiration timestamp ('exp') and a unique token identifier ('jti') to support token revocation.
"""

import hmac
import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
import jwt

from app.core.config import settings

try:
    import bcrypt

    def hash_password(password: str) -> str:
        salt = bcrypt.gensalt(rounds=12)
        hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    def verify_password(plain_password: str, hashed_password: str) -> bool:
        try:
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
        except Exception:
            return False

except ImportError:
    # PBKDF2-HMAC-SHA256 fallback using Python standard library hashlib
    def hash_password(password: str) -> str:
        salt = os.urandom(16)
        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
        return f"pbkdf2:sha256:100000${salt.hex()}${key.hex()}"

    def verify_password(plain_password: str, hashed_password: str) -> bool:
        try:
            if not hashed_password.startswith("pbkdf2:sha256:"):
                return False
            _, _, iterations_str, salt_hex, key_hex = hashed_password.split("$")
            iterations = int(iterations_str)
            salt = bytes.fromhex(salt_hex)
            expected_key = bytes.fromhex(key_hex)
            actual_key = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, iterations)
            return hmac.compare_digest(actual_key, expected_key)
        except Exception:
            return False


def create_access_token(
    subject: str,
    claims: Dict[str, Any] | None = None,
    expires_delta: timedelta | None = None
) -> str:
    """Creates a signed JWT access token with short expiration (default 15 minutes)."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": str(uuid.uuid4()),
        "type": "access",
    }
    if claims:
        payload.update(claims)

    encoded_jwt = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def create_refresh_token(
    subject: str,
    expires_delta: timedelta | None = None
) -> str:
    """Creates a signed JWT refresh token with longer expiration (default 7 days)."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": str(uuid.uuid4()),
        "type": "refresh",
    }
    encoded_jwt = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> Dict[str, Any]:
    """Decodes and validates a JWT token.
    
    Raises jwt.PyJWTError on invalid signature, expiration, or format.
    """
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        options={"require": ["exp", "sub", "jti", "type"]}
    )
