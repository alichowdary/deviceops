"use client";

import { LoaderCircle, Pencil, Plus, Power, Trash2 } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { AlertRuleDialog } from "@/components/alert-rule-dialog";
import { useAuth } from "@/components/auth-provider";
import { RefreshButton } from "@/components/refresh-button";
import { LoadingState, StatePanel } from "@/components/state-panel";
import { apiDelete, apiGet, apiPatch } from "@/lib/api";
import type {
  AlertMetric,
  AlertOperator,
  AlertRule,
  Device,
} from "@/lib/types";

interface AlertsState {
  rules: AlertRule[] | null;
  devices: Device[] | null;
  loading: boolean;
  error: string | null;
}

const initialState: AlertsState = {
  rules: null,
  devices: null,
  loading: true,
  error: null,
};

const metricLabels: Record<AlertMetric, { label: string; unit: string }> = {
  temperature_c: { label: "Temperature", unit: "°C" },
  humidity_pct: { label: "Humidity", unit: "%" },
  pressure_hpa: { label: "Pressure", unit: "hPa" },
  battery_pct: { label: "Battery", unit: "%" },
  rssi_dbm: { label: "Signal strength", unit: "dBm" },
};

const operatorLabels: Record<AlertOperator, string> = {
  gt: ">",
  gte: "≥",
  lt: "<",
  lte: "≤",
};

function formatDuration(seconds: number): string {
  if (seconds % 86_400 === 0) {
    const days = seconds / 86_400;
    return `${days} ${days === 1 ? "day" : "days"}`;
  }
  if (seconds % 3_600 === 0) {
    const hours = seconds / 3_600;
    return `${hours} ${hours === 1 ? "hour" : "hours"}`;
  }
  if (seconds % 60 === 0) {
    const minutes = seconds / 60;
    return `${minutes} ${minutes === 1 ? "minute" : "minutes"}`;
  }
  return `${seconds} seconds`;
}

function ruleCondition(rule: AlertRule): string {
  if (rule.rule_type === "device_offline") {
    return `Offline for ${formatDuration(rule.offline_after_seconds ?? 0)}`;
  }
  if (rule.metric === null || rule.operator === null || rule.threshold === null) {
    return "Invalid metric rule";
  }
  const metric = metricLabels[rule.metric];
  return `${metric.label} ${operatorLabels[rule.operator]} ${rule.threshold} ${metric.unit}`;
}

function sortRules(rules: AlertRule[]): AlertRule[] {
  return [...rules].sort((left, right) => {
    const timeDifference =
      new Date(right.created_at).getTime() - new Date(left.created_at).getTime();
    return timeDifference || right.id - left.id;
  });
}

