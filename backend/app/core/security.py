"""Security, Cryptography, and Token Management Utilities."""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from typing import Any, Dict, Optional

import bcrypt
from jose import JWTError, jwt

from backend.app.core.config import settings


def get_password_hash(password: str) -> str:
    """
    Hash a password using bcrypt with standard salt generation.
    Truncates to 72 bytes per bcrypt specification.
    """
    pwd_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain password against a bcrypt hash.
    """
    try:
        pwd_bytes = plain_password.encode("utf-8")[:72]
        hash_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pwd_bytes, hash_bytes)
    except Exception:
        return False


def create_access_token(
    subject: str,
    tenant_id: Optional[str],
    role: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Generate a signed JWT access token containing subject, tenant, and role claims.
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode: Dict[str, Any] = {
        "sub": str(subject),
        "tenant_id": str(tenant_id) if tenant_id else None,
        "role": str(role),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }

    return jwt.encode(
        to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def decode_token(token: str) -> Dict[str, Any]:
    """
    Decode and validate a JWT access token.
    Raises JWTError if invalid or expired.
    """
    return jwt.decode(
        token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
    )


def hash_secret(secret: str) -> str:
    """
    One-way cryptographic SHA-256 hash for API keys and webhook secrets.
    """
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def verify_secret(secret: str, secret_hash: str) -> bool:
    """
    Constant-time comparison between raw secret SHA-256 hash and stored hash.
    """
    computed = hash_secret(secret)
    return hmac.compare_digest(computed, secret_hash)


def verify_webhook_signature(
    payload_bytes: bytes,
    signature_header: str,
    secret: str,
) -> bool:
    """
    Verify incoming POS webhook HMAC-SHA256 signature in constant time.
    Format expected: 'sha256=<hex_digest>'
    """
    if not signature_header or not signature_header.startswith("sha256="):
        return False

    received_hash = signature_header.split("sha256=", 1)[1].strip()
    computed_hash = hmac.new(
        key=secret.encode("utf-8"),
        msg=payload_bytes,
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(received_hash, computed_hash)
