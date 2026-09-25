"""Authenticated MQTT envelope helpers for the device simulator."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import re
import secrets
from typing import Literal


MqttDirection = Literal["d2s", "s2d"]
_ENVELOPE_FIELDS = {"auth_version", "session_id", "body", "signature"}
_SESSION_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_SIGNATURE_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_BROKER_AUTH_CONTEXT = b"deviceops-broker-auth-v1"


class MqttAuthenticationError(ValueError):
    """Raised when MQTT authentication data is malformed."""


@dataclass(frozen=True)
class AuthenticatedMqttEnvelope:
    auth_version: int
    session_id: str
    body: str
    signature: str


def derive_signing_key(device_secret: str) -> bytes:
    """Derive the protocol signing key from a plaintext device secret."""
    if not device_secret:
        raise MqttAuthenticationError("device secret must not be empty")
    return hashlib.sha256(device_secret.encode("utf-8")).digest()


def derive_broker_password(device_secret: str) -> str:
    """Derive the domain-separated Mosquitto password from a device secret."""
    signing_key = derive_signing_key(device_secret)
    return hmac.new(
        signing_key,
        _BROKER_AUTH_CONTEXT,
        hashlib.sha256,
    ).hexdigest()


def generate_session_id() -> str:
    """Return a fresh random 16-byte session ID as lowercase hexadecimal."""
    return secrets.token_hex(16)


def _validate_direction(direction: str) -> None:
    if direction not in {"d2s", "s2d"}:
        raise MqttAuthenticationError("invalid MQTT direction")


def _validate_session_id(session_id: str) -> None:
    if _SESSION_ID_PATTERN.fullmatch(session_id) is None:
        raise MqttAuthenticationError("invalid MQTT session ID")


def _signature_input(
    direction: MqttDirection,
    topic: str,
    session_id: str,
    body: str,
) -> bytes:
    _validate_direction(direction)
    _validate_session_id(session_id)
    body_sha256_hex = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return (
        f"deviceops-auth-v1\n{direction}\n{topic}\n{session_id}\n{body_sha256_hex}"
    ).encode("utf-8")


def compute_mqtt_signature(
    signing_key: bytes,
    direction: MqttDirection,
    topic: str,
    session_id: str,
    body: str,
) -> str:
    """Compute the lowercase hexadecimal HMAC-SHA256 signature."""
    return hmac.new(
        signing_key,
        _signature_input(direction, topic, session_id, body),
        hashlib.sha256,
    ).hexdigest()


def create_authenticated_envelope(
    body: str,
    signing_key: bytes,
    direction: MqttDirection,
    topic: str,
    session_id: str,
) -> str:
    """Serialize a compact authenticated MQTT envelope."""
    signature = compute_mqtt_signature(
        signing_key,
        direction,
        topic,
        session_id,
        body,
    )
    return json.dumps(
        {
            "auth_version": 1,
            "session_id": session_id,
            "body": body,
            "signature": signature,
        },
        separators=(",", ":"),
    )


def parse_authenticated_envelope(
    payload: bytes | str,
) -> AuthenticatedMqttEnvelope:
    """Strictly parse an authenticated MQTT envelope."""
    try:
        encoded = payload.decode("utf-8") if isinstance(payload, bytes) else payload
        decoded = json.loads(encoded)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        raise MqttAuthenticationError("invalid authenticated MQTT envelope") from exc

    if not isinstance(decoded, dict) or set(decoded) != _ENVELOPE_FIELDS:
        raise MqttAuthenticationError("invalid authenticated MQTT envelope")
    if type(decoded["auth_version"]) is not int or decoded["auth_version"] != 1:
        raise MqttAuthenticationError("invalid authenticated MQTT envelope")

    session_id = decoded["session_id"]
    body = decoded["body"]
    signature = decoded["signature"]
    if (
        not isinstance(session_id, str)
        or _SESSION_ID_PATTERN.fullmatch(session_id) is None
    ):
        raise MqttAuthenticationError("invalid authenticated MQTT envelope")
    if not isinstance(body, str):
        raise MqttAuthenticationError("invalid authenticated MQTT envelope")
    if (
        not isinstance(signature, str)
        or _SIGNATURE_PATTERN.fullmatch(signature) is None
    ):
        raise MqttAuthenticationError("invalid authenticated MQTT envelope")

    return AuthenticatedMqttEnvelope(
        auth_version=1,
        session_id=session_id,
        body=body,
        signature=signature,
    )


def verify_authenticated_envelope(
    envelope: AuthenticatedMqttEnvelope,
    signing_key: bytes,
    direction: MqttDirection,
    topic: str,
) -> bool:
    """Return whether an envelope signature matches its exact context."""
    expected_signature = compute_mqtt_signature(
        signing_key,
        direction,
        topic,
        envelope.session_id,
        envelope.body,
    )
    return hmac.compare_digest(expected_signature, envelope.signature)
