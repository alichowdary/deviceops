import { LoaderCircle } from "lucide-react";
import type { ReactNode } from "react";

export function StatePanel({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <section className="state-panel">
      <span className="state-eyebrow">{eyebrow}</span>
      <h1 className="state-title">{title}</h1>
      <p className="state-description">{description}</p>
      {action}
    </section>
  );
}

export function LoadingState({ label }: { label: string }) {
  return (
    <section aria-live="polite" className="state-panel">
      <div className="loading-row">
        <LoaderCircle aria-hidden="true" className="icon-spin" size={16} />
        {label}
      </div>
    </section>
  );
}
