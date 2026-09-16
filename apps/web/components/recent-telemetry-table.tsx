import { formatExactTime, formatUptime } from "@/lib/format";
import type { Telemetry } from "@/lib/types";

export function RecentTelemetryTable({ telemetry }: { telemetry: Telemetry[] }) {
  const recent = telemetry.slice(-10).reverse();
  const hasBattery = telemetry.some((sample) => sample.battery_pct !== null);
  const hasHumidity = telemetry.some((sample) => sample.humidity_pct !== null);
  const hasPressure = telemetry.some((sample) => sample.pressure_hpa !== null);

  return (
    <section className="panel">
      <div className="section-header">
        <h2 className="section-title">Recent samples</h2>
        <span className="section-meta">newest first · {recent.length} shown</span>
      </div>
      <div className="data-table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Received</th>
              <th scope="col">Sent by device</th>
              <th scope="col">Sequence</th>
              <th scope="col">Temp</th>
              {hasBattery ? <th scope="col">Battery</th> : null}
              {hasHumidity ? <th scope="col">Humidity</th> : null}
              {hasPressure ? <th scope="col">Pressure</th> : null}
              <th scope="col">RSSI</th>
              <th scope="col">Uptime</th>
            </tr>
          </thead>
          <tbody>
            {recent.map((sample) => (
              <tr key={sample.id}>
                <td className="mono">{formatExactTime(sample.received_at)}</td>
                <td className="mono">{formatExactTime(sample.sent_at)}</td>
                <td className="mono">{sample.sequence}</td>
                <td className="mono">{sample.temperature_c.toFixed(1)} °C</td>
                {hasBattery ? (
                  <td className="mono">
                    {sample.battery_pct === null
                      ? "—"
                      : `${sample.battery_pct.toFixed(1)}%`}
                  </td>
                ) : null}
                {hasHumidity ? (
                  <td className="mono">
                    {sample.humidity_pct === null
                      ? "—"
                      : `${sample.humidity_pct.toFixed(1)}%`}
                  </td>
                ) : null}
                {hasPressure ? (
                  <td className="mono">
                    {sample.pressure_hpa === null
                      ? "—"
                      : `${sample.pressure_hpa.toFixed(1)} hPa`}
                  </td>
                ) : null}
                <td className="mono">{sample.rssi_dbm} dBm</td>
                <td className="mono">{formatUptime(sample.uptime_s)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
