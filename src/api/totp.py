"""RFC 6238 TOTP (time-based one-time passwords) for MFA (G10).

Self-contained (stdlib only) so no extra dependency is needed. Compatible with
Google Authenticator / Authy: SHA1, 6 digits, 30s period.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
import urllib.parse

_PERIOD = 30
_DIGITS = 6


def generate_secret(num_bytes: int = 20) -> str:
    """Return a fresh base32 TOTP secret (no padding, as authenticators expect)."""
    return base64.b32encode(secrets.token_bytes(num_bytes)).decode().rstrip("=")


def _b32_decode(secret: str) -> bytes:
    padded = secret.strip().replace(" ", "").upper()
    padded += "=" * ((8 - len(padded) % 8) % 8)
    return base64.b32decode(padded, casefold=True)


def _code_at(secret: str, counter: int, digits: int = _DIGITS) -> str:
    key = _b32_decode(secret)
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    truncated = struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % (10 ** digits)).zfill(digits)


def totp_now(secret: str, at: float | None = None, period: int = _PERIOD) -> str:
    ts = time.time() if at is None else at
    return _code_at(secret, int(ts // period))


def verify_totp(secret: str, code: str, *, valid_window: int = 1, period: int = _PERIOD, at: float | None = None) -> bool:
    """Verify a code, tolerating ±valid_window periods of clock skew."""
    if not secret or not code:
        return False
    code = code.strip()
    if not code.isdigit():
        return False
    ts = time.time() if at is None else at
    counter = int(ts // period)
    for window in range(-valid_window, valid_window + 1):
        if hmac.compare_digest(_code_at(secret, counter + window), code):
            return True
    return False


def provisioning_uri(secret: str, account_name: str, issuer: str = "DuckVault") -> str:
    """otpauth:// URI for QR-code enrollment in an authenticator app."""
    label = urllib.parse.quote(f"{issuer}:{account_name}")
    params = urllib.parse.urlencode({
        "secret": secret,
        "issuer": issuer,
        "algorithm": "SHA1",
        "digits": _DIGITS,
        "period": _PERIOD,
    })
    return f"otpauth://totp/{label}?{params}"
