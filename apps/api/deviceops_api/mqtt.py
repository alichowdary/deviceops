"""MQTT subscriptions and persistence of validated device messages."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import re

import paho.mqtt.client as mqtt
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from .config import settings
from .database import SessionLocal
from .models import Device, Telemetry
from .realtime import realtime_hub
from .schemas import TelemetryPayload


logger = logging.getLogger(__name__)

TELEMETRY_SUBSCRIPTION = "deviceops/v1/devices/+/telemetry"
STATUS_SUBSCRIPTION = "deviceops/v1/devices/+/status"
TOPIC_PATTERN = re.compile(
    r"^deviceops/v1/devices/([A-Za-z0-9][A-Za-z0-9._-]{0,63})/(telemetry|status)$"
)


def _utc_isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


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
            [(TELEMETRY_SUBSCRIPTION, 0), (STATUS_SUBSCRIPTION, 1)]
        )
        if result != mqtt.MQTT_ERR_SUCCESS:
            self._connected = False
            self._last_error = f"subscription failed: {mqtt.error_string(result)}"
            logger.error("MQTT %s", self._last_error)
            return

        self._connected = True
        self._last_error = None
        logger.info(
            "MQTT connected; subscribed to %s and %s",
            TELEMETRY_SUBSCRIPTION,
            STATUS_SUBSCRIPTION,
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
        received_at = datetime.now(timezone.utc)

        if message_kind == "telemetry":
            self._process_telemetry(topic_device_id, payload, received_at)
        else:
            self._process_status(topic_device_id, payload, received_at)

    def _process_telemetry(
        self,
        topic_device_id: str,
        raw_payload: bytes,
        received_at: datetime,
    ) -> None:
        try:
            payload = TelemetryPayload.model_validate_json(raw_payload)
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

        try:
            with SessionLocal.begin() as session:
                device = session.get(Device, topic_device_id)
                if device is None:
                    device = Device(
                        device_id=topic_device_id,
                        status="unknown",
                        first_seen_at=received_at,
                        last_seen_at=received_at,
                    )
                    session.add(device)
                else:
                    device.last_seen_at = received_at

                additional_metrics = payload.metrics.model_extra or None
                telemetry = Telemetry(
                    device_id=topic_device_id,
                    sequence=payload.sequence,
                    sent_at=payload.sent_at,
                    received_at=received_at,
                    temperature_c=payload.metrics.temperature_c,
                    battery_pct=payload.metrics.battery_pct,
                    rssi_dbm=payload.metrics.rssi_dbm,
                    uptime_s=payload.metrics.uptime_s,
                    additional_metrics=additional_metrics,
                )
                session.add(telemetry)
                session.flush()
                telemetry_id = telemetry.id
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
                    "rssi_dbm": payload.metrics.rssi_dbm,
                    "uptime_s": payload.metrics.uptime_s,
                    "additional_metrics": additional_metrics,
                },
            }
        )

    def _process_status(
        self,
        topic_device_id: str,
        raw_payload: bytes,
        received_at: datetime,
    ) -> None:
        try:
            status = raw_payload.decode("utf-8")
        except UnicodeDecodeError:
            logger.warning("Rejected non-UTF-8 status for device %s", topic_device_id)
            return

        if status not in {"online", "offline"}:
            logger.warning(
                "Rejected invalid status for device %s: %r", topic_device_id, status
            )
            return

        try:
            with SessionLocal.begin() as session:
                device = session.get(Device, topic_device_id)
                if device is None:
                    device = Device(
                        device_id=topic_device_id,
                        status=status,
                        first_seen_at=received_at,
                        last_seen_at=received_at,
                    )
                    session.add(device)
                else:
                    device.status = status
                    device.last_seen_at = received_at
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
            {
                "type": "device_status",
                "device_id": topic_device_id,
                "received_at": _utc_isoformat(received_at),
                "data": {"status": status},
            }
        )


mqtt_ingestor = MqttIngestor()
