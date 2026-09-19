"use client";

import { AlertTriangle, CheckCircle2, Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { AddDeviceDialog } from "@/components/add-device-dialog";
import { useAuth } from "@/components/auth-provider";
import { DeviceTable } from "@/components/device-table";
import { FleetSummary } from "@/components/fleet-summary";
import { LiveConnectionIndicator } from "@/components/live-connection-indicator";
import { RefreshButton } from "@/components/refresh-button";
import { LoadingState, StatePanel } from "@/components/state-panel";
import { apiGet } from "@/lib/api";
import { isLaterTimestamp } from "@/lib/format";
import { useDeviceOpsWebSocket } from "@/hooks/use-deviceops-websocket";
import type { Device, DeviceOpsEvent, Health } from "@/lib/types";

interface FleetState {
  devices: Device[] | null;
  health: Health | null;
  loading: boolean;
  error: string | null;
}

const initialState: FleetState = {
  devices: null,
  health: null,
  loading: true,
  error: null,
};

function mergeDeviceSnapshots(snapshot: Device[], current: Device[] | null): Device[] {
  if (current === null) return snapshot;
  const currentById = new Map(current.map((device) => [device.device_id, device]));
  return snapshot.map((device) => {
    const liveDevice = currentById.get(device.device_id);
    return liveDevice &&
      isLaterTimestamp(liveDevice.last_seen_at, device.last_seen_at)
      ? liveDevice
      : device;
  });
}

export default function FleetPage() {
  const { invalidateSession, token } = useAuth();
  const [addDeviceOpen, setAddDeviceOpen] = useState(false);
  const [requestNumber, setRequestNumber] = useState(0);
  const [state, setState] = useState<FleetState>(initialState);

  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();

    Promise.all([
      apiGet<Device[]>("/api/devices", {
        signal: controller.signal,
        token,
        onUnauthorized: invalidateSession,
      }),
      apiGet<Health>("/health", { signal: controller.signal }),
    ])
      .then(([devices, health]) => {
        setState((current) => ({
          devices: mergeDeviceSnapshots(devices, current.devices),
          health,
          loading: false,
          error: null,
        }));
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setState((current) => ({
          ...current,
          loading: false,
          error: error instanceof Error ? error.message : "The fleet request failed.",
        }));
      });

    return () => controller.abort();
  }, [invalidateSession, requestNumber, token]);

  const refresh = useCallback(() => {
    setState((current) => ({ ...current, loading: true, error: null }));
    setRequestNumber((value) => value + 1);
  }, []);

  const handleLiveEvent = useCallback((event: DeviceOpsEvent) => {
    if (event.type === "event_created" || event.type === "alert_update") return;
    setState((current) => {
      if (current.devices === null) return current;

      const existingIndex = current.devices.findIndex(
        (device) => device.device_id === event.device_id,
      );
      const existing = current.devices[existingIndex];
      const updated: Device = existing
        ? {
            ...existing,
            status:
              event.type === "device_status" ? event.data.status : existing.status,
            first_seen_at: existing.first_seen_at ?? event.received_at,
            last_seen_at: event.received_at,
          }
        : {
            device_id: event.device_id,
            status: event.type === "device_status" ? event.data.status : "unknown",
            first_seen_at: event.received_at,
            last_seen_at: event.received_at,
          };

      const devices = [...current.devices];
      if (existingIndex >= 0) devices[existingIndex] = updated;
      else devices.push(updated);
      devices.sort((left, right) => left.device_id.localeCompare(right.device_id));
      return { ...current, devices };
    });
  }, []);

  const handleRegisteredDevice = useCallback((registeredDevice: Device) => {
    setState((current) => {
      const devices = current.devices ?? [];
      if (
        devices.some(
          (device) => device.device_id === registeredDevice.device_id,
        )
      ) {
        return current;
      }
      return {
        ...current,
        devices: [...devices, registeredDevice].sort((left, right) =>
          left.device_id.localeCompare(right.device_id),
        ),
      };
    });
  }, []);

  const liveConnection = useDeviceOpsWebSocket({
    enabled: state.devices !== null && token !== null,
    token,
    onEvent: handleLiveEvent,
    onReconnect: refresh,
    onAuthenticationFailure: invalidateSession,
  });

  if (state.loading && state.devices === null) {
    return <LoadingState label="Loading fleet inventory" />;
  }

  if (state.error && state.devices === null) {
    return (
      <StatePanel
        action={
          <button className="button button-primary" onClick={refresh} type="button">
            Retry connection
          </button>
        }
        description={`${state.error} Confirm FastAPI is running and the frontend API URL is correct.`}
        eyebrow="Backend unavailable"
        title="Fleet data could not be loaded"
      />
    );
  }

  const devices = state.devices ?? [];

  return (
    <>
      <header className="page-header">
        <div>
          <h1 className="page-title">Fleet</h1>
          <p className="page-description">Device inventory and observed connectivity</p>
        </div>
        <div className="page-actions">
          <button
            className="button button-primary"
            onClick={() => setAddDeviceOpen(true)}
            type="button"
          >
            <Plus aria-hidden="true" size={14} />
            Add device
          </button>
          <RefreshButton loading={state.loading} onClick={refresh} />
        </div>
      </header>

      {state.health ? (
        <div className="health-line">
          {state.health.status === "ok" ? (
            <CheckCircle2 aria-hidden="true" className="health-ok" size={13} />
          ) : (
            <AlertTriangle aria-hidden="true" className="health-degraded" size={13} />
          )}
          <span className={state.health.status === "ok" ? "health-ok" : "health-degraded"}>
            Ingestion {state.health.status}
          </span>
          <span className="health-divider" />
          <span>PostgreSQL: {state.health.database}</span>
          <span className="health-divider" />
          <span>MQTT: {state.health.mqtt}</span>
          <span className="health-divider" />
          <LiveConnectionIndicator state={liveConnection} />
        </div>
      ) : null}

      <FleetSummary devices={devices} />

      {state.error ? (
        <div className="health-line health-degraded">
          <AlertTriangle aria-hidden="true" size={13} />
          Refresh failed. Showing the last successfully loaded inventory.
        </div>
      ) : null}

      {devices.length === 0 ? (
        <StatePanel
          description="Register a device to generate its one-time credentials and add it to this fleet."
          eyebrow="0 devices"
          title="No devices registered"
        />
      ) : (
        <DeviceTable devices={devices} />
      )}

      <p className="footer-note">
        Data is loaded from the DeviceOps REST API. Use Refresh to request the latest persisted state.
      </p>

      {addDeviceOpen && token ? (
        <AddDeviceDialog
          onClose={() => setAddDeviceOpen(false)}
          onRegistered={handleRegisteredDevice}
          onUnauthorized={invalidateSession}
          token={token}
        />
      ) : null}
    </>
  );
}
