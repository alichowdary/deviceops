"use client";

import { useEffect, useRef, useState } from "react";

import type {
  DeviceOpsEvent,
  DeviceStatus,
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

function parseEvent(rawMessage: string): DeviceOpsEvent | null {
  let event: unknown;
  try {
    event = JSON.parse(rawMessage);
  } catch {
    return null;
  }

  if (
    !isRecord(event) ||
    typeof event.device_id !== "string" ||
    typeof event.received_at !== "string" ||
    !isRecord(event.data)
  ) {
    return null;
  }

  if (event.type === "device_status" && isDeviceStatus(event.data.status)) {
    return event as unknown as DeviceOpsEvent;
  }

  if (
    event.type === "telemetry" &&
    typeof event.data.id === "number" &&
    typeof event.data.sequence === "number" &&
    typeof event.data.sent_at === "string" &&
    typeof event.data.temperature_c === "number" &&
    typeof event.data.battery_pct === "number" &&
    typeof event.data.rssi_dbm === "number" &&
    typeof event.data.uptime_s === "number"
  ) {
    return event as unknown as DeviceOpsEvent;
  }

  return null;
}

export function useDeviceOpsWebSocket({
  enabled,
  onEvent,
  onReconnect,
}: {
  enabled: boolean;
  onEvent: (event: DeviceOpsEvent) => void;
  onReconnect: () => void;
}): LiveConnectionState {
  const [connectionState, setConnectionState] =
    useState<LiveConnectionState>("connecting");
  const onEventRef = useRef(onEvent);
  const onReconnectRef = useRef(onReconnect);

  useEffect(() => {
    onEventRef.current = onEvent;
    onReconnectRef.current = onReconnect;
  }, [onEvent, onReconnect]);

  useEffect(() => {
    if (!enabled) return;

    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let reconnectAttempt = 0;
    let hasConnected = false;
    let stopped = false;

    function connect() {
      if (stopped) return;

      socket = new WebSocket(configuredWebSocketUrl);
      socket.onopen = () => {
        const recoveredConnection = hasConnected || reconnectAttempt > 0;
        hasConnected = true;
        reconnectAttempt = 0;
        setConnectionState("live");
        if (recoveredConnection) onReconnectRef.current();
      };
      socket.onmessage = (message) => {
        if (typeof message.data !== "string") return;
        const event = parseEvent(message.data);
        if (event) onEventRef.current(event);
      };
      socket.onerror = () => socket?.close();
      socket.onclose = () => {
        if (stopped) return;
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
  }, [enabled]);

  return connectionState;
}
