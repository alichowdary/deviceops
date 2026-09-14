export type DeviceStatus = "online" | "offline" | "unknown";

export interface Health {
  status: "ok" | "degraded";
  database: "up" | "down";
  mqtt: "up" | "down";
  mqtt_error: string | null;
}

export interface Device {
  device_id: string;
  status: DeviceStatus;
  first_seen_at: string;
  last_seen_at: string;
}

export interface Telemetry {
  id: number;
  device_id: string;
  sequence: number;
  sent_at: string;
  received_at: string;
  temperature_c: number;
  battery_pct: number;
  rssi_dbm: number;
  uptime_s: number;
  additional_metrics: Record<string, unknown> | null;
}
