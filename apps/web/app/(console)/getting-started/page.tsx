import {
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  Cpu,
  RadioTower,
} from "lucide-react";
import Link from "next/link";

const simulatorGuide =
  "https://github.com/alichowdary/deviceops/blob/main/simulator/README.md";
const esp32Guide =
  "https://github.com/alichowdary/deviceops/blob/main/firmware/esp32/README.md";
const localGuide =
  "https://github.com/alichowdary/deviceops#local-development";
const protocolGuide =
  "https://github.com/alichowdary/deviceops/blob/main/contracts/mqtt.md";

const simulatorCommand = `cd simulator
.\\.venv\\Scripts\\Activate.ps1
$env:DEVICEOPS_DEVICE_SECRET = Read-Host "Registered device secret"
python -m device_simulator --device-id <registered-device-id>
Remove-Item Env:DEVICEOPS_DEVICE_SECRET`;

export default function GettingStartedPage() {
  return (
    <>
      <header className="page-header">
        <div>
          <h1 className="page-title">Getting Started</h1>
          <p className="page-description">Connect your first device to hosted DeviceOps</p>
        </div>
        <Link className="button button-primary" href="/fleet">Open Fleet</Link>
      </header>

      <div className="setup-stack">
        <section className="panel setup-section setup-intro">
          <span className="state-eyebrow">Your first hosted connection</span>
          <h2>From registration to live telemetry</h2>
          <ol className="setup-overview">
            <li><span>1</span>Register</li>
            <li><span>2</span>Save credentials</li>
            <li><span>3</span>Connect</li>
            <li><span>4</span>Inspect</li>
            <li><span>5</span>Operate</li>
          </ol>
          <p>
            DeviceOps is a hosted fleet platform. Register here, then connect the
            simulator or compatible hardware directly to mqtt.deviceops.net. Hosted
            DeviceOps supplies the backend and provisioned broker access.
          </p>
        </section>

        <section className="panel setup-section">
          <div className="setup-step-heading">
            <span>1</span>
            <div><h2>Register a device in Fleet</h2><p>Create its hosted identity before configuring software or hardware.</p></div>
          </div>
          <ol className="setup-list">
            <li>Open <Link href="/fleet">Fleet</Link> and select <strong>Add device</strong>.</li>
            <li>Generate the device registration.</li>
            <li>Keep the credential dialog open until both returned values are saved.</li>
          </ol>
          <p className="setup-protocol-note">
            After registration, open the device from Fleet and use <strong>Rename</strong> on Device Detail if you want a friendly display name.
          </p>
        </section>

        <section className="panel setup-section">
          <div className="setup-step-heading">
            <span>2</span>
            <div><h2>Save the Device ID and one-time secret</h2><p>These two values configure every normal hosted connection.</p></div>
          </div>
          <div className="setup-callout setup-callout-warning">
            <AlertTriangle aria-hidden="true" size={15} />
            <span><strong>Save the secret now.</strong> It is shown once, cannot be recovered, and is never stored by this page. It is the only DeviceOps device secret; no separate MQTT credential is required.</span>
          </div>
        </section>

        <section className="panel setup-section">
          <div className="setup-step-heading">
            <span>3</span>
            <div><h2>Connect software or hardware</h2><p>The hosted Python simulator is the recommended quick start.</p></div>
          </div>
          <div className="setup-options">
            <article className="setup-option setup-option-recommended">
              <div className="setup-option-title"><RadioTower aria-hidden="true" size={16} /><h3>Python simulator</h3></div>
              <div className="setup-tags"><span>Recommended</span><span>No hardware</span></div>
              <p>With the simulator environment installed, run:</p>
              <pre><code>{simulatorCommand}</code></pre>
              <p className="setup-protocol-note">
                Want to see the capability-driven UI adapt? Try <code>--profile portable-sensor</code> or <code>--profile air-quality</code> after the default run.
              </p>
              <p>
                Hosted mode automatically uses mqtt.deviceops.net:443, verified TLS,
                the device ID as its MQTT identity, and a broker password derived
                locally from the DeviceOps secret.
              </p>
              <a className="setup-guide-link" href={simulatorGuide} rel="noreferrer" target="_blank">
                Open simulator install and profile guide<ArrowUpRight aria-hidden="true" size={13} />
              </a>
            </article>

            <article className="setup-option">
              <div className="setup-option-title"><Cpu aria-hidden="true" size={16} /><h3>ESP32 reference hardware</h3></div>
              <div className="setup-tags"><span>Verified reference</span><span>DeviceOps v1</span></div>
              <ol className="setup-checklist">
                <li>Copy <code>include/secrets.example.h</code> to the ignored <code>include/secrets.h</code>.</li>
                <li>Enter Wi-Fi credentials, Device ID, and the one-time DeviceOps secret.</li>
                <li>Build and upload with PlatformIO.</li>
              </ol>
              <p>
                The firmware connects to hosted DeviceOps automatically. There is no
                second MQTT password to enter.
              </p>
              <a className="setup-guide-link" href={esp32Guide} rel="noreferrer" target="_blank">
                Open ESP32-S3 instructions<ArrowUpRight aria-hidden="true" size={13} />
              </a>
              <p className="setup-protocol-note">
                Custom firmware owns its sensor drivers, wiring, sampling, units, and
                capability manifest. DeviceOps handles the hosted protocol and fleet
                workflow. <a href={protocolGuide} rel="noreferrer" target="_blank">View protocol documentation<ArrowUpRight aria-hidden="true" size={12} /></a>
              </p>
            </article>
          </div>
        </section>

        <section className="panel setup-section">
          <div className="setup-step-heading">
            <span>4</span>
            <div><h2>Confirm the device is Online</h2><p>Open its Fleet row and inspect the operational record.</p></div>
          </div>
          <div className="setup-outcomes">
            {["Online status and last-seen timestamps", "Current values and recent samples", "Numeric telemetry charts", "Capability-driven controls"].map((outcome) => (
              <div key={outcome}><CheckCircle2 aria-hidden="true" size={14} />{outcome}</div>
            ))}
          </div>
        </section>

        <section className="panel setup-section">
          <div className="setup-step-heading">
            <span>5</span>
            <div><h2>Try the supported operations</h2><p>Available controls and alert metrics come from the device capability manifest.</p></div>
          </div>
          <div className="setup-outcomes">
            {["Send an applicable command and wait for its acknowledgement", "Review the resulting fleet Event", "Create a metric-threshold or offline alert rule"].map((outcome) => (
              <div key={outcome}><CheckCircle2 aria-hidden="true" size={14} />{outcome}</div>
            ))}
          </div>
        </section>

        <section className="panel setup-section setup-secondary">
          <div className="setup-step-heading">
            <span>i</span>
            <div><h2>Local development</h2><p>A secondary path for contributors reproducing the repository stack.</p></div>
          </div>
          <p>
            Docker Compose runs local PostgreSQL and anonymous Mosquitto at
            localhost:1883. Start the local FastAPI and Next.js services, register a
            device in that local console, then run the simulator with <code>--local</code>.
            These steps are separate from normal hosted onboarding.
          </p>
          <a className="setup-guide-link" href={localGuide} rel="noreferrer" target="_blank">
            Open local development instructions<ArrowUpRight aria-hidden="true" size={13} />
          </a>
        </section>

        <section className="panel setup-section setup-secondary">
          <div className="setup-step-heading">
            <span>i</span>
            <div><h2>Data retention</h2><p>Display limits and database retention are separate.</p></div>
          </div>
          <dl className="retention-grid">
            <div><dt>Telemetry</dt><dd>3 rolling days</dd></div>
            <div><dt>Device Events</dt><dd>3 rolling days</dd></div>
            <div><dt>Recent Samples</dt><dd>Newest 10 shown</dd></div>
            <div><dt>Commands and alerts</dt><dd>Currently retained</dd></div>
          </dl>
        </section>
      </div>
    </>
  );
}
