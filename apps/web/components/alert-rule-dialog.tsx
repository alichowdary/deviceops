"use client";

import { LoaderCircle } from "lucide-react";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { apiGet, apiPatch, apiPost } from "@/lib/api";
import { formatDeviceLabel } from "@/lib/devices";
import type {
  AlertMetric,
  AlertOperator,
  AlertRule,
  AlertRuleCreate,
  AlertSeverity,
  AlertRuleType,
  CapabilityState,
  CapabilityValueDescriptor,
  Device,
} from "@/lib/types";

type DurationUnit = "seconds" | "minutes" | "hours" | "days";

const durationMultipliers: Record<DurationUnit, number> = {
  seconds: 1,
  minutes: 60,
  hours: 3_600,
  days: 86_400,
};

const alertMetricPresentation: Record<string, { label: string; unit: string }> = {
  temperature_c: { label: "Temperature", unit: "°C" },
  humidity_pct: { label: "Humidity", unit: "%" },
  pressure_hpa: { label: "Pressure", unit: "hPa" },
  battery_pct: { label: "Battery", unit: "%" },
  rssi_dbm: { label: "Signal strength", unit: "dBm" },
  uptime_s: { label: "Uptime", unit: "s" },
};

function readableMetricLabel(value: AlertMetric): string {
  return value.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}

function metricOption(
  value: AlertMetric,
  descriptor?: CapabilityValueDescriptor,
): { value: AlertMetric; label: string } {
  const presentation = alertMetricPresentation[value];
  const label =
    value === "rssi_dbm"
      ? presentation.label
      : descriptor?.label ?? presentation?.label ?? readableMetricLabel(value);
  const unit = descriptor?.unit ?? presentation?.unit ?? "";
  return { value, label: unit ? `${label} (${unit})` : label };
}

const operators: Array<{ value: AlertOperator; label: string }> = [
  { value: "gt", label: "> greater than" },
  { value: "gte", label: "≥ greater than or equal" },
  { value: "lt", label: "< less than" },
  { value: "lte", label: "≤ less than or equal" },
];

const severities: AlertSeverity[] = ["info", "warning", "critical"];

function initialDuration(seconds: number | null): {
  amount: string;
  unit: DurationUnit;
} {
  const value = seconds ?? 300;
  for (const [unit, multiplier] of [
    ["days", 86_400],
    ["hours", 3_600],
    ["minutes", 60],
  ] as const) {
    if (value % multiplier === 0) {
      return { amount: String(value / multiplier), unit };
    }
  }
  return { amount: String(value), unit: "seconds" };
}