export default function AlertsPage() {
  const { invalidateSession, token } = useAuth();
  const [requestNumber, setRequestNumber] = useState(0);
  const [dialogRule, setDialogRule] = useState<AlertRule | "create" | null>(null);
  const [pendingRuleId, setPendingRuleId] = useState<number | null>(null);
  const [state, setState] = useState<AlertsState>(initialState);

  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();

    Promise.all([
      apiGet<AlertRule[]>("/api/alert-rules", {
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
      .then(([rules, devices]) => {
        setState({
          rules: sortRules(rules),
          devices,
          loading: false,
          error: null,
        });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setState((current) => ({
          ...current,
          loading: false,
          error:
            error instanceof Error ? error.message : "The alert rules request failed.",
        }));
      });

    return () => controller.abort();
  }, [invalidateSession, requestNumber, token]);

  const refresh = useCallback(() => {
    setState((current) => ({ ...current, loading: true, error: null }));
    setRequestNumber((value) => value + 1);
  }, []);

  const handleSaved = useCallback((savedRule: AlertRule) => {
    setState((current) => ({
      ...current,
      rules: sortRules([
        ...(current.rules ?? []).filter((rule) => rule.id !== savedRule.id),
        savedRule,
      ]),
      error: null,
    }));
  }, []);

  async function toggleRule(rule: AlertRule) {
    if (!token || pendingRuleId !== null) return;
    setPendingRuleId(rule.id);
    setState((current) => ({ ...current, error: null }));
    try {
      const updated = await apiPatch<AlertRule>(
        `/api/alert-rules/${rule.id}`,
        { enabled: !rule.enabled },
        { token, onUnauthorized: invalidateSession },
      );
      handleSaved(updated);
    } catch (error) {
      setState((current) => ({
        ...current,
        error: error instanceof Error ? error.message : "The rule could not be updated.",
      }));
    } finally {
      setPendingRuleId(null);
    }
  }

  async function removeRule(rule: AlertRule) {
    if (
      !token ||
      pendingRuleId !== null ||
      !window.confirm(`Delete ${rule.name ?? "this alert rule"}?`)
    ) {
      return;
    }
    setPendingRuleId(rule.id);
    setState((current) => ({ ...current, error: null }));
    try {
      await apiDelete(`/api/alert-rules/${rule.id}`, {
        token,
        onUnauthorized: invalidateSession,
      });
      setState((current) => ({
        ...current,
        rules: (current.rules ?? []).filter((item) => item.id !== rule.id),
      }));
    } catch (error) {
      setState((current) => ({
        ...current,
        error: error instanceof Error ? error.message : "The rule could not be deleted.",
      }));
    } finally {
      setPendingRuleId(null);
    }
  }

  if (state.loading && state.rules === null) {
    return <LoadingState label="Loading alert rules" />;
  }

  if (state.error && state.rules === null) {
    return (
      <StatePanel
        action={
          <button className="button button-primary" onClick={refresh} type="button">
            Retry connection
          </button>
        }
        description={`${state.error} Confirm FastAPI is running and retry the request.`}
        eyebrow="Backend unavailable"
        title="Alert rules could not be loaded"
      />
    );
  }

  const rules = state.rules ?? [];
  const devices = state.devices ?? [];

  return (
    <>
      <header className="page-header">
        <div>
          <h1 className="page-title">Alerts</h1>
          <p className="page-description">Configure device thresholds and offline rules</p>
        </div>
        <div className="page-actions">
          <button
            className="button button-primary"
            disabled={devices.length === 0}
            onClick={() => setDialogRule("create")}
            type="button"
          >
            <Plus aria-hidden="true" size={14} />
            Create rule
          </button>
          <RefreshButton loading={state.loading} onClick={refresh} />
        </div>
      </header>

      <div className="alert-phase-note">
        Rules are configured here. Evaluation and alert instances are added in the next phase.
      </div>

      {state.error ? (
        <div className="health-line health-degraded">
          The last action failed: {state.error}
        </div>
      ) : null}

      {devices.length === 0 ? (
        <StatePanel
          description="Register a device from Fleet before creating an alert rule."
          eyebrow="No devices"
          title="Alert rules need a device"
        />
      ) : rules.length === 0 ? (
        <StatePanel
          action={
            <button
              className="button button-primary"
              onClick={() => setDialogRule("create")}
              type="button"
            >
              <Plus aria-hidden="true" size={14} />
              Create first rule
            </button>
          }
          description="Define a metric threshold or an offline duration for one of your devices."
          eyebrow="0 rules"
          title="No alert rules configured"
        />
      ) : (
        <section className="panel">
          <div className="section-header">
            <h2 className="section-title">Rule definitions</h2>
            <span className="section-meta">{rules.length} records</span>
          </div>
          <div className="data-table-wrap">
            <table className="data-table alert-rules-table">
              <thead>
                <tr>
                  <th scope="col">State</th>
                  <th scope="col">Rule</th>
                  <th scope="col">Device</th>
                  <th scope="col">Condition</th>
                  <th scope="col">Severity</th>
                  <th className="alert-actions-heading" scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rules.map((rule) => {
                  const pending = pendingRuleId === rule.id;
                  return (
                    <tr key={rule.id}>
                      <td>
                        <span
                          className={`rule-state ${rule.enabled ? "rule-state-enabled" : "rule-state-disabled"}`}
                        >
                          {rule.enabled ? "Enabled" : "Disabled"}
                        </span>
                      </td>
                      <td>
                        <span className="table-primary">
                          {rule.name ?? "Unnamed rule"}
                        </span>
                        <span className="table-secondary">
                          {rule.rule_type === "metric_threshold"
                            ? "Metric threshold"
                            : "Device offline"}
                        </span>
                      </td>
                      <td>
                        <Link
                          className="alert-device-link mono"
                          href={`/devices/${encodeURIComponent(rule.device_id)}`}
                        >
                          {rule.device_id}
                        </Link>
                      </td>
                      <td><span className="alert-condition">{ruleCondition(rule)}</span></td>
                      <td>
                        <span className={`rule-severity rule-severity-${rule.severity}`}>
                          {rule.severity}
                        </span>
                      </td>
                      <td>
                        <div className="alert-row-actions">
                          <button
                            aria-label={`Edit ${rule.name ?? "alert rule"}`}
                            className="table-action"
                            disabled={pendingRuleId !== null}
                            onClick={() => setDialogRule(rule)}
                            title="Edit rule"
                            type="button"
                          >
                            <Pencil aria-hidden="true" size={13} />
                            Edit
                          </button>
                          <button
                            aria-label={`${rule.enabled ? "Disable" : "Enable"} ${rule.name ?? "alert rule"}`}
                            className="table-action"
                            disabled={pendingRuleId !== null}
                            onClick={() => void toggleRule(rule)}
                            title={rule.enabled ? "Disable rule" : "Enable rule"}
                            type="button"
                          >
                            {pending ? (
                              <LoaderCircle aria-hidden="true" className="icon-spin" size={13} />
                            ) : (
                              <Power aria-hidden="true" size={13} />
                            )}
                            {rule.enabled ? "Disable" : "Enable"}
                          </button>
                          <button
                            aria-label={`Delete ${rule.name ?? "alert rule"}`}
                            className="table-action table-action-danger"
                            disabled={pendingRuleId !== null}
                            onClick={() => void removeRule(rule)}
                            title="Delete rule"
                            type="button"
                          >
                            <Trash2 aria-hidden="true" size={13} />
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <p className="footer-note">
        Rule definitions are persisted and owner-scoped. They are not evaluated in this phase.
      </p>

      {dialogRule !== null && token ? (
        <AlertRuleDialog
          devices={devices}
          onClose={() => setDialogRule(null)}
          onSaved={handleSaved}
          onUnauthorized={invalidateSession}
          rule={dialogRule === "create" ? null : dialogRule}
          token={token}
        />
      ) : null}
    </>
  );
}
