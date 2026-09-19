"use client";

import { useState } from "react";

import type {
  CapabilityManifest,
  CapabilityValueDescriptor,
  CommandRequest,
  DeviceCommand,
} from "@/lib/types";

interface Feedback {
  kind: "pending" | "success" | "error";
  message: string;
}

function initialInterval(descriptor: CapabilityValueDescriptor | undefined): string {
  if (!descriptor) return "5";
  const candidate = Math.min(
    descriptor.max ?? Number.POSITIVE_INFINITY,
    Math.max(descriptor.min ?? Number.NEGATIVE_INFINITY, 5),
  );
  return Number.isFinite(candidate) ? String(candidate) : "5";
}

export function DeviceControl({
  capabilities,
  commands,
  submitCommand,
}: {
  capabilities: CapabilityManifest | null;
  commands: DeviceCommand[];
  submitCommand: (request: CommandRequest) => Promise<DeviceCommand>;
}) {
  const intervalCommand = capabilities?.commands.set_reporting_interval;
  const intervalDescriptor = intervalCommand?.arguments.interval_s;
  const [interval, setInterval] = useState(() => initialInterval(intervalDescriptor));
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [submittedCommandId, setSubmittedCommandId] = useState<string | null>(null);

  const submittedCommand = commands.find(
    (candidate) => candidate.command_id === submittedCommandId,
  );
  const acknowledgementFeedback: Feedback | null =
    submittedCommand && submittedCommand.status !== "pending"
      ? {
          kind: submittedCommand.status === "failed" ? "error" : "success",
          message:
            submittedCommand.status === "failed"
              ? `Command failed${typeof submittedCommand.result?.error === "string" ? `: ${submittedCommand.result.error}` : "."}`
              : "Device acknowledged the command.",
        }
      : null;
  const visibleFeedback = acknowledgementFeedback ?? feedback;

  async function submit(request: CommandRequest) {
    setSubmitting(true);
    setFeedback(null);
    try {
      const command = await submitCommand(request);
      setSubmittedCommandId(command.command_id);
      setFeedback({
        kind: "pending",
        message: "Command accepted; awaiting device acknowledgement.",
      });
    } catch (error) {
      setSubmittedCommandId(null);
      setFeedback({
        kind: "error",
        message: error instanceof Error ? error.message : "Command submission failed.",
      });
    } finally {
      setSubmitting(false);
    }
  }

  function applyInterval() {
    if (!intervalDescriptor) return;
    const intervalSeconds = Number(interval);
    let error: string | null = null;
    if (interval.trim() === "" || !Number.isFinite(intervalSeconds)) {
      error = `${intervalDescriptor.label} must be a number.`;
    } else if (
      intervalDescriptor.type === "integer" &&
      !Number.isInteger(intervalSeconds)
    ) {
      error = `${intervalDescriptor.label} must be a whole number.`;
    } else if (
      intervalDescriptor.min != null &&
      intervalSeconds < intervalDescriptor.min
    ) {
      error = `${intervalDescriptor.label} must be at least ${intervalDescriptor.min}.`;
    } else if (
      intervalDescriptor.max != null &&
      intervalSeconds > intervalDescriptor.max
    ) {
      error = `${intervalDescriptor.label} must be at most ${intervalDescriptor.max}.`;
    }
    if (error) {
      setFeedback({ kind: "error", message: error });
      return;
    }
    void submit({
      type: "set_reporting_interval",
      arguments: { interval_s: intervalSeconds },
    });
  }

  const advertisedCommandCount = capabilities
    ? Object.keys(capabilities.commands).length
    : 0;

  return (
    <section className="panel control-panel">
      <div className="section-header">
        <h2 className="section-title">Device control</h2>
        <span className="section-meta">MQTT · QoS 1</span>
      </div>
      {!capabilities ? (
        <div className="control-empty">
          Controls are hidden until this device advertises its capabilities.
        </div>
      ) : advertisedCommandCount === 0 ? (
        <div className="control-empty">No remote controls advertised.</div>
      ) : (
        <div className="control-body">
          {capabilities.commands.set_led ? (
            <div className="control-row">
              <span className="control-label">
                {capabilities.commands.set_led.label}
              </span>
              <div className="control-actions">
                <button
                  className="button button-secondary"
                  disabled={submitting}
                  onClick={() =>
                    void submit({ type: "set_led", arguments: { on: true } })
                  }
                  type="button"
                >
                  On
                </button>
                <button
                  className="button button-secondary"
                  disabled={submitting}
                  onClick={() =>
                    void submit({ type: "set_led", arguments: { on: false } })
                  }
                  type="button"
                >
                  Off
                </button>
              </div>
            </div>
          ) : null}

          {intervalCommand && intervalDescriptor ? (
            <div className="control-row">
              <label className="control-label" htmlFor="reporting-interval">
                <span>{intervalCommand.label}</span>
                <small>{intervalDescriptor.label}</small>
              </label>
              <div className="control-actions">
                <div className="input-with-unit">
                  <input
                    className="control-input mono"
                    disabled={submitting}
                    id="reporting-interval"
                    max={intervalDescriptor.max ?? undefined}
                    min={intervalDescriptor.min ?? undefined}
                    onChange={(event) => setInterval(event.target.value)}
                    step={intervalDescriptor.type === "integer" ? 1 : "any"}
                    type="number"
                    value={interval}
                  />
                  {intervalDescriptor.unit ? (
                    <span>{intervalDescriptor.unit}</span>
                  ) : null}
                </div>
                <button
                  className="button button-secondary"
                  disabled={submitting}
                  onClick={applyInterval}
                  type="button"
                >
                  Apply
                </button>
              </div>
            </div>
          ) : null}

          {capabilities.commands.request_diagnostics ? (
            <div className="control-row">
              <span className="control-label">Device state</span>
              <button
                className="button button-secondary"
                disabled={submitting}
                onClick={() =>
                  void submit({ type: "request_diagnostics", arguments: {} })
                }
                type="button"
              >
                {capabilities.commands.request_diagnostics.label}
              </button>
            </div>
          ) : null}

          <div
            aria-live="polite"
            className={`control-feedback${visibleFeedback ? ` control-feedback-${visibleFeedback.kind}` : ""}`}
          >
            {submitting
              ? "Submitting command…"
              : visibleFeedback?.message ??
                "Commands remain pending until the device acknowledges them."}
          </div>
        </div>
      )}
    </section>
  );
}