export function AlertRuleDialog({
  devices,
  rule,
  token,
  onClose,
  onSaved,
  onUnauthorized,
}: {
  devices: Device[];
  rule: AlertRule | null;
  token: string;
  onClose: () => void;
  onSaved: (savedRule: AlertRule) => void;
  onUnauthorized: () => void;
}) {
  const duration = initialDuration(rule?.offline_after_seconds ?? null);
  const [deviceId, setDeviceId] = useState(rule?.device_id ?? devices[0]?.device_id ?? "");
  const [name, setName] = useState(rule?.name ?? "");
  const [ruleType, setRuleType] = useState<AlertRuleType>(
    rule?.rule_type ?? "metric_threshold",
  );
  const [metric, setMetric] = useState<AlertMetric>(
    rule?.metric ?? "temperature_c",
  );
  const [operator, setOperator] = useState<AlertOperator>(rule?.operator ?? "gt");
  const [threshold, setThreshold] = useState(String(rule?.threshold ?? 30));
  const [durationAmount, setDurationAmount] = useState(duration.amount);
  const [durationUnit, setDurationUnit] = useState<DurationUnit>(duration.unit);
  const [severity, setSeverity] = useState<AlertSeverity>(
    rule?.severity ?? "warning",
  );
  const [enabled, setEnabled] = useState(rule?.enabled ?? true);
  const [capabilityState, setCapabilityState] = useState<CapabilityState | null>(null);
  const [capabilitiesLoading, setCapabilitiesLoading] = useState(true);
  const [capabilitiesError, setCapabilitiesError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    apiGet<CapabilityState>(
      `/api/devices/${encodeURIComponent(deviceId)}/capabilities`,
      { signal: controller.signal, token, onUnauthorized },
    )
      .then((nextCapabilityState) => {
        setCapabilityState(nextCapabilityState);
        if (!rule && nextCapabilityState.capabilities) {
          const available = Object.entries(
            nextCapabilityState.capabilities.telemetry,
          )
            .filter(([, descriptor]) =>
              descriptor.type === "number" || descriptor.type === "integer"
            )
            .map(([candidate]) => candidate);
          setMetric((current) =>
            available.includes(current) ? current : available[0] ?? current,
          );
        }
      })
      .catch((requestError: unknown) => {
        if (requestError instanceof DOMException && requestError.name === "AbortError") {
          return;
        }
        setCapabilitiesError(
          requestError instanceof Error
            ? requestError.message
            : "Capabilities could not be loaded.",
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setCapabilitiesLoading(false);
      });
    return () => controller.abort();
  }, [deviceId, onUnauthorized, rule, token]);

  const advertisedTelemetry = capabilityState?.capabilities?.telemetry;
  const metricOptions = rule?.metric
    ? [metricOption(rule.metric, advertisedTelemetry?.[rule.metric])]
    : advertisedTelemetry
      ? Object.entries(advertisedTelemetry)
          .filter(([, descriptor]) =>
            descriptor.type === "number" || descriptor.type === "integer"
          )
          .map(([candidate, descriptor]) => metricOption(candidate, descriptor))
      : [];
  const metricUnavailable = !rule && !capabilitiesLoading && metricOptions.length === 0;

  async function saveRule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;

    if (ruleType === "metric_threshold" && metricUnavailable) {
      setError("This device has no advertised metrics supported by alert rules.");
      return;
    }

    const normalizedName = name.trim() || null;
    const thresholdValue = Number(threshold);
    const durationValue = Number(durationAmount);
    if (ruleType === "metric_threshold" && !Number.isFinite(thresholdValue)) {
      setError("Enter a finite threshold.");
      return;
    }
    if (
      ruleType === "device_offline" &&
      (!Number.isInteger(durationValue) || durationValue <= 0)
    ) {
      setError("Enter a positive whole-number duration.");
      return;
    }

    const offlineSeconds = durationValue * durationMultipliers[durationUnit];
    if (
      ruleType === "device_offline" &&
      (offlineSeconds < 5 || offlineSeconds > 604_800)
    ) {
      setError("Offline duration must be between 5 seconds and 7 days.");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      let savedRule: AlertRule;
      if (rule) {
        savedRule = await apiPatch<AlertRule>(
          `/api/alert-rules/${rule.id}`,
          ruleType === "metric_threshold"
            ? {
                name: normalizedName,
                severity,
                enabled,
                operator,
                threshold: thresholdValue,
              }
            : {
                name: normalizedName,
                severity,
                enabled,
                offline_after_seconds: offlineSeconds,
              },
          { token, onUnauthorized },
        );
      } else {
        const payload: AlertRuleCreate =
          ruleType === "metric_threshold"
            ? {
                device_id: deviceId,
                name: normalizedName,
                rule_type: "metric_threshold",
                metric,
                operator,
                threshold: thresholdValue,
                severity,
                enabled,
              }
            : {
                device_id: deviceId,
                name: normalizedName,
                rule_type: "device_offline",
                offline_after_seconds: offlineSeconds,
                severity,
                enabled,
              };
        savedRule = await apiPost<AlertRule>("/api/alert-rules", payload, {
          token,
          onUnauthorized,
        });
      }
      onSaved(savedRule);
      onClose();
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "The alert rule could not be saved.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="dialog-backdrop">
      <section
        aria-describedby="alert-rule-description"
        aria-labelledby="alert-rule-title"
        aria-modal="true"
        className="add-device-dialog alert-rule-dialog"
        onKeyDown={(event) => {
          if (event.key === "Escape" && !submitting) onClose();
        }}
        role="dialog"
      >
        <header className="dialog-header">
          <span className="state-eyebrow">Rule configuration</span>
          <h2 id="alert-rule-title">{rule ? "Edit alert rule" : "Create alert rule"}</h2>
        </header>

        <form onSubmit={(event) => void saveRule(event)}>
          <div className="dialog-body alert-rule-form">
            <p id="alert-rule-description">
              {rule
                ? "Update how this rule is configured. Its device and rule type remain fixed."
                : "Define a condition to evaluate against committed device telemetry or connectivity."}
            </p>

            <div className="alert-form-grid">
              <label className="alert-form-field alert-form-field-wide">
                <span>Device</span>
                <select
                  disabled={Boolean(rule) || submitting}
                  onChange={(event) => {
                    setDeviceId(event.target.value);
                    setCapabilityState(null);
                    setCapabilitiesLoading(true);
                    setCapabilitiesError(null);
                  }}
                  required
                  value={deviceId}
                >
                  {devices.map((device) => (
                    <option key={device.device_id} value={device.device_id}>
                      {formatDeviceLabel(device)}
                    </option>
                  ))}
                </select>
              </label>

              <label className="alert-form-field alert-form-field-wide">
                <span>Rule name <small>optional</small></span>
                <input
                  disabled={submitting}
                  maxLength={100}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="e.g. Workshop too warm"
                  value={name}
                />
              </label>

              <label className="alert-form-field alert-form-field-wide">
                <span>Rule type</span>
                <select
                  disabled={Boolean(rule) || submitting}
                  onChange={(event) => setRuleType(event.target.value as AlertRuleType)}
                  value={ruleType}
                >
                  <option value="metric_threshold">Metric threshold</option>
                  <option value="device_offline">Device offline</option>
                </select>
              </label>

              {ruleType === "metric_threshold" ? (
                <>
                  <label className="alert-form-field">
                    <span>Metric</span>
                    <select
                      disabled={
                        Boolean(rule) ||
                        submitting ||
                        capabilitiesLoading ||
                        metricOptions.length === 0
                      }
                      onChange={(event) => setMetric(event.target.value as AlertMetric)}
                      value={metric}
                    >
                      {metricOptions.length > 0 ? (
                        metricOptions.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))
                      ) : (
                        <option value={metric}>
                          {capabilitiesLoading
                            ? "Loading advertised metrics…"
                            : "No alertable metrics advertised"}
                        </option>
                      )}
                    </select>
                    {!rule && !capabilitiesLoading && !capabilitiesError && !advertisedTelemetry ? (
                      <small className="alert-metric-note">
                        This device has not advertised capabilities. Device offline
                        rules remain available.
                      </small>
                    ) : null}
                    {!rule && !capabilitiesLoading && advertisedTelemetry && metricOptions.length === 0 ? (
                      <small className="alert-metric-note">
                        This device advertises no numeric metrics. Device offline
                        rules remain available.
                      </small>
                    ) : null}
                    {capabilitiesError ? (
                      <small className="alert-metric-note">
                        Metric availability could not be loaded. {capabilitiesError}
                      </small>
                    ) : null}
                  </label>
                  <label className="alert-form-field">
                    <span>Comparison</span>
                    <select
                      disabled={submitting}
                      onChange={(event) =>
                        setOperator(event.target.value as AlertOperator)
                      }
                      value={operator}
                    >
                      {operators.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="alert-form-field alert-form-field-wide">
                    <span>Threshold</span>
                    <input
                      disabled={submitting}
                      onChange={(event) => setThreshold(event.target.value)}
                      required
                      step="any"
                      type="number"
                      value={threshold}
                    />
                  </label>
                </>
              ) : (
                <div className="alert-duration alert-form-field-wide">
                  <label className="alert-form-field">
                    <span>Offline duration</span>
                    <input
                      disabled={submitting}
                      min={durationUnit === "seconds" ? "5" : "1"}
                      onChange={(event) => setDurationAmount(event.target.value)}
                      required
                      step="1"
                      type="number"
                      value={durationAmount}
                    />
                  </label>
                  <label className="alert-form-field">
                    <span>Unit</span>
                    <select
                      disabled={submitting}
                      onChange={(event) =>
                        setDurationUnit(event.target.value as DurationUnit)
                      }
                      value={durationUnit}
                    >
                      <option value="seconds">Seconds</option>
                      <option value="minutes">Minutes</option>
                      <option value="hours">Hours</option>
                      <option value="days">Days</option>
                    </select>
                  </label>
                </div>
              )}

              <label className="alert-form-field">
                <span>Severity</span>
                <select
                  disabled={submitting}
                  onChange={(event) =>
                    setSeverity(event.target.value as AlertSeverity)
                  }
                  value={severity}
                >
                  {severities.map((value) => (
                    <option key={value} value={value}>
                      {value[0].toUpperCase() + value.slice(1)}
                    </option>
                  ))}
                </select>
              </label>

              <label className="alert-enabled-field">
                <input
                  checked={enabled}
                  disabled={submitting}
                  onChange={(event) => setEnabled(event.target.checked)}
                  type="checkbox"
                />
                <span>
                  Enabled
                  <small>The rule is available for evaluation when enabled.</small>
                </span>
              </label>
            </div>

            <div aria-live="polite" className="dialog-error">
              {error}
            </div>
          </div>

          <footer className="dialog-footer">
            <button
              className="button button-secondary"
              disabled={submitting}
              onClick={onClose}
              type="button"
            >
              Cancel
            </button>
            <button
              className="button button-primary"
              disabled={
                submitting ||
                (!rule &&
                  ruleType === "metric_threshold" &&
                  (capabilitiesLoading || metricUnavailable))
              }
              type="submit"
            >
              {submitting ? (
                <>
                  <LoaderCircle aria-hidden="true" className="icon-spin" size={14} />
                  Saving
                </>
              ) : rule ? (
                "Save changes"
              ) : (
                "Create rule"
              )}
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}
