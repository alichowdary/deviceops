"use client";

import { Activity, Bell, RadioTower } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const navItems = [
  { label: "Fleet", href: "/", icon: RadioTower, enabled: true },
  { label: "Events", href: "#", icon: Activity, enabled: false },
  { label: "Alerts", href: "#", icon: Bell, enabled: false },
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

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
              (pathname === item.href || pathname.startsWith("/devices/"));

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
          REST API · read only
          <br />
          Protocol v1
        </div>
      </aside>

      <div className="content-shell">
        <header className="topbar">
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
