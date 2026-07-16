"""At-rest field encryption (G11 — feature-implementation-plan §19).

Transparent application-layer encryption for sensitive content columns via a
SQLAlchemy TypeDecorator. Values are encrypted on write and decrypted on read,
so routers/engines are unchanged. Ciphertext is prefixed with a marker so:
  * legacy plaintext rows (written before this landed) read back untouched, and
  * a value that can't be decrypted (wrong key) is returned raw rather than
    crashing the request.
The underlying DB column stays TEXT, so no schema migration is required.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from src.config import get_settings

# Marker distinguishing encrypted values from legacy plaintext.
_PREFIX = "enc::"


@lru_cache(maxsize=1)
def _cipher() -> Fernet:
    s = get_settings()
    raw = s.field_encryption_key
    if raw:
        try:
            # Accept a ready-made Fernet key as-is...
            return Fernet(raw.encode())
        except Exception:
            # ...otherwise derive a valid 32-byte key from the provided string.
            key = base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())
            return Fernet(key)
    # No dedicated key: derive deterministically from SECRET_KEY.
    key = base64.urlsafe_b64encode(hashlib.sha256(s.secret_key.encode()).digest())
    return Fernet(key)


def encrypt_str(value: str | None) -> str | None:
    if value is None:
        return None
    return _PREFIX + _cipher().encrypt(value.encode()).decode()


def decrypt_str(value: str | None) -> str | None:
    if value is None:
        return None
    if not value.startswith(_PREFIX):
        return value  # legacy plaintext — return untouched
    try:
        return _cipher().decrypt(value[len(_PREFIX):].encode()).decode()
    except InvalidToken:
        return value  # undecryptable (e.g. key rotated) — return raw, don't crash


class EncryptedText(TypeDecorator):
    """TEXT column whose value is encrypted at rest and decrypted transparently."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt_str(value)

    def process_result_value(self, value, dialect):
        return decrypt_str(value)
