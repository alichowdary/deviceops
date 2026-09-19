"use client";

import { LoaderCircle, Pencil, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type { FormEvent } from "react";

import { apiDelete, apiPatch } from "@/lib/api";
import type { Device } from "@/lib/types";

export function DeviceManagementActions({
  device,
  token,
  onRenamed,
  onUnauthorized,
}: {
  device: Device;
  token: string;
  onRenamed: (device: Device) => void;
  onUnauthorized: () => void;
}) {
  const router = useRouter();
  const [dialog, setDialog] = useState<"rename" | "delete" | null>(null);
  const [displayName, setDisplayName] = useState(device.display_name ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function openRename() {
    setDisplayName(device.display_name ?? "");
    setError(null);
    setDialog("rename");
  }

  function closeDialog() {
    if (submitting) return;
    setError(null);
    setDialog(null);
  }

  async function renameDevice(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const updated = await apiPatch<Device>(
        `/api/devices/${encodeURIComponent(device.device_id)}`,
        { display_name: displayName.trim() || null },
        { token, onUnauthorized },
      );
      onRenamed(updated);
      setDialog(null);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "The device name could not be saved.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function deleteDevice() {
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await apiDelete(`/api/devices/${encodeURIComponent(device.device_id)}`, {
        token,
        onUnauthorized,
      });
      router.replace("/fleet");
      router.refresh();
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "The device could not be deleted.",
      );
      setSubmitting(false);
    }
  }

  return (
    <>
      <button className="button button-secondary" onClick={openRename} type="button">
        <Pencil aria-hidden="true" size={13} />
        Rename
      </button>
      <button
        className="button button-danger"
        onClick={() => {
          setError(null);
          setDialog("delete");
        }}
        type="button"
      >
        <Trash2 aria-hidden="true" size={13} />
        Delete device
      </button>

      {dialog === "rename" ? (
        <div className="dialog-backdrop">
          <section
            aria-describedby="rename-device-description"
            aria-labelledby="rename-device-title"
            aria-modal="true"
            className="add-device-dialog device-management-dialog"
            onKeyDown={(event) => {
              if (event.key === "Escape") closeDialog();
            }}
            role="dialog"
          >
            <header className="dialog-header">
              <span className="state-eyebrow">Device identity</span>
              <h2 id="rename-device-title">Rename device</h2>
            </header>
            <form onSubmit={(event) => void renameDevice(event)}>
              <div className="dialog-body">
                <p id="rename-device-description">
                  Add an optional friendly name. The immutable device ID remains{" "}
                  <span className="mono">{device.device_id}</span>.
                </p>
                <label className="dialog-field">
                  <span>Display name</span>
                  <input
                    autoFocus
                    disabled={submitting}
                    maxLength={80}
                    onChange={(event) => setDisplayName(event.target.value)}
                    placeholder="e.g. Workshop sensor"
                    value={displayName}
                  />
                </label>
                <div aria-live="polite" className="dialog-error">{error}</div>
              </div>
              <footer className="dialog-footer">
                <button
                  className="button button-secondary"
                  disabled={submitting}
                  onClick={closeDialog}
                  type="button"
                >
                  Cancel
                </button>
                <button className="button button-primary" disabled={submitting} type="submit">
                  {submitting ? (
                    <>
                      <LoaderCircle aria-hidden="true" className="icon-spin" size={14} />
                      Saving
                    </>
                  ) : (
                    "Save name"
                  )}
                </button>
              </footer>
            </form>
          </section>
        </div>
      ) : null}

      {dialog === "delete" ? (
        <div className="dialog-backdrop">
          <section
            aria-describedby="delete-device-description"
            aria-labelledby="delete-device-title"
            aria-modal="true"
            className="add-device-dialog device-management-dialog"
            onKeyDown={(event) => {
              if (event.key === "Escape") closeDialog();
            }}
            role="alertdialog"
          >
            <header className="dialog-header">
              <span className="state-eyebrow danger-text">Permanent action</span>
              <h2 id="delete-device-title">Delete device?</h2>
            </header>
            <div className="dialog-body">
              <p className="dialog-danger" id="delete-device-description">
                This permanently removes the device registration, telemetry,
                commands, events, alert rules, and alert history for{" "}
                <strong>{device.display_name ?? device.device_id}</strong>.
              </p>
              <p>
                The stable ID <span className="mono">{device.device_id}</span> and
                its existing credentials will no longer be accepted.
              </p>
              <div aria-live="polite" className="dialog-error">{error}</div>
            </div>
            <footer className="dialog-footer">
              <button
                className="button button-secondary"
                disabled={submitting}
                onClick={closeDialog}
                type="button"
              >
                Cancel
              </button>
              <button
                className="button button-danger button-danger-solid"
                disabled={submitting}
                onClick={() => void deleteDevice()}
                type="button"
              >
                {submitting ? (
                  <>
                    <LoaderCircle aria-hidden="true" className="icon-spin" size={14} />
                    Deleting
                  </>
                ) : (
                  <>
                    <Trash2 aria-hidden="true" size={13} />
                    Permanently delete
                  </>
                )}
              </button>
            </footer>
          </section>
        </div>
      ) : null}
    </>
  );
}
