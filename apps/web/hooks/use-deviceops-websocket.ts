"use client";

import { useEffect, useRef, useState } from "react";

import type {
  AlertSeverity,
  AlertStatus,
  CommandStatus,
  CommandType,
  DeviceOpsEvent,
  DeviceStatus,
  EventSeverity,
  EventType,
  LiveConnectionState,
} from "@/lib/types";

const configuredWebSocketUrl =
  process.env.NEXT_PUBLIC_DEVICEOPS_WS_URL ?? "ws://127.0.0.1:8000/ws";
const MAX_RECONNECT_DELAY_MS = 10_000;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isDeviceStatus(value: unknown): value is DeviceStatus {
  return value === "online" || value === "offline" || value === "unknown";
}

function isCommandStatus(value: unknown): value is CommandStatus {
  return value === "pending" || value === "succeeded" || value === "failed";
}

function isCommandType(value: unknown): value is CommandType {
  return (
    value === "set_led" ||
    value === "set_reporting_interval" ||
    value === "request_diagnostics"
  );
}

function isEventType(value: unknown): value is EventType {
  return (
    value === "device_registered" ||
    value === "device_online" ||
    value === "device_offline" ||
    value === "command_issued" ||
    value === "command_succeeded" ||
    value === "command_failed" ||
    value === "alert_opened" ||
    value === "alert_resolved"
  );
}

function isAlertSeverity(value: unknown): value is AlertSeverity {
  return value === "info" || value === "warning" || value === "critical";
}

function isAlertStatus(value: unknown): value is AlertStatus {
  return value === "active" || value === "resolved";
}

function isEventSeverity(value: unknown): value is EventSeverity {
  return (
    value === "info" ||
    value === "success" ||
    value === "warning" ||
    value === "error"
  );
}

