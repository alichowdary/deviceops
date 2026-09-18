"""Authenticated MQTT envelope creation and verification."""

from __future__ import annotations

import hashlib
import hmac
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


MqttDirection = Literal["d2s", "s2d"]
SESSION_ID_PATTERN = r"^[0-9a-f]{32}$"
SIGNATURE_PATTERN = r"^[0-9a-f]{64}$"
_STORED_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class MqttAuthenticationError(ValueError):
    """Raised when MQTT authentication data is malformed."""


class AuthenticatedMqttEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auth_version: Literal[1]
    session_id: str = Field(pattern=SESSION_ID_PATTERN)
    body: str
    signature: str = Field(pattern=SIGNATURE_PATTERN)


def parse_authenticated_envelope(payload: bytes) -> AuthenticatedMqttEnvelope:
    try:
        return AuthenticatedMqttEnvelope.model_validate_json(payload)
    except ValidationError as exc:
        raise MqttAuthenticationError("invalid authenticated MQTT envelope") from exc


def signing_key_from_stored_hash(stored_hash: str) -> bytes:
    if _STORED_HASH_PATTERN.fullmatch(stored_hash) is None:
        raise MqttAuthenticationError("invalid stored device credential")
    return bytes.fromhex(stored_hash)


def _signature_input(
    direction: MqttDirection,
    topic: str,
    session_id: str,
    body: str,
) -> bytes:
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
    return hmac.new(
        signing_key,
        _signature_input(direction, topic, session_id, body),
        hashlib.sha256,
    ).hexdigest()


def verify_authenticated_envelope(
    envelope: AuthenticatedMqttEnvelope,
    signing_key: bytes,
    direction: MqttDirection,
    topic: str,
) -> bool:
    expected_signature = compute_mqtt_signature(
        signing_key,
        direction,
        topic,
        envelope.session_id,
        envelope.body,
    )
    return hmac.compare_digest(expected_signature, envelope.signature)


def create_authenticated_envelope(
    body: str,
    signing_key: bytes,
    direction: MqttDirection,
    topic: str,
    session_id: str,
) -> str:
    signature = compute_mqtt_signature(
        signing_key,
        direction,
        topic,
        session_id,
        body,
    )
    try:
        envelope = AuthenticatedMqttEnvelope(
            auth_version=1,
            session_id=session_id,
            body=body,
            signature=signature,
        )
    except ValidationError as exc:
        raise MqttAuthenticationError("invalid authenticated MQTT envelope") from exc
    return envelope.model_dump_json()
