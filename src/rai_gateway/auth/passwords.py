"""Password hashing with PBKDF2 legacy support and Argon2id for new hashes."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Tuple

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError

    _ARGON2 = PasswordHasher()
except ImportError:  # pragma: no cover - optional until dependency installed
    PasswordHasher = None  # type: ignore[misc, assignment]
    VerifyMismatchError = Exception  # type: ignore[misc, assignment]
    _ARGON2 = None


def hash_password(password: str) -> str:
    """Hash a password with Argon2id when available, else PBKDF2."""
    if _ARGON2 is not None:
        return f"argon2id${_ARGON2.hash(password)}"
    return _hash_pbkdf2(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    if encoded_hash.startswith("argon2id$"):
        if _ARGON2 is None:
            return False
        raw = encoded_hash[len("argon2id$") :]
        try:
            return bool(_ARGON2.verify(raw, password))
        except VerifyMismatchError:
            return False
        except Exception:
            return False

    if encoded_hash.startswith("pbkdf2_sha256$"):
        return _verify_pbkdf2(password, encoded_hash)

    # Legacy format from core.auth.hash_password
    return _verify_pbkdf2(password, encoded_hash)


def needs_rehash(encoded_hash: str) -> bool:
    """True when the stored hash should be upgraded to Argon2id."""
    if _ARGON2 is None:
        return False
    if not encoded_hash.startswith("argon2id$"):
        return True
    raw = encoded_hash[len("argon2id$") :]
    try:
        return bool(_ARGON2.check_needs_rehash(raw))
    except Exception:
        return True


def verify_and_upgrade(password: str, encoded_hash: str) -> Tuple[bool, str | None]:
    """Verify password; return (ok, new_hash_if_upgrade_needed)."""
    if not verify_password(password, encoded_hash):
        return False, None
    if needs_rehash(encoded_hash):
        return True, hash_password(password)
    return True, None


def _hash_pbkdf2(password: str, iterations: int = 390000) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    salt_b64 = base64.b64encode(salt).decode("utf-8")
    digest_b64 = base64.b64encode(digest).decode("utf-8")
    return f"pbkdf2_sha256${iterations}${salt_b64}${digest_b64}"


def _verify_pbkdf2(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, iterations_s, salt_b64, digest_b64 = encoded_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_s)
        salt = base64.b64decode(salt_b64.encode("utf-8"))
        expected = base64.b64decode(digest_b64.encode("utf-8"))
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iterations
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False
