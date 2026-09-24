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
const protocolGuide =
  "https://github.com/alichowdary/deviceops/blob/main/contracts/mqtt.md";

export default function GettingStartedPage() {
  return (
    <>
      <header className="page-header">
        <div>
          <h1 className="page-title">Getting Started</h1>
          <p className="page-description">Connect your first DeviceOps device</p>
        </div>
        <Link className="button button-primary" href="/fleet">Open Fleet</Link>
      </header>

      <div className="setup-stack">
        <section className="panel setup-section setup-intro">
          <span className="state-eyebrow">Your first connection</span>
          <h2>From registration to a live device in three steps</h2>
          <ol className="setup-overview">
            <li><span>1</span>Register a DeviceOps device</li>
            <li><span>2</span>Choose and configure a connection path</li>
            <li><span>3</span>Confirm the device in Fleet</li>
          </ol>
        </section>

        <section className="panel setup-section">
          <div className="setup-step-heading">
            <span>1</span>
            <div><h2>Register a device</h2><p>Create its identity before configuring a simulator or hardware.</p></div>
          </div>
          <ol className="setup-list">
            <li>Open <Link href="/fleet">Fleet</Link> and select <strong>Add device</strong>.</li>
            <li>Enter a name and generate the device ID and one-time device secret.</li>
            <li>Save both values before closing the credential dialog.</li>
          </ol>
          <div className="setup-callout setup-callout-warning">
            <AlertTriangle aria-hidden="true" size={15} />
            <span><strong>Save the secret now.</strong> The plaintext secret cannot be recovered. It is never placed in an onboarding URL or saved by this page.</span>
          </div>
        </section>

        <section className="panel setup-section">
          <div className="setup-step-heading">
            <span>2</span>
            <div><h2>Choose a connection path</h2><p>Start quickly with software, or connect the reference hardware.</p></div>
          </div>
          <div className="setup-options">
            <article className="setup-option setup-option-recommended">
              <div className="setup-option-title"><RadioTower aria-hidden="true" size={16} /><h3>Python simulator</h3></div>
              <div className="setup-tags"><span>Quickest start</span><span>Easiest</span><span>No hardware</span></div>
              <p>
                The quickest way to try DeviceOps. Run this software implementation
                on your computer to see live readings, online state, commands, events,
                and alerts without buying or wiring hardware.
              </p>
              <ul className="setup-checklist">
                <li>Install Python and create the simulator environment</li>
                <li>Add the registered device ID and one-time secret</li>
                <li>Connect to the production MQTT service and start the simulator</li>
              </ul>
              <a className="setup-guide-link" href={simulatorGuide} rel="noreferrer" target="_blank">
                Open Python simulator instructions<ArrowUpRight aria-hidden="true" size={13} />
              </a>
            </article>

            <article className="setup-option">
              <div className="setup-option-title"><Cpu aria-hidden="true" size={16} /><h3>Physical hardware</h3></div>
              <div className="setup-tags"><span>Verified reference</span><span>DeviceOps v1</span></div>
              <p>
                The verified reference build uses an ESP32-S3 with a BME280. Other
                capable devices can integrate by implementing the DeviceOps v1
                protocol. Compatibility is not automatic.
              </p>
              <ul className="setup-checklist">
                <li>Install PlatformIO and prepare the ESP32-S3 + BME280</li>
                <li>Configure Wi-Fi, MQTT, device ID, and device secret locally</li>
                <li>Build, flash, and monitor the firmware</li>
              </ul>
              <a className="setup-guide-link" href={esp32Guide} rel="noreferrer" target="_blank">
                Open ESP32-S3 instructions<ArrowUpRight aria-hidden="true" size={13} />
              </a>
              <p className="setup-protocol-note">
                Other capable devices may integrate by implementing the documented
                DeviceOps v1 protocol. Compatibility is not automatic.{" "}
                <a href={protocolGuide} rel="noreferrer" target="_blank">
                  View protocol documentation<ArrowUpRight aria-hidden="true" size={12} />
                </a>
              </p>
            </article>
          </div>
        </section>

        <section className="panel setup-section">
          <div className="setup-step-heading">
            <span>3</span>
            <div><h2>Confirm the connection in Fleet</h2><p>Once connected, your device begins building an operational record.</p></div>
          </div>
          <div className="setup-outcomes">
            {[
              "Online status and last-seen timestamps",
              "Live metrics and historical charts",
              "Controls for supported commands",
              "Persistent device activity",
              "Threshold and offline alerts",
            ].map((outcome) => (
              <div key={outcome}><CheckCircle2 aria-hidden="true" size={14} />{outcome}</div>
            ))}
          </div>
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
