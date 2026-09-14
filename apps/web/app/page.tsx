"use client";

import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { useEffect, useState } from "react";

import { DeviceTable } from "@/components/device-table";
import { FleetSummary } from "@/components/fleet-summary";
import { RefreshButton } from "@/components/refresh-button";
import { LoadingState, StatePanel } from "@/components/state-panel";
import { apiGet } from "@/lib/api";
import type { Device, Health } from "@/lib/types";

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

export default function FleetPage() {
  const [requestNumber, setRequestNumber] = useState(0);
  const [state, setState] = useState<FleetState>(initialState);

  useEffect(() => {
    const controller = new AbortController();

    Promise.all([
      apiGet<Device[]>("/api/devices", controller.signal),
      apiGet<Health>("/health", controller.signal),
    ])
      .then(([devices, health]) => {
        setState({ devices, health, loading: false, error: null });
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
  }, [requestNumber]);

  function refresh() {
    setState((current) => ({ ...current, loading: true, error: null }));
    setRequestNumber((value) => value + 1);
  }

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
          description="Start a simulator to publish status and telemetry. The device will appear after FastAPI ingests its first message."
          eyebrow="0 devices"
          title="No devices observed"
        />
      ) : (
        <DeviceTable devices={devices} />
      )}

      <p className="footer-note">
        Data is loaded from the DeviceOps REST API. Use Refresh to request the latest persisted state.
      </p>
    </>
  );
}
