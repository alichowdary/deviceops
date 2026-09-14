"use client";

import {
  BatteryMedium,
  ChevronRight,
  Clock3,
  Radio,
  Thermometer,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ApiError, apiGet } from "@/lib/api";
import { useDeviceOpsWebSocket } from "@/hooks/use-deviceops-websocket";
import { formatExactTime, formatRelativeTime, formatUptime } from "@/lib/format";
import type { Device, DeviceOpsEvent, Telemetry } from "@/lib/types";

import { LiveConnectionIndicator } from "./live-connection-indicator";
import { MetricValue } from "./metric-value";
import { RecentTelemetryTable } from "./recent-telemetry-table";
import { RefreshButton } from "./refresh-button";
import { LoadingState, StatePanel } from "./state-panel";
import { StatusBadge } from "./status-badge";
import { TelemetryChart } from "./telemetry-chart";

interface DeviceState {
  device: Device | null;
  telemetry: Telemetry[] | null;
  loading: boolean;
  error: string | null;
  notFound: boolean;
}

const initialState: DeviceState = {
  device: null,
  telemetry: null,
  loading: true,
  error: null,
  notFound: false,
};

function mergeTelemetrySnapshots(
  snapshot: Telemetry[],
  current: Telemetry[] | null,
): Telemetry[] {
  if (current === null) return snapshot;
  const samples = new Map<number, Telemetry>();
  for (const sample of [...snapshot, ...current]) samples.set(sample.id, sample);
  return [...samples.values()]
    .sort(
      (left, right) =>
        new Date(left.received_at).getTime() - new Date(right.received_at).getTime(),
    )
    .slice(-100);
}

