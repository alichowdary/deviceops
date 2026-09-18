"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { LiveConnectionIndicator } from "@/components/live-connection-indicator";
import { RefreshButton } from "@/components/refresh-button";
import { LoadingState, StatePanel } from "@/components/state-panel";
import { useDeviceOpsWebSocket } from "@/hooks/use-deviceops-websocket";
import { apiGet } from "@/lib/api";
import { formatExactTime, formatRelativeTime } from "@/lib/format";
import type {
  Device,
  DeviceOpsEvent,
  EventSeverity,
  EventType,
  PersistedEvent,
} from "@/lib/types";

const EVENT_LIMIT = 100;

const eventTypeLabels: Record<EventType, string> = {
  device_registered: "Device registered",
  device_online: "Device online",
  device_offline: "Device offline",
  command_issued: "Command issued",
  command_succeeded: "Command succeeded",
  command_failed: "Command failed",
};

const eventTypes = Object.keys(eventTypeLabels) as EventType[];
const severities: EventSeverity[] = ["info", "success", "warning", "error"];

interface EventFilters {
  deviceId: string;
  eventType: EventType | "";
  severity: EventSeverity | "";
}

interface EventsState {
  events: PersistedEvent[] | null;
  devices: Device[] | null;
  filterKey: string;
  loading: boolean;
  error: string | null;
}

const initialFilters: EventFilters = {
  deviceId: "",
  eventType: "",
  severity: "",
};

function filtersKey(filters: EventFilters): string {
  return `${filters.deviceId}|${filters.eventType}|${filters.severity}`;
}

const initialState: EventsState = {
  events: null,
  devices: null,
  filterKey: filtersKey(initialFilters),
  loading: true,
  error: null,
};

function mergeEvents(
  incoming: PersistedEvent[],
  current: PersistedEvent[] | null,
): PersistedEvent[] {
  const eventsById = new Map<number, PersistedEvent>();
  for (const event of [...(current ?? []), ...incoming]) {
    eventsById.set(event.id, event);
  }
  return [...eventsById.values()]
    .sort((left, right) => {
      const timestampDifference =
        new Date(right.occurred_at).getTime() -
        new Date(left.occurred_at).getTime();
      return timestampDifference || right.id - left.id;
    })
    .slice(0, EVENT_LIMIT);
}

function matchesFilters(event: PersistedEvent, filters: EventFilters): boolean {
  return (
    (!filters.deviceId || event.device_id === filters.deviceId) &&
    (!filters.eventType || event.event_type === filters.eventType) &&
    (!filters.severity || event.severity === filters.severity)
  );
}

function commandDetail(event: PersistedEvent): string | null {
  const commandType = event.details.command_type;
  if (typeof commandType !== "string") return null;
  const argumentsValue = event.details.arguments;
  const argumentsRecord =
    typeof argumentsValue === "object" && argumentsValue !== null
      ? (argumentsValue as Record<string, unknown>)
      : {};

  if (commandType === "set_led") {
    return `Set LED ${argumentsRecord.on === true ? "on" : "off"}`;
  }
  if (commandType === "set_reporting_interval") {
    return typeof argumentsRecord.interval_s === "number"
      ? `Set reporting interval to ${argumentsRecord.interval_s} seconds`
      : "Set reporting interval";
  }
  if (commandType === "request_diagnostics") return "Request diagnostics";
  return commandType.replaceAll("_", " ");
}

function eventDescription(event: PersistedEvent): string {
  if (event.event_type === "device_registered") {
    return "One-time device credentials were generated.";
  }
  if (event.event_type === "device_online") {
    return "An authenticated device session came online.";
  }
  if (event.event_type === "device_offline") {
    return "The authenticated device session went offline.";
  }

  const detail = commandDetail(event) ?? "Device command";
  if (event.event_type === "command_issued") return detail;
  if (event.event_type === "command_succeeded") {
    return `${detail} completed successfully.`;
  }

  const result = event.details.result;
  const error =
    typeof result === "object" &&
    result !== null &&
    typeof (result as Record<string, unknown>).error === "string"
      ? (result as Record<string, unknown>).error
      : null;
  return error ? `${detail} failed: ${error}` : `${detail} failed.`;
}

function eventCommandId(event: PersistedEvent): string | null {
  return typeof event.details.command_id === "string"
    ? event.details.command_id
    : null;
}

