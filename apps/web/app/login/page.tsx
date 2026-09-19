"use client";

import { LoaderCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { AuthScreen } from "@/components/auth-screen";
import { useAuth } from "@/components/auth-provider";

export default function LoginPage() {
  const router = useRouter();
  const { initialized, user } = useAuth();

  useEffect(() => {
    if (initialized && user) router.replace("/fleet");
  }, [initialized, router, user]);

  if (!initialized || user) {
    return (
      <div aria-live="polite" className="auth-screen auth-loading">
        <LoaderCircle aria-hidden="true" className="icon-spin" size={17} />
        {user ? "Opening console" : "Verifying session"}
      </div>
    );
  }

  return <AuthScreen onAuthenticated={() => router.replace("/fleet")} />;
}
