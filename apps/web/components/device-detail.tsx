"use client";

import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { useDeviceOpsWebSocket } from "@/hooks/use-deviceops-websocket";
import { ApiError, apiGet, apiPost } from "@/lib/api";
import {
  formatExactTime,
  formatRelativeTime,
  isLaterTimestamp,
} from "@/lib/format";
import {
  getTelemetryMetricValue,
  isNumericCapability,
  isTelemetryMetricValueCompatible,
} from "@/lib/telemetry-metrics";
import type {
  CapabilityState,
  CommandRequest,
  Device,
  DeviceCommand,
  DeviceOpsEvent,
  Telemetry,
} from "@/lib/types";

import { DeviceControl } from "./device-control";
import { DeviceManagementActions } from "./device-management-actions";
import { DeviceMetricSummary } from "./device-metric-summary";
import { LiveConnectionIndicator } from "./live-connection-indicator";
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
  capabilityState: CapabilityState | null;
  loading: boolean;
  error: string | null;
  notFound: boolean;
}

const initialState: DeviceState = {
  device: null,
  telemetry: null,
  commands: null,
  capabilityState: null,
  loading: true,
  error: null,
  notFound: false,
};

const RECENT_COMMAND_LIMIT = 10;
const CHART_COLORS = [
  "#70b7ff",
  "#4dcb8a",
  "#53c7c1",
  "#e1ad62",
  "#c295e8",
  "#ef8f8f",
];

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
        new Date(left.received_at).getTime() -
        new Date(right.received_at).getTime(),
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
    if (
      !existing ||
      existing.status === "pending" ||
      candidate.status !== "pending"
    ) {
      commands.set(candidate.command_id, candidate);
    }
  }
  return [...commands.values()]
    .sort(
      (left, right) =>
        new Date(right.issued_at).getTime() -
        new Date(left.issued_at).getTime(),
    )
    .slice(0, RECENT_COMMAND_LIMIT);
}

function mergeCapabilityState(
  snapshot: CapabilityState,
  current: CapabilityState | null,
): CapabilityState {
  if (current && isLaterTimestamp(current.updated_at, snapshot.updated_at)) {
    return current;
  }
  return snapshot;
}

