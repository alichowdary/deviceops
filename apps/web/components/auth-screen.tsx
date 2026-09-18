"use client";

import { LoaderCircle } from "lucide-react";
import { useState, type FormEvent } from "react";

import { useAuth } from "@/components/auth-provider";

type AuthMode = "login" | "register";

export function AuthScreen() {
  const { initializationError, login, register } = useAuth();
  const [mode, setMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(initializationError);

  function selectMode(nextMode: AuthMode) {
    setMode(nextMode);
    setPassword("");
    setError(null);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      if (mode === "login") await login(email, password);
      else await register(email, password);
      setPassword("");
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Authentication failed. Please try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-screen">
      <header className="auth-product-bar">
        <span className="product-name">DeviceOps</span>
        <span className="product-context">IoT fleet console</span>
      </header>
      <main className="auth-main">
        <section aria-labelledby="auth-title" className="auth-panel">
          <div className="auth-heading">
            <span className="state-eyebrow">Operator access</span>
            <h1 id="auth-title">{mode === "login" ? "Sign in" : "Create account"}</h1>
            <p>
              Authenticate to inspect devices, telemetry, and command activity.
            </p>
          </div>

          <div aria-label="Authentication mode" className="auth-mode" role="group">
            <button
              aria-pressed={mode === "login"}
              className={mode === "login" ? "auth-mode-active" : undefined}
              disabled={submitting}
              onClick={() => selectMode("login")}
              type="button"
            >
              Login
            </button>
            <button
              aria-pressed={mode === "register"}
              className={mode === "register" ? "auth-mode-active" : undefined}
              disabled={submitting}
              onClick={() => selectMode("register")}
              type="button"
            >
              Register
            </button>
          </div>

          <form className="auth-form" onSubmit={(event) => void submit(event)}>
            <label htmlFor="auth-email">Email</label>
            <input
              autoComplete="email"
              disabled={submitting}
              id="auth-email"
              maxLength={320}
              onChange={(event) => setEmail(event.target.value)}
              required
              type="email"
              value={email}
            />

            <label htmlFor="auth-password">Password</label>
            <input
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              disabled={submitting}
              id="auth-password"
              maxLength={128}
              minLength={8}
              onChange={(event) => setPassword(event.target.value)}
              required
              type="password"
              value={password}
            />

            <div aria-live="polite" className="auth-error">
              {error}
            </div>

            <button className="button button-primary auth-submit" disabled={submitting}>
              {submitting ? (
                <>
                  <LoaderCircle aria-hidden="true" className="icon-spin" size={14} />
                  {mode === "login" ? "Signing in" : "Creating account"}
                </>
              ) : mode === "login" ? (
                "Sign in"
              ) : (
                "Create account"
              )}
            </button>
          </form>
        </section>
      </main>
      <footer className="auth-footer">REST + WebSocket · Protocol v1</footer>
    </div>
  );
}
