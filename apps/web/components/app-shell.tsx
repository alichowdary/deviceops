"use client";

import { Activity, Bell, LoaderCircle, LogOut, RadioTower } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { useAuth } from "@/components/auth-provider";
import { AuthScreen } from "@/components/auth-screen";

const navItems = [
  { label: "Fleet", href: "/", icon: RadioTower, enabled: true },
  { label: "Events", href: "/events", icon: Activity, enabled: true },
  { label: "Alerts", href: "#", icon: Bell, enabled: false },
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { initialized, invalidateSession, user } = useAuth();

  if (!initialized) {
    return (
      <div aria-live="polite" className="auth-screen auth-loading">
        <LoaderCircle aria-hidden="true" className="icon-spin" size={17} />
        Verifying session
      </div>
    );
  }

  if (!user) return <AuthScreen />;

  return (
    <div className="app-grid">
      <aside className="sidebar">
        <div className="sidebar-header">
          <span className="product-name">DeviceOps</span>
          <span className="product-context">IoT fleet console</span>
        </div>

        <nav aria-label="Primary" className="sidebar-nav">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active =
              item.enabled &&
              (item.href === "/"
                ? pathname === "/" || pathname.startsWith("/devices/")
                : pathname === item.href || pathname.startsWith(`${item.href}/`));

            if (!item.enabled) {
              return (
                <span
                  aria-disabled="true"
                  className="nav-item nav-item-disabled"
                  key={item.label}
                >
                  <Icon aria-hidden="true" size={15} strokeWidth={1.8} />
                  {item.label}
                  <span className="nav-later">later</span>
                </span>
              );
            }

            return (
              <Link
                aria-current={active ? "page" : undefined}
                className={`nav-item${active ? " nav-item-active" : ""}`}
                href={item.href}
                key={item.label}
              >
                <Icon aria-hidden="true" size={15} strokeWidth={1.8} />
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="sidebar-footer">
          REST + WebSocket
          <br />
          Protocol v1
        </div>
      </aside>

      <div className="content-shell">
        <header className="topbar">
          <div className="session-controls">
            <span className="session-email" title={user.email}>
              {user.email}
            </span>
            <button
              className="session-logout"
              onClick={invalidateSession}
              type="button"
            >
              <LogOut aria-hidden="true" size={13} />
              Logout
            </button>
          </div>
          <span className="environment-label">
            <span className="environment-dot" />
            local development
          </span>
        </header>
        <main className="main-content">{children}</main>
      </div>
    </div>
  );
}
