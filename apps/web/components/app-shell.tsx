"use client";

import {
  Activity,
  Bell,
  BookOpen,
  LoaderCircle,
  LogOut,
  RadioTower,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, type ReactNode } from "react";

import { useAuth } from "@/components/auth-provider";
const navItems = [
  { label: "Fleet", href: "/fleet", icon: RadioTower },
  { label: "Events", href: "/events", icon: Activity },
  { label: "Alerts", href: "/alerts", icon: Bell },
  { label: "Getting Started", href: "/getting-started", icon: BookOpen },
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { initialized, invalidateSession, user } = useAuth();
  const loggingOut = useRef(false);

  useEffect(() => {
    if (initialized && !user && !loggingOut.current) {
      router.replace("/login");
    }
  }, [initialized, router, user]);

  function logout() {
    loggingOut.current = true;
    invalidateSession();
    router.replace("/");
  }

  if (!initialized) {
    return (
      <div aria-live="polite" className="auth-screen auth-loading">
        <LoaderCircle aria-hidden="true" className="icon-spin" size={17} />
        Verifying session
      </div>
    );
  }

  if (!user) {
    return (
      <div aria-live="polite" className="auth-screen auth-loading">
        <LoaderCircle aria-hidden="true" className="icon-spin" size={17} />
        Redirecting to sign in
      </div>
    );
  }

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
              item.href === "/fleet"
                ? pathname === "/fleet" || pathname.startsWith("/devices/")
                : pathname === item.href || pathname.startsWith(`${item.href}/`);

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
              onClick={logout}
              type="button"
            >
              <LogOut aria-hidden="true" size={13} />
              Logout
            </button>
          </div>
          <span className="environment-label">DeviceOps console</span>
        </header>
        <main className="main-content">{children}</main>
      </div>
    </div>
  );
}
