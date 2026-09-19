"use client";

import {
  Activity,
  ArrowRight,
  BellRing,
  Boxes,
  Braces,
  CheckCircle2,
  Cpu,
  RadioTower,
  ShieldCheck,
  TerminalSquare,
} from "lucide-react";
import Link from "next/link";

import { useAuth } from "@/components/auth-provider";

const capabilities = [
  {
    icon: Activity,
    title: "Realtime fleet state",
    description: "REST snapshots stay current through authenticated WebSocket deltas.",
  },
  {
    icon: Braces,
    title: "Capability-driven UI",
    description: "Each device declares the metrics, charts, and controls it supports.",
  },
  {
    icon: ShieldCheck,
    title: "Signed device messages",
    description: "Versioned MQTT envelopes authenticate telemetry, status, and acknowledgements.",
  },
  {
    icon: TerminalSquare,
    title: "Acknowledged commands",
    description: "Remote operations stay pending until the device commits a success or failure.",
  },
  {
    icon: BellRing,
    title: "Events and alerts",
    description: "Persistent activity, metric thresholds, and offline conditions share one console.",
  },
  {
    icon: Cpu,
    title: "Simulator and ESP32",
    description: "Exercise the same contract with Python profiles or ESP32-S3 reference firmware.",
  },
] as const;

const steps = [
  ["01", "Create an account", "Start an isolated operator workspace."],
  ["02", "Register a device", "Receive a device ID and one-time secret."],
  ["03", "Configure an implementation", "Run the simulator or flash a compatible ESP32."],
  ["04", "Operate live", "Watch capabilities, telemetry, events, alerts, and controls appear."],
] as const;

export default function LandingPage() {
  const { initialized, user } = useAuth();
  const consoleHref = user ? "/fleet" : "/login";
  const consoleLabel = initialized && user ? "Open console" : "Try DeviceOps";

  return (
    <div className="landing-shell">
      <header className="landing-header">
        <Link className="landing-brand" href="/">
          <span className="product-name">DeviceOps</span>
          <span className="product-context">IoT fleet operations</span>
        </Link>
        <nav aria-label="Public navigation" className="landing-nav">
          <a href="#architecture">Architecture</a>
          <a href="#how-it-works">How it works</a>
          <Link className="button button-secondary" href={consoleHref}>
            {initialized && user ? "Open console" : "Sign in"}
          </Link>
        </nav>
      </header>

      <main>
        <section className="landing-hero">
          <div className="landing-hero-copy">
            <span className="state-eyebrow">Heterogeneous device operations</span>
            <h1>Operate IoT devices from one console.</h1>
            <p>
              Devices publish signed MQTT telemetry. FastAPI persists and evaluates
              it, while Next.js combines REST snapshots with realtime WebSocket
              updates. Capability manifests let every device describe its own
              metrics and controls.
            </p>
            <div className="landing-actions">
              <Link className="button button-primary" href={consoleHref}>
                {consoleLabel}
                <ArrowRight aria-hidden="true" size={14} />
              </Link>
              <a className="button button-secondary" href="#architecture">
                View architecture
              </a>
            </div>
          </div>

          <div aria-label="Example fleet state" className="landing-console-preview">
            <div className="preview-titlebar">
              <span>Fleet / live inventory</span>
              <span className="preview-live">
                <span aria-hidden="true" /> Live
              </span>
            </div>
            <div className="preview-summary">
              <div><strong>3</strong><span>Devices</span></div>
              <div><strong className="health-ok">2</strong><span>Online</span></div>
              <div><strong className="health-degraded">1</strong><span>Offline</span></div>
            </div>
            <div className="preview-device-row">
              <span className="status-dot status-dot-online" />
              <span><strong>Workshop sensor</strong><small>Temperature · humidity · pressure</small></span>
              <code>online</code>
            </div>
            <div className="preview-device-row">
              <span className="status-dot status-dot-online" />
              <span><strong>Portable monitor</strong><small>Battery · ambient light · motion</small></span>
              <code>online</code>
            </div>
            <div className="preview-event">
              <CheckCircle2 aria-hidden="true" size={13} />
              Command acknowledged · reporting interval updated
            </div>
          </div>
        </section>

        <section aria-labelledby="capabilities-title" className="landing-section">
          <div className="landing-section-heading">
            <span className="state-eyebrow">Implemented product</span>
            <h2 id="capabilities-title">Built around the operational evidence</h2>
            <p>Monitor state, inspect history, and act without bypassing the device protocol.</p>
          </div>
          <div className="landing-capability-grid">
            {capabilities.map(({ icon: Icon, title, description }) => (
              <article className="landing-capability" key={title}>
                <Icon aria-hidden="true" size={16} strokeWidth={1.7} />
                <h3>{title}</h3>
                <p>{description}</p>
              </article>
            ))}
          </div>
        </section>

        <section
          aria-labelledby="architecture-title"
          className="landing-section landing-architecture"
          id="architecture"
        >
          <div className="landing-section-heading">
            <span className="state-eyebrow">System path</span>
            <h2 id="architecture-title">One versioned path from device to operator</h2>
          </div>
          <div className="architecture-board">
            <div className="architecture-flow">
              <div className="architecture-node"><Cpu size={15} />Device / ESP32-S3</div>
              <span aria-hidden="true">→</span>
              <div className="architecture-node"><RadioTower size={15} />MQTT / Mosquitto</div>
              <span aria-hidden="true">→</span>
              <div className="architecture-node architecture-node-core"><Boxes size={15} />FastAPI</div>
              <span aria-hidden="true">→</span>
              <div className="architecture-node">PostgreSQL</div>
            </div>
            <div className="architecture-client-flow">
              <span>Next.js console</span>
              <span aria-hidden="true">←</span>
              <code>REST + WebSocket</code>
              <span aria-hidden="true">←</span>
              <span>FastAPI</span>
            </div>
            <p>
              The browser communicates only with FastAPI. MQTT remains between
              devices, Mosquitto, and the backend ingestion process.
            </p>
          </div>
          <div className="technology-list" aria-label="Technology stack">
            {[
              "ESP32-S3",
              "Python simulator",
              "MQTT / Mosquitto",
              "FastAPI",
              "PostgreSQL",
              "Next.js / TypeScript",
              "WebSockets",
              "Docker",
            ].map((technology) => <span key={technology}>{technology}</span>)}
          </div>
        </section>

        <section
          aria-labelledby="how-title"
          className="landing-section"
          id="how-it-works"
        >
          <div className="landing-section-heading">
            <span className="state-eyebrow">How it works</span>
            <h2 id="how-title">From registration to live operations</h2>
            <p>
              Compatible devices follow a versioned MQTT contract and sign
              application-layer messages without exposing their secret.
            </p>
          </div>
          <ol className="landing-steps">
            {steps.map(([number, title, description]) => (
              <li key={number}>
                <code>{number}</code>
                <div><h3>{title}</h3><p>{description}</p></div>
              </li>
            ))}
          </ol>
        </section>

        <section className="landing-final-cta">
          <div>
            <span className="state-eyebrow">DeviceOps console</span>
            <h2>Connect a simulator or physical ESP32.</h2>
            <p>Register a device, save its credentials once, and follow the signed-in setup guide.</p>
          </div>
          <Link className="button button-primary" href={consoleHref}>
            {consoleLabel}<ArrowRight aria-hidden="true" size={14} />
          </Link>
        </section>
      </main>

      <footer className="landing-footer">
        <span>DeviceOps</span>
        <span>MQTT protocol v1 · REST snapshots · WebSocket deltas</span>
      </footer>
    </div>
  );
}
