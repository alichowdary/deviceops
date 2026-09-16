"use client";

import {
  BatteryMedium,
  ChevronRight,
  Clock3,
  Droplets,
  Gauge,
  Radio,
  Thermometer,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ApiError, apiGet, apiPost } from "@/lib/api";
import { useDeviceOpsWebSocket } from "@/hooks/use-deviceops-websocket";
import { formatExactTime, formatRelativeTime, formatUptime } from "@/lib/format";
import type {
  CommandRequest,
  Device,
  DeviceCommand,
  DeviceOpsEvent,
  Telemetry,
} from "@/lib/types";

import { DeviceControl } from "./device-control";
import { LiveConnectionIndicator } from "./live-connection-indicator";
import { MetricValue } from "./metric-value";
import { RecentCommands } from "./recent-commands";
import { RecentTelemetryTable } from "./recent-telemetry-table";
import { RefreshButton } from "./refresh-button";
import { LoadingState, StatePanel } from "./state-panel";
import { StatusBadge } from "./status-badge";
import { TelemetryChart } from "./telemetry-chart";

interface DeviceState {
  device: Device | null;
  telemetry: Telemetry[] | null;
  commands: DeviceCommand[] | null;
  loading: boolean;
  error: string | null;
  notFound: boolean;
}

const initialState: DeviceState = {
  device: null,
  telemetry: null,
  commands: null,
  loading: true,
  error: null,
  notFound: false,
};

const RECENT_COMMAND_LIMIT = 10;

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

function mergeCommandSnapshots(
  snapshot: DeviceCommand[],
  current: DeviceCommand[] | null,
): DeviceCommand[] {
  const commands = new Map(
    (current ?? []).map((command) => [command.command_id, command]),
  );
  for (const candidate of snapshot) {
    const existing = commands.get(candidate.command_id);
    if (!existing || existing.status === "pending" || candidate.status !== "pending") {
      commands.set(candidate.command_id, candidate);
    }
  }
  return [...commands.values()]
    .sort(
      (left, right) =>
        new Date(right.issued_at).getTime() - new Date(left.issued_at).getTime(),
    )
    .slice(0, RECENT_COMMAND_LIMIT);
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
      apiGet<DeviceCommand[]>(
        `/api/devices/${encodedDeviceId}/commands?limit=${RECENT_COMMAND_LIMIT}`,
        controller.signal,
      ),
    ])
      .then(([device, telemetry, commands]) => {
        setState((current) => ({
          device:
            current.device &&
            new Date(current.device.last_seen_at) > new Date(device.last_seen_at)
              ? current.device
              : device,
          telemetry: mergeTelemetrySnapshots(telemetry, current.telemetry),
          commands: mergeCommandSnapshots(commands, current.commands),
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

        if (event.type === "command_update") {
          const command: DeviceCommand = {
            ...event.data,
            device_id: event.device_id,
          };
          return {
            ...current,
            commands: mergeCommandSnapshots([command], current.commands),
          };
        }

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

  const submitCommand = useCallback(
    async (request: CommandRequest) => {
      const command = await apiPost<DeviceCommand>(
        `/api/devices/${encodeURIComponent(deviceId)}/commands`,
        request,
      );
      setState((current) => ({
        ...current,
        commands: mergeCommandSnapshots([command], current.commands),
      }));
      return command;
    },
    [deviceId],
  );

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
  const commands = state.commands ?? [];
  if (!device) return null;
  const latest = telemetry.at(-1);
  const hasBattery = telemetry.some((sample) => sample.battery_pct !== null);
  const hasHumidity = telemetry.some((sample) => sample.humidity_pct !== null);
  const hasPressure = telemetry.some((sample) => sample.pressure_hpa !== null);

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

      <div className="command-grid">
        <DeviceControl commands={commands} submitCommand={submitCommand} />
        <RecentCommands commands={commands} />
      </div>

      {latest ? (
        <>
          <section aria-label="Latest telemetry" className="metric-grid">
            <MetricValue
              icon={Thermometer}
              label="Temperature"
              unit="°C"
              value={latest.temperature_c.toFixed(1)}
            />
            {latest.battery_pct !== null ? (
              <MetricValue
                icon={BatteryMedium}
                label="Battery"
                unit="%"
                value={latest.battery_pct.toFixed(1)}
              />
            ) : null}
            {latest.humidity_pct !== null ? (
              <MetricValue
                icon={Droplets}
                label="Humidity"
                unit="%"
                value={latest.humidity_pct.toFixed(1)}
              />
            ) : null}
            {latest.pressure_hpa !== null ? (
              <MetricValue
                icon={Gauge}
                label="Pressure"
                unit="hPa"
                value={latest.pressure_hpa.toFixed(1)}
              />
            ) : null}
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
            {hasBattery ? (
              <TelemetryChart
                color="#4dcb8a"
                data={telemetry}
                dataKey="battery_pct"
                domain={[0, 100]}
                label="Battery"
                unit="%"
              />
            ) : null}
            {hasHumidity ? (
              <TelemetryChart
                color="#53c7c1"
                data={telemetry}
                dataKey="humidity_pct"
                domain={[0, 100]}
                label="Humidity"
                unit="%"
              />
            ) : null}
            {hasPressure ? (
              <TelemetryChart
                color="#e1ad62"
                data={telemetry}
                dataKey="pressure_hpa"
                label="Pressure"
                unit="hPa"
              />
            ) : null}
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
