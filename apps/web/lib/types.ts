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
  | "command_failed"
  | "alert_opened"
  | "alert_resolved";

export type EventSeverity = "info" | "success" | "warning" | "error";

export interface PersistedEvent {
  id: number;
  device_id: string;
  event_type: EventType;
  severity: EventSeverity;
  occurred_at: string;
  details: Record<string, unknown>;
}

export type AlertRuleType = "metric_threshold" | "device_offline";
export type AlertSeverity = "info" | "warning" | "critical";
export type AlertMetric =
  | "temperature_c"
  | "humidity_pct"
  | "pressure_hpa"
  | "battery_pct"
  | "rssi_dbm";
export type AlertOperator = "gt" | "gte" | "lt" | "lte";

export interface AlertRule {
  id: number;
  device_id: string;
  name: string | null;
  rule_type: AlertRuleType;
  severity: AlertSeverity;
  enabled: boolean;
  metric: AlertMetric | null;
  operator: AlertOperator | null;
  threshold: number | null;
  offline_after_seconds: number | null;
  created_at: string;
  updated_at: string;
}

export type AlertStatus = "active" | "resolved";

export interface Alert {
  id: number;
  device_id: string;
  rule_id: number | null;
  rule_name: string | null;
  rule_type: AlertRuleType;
  severity: AlertSeverity;
  status: AlertStatus;
  condition: string;
  metric: AlertMetric | null;
  operator: AlertOperator | null;
  threshold: number | null;
  offline_after_seconds: number | null;
  observed_value: number | null;
  resolved_value: number | null;
  opened_at: string;
  resolved_at: string | null;
  resolution_reason: string | null;
  created_at: string;
  updated_at: string;
}

interface AlertRuleCreateBase {
  device_id: string;
  name?: string | null;
  severity: AlertSeverity;
  enabled: boolean;
}

export interface MetricThresholdRuleCreate extends AlertRuleCreateBase {
  rule_type: "metric_threshold";
  metric: AlertMetric;
  operator: AlertOperator;
  threshold: number;
}

export interface DeviceOfflineRuleCreate extends AlertRuleCreateBase {
  rule_type: "device_offline";
  offline_after_seconds: number;
}

export type AlertRuleCreate =
  | MetricThresholdRuleCreate
  | DeviceOfflineRuleCreate;

export interface AlertRuleUpdate {
  name?: string | null;
  severity?: AlertSeverity;
  enabled?: boolean;
  operator?: AlertOperator;
  threshold?: number;
  offline_after_seconds?: number;
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

export interface AlertUpdateEvent {
  type: "alert_update";
  received_at: string;
  data: Alert;
}

export type CapabilityValueType = "number" | "integer" | "boolean" | "string";

export interface CapabilityValueDescriptor {
  type: CapabilityValueType;
  label: string;
  unit?: string;
  min?: number;
  max?: number;
}

export interface CapabilityManifest {
  protocol_version: 1;
  capabilities_version: 1;
  device_id: string;
  sent_at: string;
  telemetry: Record<string, CapabilityValueDescriptor>;
  commands: Partial<
    Record<
      CommandType,
      {
        label: string;
        arguments: Record<string, CapabilityValueDescriptor>;
      }
    >
  >;
}

export interface CapabilitiesUpdatedEvent {
  type: "capabilities_updated";
  device_id: string;
  received_at: string;
  data: { capabilities: CapabilityManifest };
}

export type DeviceOpsEvent =
  | TelemetryEvent
  | DeviceStatusEvent
  | CommandUpdateEvent
  | EventCreatedEvent
  | AlertUpdateEvent
  | CapabilitiesUpdatedEvent;
export type LiveConnectionState = "connecting" | "live" | "reconnecting";
