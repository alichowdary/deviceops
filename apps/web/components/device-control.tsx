"use client";

import { useState } from "react";

import type { CommandRequest, DeviceCommand } from "@/lib/types";


interface Feedback {
  kind: "pending" | "success" | "error";
  message: string;
}

export function DeviceControl({
  commands,
  submitCommand,
}: {
  commands: DeviceCommand[];
  submitCommand: (request: CommandRequest) => Promise<DeviceCommand>;
}) {
  const [interval, setInterval] = useState("5");
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
              ? `Command ${submittedCommand.command_id.slice(0, 8)} failed${typeof submittedCommand.result?.error === "string" ? `: ${submittedCommand.result.error}` : "."}`
              : `Command ${submittedCommand.command_id.slice(0, 8)} succeeded.`,
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
        message: `Command ${command.command_id.slice(0, 8)} accepted; awaiting device acknowledgement.`,
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
    const intervalSeconds = Number(interval);
    if (!Number.isFinite(intervalSeconds) || intervalSeconds < 1 || intervalSeconds > 60) {
      setFeedback({
        kind: "error",
        message: "Reporting interval must be between 1 and 60 seconds.",
      });
      return;
    }
    void submit({
      type: "set_reporting_interval",
      arguments: { interval_s: intervalSeconds },
    });
  }

  return (
    <section className="panel control-panel">
      <div className="section-header">
        <h2 className="section-title">Device control</h2>
        <span className="section-meta">MQTT · QoS 1</span>
      </div>
      <div className="control-body">
        <div className="control-row">
          <span className="control-label">LED state</span>
          <div className="control-actions">
            <button
              className="button button-secondary"
              disabled={submitting}
              onClick={() => void submit({ type: "set_led", arguments: { on: true } })}
              type="button"
            >
              LED on
            </button>
            <button
              className="button button-secondary"
              disabled={submitting}
              onClick={() => void submit({ type: "set_led", arguments: { on: false } })}
              type="button"
            >
              LED off
            </button>
          </div>
        </div>
        <div className="control-row">
          <label className="control-label" htmlFor="reporting-interval">
            Reporting interval
          </label>
          <div className="control-actions">
            <div className="input-with-unit">
              <input
                className="control-input mono"
                disabled={submitting}
                id="reporting-interval"
                max="60"
                min="1"
                onChange={(event) => setInterval(event.target.value)}
                step="1"
                type="number"
                value={interval}
              />
              <span>s</span>
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
            Request diagnostics
          </button>
        </div>
        <div
          aria-live="polite"
          className={`control-feedback${visibleFeedback ? ` control-feedback-${visibleFeedback.kind}` : ""}`}
        >
          {submitting ? "Submitting command…" : visibleFeedback?.message ?? "Commands remain pending until the device acknowledges them."}
        </div>
      </div>
    </section>
  );
}