export function DeviceDetail({ deviceId }: { deviceId: string }) {
  const [requestNumber, setRequestNumber] = useState(0);
  const [state, setState] = useState<DeviceState>(initialState);

  useEffect(() => {
    const controller = new AbortController();
    const encodedDeviceId = encodeURIComponent(deviceId);

    Promise.all([
      apiGet<Device>(`/api/devices/${encodedDeviceId}`, controller.signal),
      apiGet<Telemetry[]>(
        `/api/devices/${encodedDeviceId}/telemetry?limit=100`,
        controller.signal,
      ),
    ])
      .then(([device, telemetry]) => {
        setState((current) => ({
          device:
            current.device &&
            new Date(current.device.last_seen_at) > new Date(device.last_seen_at)
              ? current.device
              : device,
          telemetry: mergeTelemetrySnapshots(telemetry, current.telemetry),
          loading: false,
          error: null,
          notFound: false,
        }));
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setState((current) => ({
          ...current,
          loading: false,
          error: error instanceof Error ? error.message : "The device request failed.",
          notFound: error instanceof ApiError && error.status === 404,
        }));
      });

    return () => controller.abort();
  }, [deviceId, requestNumber]);

  const refresh = useCallback(() => {
    setState((current) => ({ ...current, loading: true, error: null }));
    setRequestNumber((value) => value + 1);
  }, []);

  const handleLiveEvent = useCallback(
    (event: DeviceOpsEvent) => {
      if (event.device_id !== deviceId) return;

      setState((current) => {
        if (current.device === null) return current;

        if (event.type === "device_status") {
          return {
            ...current,
            device: {
              ...current.device,
              status: event.data.status,
              last_seen_at: event.received_at,
            },
          };
        }

        const sample: Telemetry = {
          ...event.data,
          device_id: event.device_id,
          received_at: event.received_at,
        };
        return {
          ...current,
          device: { ...current.device, last_seen_at: event.received_at },
          telemetry: mergeTelemetrySnapshots([sample], current.telemetry),
        };
      });
    },
    [deviceId],
  );

  const liveConnection = useDeviceOpsWebSocket({
    enabled: state.device !== null,
    onEvent: handleLiveEvent,
    onReconnect: refresh,
  });

  if (state.loading && state.device === null) {
    return <LoadingState label={`Loading ${deviceId}`} />;
  }

  if (state.notFound) {
    return (
      <StatePanel
        action={<Link className="button button-secondary" href="/">Return to fleet</Link>}
        description={`No device with the stable ID “${deviceId}” exists in the backend.`}
        eyebrow="Unknown device"
        title="Device not found"
      />
    );
  }

  if (state.error && state.device === null) {
    return (
      <StatePanel
        action={
          <button className="button button-primary" onClick={refresh} type="button">
            Retry connection
          </button>
        }
        description={`${state.error} Confirm FastAPI is running and retry the request.`}
        eyebrow="Backend unavailable"
        title="Device data could not be loaded"
      />
    );
  }

  const device = state.device;
  const telemetry = state.telemetry ?? [];
  if (!device) return null;
  const latest = telemetry.at(-1);

  return (
    <>
      <nav aria-label="Breadcrumb" className="breadcrumb">
        <Link href="/">Fleet</Link>
        <ChevronRight aria-hidden="true" size={11} />
        <span className="mono">{device.device_id}</span>
      </nav>

      <header className="page-header">
        <div>
          <div className="device-title-row">
            <h1 className="page-title mono">{device.device_id}</h1>
            <StatusBadge status={device.status} />
          </div>
          <p className="page-description">Observed device state and persisted telemetry</p>
        </div>
        <div className="page-actions">
          <LiveConnectionIndicator state={liveConnection} />
          <RefreshButton loading={state.loading} onClick={refresh} />
        </div>
      </header>

      {state.error ? (
        <div className="health-line health-degraded">
          Refresh failed. Showing the last successfully loaded device state.
        </div>
      ) : null}

      <section aria-label="Device timestamps" className="detail-meta-grid">
        <div className="detail-meta-item">
          <span className="detail-label">Stable identifier</span>
          <span className="detail-value mono">{device.device_id}</span>
        </div>
        <div className="detail-meta-item">
          <span className="detail-label">Last seen</span>
          <span className="detail-value" title={formatExactTime(device.last_seen_at)}>
            {formatRelativeTime(device.last_seen_at)} · <span className="mono">{formatExactTime(device.last_seen_at)}</span>
          </span>
        </div>
        <div className="detail-meta-item">
          <span className="detail-label">First seen</span>
          <span className="detail-value" title={formatExactTime(device.first_seen_at)}>
            {formatRelativeTime(device.first_seen_at)} · <span className="mono">{formatExactTime(device.first_seen_at)}</span>
          </span>
        </div>
      </section>

      {latest ? (
        <>
          <section aria-label="Latest telemetry" className="metric-grid">
            <MetricValue
              icon={Thermometer}
              label="Temperature"
              unit="°C"
              value={latest.temperature_c.toFixed(1)}
            />
            <MetricValue
              icon={BatteryMedium}
              label="Battery"
              unit="%"
              value={latest.battery_pct.toFixed(1)}
            />
            <MetricValue
              icon={Radio}
              label="RSSI"
              unit="dBm"
              value={String(latest.rssi_dbm)}
            />
            <MetricValue
              icon={Clock3}
              label="Uptime"
              value={formatUptime(latest.uptime_s)}
            />
          </section>

          <div className="chart-grid">
            <TelemetryChart
              color="#70b7ff"
              data={telemetry}
              dataKey="temperature_c"
              label="Temperature"
              unit="°C"
            />
            <TelemetryChart
              color="#4dcb8a"
              data={telemetry}
              dataKey="battery_pct"
              domain={[0, 100]}
              label="Battery"
              unit="%"
            />
            <TelemetryChart
              color="#c295e8"
              data={telemetry}
              dataKey="rssi_dbm"
              decimals={0}
              label="Signal strength"
              unit="dBm"
            />
          </div>

          <RecentTelemetryTable telemetry={telemetry} />
        </>
      ) : (
        <section className="panel">
          <div className="section-header">
            <h2 className="section-title">Telemetry</h2>
            <span className="section-meta">0 samples</span>
          </div>
          <div className="no-telemetry">No telemetry has been persisted for this device.</div>
        </section>
      )}

      <p className="footer-note">
        Charts use the backend-controlled received_at timeline. The table also exposes device-reported sent_at.
      </p>
    </>
  );
}
