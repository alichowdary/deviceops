"""Generation and deterministic hashing of high-entropy device credentials."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from uuid import uuid4


def generate_device_id() -> str:
    return f"dev-{uuid4()}"


def generate_device_secret() -> str:
    return f"dop_{secrets.token_urlsafe(32)}"


def hash_device_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def verify_device_secret(secret: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_device_secret(secret), stored_hash)
