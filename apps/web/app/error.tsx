"use client";

import { useEffect } from "react";

import { StatePanel } from "@/components/state-panel";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <StatePanel
      eyebrow="Application error"
      title="This view could not be rendered"
      description="Retry the request. If the problem continues, inspect the frontend terminal output."
      action={
        <button className="button button-primary" onClick={reset} type="button">
          Try again
        </button>
      }
    />
  );
}
