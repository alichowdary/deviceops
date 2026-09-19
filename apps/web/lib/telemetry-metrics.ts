import { formatUptime } from "@/lib/format";
import type { CapabilityValueDescriptor, Telemetry } from "@/lib/types";

export type TelemetryMetricValue = number | boolean | string;

const firstClassMetricReaders: Record<
  string,
  (sample: Telemetry) => unknown
> = {
  temperature_c: (sample) => sample.temperature_c,
  battery_pct: (sample) => sample.battery_pct,
  humidity_pct: (sample) => sample.humidity_pct,
  pressure_hpa: (sample) => sample.pressure_hpa,
  rssi_dbm: (sample) => sample.rssi_dbm,
  uptime_s: (sample) => sample.uptime_s,
};

export function getTelemetryMetricValue(
  sample: Telemetry,
  metricName: string,
): TelemetryMetricValue | null {
  const reader = firstClassMetricReaders[metricName];
  const value = reader
    ? reader(sample)
    : sample.additional_metrics?.[metricName];

  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "boolean" || typeof value === "string") return value;
  return null;
}

function formatNumber(value: number, maximumFractionDigits: number): string {
  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits,
  }).format(value);
}

export function formatTelemetryMetricValue(
  metricName: string,
  descriptor: CapabilityValueDescriptor,
  value: TelemetryMetricValue | null,
): string {
  if (!isTelemetryMetricValueCompatible(descriptor, value)) return "—";
  if (typeof value === "boolean") return value ? "True" : "False";
  if (typeof value === "string") return value;

  if (metricName === "uptime_s") return formatUptime(value);
  if (metricName === "rssi_dbm") return formatNumber(value, 0);
  if (
    metricName === "temperature_c" ||
    metricName === "battery_pct" ||
    metricName === "humidity_pct" ||
    metricName === "pressure_hpa"
  ) {
    return formatNumber(value, 1);
  }
  if (descriptor.type === "integer" && Number.isInteger(value)) {
    return formatNumber(value, 0);
  }
  return formatNumber(value, 3);
}

export function isTelemetryMetricValueCompatible(
  descriptor: CapabilityValueDescriptor,
  value: TelemetryMetricValue | null,
): value is TelemetryMetricValue {
  if (value === null) return false;
  if (descriptor.type === "boolean") return typeof value === "boolean";
  if (descriptor.type === "string") return typeof value === "string";
  if (descriptor.type === "integer") {
    return typeof value === "number" && Number.isInteger(value);
  }
  return typeof value === "number";
}

export function isNumericCapability(
  descriptor: CapabilityValueDescriptor,
): boolean {
  return descriptor.type === "number" || descriptor.type === "integer";
}
