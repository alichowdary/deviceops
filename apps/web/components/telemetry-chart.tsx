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
import type { Telemetry } from "@/lib/types";

type NumericTelemetryKey =
  | "temperature_c"
  | "battery_pct"
  | "humidity_pct"
  | "pressure_hpa"
  | "rssi_dbm";

export function TelemetryChart({
  data,
  dataKey,
  label,
  unit,
  color,
  decimals = 1,
  domain,
}: {
  data: Telemetry[];
  dataKey: NumericTelemetryKey;
  label: string;
  unit: string;
  color: string;
  decimals?: number;
  domain?: [number | "auto", number | "auto"];
}) {
  return (
    <section className="chart-panel">
      <div className="chart-heading">
        <span className="chart-title">{label}</span>
        <span className="chart-unit">{unit}</span>
      </div>
      <div className="chart-canvas">
        <ResponsiveContainer height="100%" width="100%">
          <LineChart data={data} margin={{ top: 16, right: 12, bottom: 2, left: 0 }}>
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
              domain={domain ?? ["auto", "auto"]}
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
                `${Number(value).toFixed(decimals)} ${unit}`,
                label,
              ]}
              labelFormatter={(value) => formatExactTime(String(value))}
            />
            <Line
              activeDot={{ r: 3, strokeWidth: 0 }}
              dataKey={dataKey}
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
