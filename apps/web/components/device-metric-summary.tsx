import {
  Activity,
  BatteryMedium,
  Clock3,
  Droplets,
  Gauge,
  Radio,
  Thermometer,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import {
  formatTelemetryMetricValue,
  getTelemetryMetricValue,
} from "@/lib/telemetry-metrics";
import type { CapabilityManifest, Telemetry } from "@/lib/types";

import { MetricValue } from "./metric-value";

const knownMetricIcons: Record<string, LucideIcon> = {
  temperature_c: Thermometer,
  battery_pct: BatteryMedium,
  humidity_pct: Droplets,
  pressure_hpa: Gauge,
  rssi_dbm: Radio,
  uptime_s: Clock3,
};

export function DeviceMetricSummary({
  capabilities,
  latest,
}: {
  capabilities: CapabilityManifest;
  latest: Telemetry | undefined;
}) {
  const metrics = Object.entries(capabilities.telemetry);
  if (metrics.length === 0) return null;

  return (
    <section aria-label="Latest telemetry" className="metric-grid">
      {metrics.map(([metricName, descriptor]) => {
        const value = latest
          ? getTelemetryMetricValue(latest, metricName)
          : null;
        return (
          <MetricValue
            icon={knownMetricIcons[metricName] ?? Activity}
            key={metricName}
            label={descriptor.label}
            unit={metricName === "uptime_s" ? undefined : descriptor.unit ?? undefined}
            value={formatTelemetryMetricValue(metricName, descriptor, value)}
          />
        );
      })}
    </section>
  );
}
