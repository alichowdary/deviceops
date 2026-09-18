export type DeviceStatus = "online" | "offline" | "unknown";

export interface User {
  id: number;
  email: string;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
}

export interface Health {
  status: "ok" | "degraded";
  database: "up" | "down";
  mqtt: "up" | "down";
  mqtt_error: string | null;
}

export interface Device {
  device_id: string;
  status: DeviceStatus;
  first_seen_at: string | null;
  last_seen_at: string | null;
}

export interface DeviceRegistration {
  device_id: string;
  device_secret: string;
  status: "unknown";
  created_at: string;
}

export interface Telemetry {
  id: number;
  device_id: string;
  sequence: number;
  sent_at: string;
  received_at: string;
  temperature_c: number;
  battery_pct: number | null;
  humidity_pct: number | null;
  pressure_hpa: number | null;
  rssi_dbm: number;
  uptime_s: number;
  additional_metrics: Record<string, unknown> | null;
}

export type CommandType =
  | "set_led"
  | "set_reporting_interval"
  | "request_diagnostics";
export type CommandStatus = "pending" | "succeeded" | "failed";

export interface DeviceCommand {
  command_id: string;
  device_id: string;
  type: CommandType;
  arguments: Record<string, unknown>;
  status: CommandStatus;
  issued_at: string;
  acknowledged_at: string | null;
  ack_sent_at: string | null;
  result: Record<string, unknown> | null;
}

export interface CommandRequest {
  type: CommandType;
  arguments: Record<string, unknown>;
}

export type EventType =
  | "device_registered"
  | "device_online"
  | "device_offline"
  | "command_issued"
  | "command_succeeded"
  | "command_failed";

export type EventSeverity = "info" | "success" | "warning" | "error";

export interface PersistedEvent {
  id: number;
  device_id: string;
  event_type: EventType;
  severity: EventSeverity;
  occurred_at: string;
  details: Record<string, unknown>;
}

export interface TelemetryEvent {
  type: "telemetry";
  device_id: string;
  received_at: string;
  data: Omit<Telemetry, "device_id" | "received_at">;
}

export interface DeviceStatusEvent {
  type: "device_status";
  device_id: string;
  received_at: string;
  data: {
    status: DeviceStatus;
  };
}

export interface CommandUpdateEvent {
  type: "command_update";
  device_id: string;
  received_at: string;
  data: Omit<DeviceCommand, "device_id">;
}

export interface EventCreatedEvent {
  type: "event_created";
  received_at: string;
  data: PersistedEvent;
}

export type DeviceOpsEvent =
  | TelemetryEvent
  | DeviceStatusEvent
  | CommandUpdateEvent
  | EventCreatedEvent;
export type LiveConnectionState = "connecting" | "live" | "reconnecting";
