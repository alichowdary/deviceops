"""MQTT subscriptions and persistence of validated device messages."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import re

import paho.mqtt.client as mqtt
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .alerts import (
    evaluate_committed_metric_sample,
    evaluate_offline_alerts_once,
)
from .config import settings
from .database import SessionLocal
from .events import create_device_event, event_created_message
from .models import Device, DeviceCommand, Telemetry
from .mqtt_auth import (
    AuthenticatedMqttEnvelope,
    MqttAuthenticationError,
    create_authenticated_envelope,
    parse_authenticated_envelope,
    signing_key_from_stored_hash,
    verify_authenticated_envelope,
)
from .realtime import realtime_hub
from .schemas import CapabilityManifest, CommandAckPayload, TelemetryPayload


logger = logging.getLogger(__name__)

TELEMETRY_SUBSCRIPTION = "deviceops/v1/devices/+/telemetry"
STATUS_SUBSCRIPTION = "deviceops/v1/devices/+/status"
COMMAND_ACK_SUBSCRIPTION = "deviceops/v1/devices/+/command-acks"
CAPABILITIES_SUBSCRIPTION = "deviceops/v1/devices/+/capabilities"
MAX_CAPABILITY_BODY_BYTES = 16_384
TOPIC_PATTERN = re.compile(
    r"^deviceops/v1/devices/([A-Za-z0-9][A-Za-z0-9._-]{0,63})/"
    r"(telemetry|status|command-acks|capabilities)$"
)


def _utc_isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class MqttPublishError(RuntimeError):
    """Raised when FastAPI cannot confirm publication to the MQTT broker."""


class MqttIngestor:
    def __init__(self) -> None:
        self._connected = False
        self._last_error: str | None = None
        self._started = False
        self._stopping = False
        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=settings.mqtt_client_id,
            protocol=mqtt.MQTTv311,
        )
        self._client.on_connect = self._on_connect
        self._client.on_connect_fail = self._on_connect_fail
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def start(self) -> None:
        if self._started:
            return
        self._stopping = False
        logger.info(
            "Starting MQTT connection to %s:%s",
            settings.mqtt_host,
            settings.mqtt_port,
        )
        self._client.connect_async(settings.mqtt_host, settings.mqtt_port, keepalive=30)
        self._client.loop_start()
        self._started = True

    def stop(self) -> None:
        if not self._started:
            return
        self._stopping = True
        self._client.disconnect()
        self._client.loop_stop()
        self._connected = False
        self._started = False
        logger.info("MQTT client stopped")

    def publish_command(self, command: DeviceCommand) -> None:
        topic = f"deviceops/v1/devices/{command.device_id}/commands"
        body = json.dumps(
            {
                "protocol_version": 1,
                "command_id": command.command_id,
                "device_id": command.device_id,
                "issued_at": _utc_isoformat(command.issued_at),
                "type": command.command_type,
                "arguments": command.arguments,
            },
            separators=(",", ":"),
        )

        try:
            with SessionLocal() as session:
                device = session.get(Device, command.device_id)
                if device is None:
                    raise MqttPublishError("Command device does not exist")
                if device.device_secret_hash is None:
                    raise MqttPublishError("Command device has no MQTT credential")
                if device.mqtt_session_id is None:
                    raise MqttPublishError("Command device has no active MQTT session")
                signing_key = signing_key_from_stored_hash(
                    device.device_secret_hash
                )
                mqtt_session_id = device.mqtt_session_id
        except SQLAlchemyError as exc:
            raise MqttPublishError("Could not load command device") from exc
        except MqttAuthenticationError as exc:
            raise MqttPublishError("Command device credential is invalid") from exc

        if not self._connected:
            raise MqttPublishError("MQTT is not connected")

        try:
            payload = create_authenticated_envelope(
                body=body,
                signing_key=signing_key,
                direction="s2d",
                topic=topic,
                session_id=mqtt_session_id,
            )
        except MqttAuthenticationError as exc:
            raise MqttPublishError("Command device MQTT session is invalid") from exc
        publish = self._client.publish(topic, payload, qos=1, retain=False)
        if publish.rc != mqtt.MQTT_ERR_SUCCESS:
            raise MqttPublishError(mqtt.error_string(publish.rc))

        try:
            publish.wait_for_publish(timeout=5)
        except RuntimeError as exc:
            raise MqttPublishError(str(exc)) from exc
        if not publish.is_published():
            raise MqttPublishError("timed out waiting for broker acknowledgement")

        logger.info(
            "Published command device=%s command_id=%s type=%s",
            command.device_id,
            command.command_id,
            command.command_type,
        )

    def _on_connect(
        self,
        client: mqtt.Client,
        _userdata: object,
        _flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        _properties: mqtt.Properties | None,
    ) -> None:
        if reason_code.is_failure:
            self._connected = False
            self._last_error = f"connection rejected: {reason_code}"
            logger.error("MQTT %s", self._last_error)
            return

        result, _message_id = client.subscribe(
            [
                (TELEMETRY_SUBSCRIPTION, 0),
                (STATUS_SUBSCRIPTION, 1),
                (COMMAND_ACK_SUBSCRIPTION, 1),
                (CAPABILITIES_SUBSCRIPTION, 1),
            ]
        )
        if result != mqtt.MQTT_ERR_SUCCESS:
            self._connected = False
            self._last_error = f"subscription failed: {mqtt.error_string(result)}"
            logger.error("MQTT %s", self._last_error)
            return

        self._connected = True
        self._last_error = None
        logger.info(
            "MQTT connected; subscribed to %s, %s, %s, and %s",
            TELEMETRY_SUBSCRIPTION,
            STATUS_SUBSCRIPTION,
            COMMAND_ACK_SUBSCRIPTION,
            CAPABILITIES_SUBSCRIPTION,
        )

    def _on_connect_fail(self, _client: mqtt.Client, _userdata: object) -> None:
        self._connected = False
        self._last_error = (
            f"could not connect to {settings.mqtt_host}:{settings.mqtt_port}"
        )
        logger.error("MQTT %s; retrying", self._last_error)

    def _on_disconnect(
        self,
        _client: mqtt.Client,
        _userdata: object,
        _disconnect_flags: mqtt.DisconnectFlags,
        reason_code: mqtt.ReasonCode,
        _properties: mqtt.Properties | None,
    ) -> None:
        self._connected = False
        if not self._stopping:
            self._last_error = f"disconnected: {reason_code}"
            logger.warning("MQTT %s; reconnecting", self._last_error)

    def _on_message(
        self,
        _client: mqtt.Client,
        _userdata: object,
        message: mqtt.MQTTMessage,
    ) -> None:
        try:
            self._process_message(message.topic, message.payload)
        except Exception:
            # A malformed device message or database error must not stop Paho's loop.
            logger.exception("Unexpected error processing MQTT message on %s", message.topic)

    def _process_message(self, topic: str, payload: bytes) -> None:
        topic_match = TOPIC_PATTERN.fullmatch(topic)
        if topic_match is None:
            logger.warning("Rejected MQTT message with unexpected topic: %s", topic)
            return

        topic_device_id, message_kind = topic_match.groups()
        try:
            envelope = parse_authenticated_envelope(payload)
        except MqttAuthenticationError:
            logger.warning(
                "Rejected MQTT message with invalid authentication envelope: device=%s",
                topic_device_id,
            )
            return

        received_at = datetime.now(timezone.utc)

        if message_kind == "telemetry":
            self._process_telemetry(topic_device_id, topic, envelope, received_at)
        elif message_kind == "status":
            self._process_status(topic_device_id, topic, envelope, received_at)
        elif message_kind == "capabilities":
            self._process_capabilities(
                topic_device_id, topic, envelope, received_at
            )
        else:
            self._process_command_ack(topic_device_id, topic, envelope, received_at)

    def _authenticate_device_envelope(
        self,
        session: Session,
        topic_device_id: str,
        topic: str,
        envelope: AuthenticatedMqttEnvelope,
    ) -> Device | None:
        device = session.get(Device, topic_device_id)
        if device is None:
            logger.warning(
                "Rejected authenticated MQTT message for unknown device=%s",
                topic_device_id,
            )
            return None
        if device.owner_id is None:
            logger.warning(
                "Rejected authenticated MQTT message for unowned device=%s",
                topic_device_id,
            )
            return None
        if device.device_secret_hash is None:
            logger.warning(
                "Rejected authenticated MQTT message without credential: device=%s",
                topic_device_id,
            )
            return None

        try:
            signing_key = signing_key_from_stored_hash(device.device_secret_hash)
        except MqttAuthenticationError:
            logger.warning(
                "Rejected authenticated MQTT message with invalid stored credential: device=%s",
                topic_device_id,
            )
            return None
        if not verify_authenticated_envelope(
            envelope,
            signing_key,
            direction="d2s",
            topic=topic,
        ):
            logger.warning(
                "Rejected MQTT message with invalid signature: device=%s",
                topic_device_id,
            )
            return None
        return device

    def _process_capabilities(
        self,
        topic_device_id: str,
        topic: str,
        envelope: AuthenticatedMqttEnvelope,
        received_at: datetime,
    ) -> None:
        try:
            with SessionLocal.begin() as session:
                device = self._authenticate_device_envelope(
                    session,
                    topic_device_id,
                    topic,
                    envelope,
                )
                if device is None:
                    return
                if device.mqtt_session_id != envelope.session_id:
                    logger.warning(
                        "Rejected capabilities with stale MQTT session: device=%s",
                        topic_device_id,
                    )
                    return
                if len(envelope.body.encode("utf-8")) > MAX_CAPABILITY_BODY_BYTES:
                    logger.warning(
                        "Rejected oversized capabilities manifest: device=%s",
                        topic_device_id,
                    )
                    return

                try:
                    payload = CapabilityManifest.model_validate_json(envelope.body)
                except ValidationError as exc:
                    logger.warning(
                        "Rejected malformed capabilities for device %s: %s",
                        topic_device_id,
                        exc.errors(include_url=False, include_input=False),
                    )
                    return

                if payload.device_id != topic_device_id:
                    logger.warning(
                        "Rejected capabilities device ID mismatch: topic=%s payload=%s",
                        topic_device_id,
                        payload.device_id,
                    )
                    return

                capabilities = payload.model_dump(mode="json")
                device.capabilities = capabilities
                device.capabilities_updated_at = received_at
                device.last_seen_at = received_at
                owner_id = device.owner_id
        except SQLAlchemyError:
            logger.exception(
                "Database write failed for capabilities from %s", topic_device_id
            )
            return

        logger.info(
            "Stored capabilities device=%s received_at=%s",
            topic_device_id,
            received_at.isoformat(),
        )
        realtime_hub.publish_from_thread(
            owner_id,
            {
                "type": "capabilities_updated",
                "device_id": topic_device_id,
                "received_at": _utc_isoformat(received_at),
                "data": {"capabilities": capabilities},
            },
        )

    def _process_telemetry(
        self,
        topic_device_id: str,
        topic: str,
        envelope: AuthenticatedMqttEnvelope,
        received_at: datetime,
    ) -> None:
        try:
            with SessionLocal.begin() as session:
                device = self._authenticate_device_envelope(
                    session,
                    topic_device_id,
                    topic,
                    envelope,
                )
                if device is None:
                    return
                if device.mqtt_session_id != envelope.session_id:
                    logger.warning(
                        "Rejected telemetry with stale MQTT session: device=%s",
                        topic_device_id,
                    )
                    return

                try:
                    payload = TelemetryPayload.model_validate_json(envelope.body)
                except ValidationError as exc:
                    logger.warning(
                        "Rejected malformed telemetry for device %s: %s",
                        topic_device_id,
                        exc.errors(include_url=False, include_input=False),
                    )
                    return

                if payload.device_id != topic_device_id:
                    logger.warning(
                        "Rejected telemetry device ID mismatch: topic=%s payload=%s",
                        topic_device_id,
                        payload.device_id,
                    )
                    return

                if device.first_seen_at is None:
                    device.first_seen_at = received_at
                device.last_seen_at = received_at

                additional_metrics = payload.metrics.model_extra or None
                telemetry = Telemetry(
                    device_id=topic_device_id,
                    sequence=payload.sequence,
                    sent_at=payload.sent_at,
                    received_at=received_at,
                    temperature_c=payload.metrics.temperature_c,
                    battery_pct=payload.metrics.battery_pct,
                    humidity_pct=payload.metrics.humidity_pct,
                    pressure_hpa=payload.metrics.pressure_hpa,
                    rssi_dbm=payload.metrics.rssi_dbm,
                    uptime_s=payload.metrics.uptime_s,
                    additional_metrics=additional_metrics,
                )
                session.add(telemetry)
                session.flush()
                telemetry_id = telemetry.id
                owner_id = device.owner_id
        except SQLAlchemyError:
            logger.exception("Database write failed for telemetry from %s", topic_device_id)
            return

        logger.info(
            "Stored telemetry device=%s sequence=%s received_at=%s",
            topic_device_id,
            payload.sequence,
            received_at.isoformat(),
        )
        realtime_hub.publish_from_thread(
            owner_id,
            {
                "type": "telemetry",
                "device_id": topic_device_id,
                "received_at": _utc_isoformat(received_at),
                "data": {
                    "id": telemetry_id,
                    "sequence": payload.sequence,
                    "sent_at": _utc_isoformat(payload.sent_at),
                    "temperature_c": payload.metrics.temperature_c,
                    "battery_pct": payload.metrics.battery_pct,
                    "humidity_pct": payload.metrics.humidity_pct,
                    "pressure_hpa": payload.metrics.pressure_hpa,
                    "rssi_dbm": payload.metrics.rssi_dbm,
                    "uptime_s": payload.metrics.uptime_s,
                    "additional_metrics": additional_metrics,
                },
            }
        )
        try:
            evaluate_committed_metric_sample(
                device_id=topic_device_id,
                metrics={
                    "temperature_c": payload.metrics.temperature_c,
                    "battery_pct": payload.metrics.battery_pct,
                    "humidity_pct": payload.metrics.humidity_pct,
                    "pressure_hpa": payload.metrics.pressure_hpa,
                    "rssi_dbm": payload.metrics.rssi_dbm,
                },
                observed_at=received_at,
            )
        except Exception:
            logger.exception(
                "Unexpected metric alert evaluation failure for device=%s",
                topic_device_id,
            )

    def _process_status(
        self,
        topic_device_id: str,
        topic: str,
        envelope: AuthenticatedMqttEnvelope,
        received_at: datetime,
    ) -> None:
        event = None
        try:
            with SessionLocal.begin() as session:
                device = self._authenticate_device_envelope(
                    session,
                    topic_device_id,
                    topic,
                    envelope,
                )
                if device is None:
                    return

                status = envelope.body
                if status not in {"online", "offline"}:
                    logger.warning(
                        "Rejected invalid status body: device=%s",
                        topic_device_id,
                    )
                    return

                previous_status = device.status
                if status == "online":
                    device.mqtt_session_id = envelope.session_id
                    if device.first_seen_at is None:
                        device.first_seen_at = received_at
                    device.offline_since = None
                else:
                    if device.mqtt_session_id != envelope.session_id:
                        logger.warning(
                            "Rejected stale offline status: device=%s",
                            topic_device_id,
                        )
                        return
                    if previous_status != "offline" or device.offline_since is None:
                        device.offline_since = received_at

                device.status = status
                device.last_seen_at = received_at
                owner_id = device.owner_id
                if previous_status != status:
                    event = create_device_event(
                        session,
                        owner_id=owner_id,
                        device_id=topic_device_id,
                        event_type=(
                            "device_online"
                            if status == "online"
                            else "device_offline"
                        ),
                        occurred_at=received_at,
                        details={
                            "previous_status": previous_status,
                            "status": status,
                        },
                    )
        except SQLAlchemyError:
            logger.exception("Database write failed for status from %s", topic_device_id)
            return

        logger.info(
            "Stored status device=%s status=%s received_at=%s",
            topic_device_id,
            status,
            received_at.isoformat(),
        )
        realtime_hub.publish_from_thread(
            owner_id,
            {
                "type": "device_status",
                "device_id": topic_device_id,
                "received_at": _utc_isoformat(received_at),
                "data": {"status": status},
            }
        )
        if event is not None:
            realtime_hub.publish_from_thread(
                owner_id,
                event_created_message(event, received_at=received_at),
            )
        try:
            evaluate_offline_alerts_once(
                observed_at=received_at,
                device_id=topic_device_id,
            )
        except Exception:
            logger.exception(
                "Unexpected offline alert evaluation failure for device=%s",
                topic_device_id,
            )

    def _process_command_ack(
        self,
        topic_device_id: str,
        topic: str,
        envelope: AuthenticatedMqttEnvelope,
        received_at: datetime,
    ) -> None:
        event = None
        try:
            with SessionLocal.begin() as session:
                device = self._authenticate_device_envelope(
                    session,
                    topic_device_id,
                    topic,
                    envelope,
                )
                if device is None:
                    return
                if device.mqtt_session_id != envelope.session_id:
                    logger.warning(
                        "Rejected command acknowledgement with stale MQTT session: device=%s",
                        topic_device_id,
                    )
                    return

                try:
                    payload = CommandAckPayload.model_validate_json(envelope.body)
                except ValidationError as exc:
                    logger.warning(
                        "Rejected malformed command acknowledgement for device %s: %s",
                        topic_device_id,
                        exc.errors(include_url=False, include_input=False),
                    )
                    return

                if payload.device_id != topic_device_id:
                    logger.warning(
                        "Rejected command acknowledgement device ID mismatch: "
                        "topic=%s payload=%s",
                        topic_device_id,
                        payload.device_id,
                    )
                    return

                device.last_seen_at = received_at
                command = session.get(DeviceCommand, payload.command_id)
                if command is None:
                    logger.warning(
                        "Ignored acknowledgement for unknown command_id=%s device=%s",
                        payload.command_id,
                        topic_device_id,
                    )
                    return
                if command.device_id != topic_device_id:
                    logger.warning(
                        "Rejected acknowledgement command/device mismatch: "
                        "command_id=%s expected=%s received=%s",
                        payload.command_id,
                        command.device_id,
                        topic_device_id,
                    )
                    return
                if command.status != "pending":
                    logger.info(
                        "Ignored duplicate acknowledgement command_id=%s status=%s",
                        payload.command_id,
                        command.status,
                    )
                    return

                command.status = payload.status
                command.result = payload.result
                command.ack_sent_at = payload.sent_at
                command.acknowledged_at = received_at
                command_type = command.command_type
                arguments = command.arguments
                issued_at = command.issued_at
                owner_id = device.owner_id
                event = create_device_event(
                    session,
                    owner_id=owner_id,
                    device_id=topic_device_id,
                    event_type=(
                        "command_succeeded"
                        if payload.status == "succeeded"
                        else "command_failed"
                    ),
                    occurred_at=received_at,
                    details={
                        "command_id": payload.command_id,
                        "command_type": command_type,
                        "arguments": arguments,
                        "result": payload.result,
                    },
                )
        except SQLAlchemyError:
            logger.exception(
                "Database update failed for command acknowledgement from device=%s",
                topic_device_id,
            )
            return

        logger.info(
            "Stored command acknowledgement device=%s command_id=%s status=%s",
            topic_device_id,
            payload.command_id,
            payload.status,
        )
        realtime_hub.publish_from_thread(
            owner_id,
            {
                "type": "command_update",
                "device_id": topic_device_id,
                "received_at": _utc_isoformat(received_at),
                "data": {
                    "command_id": payload.command_id,
                    "type": command_type,
                    "status": payload.status,
                    "arguments": arguments,
                    "issued_at": _utc_isoformat(issued_at),
                    "acknowledged_at": _utc_isoformat(received_at),
                    "ack_sent_at": _utc_isoformat(payload.sent_at),
                    "result": payload.result,
                },
            }
        )
        realtime_hub.publish_from_thread(
            owner_id,
            event_created_message(event, received_at=received_at),
        )


mqtt_ingestor = MqttIngestor()
