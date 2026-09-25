"use client";

import {
  Activity,
  ArrowRight,
  BellRing,
  CheckCircle2,
  TerminalSquare,
} from "lucide-react";
import Link from "next/link";

import { useAuth } from "@/components/auth-provider";

const productAreas = [
  {
    icon: Activity,
    title: "Monitor",
    description:
      "See which devices are online, inspect current sensor readings, and review recent history from one fleet view.",
  },
  {
    icon: TerminalSquare,
    title: "Control",
    description:
      "Send the commands each device supports and follow their progress until the device confirms the result.",
  },
  {
    icon: BellRing,
    title: "Respond",
    description:
      "Track device activity and create alerts for important readings or devices that go offline.",
  },
] as const;

export default function LandingPage() {
  const { initialized, user } = useAuth();
  const consoleHref = user ? "/fleet" : "/login";
  const consoleLabel = initialized && user ? "Open console" : "Create account";

  return (
    <div className="landing-shell">
      <header className="landing-header">
        <Link className="landing-brand" href="/">
          <span className="product-name">DeviceOps</span>
          <span className="product-context">IoT fleet operations</span>
        </Link>
        <nav aria-label="Public navigation" className="landing-nav">
          <Link href="/about">About</Link>
          <Link className="button button-secondary" href={consoleHref}>
            {initialized && user ? "Open console" : "Sign in"}
          </Link>
        </nav>
      </header>

      <main>
        <section className="landing-hero">
          <div className="landing-hero-copy">
            <span className="state-eyebrow">Hosted IoT fleet operations</span>
            <h1>Operate IoT devices from one console.</h1>
            <p>
              Register your own devices, monitor live and historical telemetry,
              see what is online, send supported commands, and act on events and
              alerts from one focused operations console.
            </p>
            <div className="landing-actions">
              <Link className="button button-primary" href={consoleHref}>
                {consoleLabel}
                <ArrowRight aria-hidden="true" size={14} />
              </Link>
              <Link className="button button-secondary" href="/about">
                Learn more
              </Link>
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

        <section aria-labelledby="product-areas-title" className="landing-section">
          <div className="landing-section-heading">
            <span className="state-eyebrow">One operational view</span>
            <h2 id="product-areas-title">Know what is happening and act with confidence</h2>
            <p>
              DeviceOps brings day-to-day monitoring, control, and response into
              a single console—even when devices expose different data and controls.
            </p>
          </div>
          <div className="landing-capability-grid landing-product-grid">
            {productAreas.map(({ icon: Icon, title, description }) => (
              <article className="landing-capability" key={title}>
                <Icon aria-hidden="true" size={16} strokeWidth={1.7} />
                <h3>{title}</h3>
                <p>{description}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="landing-final-cta">
          <div>
            <span className="state-eyebrow">Connect software or hardware</span>
            <h2>Register a device and connect it directly to DeviceOps.</h2>
            <p>
              Create an account to receive a device ID and one-time secret. Start
              quickly with the Python simulator or use the verified ESP32 reference
              firmware; secure broker access is provisioned automatically.
            </p>
          </div>
          <Link className="button button-primary" href={consoleHref}>
            {consoleLabel}<ArrowRight aria-hidden="true" size={14} />
          </Link>
        </section>
      </main>

      <footer className="landing-footer">
        <span>DeviceOps</span>
        <span>Monitor · Control · Respond</span>
      </footer>
    </div>
  );
}