function isNullableNumber(value: unknown): value is number | null {
  return value === null || typeof value === "number";
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function parseEvent(rawMessage: string): DeviceOpsEvent | null {
  let event: unknown;
  try {
    event = JSON.parse(rawMessage);
  } catch {
    return null;
  }

  if (!isRecord(event) || typeof event.received_at !== "string" || !isRecord(event.data)) {
    return null;
  }

  if (
    event.type === "event_created" &&
    typeof event.data.id === "number" &&
    typeof event.data.device_id === "string" &&
    isEventType(event.data.event_type) &&
    isEventSeverity(event.data.severity) &&
    typeof event.data.occurred_at === "string" &&
    isRecord(event.data.details)
  ) {
    return event as unknown as DeviceOpsEvent;
  }

  if (
    event.type === "alert_update" &&
    typeof event.data.id === "number" &&
    typeof event.data.device_id === "string" &&
    isNullableNumber(event.data.rule_id) &&
    isNullableString(event.data.rule_name) &&
    (event.data.rule_type === "metric_threshold" ||
      event.data.rule_type === "device_offline") &&
    isAlertSeverity(event.data.severity) &&
    isAlertStatus(event.data.status) &&
    typeof event.data.condition === "string" &&
    isNullableNumber(event.data.observed_value) &&
    isNullableNumber(event.data.resolved_value) &&
    typeof event.data.opened_at === "string" &&
    isNullableString(event.data.resolved_at) &&
    isNullableString(event.data.resolution_reason) &&
    typeof event.data.created_at === "string" &&
    typeof event.data.updated_at === "string"
  ) {
    return event as unknown as DeviceOpsEvent;
  }

  if (typeof event.device_id !== "string") return null;

  if (
    event.type === "capabilities_updated" &&
    isRecord(event.data.capabilities) &&
    event.data.capabilities.protocol_version === 1 &&
    event.data.capabilities.capabilities_version === 1 &&
    event.data.capabilities.device_id === event.device_id &&
    typeof event.data.capabilities.sent_at === "string" &&
    isRecord(event.data.capabilities.telemetry) &&
    isRecord(event.data.capabilities.commands)
  ) {
    return event as unknown as DeviceOpsEvent;
  }

  if (event.type === "device_status" && isDeviceStatus(event.data.status)) {
    return event as unknown as DeviceOpsEvent;
  }

  if (
    event.type === "command_update" &&
    typeof event.data.command_id === "string" &&
    isCommandType(event.data.type) &&
    isCommandStatus(event.data.status) &&
    isRecord(event.data.arguments) &&
    typeof event.data.issued_at === "string" &&
    typeof event.data.acknowledged_at === "string" &&
    typeof event.data.ack_sent_at === "string" &&
    isRecord(event.data.result)
  ) {
    return event as unknown as DeviceOpsEvent;
  }

  if (
    event.type === "telemetry" &&
    typeof event.data.id === "number" &&
    typeof event.data.sequence === "number" &&
    typeof event.data.sent_at === "string" &&
    typeof event.data.temperature_c === "number" &&
    isNullableNumber(event.data.battery_pct) &&
    isNullableNumber(event.data.humidity_pct) &&
    isNullableNumber(event.data.pressure_hpa) &&
    typeof event.data.rssi_dbm === "number" &&
    typeof event.data.uptime_s === "number"
  ) {
    return event as unknown as DeviceOpsEvent;
  }

  return null;
}

function isAuthenticatedControlMessage(rawMessage: string): boolean {
  let message: unknown;
  try {
    message = JSON.parse(rawMessage);
  } catch {
    return false;
  }
  return (
    isRecord(message) &&
    Object.keys(message).length === 1 &&
    message.type === "authenticated"
  );
}

export function useDeviceOpsWebSocket({
  enabled,
  token,
  onEvent,
  onReconnect,
  onAuthenticationFailure,
}: {
  enabled: boolean;
  token: string | null;
  onEvent: (event: DeviceOpsEvent) => void;
  onReconnect: () => void;
  onAuthenticationFailure: () => void;
}): LiveConnectionState {
  const [connectionState, setConnectionState] =
    useState<LiveConnectionState>("connecting");
  const onEventRef = useRef(onEvent);
  const onReconnectRef = useRef(onReconnect);
  const onAuthenticationFailureRef = useRef(onAuthenticationFailure);

  useEffect(() => {
    onEventRef.current = onEvent;
    onReconnectRef.current = onReconnect;
    onAuthenticationFailureRef.current = onAuthenticationFailure;
  }, [onAuthenticationFailure, onEvent, onReconnect]);

  useEffect(() => {
    if (!enabled || !token) return;

    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let reconnectAttempt = 0;
    let hasAuthenticated = false;
    let stopped = false;

    function connect() {
      if (stopped) return;

      const currentSocket = new WebSocket(configuredWebSocketUrl);
      let authenticated = false;
      let authenticationSent = false;
      socket = currentSocket;

      currentSocket.onopen = () => {
        if (stopped || authenticationSent) return;
        authenticationSent = true;
        currentSocket.send(JSON.stringify({ type: "authenticate", token }));
      };

      currentSocket.onmessage = (message) => {
        if (stopped) return;
        if (!authenticated) {
          if (
            typeof message.data !== "string" ||
            !isAuthenticatedControlMessage(message.data)
          ) {
            currentSocket.close(1008, "Unexpected authentication response");
            return;
          }

          const recoveredConnection = hasAuthenticated || reconnectAttempt > 0;
          authenticated = true;
          hasAuthenticated = true;
          reconnectAttempt = 0;
          setConnectionState("live");
          if (recoveredConnection) onReconnectRef.current();
          return;
        }

        if (typeof message.data !== "string") return;
        const event = parseEvent(message.data);
        if (event) onEventRef.current(event);
      };

      currentSocket.onerror = () => currentSocket.close();
      currentSocket.onclose = (event) => {
        if (socket === currentSocket) socket = null;
        if (stopped) return;

        if (!authenticated && event.code === 1008) {
          stopped = true;
          onAuthenticationFailureRef.current();
          return;
        }

        setConnectionState("reconnecting");
        const delay = Math.min(
          1_000 * 2 ** reconnectAttempt,
          MAX_RECONNECT_DELAY_MS,
        );
        reconnectAttempt += 1;
        reconnectTimer = setTimeout(connect, delay);
      };
    }

    connect();
    return () => {
      stopped = true;
      if (reconnectTimer !== null) clearTimeout(reconnectTimer);
      socket?.close(1000, "Page closed");
    };
  }, [enabled, token]);

  return connectionState;
}
