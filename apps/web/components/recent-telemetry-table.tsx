import { formatExactTime, formatUptime } from "@/lib/format";
import type { Telemetry } from "@/lib/types";

export function RecentTelemetryTable({ telemetry }: { telemetry: Telemetry[] }) {
  const recent = telemetry.slice(-10).reverse();

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
              <th scope="col">Battery</th>
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
                <td className="mono">{sample.battery_pct.toFixed(1)}%</td>
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
