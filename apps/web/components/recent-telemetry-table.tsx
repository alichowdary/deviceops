import { formatExactTime } from "@/lib/format";
import {
  formatTelemetryMetricValue,
  getTelemetryMetricValue,
} from "@/lib/telemetry-metrics";
import type {
  CapabilityManifest,
  CapabilityValueDescriptor,
  Telemetry,
} from "@/lib/types";

type MetricColumn = [string, CapabilityValueDescriptor];

const firstClassMetricNames = [
  "temperature_c",
  "battery_pct",
  "humidity_pct",
  "pressure_hpa",
  "rssi_dbm",
  "uptime_s",
];

function inferLegacyDescriptor(
  metricName: string,
  telemetry: Telemetry[],
): CapabilityValueDescriptor {
  const value = telemetry
    .map((sample) => getTelemetryMetricValue(sample, metricName))
    .find((candidate) => candidate !== null);
  const type =
    typeof value === "boolean"
      ? "boolean"
      : typeof value === "string"
        ? "string"
        : metricName === "rssi_dbm" || metricName === "uptime_s"
          ? "integer"
          : "number";
  return { type, label: metricName };
}

function legacyMetricColumns(telemetry: Telemetry[]): MetricColumn[] {
  const names = new Set(
    firstClassMetricNames.filter((metricName) =>
      telemetry.some(
        (sample) => getTelemetryMetricValue(sample, metricName) !== null,
      ),
    ),
  );
  for (const sample of telemetry) {
    for (const metricName of Object.keys(sample.additional_metrics ?? {})) {
      names.add(metricName);
    }
  }
  return [...names].map((metricName) => [
    metricName,
    inferLegacyDescriptor(metricName, telemetry),
  ]);
}

function formattedCell(
  sample: Telemetry,
  metricName: string,
  descriptor: CapabilityValueDescriptor,
): string {
  const formatted = formatTelemetryMetricValue(
    metricName,
    descriptor,
    getTelemetryMetricValue(sample, metricName),
  );
  if (formatted === "—" || !descriptor.unit || metricName === "uptime_s") {
    return formatted;
  }
  return `${formatted} ${descriptor.unit}`;
}

export function RecentTelemetryTable({
  capabilities,
  telemetry,
}: {
  capabilities: CapabilityManifest | null;
  telemetry: Telemetry[];
}) {
  const recent = telemetry.slice(-10).reverse();
  const metrics: MetricColumn[] = capabilities
    ? Object.entries(capabilities.telemetry)
    : legacyMetricColumns(telemetry);

  return (
    <section className="panel">
      <div className="section-header">
        <h2 className="section-title">Recent samples</h2>
        <span className="section-meta">
          {capabilities ? "manifest columns" : "legacy raw fields"} · newest first ·{" "}
          {recent.length} shown
        </span>
      </div>
      {recent.length === 0 ? (
        <div className="no-telemetry">No telemetry has been persisted for this device.</div>
      ) : (
        <div className="data-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Received</th>
                <th scope="col">Sent by device</th>
                <th scope="col">Sequence</th>
                {metrics.map(([metricName, descriptor]) => (
                  <th key={metricName} scope="col">
                    {capabilities ? descriptor.label : <code>{metricName}</code>}
                    {descriptor.unit ? ` (${descriptor.unit})` : ""}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {recent.map((sample) => (
                <tr key={sample.id}>
                  <td className="mono">{formatExactTime(sample.received_at)}</td>
                  <td className="mono">{formatExactTime(sample.sent_at)}</td>
                  <td className="mono">{sample.sequence}</td>
                  {metrics.map(([metricName, descriptor]) => (
                    <td className="mono" key={metricName}>
                      {formattedCell(sample, metricName, descriptor)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
