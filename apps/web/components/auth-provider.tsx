"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { ApiError, apiGet, apiPost } from "@/lib/api";
import type { TokenResponse, User } from "@/lib/types";

const SESSION_TOKEN_KEY = "deviceops.access_token";

interface AuthContextValue {
  initialized: boolean;
  initializationError: string | null;
  token: string | null;
  user: User | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  invalidateSession: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function removeStoredToken() {
  try {
    window.sessionStorage.removeItem(SESSION_TOKEN_KEY);
  } catch {
    // Memory state is still cleared when browser storage is unavailable.
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [initialized, setInitialized] = useState(false);
  const [initializationError, setInitializationError] = useState<string | null>(
    null,
  );
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);

  const invalidateSession = useCallback(() => {
    removeStoredToken();
    setToken(null);
    setUser(null);
    setInitializationError(null);
    setInitialized(true);
  }, []);

  useEffect(() => {
    let active = true;
    const storedToken = window.sessionStorage.getItem(SESSION_TOKEN_KEY);
    if (!storedToken) {
      queueMicrotask(() => {
        if (active) setInitialized(true);
      });
      return () => {
        active = false;
      };
    }

    const controller = new AbortController();
    apiGet<User>("/api/auth/me", {
      signal: controller.signal,
      token: storedToken,
    })
      .then((account) => {
        if (!active) return;
        setToken(storedToken);
        setUser(account);
        setInitializationError(null);
      })
      .catch((error: unknown) => {
        if (!active) return;
        if (error instanceof DOMException && error.name === "AbortError") return;
        if (error instanceof ApiError && error.status === 401) {
          removeStoredToken();
        } else {
          setInitializationError(
            error instanceof Error
              ? error.message
              : "The saved session could not be verified.",
          );
        }
      })
      .finally(() => {
        if (active) setInitialized(true);
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, []);

  const authenticate = useCallback(async (email: string, password: string) => {
    const tokenResponse = await apiPost<TokenResponse>("/api/auth/login", {
      email,
      password,
    });
    window.sessionStorage.setItem(SESSION_TOKEN_KEY, tokenResponse.access_token);

    try {
      const account = await apiGet<User>("/api/auth/me", {
        token: tokenResponse.access_token,
      });
      setToken(tokenResponse.access_token);
      setUser(account);
      setInitializationError(null);
      setInitialized(true);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) removeStoredToken();
      throw error;
    }
  }, []);

  const login = useCallback(
    async (email: string, password: string) => authenticate(email, password),
    [authenticate],
  );

  const register = useCallback(
    async (email: string, password: string) => {
      await apiPost<User>("/api/auth/register", { email, password });
      await authenticate(email, password);
    },
    [authenticate],
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      initialized,
      initializationError,
      token,
      user,
      login,
      register,
      invalidateSession,
    }),
    [
      initialized,
      initializationError,
      token,
      user,
      login,
      register,
      invalidateSession,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
