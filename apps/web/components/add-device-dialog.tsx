"use client";

import { Check, Copy, LoaderCircle } from "lucide-react";
import { useState } from "react";

import { apiPost } from "@/lib/api";
import type { Device, DeviceRegistration } from "@/lib/types";

type CopiedField = "device_id" | "device_secret";

export function AddDeviceDialog({
  token,
  onClose,
  onRegistered,
  onUnauthorized,
}: {
  token: string;
  onClose: () => void;
  onRegistered: (device: Device) => void;
  onUnauthorized: () => void;
}) {
  const [credentials, setCredentials] = useState<DeviceRegistration | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [saved, setSaved] = useState(false);
  const [copiedField, setCopiedField] = useState<CopiedField | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function registerDevice() {
    if (submitting || credentials) return;
    setSubmitting(true);
    setError(null);
    try {
      const registration = await apiPost<DeviceRegistration>(
        "/api/devices",
        {},
        { token, onUnauthorized },
      );
      setCredentials(registration);
      onRegistered({
        device_id: registration.device_id,
        display_name: null,
        status: registration.status,
        first_seen_at: null,
        last_seen_at: null,
      });
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Device registration failed.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function copyCredential(field: CopiedField, value: string) {
    if (!navigator.clipboard) {
      setError("Clipboard access is unavailable. Select and copy the value manually.");
      return;
    }
    try {
      await navigator.clipboard.writeText(value);
      setCopiedField(field);
      setError(null);
    } catch {
      setError("Could not copy the value. Select and copy it manually.");
    }
  }

  function closeDialog() {
    if (credentials && !saved) return;
    setCredentials(null);
    setCopiedField(null);
    setSaved(false);
    setError(null);
    onClose();
  }

  return (
    <div className="dialog-backdrop">
      <section
        aria-describedby="add-device-description"
        aria-labelledby="add-device-title"
        aria-modal="true"
        className="add-device-dialog"
        onKeyDown={(event) => {
          if (event.key === "Escape" && (!credentials || saved)) closeDialog();
        }}
        role="dialog"
      >
        <header className="dialog-header">
          <div>
            <span className="state-eyebrow">
              {credentials ? "Registration complete" : "Fleet onboarding"}
            </span>
            <h2 id="add-device-title">
              {credentials ? "Save device credentials" : "Add device"}
            </h2>
          </div>
        </header>

        <div className="dialog-body">
          {credentials ? (
            <>
              <p className="dialog-warning" id="add-device-description">
                Save these credentials now. The device secret cannot be shown again
                after this dialog is closed.
              </p>

              <div className="credential-list">
                <div className="credential-row">
                  <div className="credential-heading">
                    <span>Device ID</span>
                    <button
                      aria-label="Copy device ID"
                      className="credential-copy"
                      onClick={() =>
                        void copyCredential("device_id", credentials.device_id)
                      }
                      type="button"
                    >
                      {copiedField === "device_id" ? (
                        <Check aria-hidden="true" size={13} />
                      ) : (
                        <Copy aria-hidden="true" size={13} />
                      )}
                      {copiedField === "device_id" ? "Copied" : "Copy"}
                    </button>
                  </div>
                  <code>{credentials.device_id}</code>
                </div>

                <div className="credential-row credential-secret">
                  <div className="credential-heading">
                    <span>
                      Device secret <strong>Shown only once</strong>
                    </span>
                    <button
                      aria-label="Copy device secret"
                      className="credential-copy"
                      onClick={() =>
                        void copyCredential(
                          "device_secret",
                          credentials.device_secret,
                        )
                      }
                      type="button"
                    >
                      {copiedField === "device_secret" ? (
                        <Check aria-hidden="true" size={13} />
                      ) : (
                        <Copy aria-hidden="true" size={13} />
                      )}
                      {copiedField === "device_secret" ? "Copied secret" : "Copy"}
                    </button>
                  </div>
                  <code>{credentials.device_secret}</code>
                </div>
              </div>

              <label className="credential-confirmation">
                <input
                  checked={saved}
                  onChange={(event) => setSaved(event.target.checked)}
                  type="checkbox"
                />
                I have saved these credentials
              </label>
            </>
          ) : (
            <>
              <p id="add-device-description">
                DeviceOps will generate a device ID and secret. Copy both into the
                device configuration before dismissing the credentials.
              </p>
              <p className="dialog-warning">
                The plaintext device secret is shown once and cannot be recovered
                later through DeviceOps.
              </p>
            </>
          )}

          <div aria-live="polite" className="dialog-error">
            {error}
          </div>
        </div>

        <footer className="dialog-footer">
          {credentials ? (
            <button
              className="button button-primary"
              disabled={!saved}
              onClick={closeDialog}
              type="button"
            >
              Done
            </button>
          ) : (
            <>
              <button
                className="button button-secondary"
                disabled={submitting}
                onClick={closeDialog}
                type="button"
              >
                Cancel
              </button>
              <button
                className="button button-primary"
                disabled={submitting}
                onClick={() => void registerDevice()}
                type="button"
              >
                {submitting ? (
                  <>
                    <LoaderCircle
                      aria-hidden="true"
                      className="icon-spin"
                      size={14}
                    />
                    Registering
                  </>
                ) : (
                  "Generate credentials"
                )}
              </button>
            </>
          )}
        </footer>
      </section>
    </div>
  );
}