export default function EventsPage() {
  const { invalidateSession, token } = useAuth();
  const [filters, setFilters] = useState<EventFilters>(initialFilters);
  const [requestNumber, setRequestNumber] = useState(0);
  const [state, setState] = useState<EventsState>(initialState);
  const filterKey = filtersKey(filters);

  const requestPath = useMemo(() => {
    const query = new URLSearchParams({ limit: String(EVENT_LIMIT) });
    if (filters.deviceId) query.set("device_id", filters.deviceId);
    if (filters.eventType) query.set("event_type", filters.eventType);
    if (filters.severity) query.set("severity", filters.severity);
    return `/api/events?${query.toString()}`;
  }, [filters]);

  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();

    Promise.all([
      apiGet<PersistedEvent[]>(requestPath, {
        signal: controller.signal,
        token,
        onUnauthorized: invalidateSession,
      }),
      apiGet<Device[]>("/api/devices", {
        signal: controller.signal,
        token,
        onUnauthorized: invalidateSession,
      }),
    ])
      .then(([events, devices]) => {
        setState((current) => {
          if (current.filterKey !== filterKey) return current;
          return {
            events: mergeEvents(events, current.events),
            devices,
            filterKey,
            loading: false,
            error: null,
          };
        });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setState((current) => {
          if (current.filterKey !== filterKey) return current;
          return {
            ...current,
            loading: false,
            error:
              error instanceof Error ? error.message : "The events request failed.",
          };
        });
      });

    return () => controller.abort();
  }, [filterKey, invalidateSession, requestNumber, requestPath, token]);

  const refresh = useCallback(() => {
    setState((current) => ({ ...current, loading: true, error: null }));
    setRequestNumber((value) => value + 1);
  }, []);

  const applyFilters = useCallback((nextFilters: EventFilters) => {
    setFilters(nextFilters);
    setState((current) => ({
      ...current,
      events: current.events === null ? null : [],
      filterKey: filtersKey(nextFilters),
      loading: true,
      error: null,
    }));
  }, []);

  const handleLiveEvent = useCallback(
    (event: DeviceOpsEvent) => {
      if (event.type !== "event_created" || !matchesFilters(event.data, filters)) {
        return;
      }
      setState((current) => {
        if (current.filterKey !== filterKey) return current;
        return {
          ...current,
          events: mergeEvents([event.data], current.events),
        };
      });
    },
    [filterKey, filters],
  );

  const liveConnection = useDeviceOpsWebSocket({
    enabled: state.events !== null && token !== null,
    token,
    onEvent: handleLiveEvent,
    onReconnect: refresh,
    onAuthenticationFailure: invalidateSession,
  });

  if (state.loading && state.events === null) {
    return <LoadingState label="Loading fleet events" />;
  }

  if (state.error && state.events === null) {
    return (
      <StatePanel
        action={
          <button className="button button-primary" onClick={refresh} type="button">
            Retry connection
          </button>
        }
        description={`${state.error} Confirm FastAPI is running and retry the request.`}
        eyebrow="Backend unavailable"
        title="Events could not be loaded"
      />
    );
  }

  const events = state.events ?? [];
  const devices = state.devices ?? [];

  return (
    <>
      <header className="page-header">
        <div>
          <h1 className="page-title">Events</h1>
          <p className="page-description">
            Durable registration, connectivity, and command activity
          </p>
        </div>
        <div className="page-actions">
          <LiveConnectionIndicator state={liveConnection} />
          <RefreshButton loading={state.loading} onClick={refresh} />
        </div>
      </header>

      <section aria-label="Event filters" className="event-filters panel">
        <label className="event-filter">
          <span>Device</span>
          <select
            onChange={(event) =>
              applyFilters({
                ...filters,
                deviceId: event.target.value,
              })
            }
            value={filters.deviceId}
          >
            <option value="">All devices</option>
            {devices.map((device) => (
              <option key={device.device_id} value={device.device_id}>
                {device.device_id}
              </option>
            ))}
          </select>
        </label>

        <label className="event-filter">
          <span>Event type</span>
          <select
            onChange={(event) =>
              applyFilters({
                ...filters,
                eventType: event.target.value as EventType | "",
              })
            }
            value={filters.eventType}
          >
            <option value="">All event types</option>
            {eventTypes.map((eventType) => (
              <option key={eventType} value={eventType}>
                {eventTypeLabels[eventType]}
              </option>
            ))}
          </select>
        </label>

        <label className="event-filter">
          <span>Severity</span>
          <select
            onChange={(event) =>
              applyFilters({
                ...filters,
                severity: event.target.value as EventSeverity | "",
              })
            }
            value={filters.severity}
          >
            <option value="">All severities</option>
            {severities.map((severity) => (
              <option key={severity} value={severity}>
                {severity[0].toUpperCase() + severity.slice(1)}
              </option>
            ))}
          </select>
        </label>

        <div className="event-filter-summary">
          {state.loading ? "Refreshing" : `${events.length} recent events`}
        </div>
      </section>

      {state.error ? (
        <div className="health-line health-degraded">
          Refresh failed. Showing the last successfully loaded event feed.
        </div>
      ) : null}

      {events.length === 0 ? (
        <StatePanel
          description="Registration, connectivity transitions, and command outcomes will appear here. Telemetry samples are intentionally excluded."
          eyebrow="0 events"
          title="No matching fleet activity"
        />
      ) : (
        <section className="event-feed panel">
          <div className="section-header">
            <h2 className="section-title">Activity feed</h2>
            <span className="section-meta">Newest first</span>
          </div>
          <ol className="event-list">
            {events.map((event) => {
              const commandId = eventCommandId(event);
              return (
                <li className="event-row" key={event.id}>
                  <span
                    aria-hidden="true"
                    className={`event-marker event-marker-${event.severity}`}
                  />
                  <div className="event-content">
                    <div className="event-heading">
                      <span className="event-label">
                        {eventTypeLabels[event.event_type]}
                      </span>
                      <span
                        className={`event-severity event-severity-${event.severity}`}
                      >
                        {event.severity}
                      </span>
                    </div>
                    <p className="event-description">{eventDescription(event)}</p>
                    <div className="event-context">
                      <Link
                        className="event-device mono"
                        href={`/devices/${encodeURIComponent(event.device_id)}`}
                      >
                        {event.device_id}
                      </Link>
                      {commandId ? (
                        <span className="event-command mono" title={commandId}>
                          command {commandId.slice(0, 8)}
                        </span>
                      ) : null}
                    </div>
                  </div>
                  <time
                    className="event-time"
                    dateTime={event.occurred_at}
                    title={formatExactTime(event.occurred_at)}
                  >
                    <span>{formatRelativeTime(event.occurred_at)}</span>
                    <span className="mono">{formatExactTime(event.occurred_at)}</span>
                  </time>
                </li>
              );
            })}
          </ol>
        </section>
      )}

      <p className="footer-note">
        Events are persisted operational records. Routine telemetry samples are not included.
      </p>
    </>
  );
}