export function DeviceDetail({ deviceId }: { deviceId: string }) {
  const { invalidateSession, token } = useAuth();
  const [requestNumber, setRequestNumber] = useState(0);
  const [state, setState] = useState<DeviceState>(initialState);

  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    const encodedDeviceId = encodeURIComponent(deviceId);
    const requestOptions = {
      signal: controller.signal,
      token,
      onUnauthorized: invalidateSession,
    };

    Promise.all([
      apiGet<Device>(`/api/devices/${encodedDeviceId}`, requestOptions),
      apiGet<Telemetry[]>(
        `/api/devices/${encodedDeviceId}/telemetry?limit=100`,
        requestOptions,
      ),
      apiGet<DeviceCommand[]>(
        `/api/devices/${encodedDeviceId}/commands?limit=${RECENT_COMMAND_LIMIT}`,
        requestOptions,
      ),
      apiGet<CapabilityState>(
        `/api/devices/${encodedDeviceId}/capabilities`,
        requestOptions,
      ),
    ])
      .then(([device, telemetry, commands, capabilityState]) => {
        setState((current) => ({
          device:
            current.device &&
            isLaterTimestamp(current.device.last_seen_at, device.last_seen_at)
              ? {
                  ...device,
                  status: current.device.status,
                  first_seen_at: current.device.first_seen_at,
                  last_seen_at: current.device.last_seen_at,
                }
              : device,
          telemetry: mergeTelemetrySnapshots(telemetry, current.telemetry),
          commands: mergeCommandSnapshots(commands, current.commands),
          capabilityState: mergeCapabilityState(
            capabilityState,
            current.capabilityState,
          ),
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
          error:
            error instanceof Error
              ? error.message
              : "The device request failed.",
          notFound: error instanceof ApiError && error.status === 404,
        }));
      });

    return () => controller.abort();
  }, [deviceId, invalidateSession, requestNumber, token]);

  const refresh = useCallback(() => {
    setState((current) => ({ ...current, loading: true, error: null }));
    setRequestNumber((value) => value + 1);
  }, []);

  const handleLiveEvent = useCallback(
    (event: DeviceOpsEvent) => {
      if (event.type === "event_created" || event.type === "alert_update") return;
      if (event.device_id !== deviceId) return;

      setState((current) => {
        if (current.device === null) return current;

        if (event.type === "capabilities_updated") {
          return {
            ...current,
            device: {
              ...current.device,
              first_seen_at: current.device.first_seen_at ?? event.received_at,
              last_seen_at: event.received_at,
            },
            capabilityState: mergeCapabilityState(
              {
                capabilities: event.data.capabilities,
                updated_at: event.received_at,
              },
              current.capabilityState,
            ),
          };
        }

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
              first_seen_at: current.device.first_seen_at ?? event.received_at,
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
          device: {
            ...current.device,
            first_seen_at: current.device.first_seen_at ?? event.received_at,
            last_seen_at: event.received_at,
          },
          telemetry: mergeTelemetrySnapshots([sample], current.telemetry),
        };
      });
    },
    [deviceId],
  );

  const liveConnection = useDeviceOpsWebSocket({
    enabled: state.device !== null && token !== null,
    token,
    onEvent: handleLiveEvent,
    onReconnect: refresh,
    onAuthenticationFailure: invalidateSession,
  });

  const submitCommand = useCallback(
    async (request: CommandRequest) => {
      if (!token) throw new ApiError("Authentication is required.", 401);
      const command = await apiPost<DeviceCommand>(
        `/api/devices/${encodeURIComponent(deviceId)}/commands`,
        request,
        { token, onUnauthorized: invalidateSession },
      );
      setState((current) => ({
        ...current,
        commands: mergeCommandSnapshots([command], current.commands),
      }));
      return command;
    },
    [deviceId, invalidateSession, token],
  );

  const handleRenamed = useCallback((updatedDevice: Device) => {
    setState((current) => ({ ...current, device: updatedDevice }));
  }, []);

  if (state.loading && state.device === null) {
    return <LoadingState label={`Loading ${deviceId}`} />;
  }

  if (state.notFound) {
    return (
      <StatePanel
        action={
          <Link className="button button-secondary" href="/fleet">
            Return to fleet
          </Link>
        }
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
  if (!device) return null;
  const telemetry = state.telemetry ?? [];
  const commands = state.commands ?? [];
  const capabilities = state.capabilityState?.capabilities ?? null;
  const capabilitiesUpdatedAt = state.capabilityState?.updated_at ?? null;
  const latest = telemetry.at(-1);
  const numericCapabilities = capabilities
    ? Object.entries(capabilities.telemetry).filter(
        ([metricName, descriptor]) =>
          isNumericCapability(descriptor) &&
          telemetry.some(
            (sample) => {
              const value = getTelemetryMetricValue(sample, metricName);
              return (
                typeof value === "number" &&
                isTelemetryMetricValueCompatible(descriptor, value)
              );
            },
          ),
      )
    : [];

  return (
    <>
      <nav aria-label="Breadcrumb" className="breadcrumb">
        <Link href="/">Fleet</Link>
        <ChevronRight aria-hidden="true" size={11} />
        <span className={device.display_name ? "" : "mono"}>
          {device.display_name ?? device.device_id}
        </span>
      </nav>

      <header className="page-header">
        <div>
          <div className="device-title-row">
            <h1 className={device.display_name ? "page-title" : "page-title mono"}>
              {device.display_name ?? device.device_id}
            </h1>
            <StatusBadge status={device.status} />
          </div>
          <p className="page-description">
            {device.display_name ? (
              <>
                <span className="mono">{device.device_id}</span> · Observed device
                state and persisted telemetry
              </>
            ) : (
              "Observed device state and persisted telemetry"
            )}
          </p>
        </div>
        <div className="page-actions">
          <LiveConnectionIndicator state={liveConnection} />
          {token ? (
            <DeviceManagementActions
              device={device}
              onRenamed={handleRenamed}
              onUnauthorized={invalidateSession}
              token={token}
            />
          ) : null}
          <RefreshButton loading={state.loading} onClick={refresh} />
        </div>
      </header>

      {state.error ? (
        <div className="health-line health-degraded">
          Refresh failed. Showing the last successfully loaded device state.
        </div>
      ) : null}

      <section aria-label="Device metadata" className="detail-meta-grid">
        <div className="detail-meta-item">
          <span className="detail-label">Stable identifier</span>
          <span className="detail-value mono">{device.device_id}</span>
        </div>
        <div className="detail-meta-item">
          <span className="detail-label">Last seen</span>
          <span className="detail-value" title={formatExactTime(device.last_seen_at)}>
            {device.last_seen_at ? (
              <>
                {formatRelativeTime(device.last_seen_at)} ·{" "}
                <span className="mono">{formatExactTime(device.last_seen_at)}</span>
              </>
            ) : (
              "Never"
            )}
          </span>
        </div>
        <div className="detail-meta-item">
          <span className="detail-label">First seen</span>
          <span className="detail-value" title={formatExactTime(device.first_seen_at)}>
            {device.first_seen_at ? (
              <>
                {formatRelativeTime(device.first_seen_at)} ·{" "}
                <span className="mono">{formatExactTime(device.first_seen_at)}</span>
              </>
            ) : (
              "Never"
            )}
          </span>
        </div>
        <div className="detail-meta-item">
          <span className="detail-label">Capabilities</span>
          <span
            className="detail-value"
            title={formatExactTime(capabilitiesUpdatedAt)}
          >
            {capabilities ? (
              capabilitiesUpdatedAt ? (
                <>
                  Advertised · {formatRelativeTime(capabilitiesUpdatedAt)} ·{" "}
                  <span className="mono">
                    {formatExactTime(capabilitiesUpdatedAt)}
                  </span>
                </>
              ) : (
                "Advertised"
              )
            ) : (
              "Not advertised"
            )}
          </span>
        </div>
      </section>

      {!capabilities ? (
        <div className="capability-note">
          <strong>Capabilities not advertised.</strong> Telemetry remains available
          below as legacy raw fields; remote controls stay hidden until the device
          publishes a manifest.
        </div>
      ) : null}

      <div className="command-grid">
        <DeviceControl
          capabilities={capabilities}
          commands={commands}
          key={capabilities?.sent_at ?? "no-capabilities"}
          submitCommand={submitCommand}
        />
        <RecentCommands commands={commands} />
      </div>

      {capabilities ? (
        <DeviceMetricSummary capabilities={capabilities} latest={latest} />
      ) : null}

      {numericCapabilities.length > 0 ? (
        <div className="chart-grid">
          {numericCapabilities.map(([metricName, descriptor], index) => (
            <TelemetryChart
              color={CHART_COLORS[index % CHART_COLORS.length]}
              data={telemetry}
              descriptor={descriptor}
              key={metricName}
              label={descriptor.label}
              metricName={metricName}
            />
          ))}
        </div>
      ) : null}

      <RecentTelemetryTable capabilities={capabilities} telemetry={telemetry} />

      <p className="footer-note">
        Charts use the backend-controlled received_at timeline. The table also
        exposes device-reported sent_at.
      </p>
    </>
  );
}
