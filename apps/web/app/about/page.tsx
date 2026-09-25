"use client";

import {
  Activity,
  ArrowRight,
  BellRing,
  Boxes,
  Braces,
  Cpu,
  Database,
  RadioTower,
  ShieldCheck,
  TerminalSquare,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";

import { useAuth } from "@/components/auth-provider";

const operationalAreas = [
  {
    icon: Activity,
    title: "Telemetry and history",
    description: "Current readings and retained history make device behavior inspectable over time.",
  },
  {
    icon: RadioTower,
    title: "Online and offline lifecycle",
    description: "Presence and last-seen evidence show whether each device is available.",
  },
  {
    icon: TerminalSquare,
    title: "Commands and acknowledgements",
    description: "Commands remain pending until the device commits a success or failure acknowledgement.",
  },
  {
    icon: BellRing,
    title: "Events and alerts",
    description: "Persistent activity records sit alongside threshold and offline alert lifecycles.",
  },
] as const;

export default function AboutPage() {
  const { initialized, user } = useAuth();
  const consoleHref = user ? "/fleet" : "/login";
  const consoleLabel = initialized && user ? "Open console" : "Create account";
  const gettingStartedHref = user ? "/getting-started" : "/login";

  return (
    <div className="landing-shell about-page">
      <header className="landing-header">
        <Link className="landing-brand" href="/">
          <span className="product-name">DeviceOps</span>
          <span className="product-context">IoT fleet operations</span>
        </Link>
        <nav aria-label="Public navigation" className="landing-nav">
          <Link aria-current="page" href="/about">About</Link>
          <Link className="button button-secondary" href={consoleHref}>
            {initialized && user ? "Open console" : "Sign in"}
          </Link>
        </nav>
      </header>

      <main>
        <div className="about-introduction">
          <section className="about-hero landing-section">
            <span className="state-eyebrow">About DeviceOps</span>
            <h1>One console for devices that do different jobs.</h1>
            <p>
              DeviceOps is an IoT fleet management and observability platform. It
              gives operators a consistent way to monitor and control heterogeneous
              devices while allowing each device to expose its own metrics and controls.
            </p>
            <div className="landing-actions">
              <Link className="button button-primary" href={consoleHref}>
                {consoleLabel}<ArrowRight aria-hidden="true" size={14} />
              </Link>
              <Link className="button button-secondary" href={gettingStartedHref}>
                Get started
              </Link>
            </div>
          </section>
          <figure
            aria-labelledby="capability-console-title"
            className="about-product-evidence"
          >
            <figcaption className="landing-section-heading about-product-evidence-copy">
              <span className="state-eyebrow">Capability-driven console</span>
              <h2 id="capability-console-title">
                One device manifest, a UI built from its capabilities.
              </h2>
              <p>
                This production Air Sensor advertises its own telemetry and supported
                commands. DeviceOps renders the relevant values, numeric charts, and
                controls from that manifest without a device-specific frontend. The
                live view also records the device&apos;s successful diagnostics
                acknowledgement.
              </p>
            </figcaption>
            <div className="about-product-evidence-frame">
              <Image
                alt="Production DeviceOps Air Sensor view showing live online status, CO₂, VOC index, Occupied and Air quality values, two numeric charts, and a succeeded diagnostics command."
                height={840}
                sizes="(max-width: 780px) calc(100vw - 28px), 1180px"
                src="/images/air-sensor-capabilities.png"
                width={1918}
              />
            </div>
          </figure>
        </div>

        <section aria-labelledby="architecture-title" className="landing-section">
          <div className="landing-section-heading">
            <span className="state-eyebrow">Architecture</span>
            <h2 id="architecture-title">A deliberate path from device to operator</h2>
            <p>
              Device traffic is ingested, authenticated, committed, and then delivered
              to the browser through the application backend. Compatible devices
              implement the DeviceOps v1 protocol and advertise their own metrics
              and commands. In production the path is device or simulator →
              mqtt.deviceops.net → Fly-hosted Mosquitto → FastAPI → PostgreSQL →
              REST/WebSocket → Next.js console.
            </p>
          </div>
          <div className="architecture-board">
            <div className="architecture-flow">
              <div className="architecture-node"><Cpu size={15} />Device / simulator</div>
              <span aria-hidden="true">→</span>
              <div className="architecture-node"><RadioTower size={15} />mqtt.deviceops.net</div>
              <span aria-hidden="true">→</span>
              <div className="architecture-node"><RadioTower size={15} />Fly Mosquitto</div>
              <span aria-hidden="true">→</span>
              <div className="architecture-node architecture-node-core"><Boxes size={15} />FastAPI</div>
              <span aria-hidden="true">→</span>
              <div className="architecture-node"><Database size={15} />PostgreSQL</div>
            </div>
            <div className="architecture-client-flow">
              <span>Next.js console</span>
              <span aria-hidden="true">←</span>
              <code>REST + authenticated WebSocket</code>
              <span aria-hidden="true">←</span>
              <span>FastAPI</span>
            </div>
            <p>
              The browser never connects to MQTT directly. It loads snapshots and
              history through REST, then receives newly committed events over an
              authenticated WebSocket.
            </p>
          </div>
        </section>

        <section aria-labelledby="capability-title" className="landing-section about-split">
          <div className="landing-section-heading">
            <span className="state-eyebrow">Device capability model</span>
            <h2 id="capability-title">The device describes what it can do</h2>
          </div>
          <div className="about-copy-block">
            <Braces aria-hidden="true" size={18} />
            <p>
              Each compatible device advertises the metrics and commands it supports.
              The console renders those capabilities instead of hard-coding a single
              device type, so a sensor, portable monitor, or future implementation can
              share the same operational workflow without pretending to be identical.
              Device firmware still owns sensor drivers, wiring, sampling, units, and
              the decision about which compatible capabilities to advertise.
            </p>
          </div>
        </section>

        <section aria-labelledby="security-title" className="landing-section about-split">
          <div className="landing-section-heading">
            <span className="state-eyebrow">Security and ownership</span>
            <h2 id="security-title">User, device, and transport boundaries</h2>
          </div>
          <div className="about-copy-block">
            <ShieldCheck aria-hidden="true" size={18} />
            <p>
              User authentication protects the console, and device ownership keeps
              fleet data scoped to its operator. Registration issues a one-time device
              secret that cannot be recovered later. That one secret supplies key
              material for separate broker authentication and signed, versioned
              DeviceOps envelopes. Production MQTT uses verified TLS. Credentials and
              internal secrets are never shown on this page.
            </p>
          </div>
        </section>

        <section aria-labelledby="operations-title" className="landing-section">
          <div className="landing-section-heading">
            <span className="state-eyebrow">Operational behavior</span>
            <h2 id="operations-title">Evidence across the device lifecycle</h2>
          </div>
          <div className="landing-capability-grid about-operations-grid">
            {operationalAreas.map(({ icon: Icon, title, description }) => (
              <article className="landing-capability" key={title}>
                <Icon aria-hidden="true" size={16} strokeWidth={1.7} />
                <h3>{title}</h3>
                <p>{description}</p>
              </article>
            ))}
          </div>
        </section>

        <section aria-labelledby="implementations-title" className="landing-section about-detail-grid">
          <article>
            <span className="state-eyebrow">Implementations</span>
            <h2 id="implementations-title">Try software first or connect hardware</h2>
            <p>
              The Python simulator is one software implementation and provides
              selectable device profiles without physical hardware. The ESP32-S3 +
              BME280 build is the verified reference hardware implementation. Other
              capable devices can integrate by implementing the documented DeviceOps
              v1 protocol; compatibility is not automatic.
            </p>
          </article>
          <article>
            <span className="state-eyebrow">Production deployment</span>
            <h2>Hosted as a complete system</h2>
            <p>
              The production stack uses Vercel for the Next.js frontend, Fly.io for
              the FastAPI backend, Supabase PostgreSQL for persistence, and a
              DeviceOps-managed Mosquitto broker on Fly.io at
              mqtt.deviceops.net:443 with verified TLS.
            </p>
          </article>
        </section>

        <section className="landing-final-cta">
          <div>
            <span className="state-eyebrow">DeviceOps console</span>
            <h2>Connect your device to the hosted system.</h2>
            <p>
              Create an account, register a device, and connect the Python simulator,
              ESP32 reference firmware, or a compatible custom implementation. The
              repository&apos;s Docker stack remains available separately for local development.
            </p>
          </div>
          <div className="landing-actions about-final-actions">
            <Link className="button button-primary" href={consoleHref}>{consoleLabel}</Link>
            <Link className="button button-secondary" href={gettingStartedHref}>Get started</Link>
          </div>
        </section>
      </main>

      <footer className="landing-footer">
        <span>DeviceOps</span>
        <span>MQTT protocol v1 · REST snapshots · WebSocket updates</span>
      </footer>
    </div>
  );
}
