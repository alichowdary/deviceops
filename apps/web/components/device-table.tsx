"use client";

import { ChevronRight } from "lucide-react";
import { useRouter } from "next/navigation";

import { formatExactTime, formatRelativeTime } from "@/lib/format";
import type { Device } from "@/lib/types";

import { StatusBadge } from "./status-badge";

export function DeviceTable({ devices }: { devices: Device[] }) {
  const router = useRouter();

  function openDevice(deviceId: string) {
    router.push(`/devices/${encodeURIComponent(deviceId)}`);
  }

  return (
    <section className="panel">
      <div className="section-header">
        <h2 className="section-title">Device inventory</h2>
        <span className="section-meta">{devices.length} records</span>
      </div>
      <div className="data-table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Status</th>
              <th scope="col">Device</th>
              <th scope="col">Last seen</th>
              <th scope="col">First seen</th>
              <th aria-label="Open device" scope="col" />
            </tr>
          </thead>
          <tbody>
            {devices.map((device) => (
              <tr
                aria-label={`Open ${device.display_name ?? device.device_id}`}
                data-clickable="true"
                key={device.device_id}
                onClick={() => openDevice(device.device_id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    openDevice(device.device_id);
                  }
                }}
                tabIndex={0}
              >
                <td><StatusBadge status={device.status} /></td>
                <td>
                  <span className={device.display_name ? "table-primary" : "mono table-primary"}>
                    {device.display_name ?? device.device_id}
                  </span>
                  {device.display_name ? (
                    <span className="mono table-secondary">{device.device_id}</span>
                  ) : null}
                </td>
                <td title={formatExactTime(device.last_seen_at)}>
                  <span className="table-primary">{formatRelativeTime(device.last_seen_at)}</span>
                  {device.last_seen_at ? (
                    <span className="mono table-secondary">
                      {formatExactTime(device.last_seen_at)}
                    </span>
                  ) : null}
                </td>
                <td title={formatExactTime(device.first_seen_at)}>
                  <span className="table-primary">{formatRelativeTime(device.first_seen_at)}</span>
                  {device.first_seen_at ? (
                    <span className="mono table-secondary">
                      {formatExactTime(device.first_seen_at)}
                    </span>
                  ) : null}
                </td>
                <td className="chevron-cell">
                  <ChevronRight aria-hidden="true" size={14} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
