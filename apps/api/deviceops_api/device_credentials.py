"""Generation and deterministic hashing of high-entropy device credentials."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from uuid import uuid4

from .mqtt_auth import signing_key_from_stored_hash


BROKER_AUTH_CONTEXT = b"deviceops-broker-auth-v1"


def generate_device_id() -> str:
    return f"dev-{uuid4()}"


def generate_device_secret() -> str:
    return f"dop_{secrets.token_urlsafe(32)}"


def hash_device_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def verify_device_secret(secret: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_device_secret(secret), stored_hash)


def derive_broker_password_from_stored_hash(stored_hash: str) -> str:
    """Derive a domain-separated broker password from stored signing-key hex."""
    signing_key = signing_key_from_stored_hash(stored_hash)
    return hmac.new(
        signing_key,
        BROKER_AUTH_CONTEXT,
        hashlib.sha256,
    ).hexdigest()
