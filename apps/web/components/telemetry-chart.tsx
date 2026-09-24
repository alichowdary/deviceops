"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatChartTime, formatExactTime } from "@/lib/format";
import {
  getTelemetryMetricValue,
  isTelemetryMetricValueCompatible,
} from "@/lib/telemetry-metrics";
import type { CapabilityValueDescriptor, Telemetry } from "@/lib/types";

export function TelemetryChart({
  data,
  descriptor,
  metricName,
  label,
  color,
}: {
  data: Telemetry[];
  descriptor: CapabilityValueDescriptor;
  metricName: string;
  label: string;
  color: string;
}) {
  const points = data.flatMap((sample) => {
    const value = getTelemetryMetricValue(sample, metricName);
    return typeof value === "number" &&
      isTelemetryMetricValueCompatible(descriptor, value)
      ? [{ received_at: sample.received_at, value }]
      : [];
  });
  if (points.length === 0) return null;

  const decimals = descriptor.type === "integer" ? 0 : 2;
  const domain: [number | "auto", number | "auto"] =
    metricName === "battery_pct" || metricName === "humidity_pct"
      ? [0, 100]
      : ["auto", "auto"];
  const unitSuffix = descriptor.unit ? ` ${descriptor.unit}` : "";

  return (
    <section className="chart-panel">
      <div className="chart-heading">
        <span className="chart-title">{label}</span>
        <span className="chart-unit">{descriptor.unit ?? ""}</span>
      </div>
      <div className="chart-canvas">
        <ResponsiveContainer height="100%" width="100%">
          <LineChart data={points} margin={{ top: 16, right: 12, bottom: 2, left: 0 }}>
            <CartesianGrid stroke="#273039" strokeDasharray="2 4" vertical={false} />
            <XAxis
              axisLine={{ stroke: "#35414d" }}
              dataKey="received_at"
              minTickGap={36}
              tick={{ fill: "#69757f", fontSize: 9 }}
              tickFormatter={formatChartTime}
              tickLine={false}
            />
            <YAxis
              axisLine={false}
              domain={domain}
              tick={{ fill: "#69757f", fontSize: 9 }}
              tickLine={false}
              width={42}
            />
            <Tooltip
              contentStyle={{
                background: "#171d23",
                border: "1px solid #35414d",
                borderRadius: 4,
                color: "#e7ebef",
                fontSize: 11,
              }}
              formatter={(value) => [
                `${Number(value).toFixed(decimals)}${unitSuffix}`,
                label,
              ]}
              labelFormatter={(value) => formatExactTime(String(value))}
            />
            <Line
              activeDot={{ r: 3, strokeWidth: 0 }}
              dataKey="value"
              dot={false}
              isAnimationActive={false}
              stroke={color}
              strokeWidth={1.7}
              type="monotone"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
