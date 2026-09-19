import { AlertTriangle, CheckCircle2, Cpu, RadioTower } from "lucide-react";
import Link from "next/link";

export default function GettingStartedPage() {
  return (
    <>
      <header className="page-header">
        <div>
          <h1 className="page-title">Getting Started</h1>
          <p className="page-description">Connect a simulator or ESP32 reference device</p>
        </div>
        <Link className="button button-primary" href="/fleet">Open Fleet</Link>
      </header>

      <div className="setup-stack">
        <section className="panel setup-section">
          <div className="setup-step-heading">
            <span>1</span>
            <div><h2>Register a device</h2><p>Create its identity before configuring hardware or a simulator.</p></div>
          </div>
          <ol className="setup-list">
            <li>Open <Link href="/fleet">Fleet</Link> and select <strong>Add device</strong>.</li>
            <li>Generate the device ID and one-time device secret.</li>
            <li>Save both values before closing the credential dialog.</li>
          </ol>
          <div className="setup-callout setup-callout-warning">
            <AlertTriangle aria-hidden="true" size={15} />
            The plaintext secret cannot be recovered. It is never placed in an onboarding URL or saved by this page.
          </div>
        </section>

        <section className="panel setup-section">
          <div className="setup-step-heading">
            <span>2</span>
            <div><h2>Choose a device implementation</h2><p>Both options use the same signed protocol and capability manifest.</p></div>
          </div>
          <div className="setup-options">
            <article className="setup-option">
              <div className="setup-option-title"><RadioTower aria-hidden="true" size={16} /><h3>Python simulator</h3></div>
              <p>Run the default temperature and battery profile from PowerShell:</p>
              <pre><code>{`cd simulator
.\.venv\Scripts\Activate.ps1
$env:DEVICEOPS_DEVICE_SECRET = Read-Host "Registered device secret"
python -m device_simulator --device-id <device-id>
Remove-Item Env:DEVICEOPS_DEVICE_SECRET`}</code></pre>
              <p>
                The default profile advertises temperature, battery, LED,
                reporting interval, and diagnostics. To exercise ambient light,
                motion, and a smaller command surface, add:
              </p>
              <pre><code>--profile portable-sensor</code></pre>
            </article>

            <article className="setup-option">
              <div className="setup-option-title"><Cpu aria-hidden="true" size={16} /><h3>ESP32-S3 reference firmware</h3></div>
              <p>
                The PlatformIO project is under <code>firmware/esp32</code>. Copy
                <code> include\secrets.example.h</code> to the ignored local
                <code> include\secrets.h</code>, then set Wi-Fi, broker, device ID,
                and secret values as described in its README.
              </p>
              <pre><code>{`cd firmware\esp32
pio run
pio run --target upload
pio device monitor --baud 115200`}</code></pre>
              <p>
                The BME280 reference wiring uses SDA GPIO 8 and SCL GPIO 9. The
                verified board also advertises WS2812 LED command support.
              </p>
            </article>
          </div>
        </section>

        <section className="panel setup-section">
          <div className="setup-step-heading">
            <span>3</span>
            <div><h2>Watch the console populate</h2><p>Device evidence appears after authenticated messages commit.</p></div>
          </div>
          <div className="setup-outcomes">
            {[
              "Online status and last-seen timestamps",
              "Capability-driven metrics and charts",
              "Controls for advertised commands",
              "Persistent fleet Events",
              "Threshold and offline Alerts",
            ].map((outcome) => (
              <div key={outcome}><CheckCircle2 aria-hidden="true" size={14} />{outcome}</div>
            ))}
          </div>
        </section>

        <section className="panel setup-section">
          <div className="setup-step-heading">
            <span>4</span>
            <div><h2>Understand retention</h2><p>Display limits and database retention are separate.</p></div>
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
